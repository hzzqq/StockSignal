"""modules/event_backtest.py — 事件因子回测实验室（离线 · walk-forward · 无未来函数）

为什么有这一层
============
``modules/sentiment_edge.py`` 已用 walk-forward 证明**唯一**有统计依据的市场信号是
「极端恐慌（跌停占比前 10%）→ 次日红盘概率显著高于基准」。本模块把这套方法论**泛化**
成一个可配置的事件因子实验室：用户选一个**市场广度类事件**（或自定义阈值），看它在
前向 N 日里对「市场红盘日占比」的统计边缘。

设计原则（与 sentiment_edge / 全站诚实红线一致）
=============================================
1. **尺度无关**：事件只定义在占比类指标（red_ratio / limit_up_ratio / limit_down_ratio），
   跨年代采样规模变化可比；
2. **无未来函数**：第 i 天的触发阈值只用 [0, i) 窗口的 expanding 分位计算，绝不用当日或
   之后的数据；
3. **广度层面结果**：前向结果定义为「红盘日占比」（up_count > down_count 的天数占比），
   **不是指数收益率** —— 这是诚实的能力边界，页脚原样带出，不伪装成收益；
4. **优雅降级**：指标 NaN 跳过、窗口不足不评估、触发样本 < MIN_N 不报 z 值（显式弃权），
   数据缺失返回 available=False 带 reason，绝不抛异常、绝不补零；
5. **纯函数 + 缓存**：结果按 (metric, tail, direction, horizon, 数据 mtime) 内存缓存。

统计方法
========
- 触发集：每个触发日贡献其后 horizon 个交易日的「红/绿」二元观测；
- 基准集：所有「可评估但非触发」日贡献同等结构的二元观测（无条件基准率）；
- 边缘：edge_pp = (p_event - p_base) × 100；
- 显著性：两比例 z 检验（pooled），n_event < MIN_N 或 n_base < MIN_N 时 z = None。
"""
from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path

try:
    import numpy as np
except Exception:  # numpy 缺失（极端环境）时降级为纯 Python 分位/均值
    np = None

logger = logging.getLogger(__name__) if (logging := __import__("logging")) else None

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_DATA = _ROOT / "data"
_FILE = _DATA / "shepherd_history.json"

# 事件可定义的指标白名单（均为尺度无关的占比类）
METRIC_KEYS = ("red_ratio", "limit_up_ratio", "limit_down_ratio")
# 允许的 horizon（交易日）
HORIZONS = (1, 3, 5, 10)
# 触发集最小观测数：低于此不报 z 值（显著性不可靠）
MIN_N = 30
# expanding 窗口最小长度：太短分位不稳，约 1 个交易年内不评估
MIN_WINDOW = 250
# 分布直方图分箱数
N_BINS = 10

# 预设事件（与前端 PRESETS 对应；此处为单一真理源文档，前端硬编码同义结构）
PRESETS = {
    "panic": dict(name="极端恐慌", metric="limit_down_ratio", tail=0.10, direction="high",
                  why="跌停占比达历史前 10%：恐慌出清，次日红盘概率抬升（sentiment_edge 已验证）"),
    "euphoria": dict(name="极端亢奋", metric="limit_up_ratio", tail=0.10, direction="high",
                     why="涨停占比达历史前 10%：情绪过热，后续广度易回落"),
    "breadth_ice": dict(name="广度冰点", metric="red_ratio", tail=0.10, direction="low",
                        why="红盘率落历史后 10%：广度冰点，关注否极泰来"),
}

_cache: dict = {}
_cache_lock = threading.Lock()


def _num(v):
    """安全取数值：None / 非数 / NaN → None（不用 0 冒充）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _metric_of(rec: dict, metric: str):
    """从一条日记录算出指标值（占比 %），缺字段/NaN → None。"""
    if metric == "red_ratio":
        return _num(rec.get("red_ratio"))
    up = _num(rec.get("up_count"))
    down = _num(rec.get("down_count"))
    flat = _num(rec.get("flat_count"))
    if up is None or down is None:
        return None
    total = up + down + (flat or 0)
    if total <= 0:
        return None
    if metric == "limit_up_ratio":
        lu = _num(rec.get("limit_up"))
        return (lu / total * 100) if lu is not None else None
    if metric == "limit_down_ratio":
        ld = _num(rec.get("limit_down"))
        return (ld / total * 100) if ld is not None else None
    return None


def _percentile(values, q):
    """q ∈ [0,100]，返回分位值；纯 Python 降级实现（np 缺失时）。"""
    if not values:
        return None
    if np is not None:
        return float(np.percentile(values, q))
    s = sorted(values)
    k = (len(s) - 1) * (q / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _load_series():
    """加载并规整 shepherd_history.json → 按日期升序的 (dates, recs) 列表。"""
    if not _FILE.is_file():
        return None, "数据文件缺失：data/shepherd_history.json"
    try:
        with _FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # 文件损坏不得让页面崩
        return None, f"数据文件解析失败：{exc}"
    if not isinstance(data, list) or not data:
        return None, "数据文件结构异常（非空数组）"
    recs = [r for r in data if isinstance(r, dict) and r.get("date")]
    recs.sort(key=lambda r: str(r.get("date")))
    if not recs:
        return None, "数据文件无有效记录"
    return recs, None


def run(metric: str, tail: float, direction: str, horizon: int) -> dict:
    """执行一次事件因子回测。

    Args:
        metric: 见 METRIC_KEYS
        tail: 尾部比例 (0,1)，如 0.10 表示前/后 10%
        direction: 'high'（指标达历史高位触发）/ 'low'（低位触发）
        horizon: 见 HORIZONS

    Returns:
        dict: 见模块文档「统计方法」；含 available / n_event / base_rate / event_rate /
              edge_pp / z(null if 不足) / distribution / example_dates / method / honesty_notes
    """
    if metric not in METRIC_KEYS:
        return dict(available=False, reason=f"metric 不在白名单：{metric}")
    if not (0 < tail < 1):
        return dict(available=False, reason=f"tail 必须 ∈ (0,1)：{tail}")
    if direction not in ("high", "low"):
        return dict(available=False, reason=f"direction 必须是 high/low：{direction}")
    if horizon not in HORIZONS:
        return dict(available=False, reason=f"horizon 必须是 {HORIZONS}：{horizon}")

    recs, err = _load_series()
    if err:
        return dict(available=False, reason=err)

    # 缓存键含数据 mtime，保证数据更新后失效
    mtime = _FILE.stat().st_mtime
    key = (metric, round(tail, 6), direction, horizon, mtime)
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    n = len(recs)
    # 预计算每日指标值
    mvals = [_metric_of(r, metric) for r in recs]
    # 预计算每日是否红盘（up > down），用于前向结果
    red_day = []
    for r in recs:
        up = _num(r.get("up_count"))
        down = _num(r.get("down_count"))
        red_day.append((up is not None and down is not None and up > down))

    hist: list = []          # expanding 窗口指标值（用于分位）
    event_obs: list = []     # 触发日的前向二元观测（1=红盘）
    base_obs: list = []      # 非触发可评估日的前向二元观测
    event_fracs: list = []   # 触发日的前向红盘日占比（用于分布直方图）
    base_fracs: list = []    # 基准日的前向红盘日占比
    example: list = []       # 触发示例日期

    for i in range(n):
        mv = mvals[i]
        if mv is None:
            continue  # 当日指标缺失：无法评估，也不计入窗口
        # 仅用 [0, i) 构造阈值（无未来函数）
        thr = None
        if len(hist) >= MIN_WINDOW:
            q = (1 - tail) * 100 if direction == "high" else tail * 100
            thr = _percentile(hist, q)
        # 前向窗口 [i+1, i+horizon]
        fwd = [j for j in range(i + 1, min(i + 1 + horizon, n))]
        if not fwd:
            hist.append(mv)
            continue
        fwd_red = [1 if red_day[j] else 0 for j in fwd]
        frac = sum(fwd_red) / len(fwd_red)
        triggered = thr is not None and (
            (direction == "high" and mv > thr) or (direction == "low" and mv < thr)
        )
        if triggered:
            event_obs.extend(fwd_red)
            event_fracs.append(frac)
            if len(example) < 10:
                example.append(dict(date=str(recs[i].get("date")),
                                    metric_value=round(mv, 4),
                                    forward_red_day_frac=round(frac, 4)))
        else:
            # 仅当窗口足够（该日「可评估」）才计入基准，避免早期不稳定污染基准率
            if thr is not None:
                base_obs.extend(fwd_red)
                base_fracs.append(frac)
        hist.append(mv)

    n_event = len(event_obs)
    n_base = len(base_obs)
    p_event = (sum(event_obs) / n_event) if n_event else None
    p_base = (sum(base_obs) / n_base) if n_base else None
    edge_pp = ((p_event - p_base) * 100) if (p_event is not None and p_base is not None) else None

    z = None
    if n_event >= MIN_N and n_base >= MIN_N and p_event is not None and p_base is not None:
        p_pool = (sum(event_obs) + sum(base_obs)) / (n_event + n_base)
        se = math.sqrt(p_pool * (1 - p_pool) * (1.0 / n_event + 1.0 / n_base))
        if se > 0:
            z = (p_event - p_base) / se

    distribution = _histogram(event_fracs, base_fracs)

    notes = [
        "方法：walk-forward（第 i 天阈值只用 [0,i) 历史分位，无未来函数）。",
        "结果度量：前向 N 日「红盘日占比」（up_count>down_count），非指数收益率。",
        "指标均为尺度无关的占比类（跨年代采样规模可比）。",
    ]
    if n_event < MIN_N:
        notes.append(f"触发观测 {n_event} < {MIN_N}，显著性（z）未计算，仅作描述性参考。")
    if n_base == 0:
        notes.append("无足够基准观测（早期窗口未成熟或无非触发日），基准率不可用。")

    result = dict(
        available=True,
        metric=metric,
        tail=tail,
        direction=direction,
        horizon=horizon,
        n_event=n_event,
        n_base=n_base,
        base_rate=(round(p_base, 4) if p_base is not None else None),
        event_rate=(round(p_event, 4) if p_event is not None else None),
        edge_pp=(round(edge_pp, 2) if edge_pp is not None else None),
        z=(round(z, 3) if z is not None else None),
        distribution=distribution,
        example_dates=example,
        method="two-proportion z-test（pooled）on forward red-day binary observations",
        honesty_notes=notes,
    )
    with _cache_lock:
        _cache[key] = result
    return result


def _histogram(event_fracs: list, base_fracs: list) -> list:
    """把事件/基准的前向红盘日占比分别分箱（10 箱，[0,1]）。"""
    edges = [i / N_BINS for i in range(N_BINS + 1)]
    ev = [0] * N_BINS
    bs = [0] * N_BINS

    def _bin(v):
        if v is None:
            return None
        idx = int(v * N_BINS)
        if idx >= N_BINS:
            idx = N_BINS - 1
        if idx < 0:
            idx = 0
        return idx

    for v in event_fracs:
        b = _bin(v)
        if b is not None:
            ev[b] += 1
    for v in base_fracs:
        b = _bin(v)
        if b is not None:
            bs[b] += 1
    out = []
    for i in range(N_BINS):
        out.append(dict(
            bucket=f"{edges[i]:.1f}–{edges[i+1]:.1f}",
            event_count=ev[i],
            base_count=bs[i],
        ))
    return out
