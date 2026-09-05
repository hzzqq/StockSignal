"""
modules/shepherd_ladder.py — 连板梯队晋级率（每日落盘 + 跨日晋级率递推）

牧羊人体系里「梯队厚度」只用家数（连板≥2板多少家），而**晋级率**比家数更精细：
  首板→二板晋级率 = 昨日首板今日有几成封住二板，是接力意愿最纯粹的度量。

本模块把每日各档连板家数落盘 data/shepherd_ladder_history.json，
再跨日递推各档晋级率，并把最新综合晋级率打包成 forecast 的派生指标
（ladder_promo），让「次日走势预判」能用上这一更细的接力信号。

设计原则：
  ✅ 纯函数与 IO 分离：ladder_promotion_rates / current_promo_as_indicators 吃文件出结果，可离线单测
  ✅ 文件损坏/缺失优雅降级，绝不抛异常到页面
  ✅ 历史不足 2 日时 ready=False，不误报晋级率
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta

from modules.atomic_io import atomic_json_dump
from modules.time_utils import now_cst, now_cst_str, now_cst_naive

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# SS_DATA_DIR 可重定向整个数据目录（测试隔离用；生产默认 data/）。
# conftest 在 pytest 启动时把它指到临时目录，避免测试写穿真实 data/。
LADDER_DIR = os.environ.get("SS_DATA_DIR", os.path.join(_ROOT, "data"))
LADDER_FILE = os.path.join(LADDER_DIR, "shepherd_ladder_history.json")
_lock = threading.Lock()

# 晋级率进入「决策」所需的最小样本天数。
#
# 背景（2026-09-05 锐评发现）：ladder_promotion_rates() 只用「最近 2 天」快照算比率，
# 即 **1 个交易日对**；而 ready=True 仅代表"算得出来"，不代表"可信"。
# 实测曾出现 6 天样本、单日比率 8.6% 以 ready=True 身份经 current_promo_as_indicators()
# 注入 forecast 的 ladder_promo（weight=8）并驱动仓位建议——统计上属小样本过拟合。
#
# 对齐 modules/calibration.py 铁律 T3（n_call<8 不出观察行、<20 不 actionable），
# 取 10 作为「可驱动决策」门槛。未达标时 ladder_promotion_rates() **仍返回数值**供页面
# 展示（附 confidence="low"），只是不再进 forecast / 仓位推导。
MIN_PROMO_DAYS = 10


def _ensure_dir():
    try:
        os.makedirs(LADDER_DIR, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_ladder] 建目录失败: {e}")


def _ds(v) -> str:
    """统一成 'YYYY-MM-DD'。"""
    try:
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        return str(v)[:10]
    except Exception:
        return str(v)[:10]


def trading_date(now=None) -> str:
    """推测「当前实时梯队该归属哪个交易日」：周六/周日回退到上周五。

    ⚠️ 为什么不能直接用 now()：
        get_zt_ladder() 抓的是**实时**梯队。周末跑脚本时它返回的是上周五收盘的数据，
        若按 now() 落盘就会记成周六/周日 → 跨日晋级率递推把非交易日当「昨日」，直接算错。

    ⚠️ 局限：只处理周末，**不处理法定节假日**（那需要交易日历）。
       节假日跑脚本仍会记一条，由 audit_history() 事后检出。
    """
    d = now or now_cst()
    if d.weekday() >= 5:  # 5=周六 6=周日
        d = d - timedelta(days=d.weekday() - 4)
    return d.strftime("%Y-%m-%d")


def _dist_to_map(distribution) -> dict:
    """distribution: [(boards, count), ...] -> {boards: count}。"""
    out = {}
    try:
        for b, c in distribution or []:
            try:
                out[int(b)] = int(c)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _int_keys(d) -> dict:
    """把 distribution 的档位 key 统一还原成 int。

    ⚠️ 坑：json.dump 会把 dict 的 int key 强制写成字符串（{"2": 25}），
    读回来 d.keys() 是 str，直接 `n - 1` / `max(keys)` 会炸或算错。
    所以每次从文件读都要过一遍这里，保证消费方拿到的永远是 int key。
    """
    out = {}
    try:
        for k, v in (d or {}).items():
            try:
                out[int(k)] = int(v)
            except Exception:
                continue
    except Exception:
        return {}
    return out


def load_history() -> dict:
    """{date: {date, distribution, max_boards, total_connect, updated_at}}。缺失/损坏返回 {}。

    返回的每条 distribution 已归一化成 {int 档位: int 家数}。
    """
    try:
        if not os.path.exists(LADDER_FILE):
            return {}
        with open(LADDER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        for _d, entry in data.items():
            if isinstance(entry, dict) and "distribution" in entry:
                entry["distribution"] = _int_keys(entry["distribution"])
        return data
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_ladder] 读取历史失败: {e}")
        return {}


def _save_history(hist: dict) -> bool:
    try:
        _ensure_dir()
        atomic_json_dump(hist, LADDER_FILE)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_ladder] 保存历史失败: {e}")
        return False


def record_ladder_snapshot(date, distribution, max_boards=None, total_connect=None) -> bool:
    """落盘某日连板梯队快照（按日期覆盖更新）。

    无有效分布时不记录（避免污染历史）。
    """
    d = _ds(date)
    if not d:
        return False
    dist = _dist_to_map(distribution)
    if not dist:
        return False
    with _lock:
        hist = load_history()
        hist[d] = {
            "date": d,
            "distribution": dist,
            "max_boards": int(max_boards) if max_boards is not None else max(dist.keys()),
            "total_connect": int(total_connect) if total_connect is not None
            else sum(v for k, v in dist.items() if k >= 2),
            "updated_at": now_cst_naive().isoformat(timespec="seconds"),
        }
        return _save_history(hist)


def _promo_confidence(days: int) -> str:
    """样本天数 → 可信度档位（仅用于展示，不驱动决策）。"""
    if days >= 20:
        return "high"
    if days >= MIN_PROMO_DAYS:
        return "medium"
    if days >= 2:
        return "low"
    return "none"


def _promo_actionable(days: int, overall) -> bool:
    """晋级率是否可信到能驱动决策（对齐 calibration 铁律 T3：小样本不表态）。

    注意：晋级率只用最近 2 天算，days 是「已积累的快照天数」而非比率样本数；
    用 days 兜底是因为单日比率噪声极大，必须靠积累天数证明序列稳定。
    """
    return days >= MIN_PROMO_DAYS and overall is not None


def ladder_promotion_rates(as_of: str | None = None) -> dict:
    """算各档晋级率（跨日递推）。

    晋级率定义：某档 n（≥2板）的晋级率 = 当日 n板家数 / 昨日 (n-1)板家数。
      · 2板晋级率 = 当日2板家数 / 昨日首板家数（最能代表接力意愿）
      · 3板晋级率 = 当日3板 / 昨日2板，以此类推
    仅当存在「今日」与「昨日」两条快照时才有意义。

    :param as_of: 可选时点截止日（YYYY-MM-DD）。传入后只用 ≤ as_of 的历史快照递推
                  （历史回填的时点诚实口径：不偷看未来数据）；None = 最新（现行为）。

    返回：
      ready       bool（有任一档晋级率可算才有意义）
      days        int（历史天数）
      latest      dict（最新快照）
      latest_date str
      rates       {tier_label: rate_or_None}，tier_label 形如 "2b"(首板→二板) / "3b" / …
      overall     float|None（综合晋级率：优先取首板→二板，缺失则取可用档均值）
    """
    empty = dict(ready=False, days=0, latest=None, latest_date=None, rates={}, overall=None,
                 actionable=False, confidence="none")
    hist = load_history()
    if not hist:
        return empty
    # 跳过被标记为不可信的条目（audit_history 检出 + mark_suspect 标记，软处理可撤销）
    dates = sorted(d for d, e in hist.items()
                   if not (isinstance(e, dict) and e.get("suspect")))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    if not dates:
        return empty
    if len(dates) < 2:
        return dict(ready=False, days=len(dates), latest=hist[dates[-1]],
                    latest_date=dates[-1], rates={}, overall=None,
                    actionable=False, confidence=_promo_confidence(len(dates)))
    latest = hist[dates[-1]]
    yest = hist[dates[-2]]
    d_cur = _int_keys(latest.get("distribution"))
    d_prev = _int_keys(yest.get("distribution"))
    max_tier = int(max(d_cur.keys())) if d_cur else 0
    rates = {}
    for n in range(2, max_tier + 1):
        prev_cnt = d_prev.get(n - 1)
        cur_cnt = d_cur.get(n)
        if prev_cnt is None or prev_cnt <= 0:
            rates[f"{n}b"] = None
        else:
            rates[f"{n}b"] = round(cur_cnt / prev_cnt * 100, 1) if cur_cnt is not None else None
    overall = rates.get("2b")
    if overall is None:
        avail = [v for v in rates.values() if v is not None]
        overall = round(sum(avail) / len(avail), 1) if avail else None
    return dict(ready=any(v is not None for v in rates.values()),
                days=len(dates), latest=latest, latest_date=dates[-1],
                rates=rates, overall=overall,
                actionable=_promo_actionable(len(dates), overall),
                confidence=_promo_confidence(len(dates)))


def current_promo_as_indicators() -> dict:
    """把最新综合晋级率打包成 forecast 派生指标 {ladder_promo: rate}。

    样本不足 MIN_PROMO_DAYS 天时返回 {}：晋级率只用最近 2 天算，样本太少时
    单日噪声会被当成趋势喂进 forecast（ladder_promo weight=8）并驱动仓位，
    属小样本过拟合。未达标时 ladder_promotion_rates() 仍返回数值供页面展示
    （confidence="low"），只是不进决策链路。
    """
    pr = ladder_promotion_rates()
    if not pr.get("actionable") or pr.get("overall") is None:
        return {}
    return {"ladder_promo": pr["overall"]}


def prev_overall(as_of: str | None = None) -> float | None:
    """倒数第二天的综合晋级率（用于首页/决策面板的环比 delta）。

    口径与 ladder_promotion_rates() 一致：取「最新-1 日 vs 最新-2 日」的 2板晋级率。
    :param as_of: 可选时点截止日——传入后只用 ≤ as_of 的历史（回填时点诚实口径）。
    历史不足 3 日返回 None（无法算环比）。
    """
    hist = load_history()
    dates = sorted(d for d, e in hist.items() if not (isinstance(e, dict) and e.get("suspect")))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    if len(dates) < 3:
        return None
    d_cur = _int_keys(hist[dates[-2]].get("distribution"))
    d_prev = _int_keys(hist[dates[-3]].get("distribution"))
    prev_cnt = d_prev.get(1)
    cur_cnt = d_cur.get(2)
    if not prev_cnt or prev_cnt <= 0:
        return None
    return round(cur_cnt / prev_cnt * 100, 1) if cur_cnt is not None else None


# ────────────────── 历史数据体检：脏数据检测 + 软标记 ──────────────────
def audit_history() -> dict:
    """体检梯队历史，检出「不可信」条目。**只读，不改动任何数据。**

    两条判据：

    · **补记滞后（主判据，可靠）**：`updated_at` 的日期 ≠ 该条的 `date`。
      说明这条不是当天写的 —— 而 distribution 来自**实时抓取**，于是「那一天」名下
      记的其实是「补记那一刻」的梯队，日期张冠李戴。
      典型场景：8-30 打开情绪页，牧羊人数据还停在 8-27，页面就把 8-30 抓到的实时
      梯队记到了 8-27 名下（根因已在页面侧改用 trading_date() 修正）。

    · **重复分布（辅助，仅提示）**：与相邻日期的分布逐档完全相同。
      真实市场两天梯队完全一致的概率极低，通常意味着其中一条是陈旧/复制值。

    :return: {date: {date, severity, reason, detail, updated_at, distribution}}
             severity: "bad"（补记滞后，强烈建议排除）/ "warn"（仅提示）
    """
    hist = load_history()
    if not hist:
        return {}
    dates = sorted(hist.keys())
    out: dict = {}

    # 主判据：补记滞后
    for d in dates:
        entry = hist[d]
        if not isinstance(entry, dict):
            continue
        upd = str(entry.get("updated_at") or "")[:10]
        if upd and upd != d:
            out[d] = {
                "date": d, "severity": "bad", "reason": "补记滞后",
                "detail": (f"updated_at={entry.get('updated_at')} 与 date={d} 不符；"
                           f"分布来自实时抓取，实为补记当日的梯队"),
                "updated_at": entry.get("updated_at"),
                "distribution": entry.get("distribution"),
                "marked": bool(entry.get("suspect")),
            }

    # 辅助判据：与相邻日期分布完全相同
    for i, d in enumerate(dates):
        entry = hist[d]
        if not isinstance(entry, dict) or d in out:
            continue
        cur = _int_keys(entry.get("distribution") or {})
        if not cur:
            continue
        neighbours = [dates[i - 1] if i > 0 else None,
                      dates[i + 1] if i + 1 < len(dates) else None]
        for nb in neighbours:
            if not nb:
                continue
            other = hist.get(nb)
            if not isinstance(other, dict):
                continue
            if _int_keys(other.get("distribution") or {}) == cur:
                out[d] = {
                    "date": d, "severity": "warn", "reason": "分布与相邻日完全相同",
                    "detail": f"与 {nb} 的分布逐档一致 {cur}，疑似陈旧/复制值",
                    "updated_at": entry.get("updated_at"),
                    "distribution": cur,
                    "marked": bool(entry.get("suspect")),
                }
                break
    return out


def mark_suspect(dates, reason="人工标记") -> int:
    """给指定日期打 suspect 标记 —— **软处理，数据不删，随时可 unmark 撤销**。

    被标记的条目会被 ladder_promotion_rates() 跳过，不再污染晋级率。

    :param dates: 单个日期字符串或日期列表
    :return: 实际标记成功的条数
    """
    if isinstance(dates, str):
        dates = [dates]
    n = 0
    with _lock:
        hist = load_history()
        for d in dates:
            d = _ds(d)
            e = hist.get(d)
            if not isinstance(e, dict):
                continue
            e["suspect"] = True
            e["suspect_reason"] = reason
            e["suspect_at"] = now_cst_naive().isoformat(timespec="seconds")
            n += 1
        if n:
            _save_history(hist)
    return n


def unmark_suspect(dates) -> int:
    """撤销 suspect 标记，恢复参与晋级率计算（数据从未被删除，可完整恢复）。"""
    if isinstance(dates, str):
        dates = [dates]
    n = 0
    with _lock:
        hist = load_history()
        for d in dates:
            d = _ds(d)
            e = hist.get(d)
            if not isinstance(e, dict):
                continue
            for k in ("suspect", "suspect_reason", "suspect_at"):
                e.pop(k, None)
            n += 1
        if n:
            _save_history(hist)
    return n
