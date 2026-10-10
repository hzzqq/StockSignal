"""lib/edge_engine.py — 牧羊人情绪极值信号的「自带兜底引擎」（纯标准库，无第三方依赖）。

为什么存在：避免对 StockSignal 仓库的硬依赖，使本 skill 在发布到 WorkBuddy 市场后、
即便使用者没有 StockSignal 也能独立运行。逻辑与 modules/sentiment_edge.py 保持一致，
校准件优先从 StockSignal 仓库的 data/、reports/ 读取（单一真理源），
仅当两者都不存在时才回退到本 skill 自带的 assets/sentiment_edge_calibration.json（冻结快照）。

⚠️ 诚实红线：本引擎只实现"极端恐慌 → 次日反弹"这一条有 walk-forward 统计依据的规律；
其余日子一律 abstain，绝不硬猜方向。
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
# <skill>/assets/sentiment_edge_calibration.json —— 冻结兜底校准件
_BUNDLED_CAL = os.path.normpath(os.path.join(_HERE, "..", "assets", "sentiment_edge_calibration.json"))

# 校准件解析顺序：环境变量 > StockSignal 仓库(data/ 与 reports/) > 自带冻结件
# STOCKSIGNAL_ROOT 指向 StockSignal 仓库根目录（默认留空则只用自带件）。
_ENV = "SS_SENTIMENT_EDGE_PATH"
_ROOT_ENV = "STOCKSIGNAL_ROOT"


def _candidate_paths():
    paths = []
    env = os.environ.get(_ENV)
    if env:
        paths.append(env)
    root = os.environ.get(_ROOT_ENV)
    if root:
        paths.append(os.path.join(root, "data", "sentiment_edge_calibration.json"))
        paths.append(os.path.join(root, "reports", "sentiment_edge_calibration.json"))
    paths.append(_BUNDLED_CAL)
    return paths


def calibration_path() -> str:
    """返回实际生效的校准件路径：环境变量 > 首个存在的候选 > 冻结件。"""
    for p in _candidate_paths():
        if os.path.exists(p):
            return p
    return _BUNDLED_CAL


_cache: dict = {"path": None, "mtime": None, "data": None}


def load_calibration() -> dict:
    """加载校准件（按 mtime 缓存）。缺失或损坏时返回 {'available': False, ...}。"""
    path = calibration_path()
    if not os.path.exists(path):
        return {"available": False,
                "reason": f"校准件不存在：{path}；请先运行 scripts/calibrate_sentiment_edge.py 或设置 STOCKSIGNAL_ROOT"}
    try:
        mtime = os.path.getmtime(path)
        if _cache["data"] is not None and _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["data"]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "features" not in data:
            return {"available": False, "reason": "校准件结构异常（缺 features 字段）"}
        data["available"] = True
        _cache.update(path=path, mtime=mtime, data=data)
        return data
    except Exception as exc:  # 校准件损坏不得让调用方崩掉
        return {"available": False, "reason": f"校准件读取失败：{exc}"}


def _num(d: dict, key: str):
    """安全取数值：非数值/缺失返回 None（不用 0 冒充，避免把缺失当极值）。"""
    if not d:
        return None
    v = d.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def day_sample(today: dict):
    """当日有效样本数 = 上涨 + 下跌 + 平盘家数（分母，用于把家数换算成占比）。"""
    parts = [_num(today, k) for k in ("up_count", "down_count", "flat_count")]
    got = [p for p in parts if p is not None]
    if not got:
        return None
    s = sum(got)
    return s if s > 0 else None


def ratios(today: dict, sample=None) -> dict:
    """把家数类指标换算为**尺度无关**的占比（%）。分母缺失则对应项为 None。"""
    s = sample if sample is not None else day_sample(today)
    out: dict = {}
    if not s:
        return out
    for key, col in (("limit_down_ratio", "limit_down"),
                     ("touch_down_ratio", "touch_down"),
                     ("limit_up_ratio", "limit_up"),
                     ("hb_wave_ratio", "hb_wave10")):
        v = _num(today, col)
        if v is not None:
            out[key] = round(v / s * 100, 4)
    return out


def panic_reversal(today: dict, sample=None) -> dict:
    """极端恐慌反弹信号：恐慌出清（跌停/触及跌停占比达历史前 10%）→ 次日上涨概率显著抬升。

    Returns:
        dict: available / evaluated / triggered / hits / prob / base_rate / edge_pp /
              strength_hint / statement / abstain
    """
    cal = load_calibration()
    if not cal.get("available"):
        return dict(available=False, triggered=False, evaluated=False, hits=[], prob=None,
                    base_rate=None, edge_pp=None, strength_hint=None, abstain=True,
                    statement="情绪极值信号校准件不可用，本次不做方向表态。",
                    reason=cal.get("reason", ""))

    base = cal.get("base_next_day_up_rate")
    r = ratios(today, sample)
    hits = []
    evaluable = []
    for key, cfg in (cal.get("features") or {}).items():
        if not cfg.get("publishable"):
            continue
        v = r.get(key)
        thr = cfg.get("production_threshold")
        if v is None or thr is None:
            continue
        evaluable.append(key)
        if v >= float(thr):
            wf = cfg.get("walk_forward") or {}
            hits.append(dict(key=key, name=cfg.get("name", key), value=v,
                             threshold=float(thr), prob=wf.get("up_rate"),
                             n=wf.get("trigger_days"), z=wf.get("z"),
                             why=cfg.get("why", "")))

    strength = None
    sic = (cal.get("strength_ic") or {}).get("touch_down_ratio")
    td = r.get("touch_down_ratio")
    if sic is not None and td is not None and td > 0:
        strength = dict(ic=sic, value=td,
                        hint="次日波动可能偏大（弱信号 IC≈%.2f，仅风险提示）" % sic)

    if not hits:
        if not evaluable:
            return dict(available=True, triggered=False, evaluated=False,
                        hits=[], prob=None, base_rate=base, edge_pp=None,
                        strength_hint=strength, abstain=True,
                        statement=("当日关键情绪指标缺失（跌停 / 触及跌停家数，或涨跌家数不全），"
                                   "**本次无法判定**是否处于历史极值区间，故不做任何方向表态。"),
                        ratios=r)
        return dict(available=True, triggered=False, evaluated=True, hits=[], prob=None,
                    base_rate=base, edge_pp=None, strength_hint=strength, abstain=True,
                    statement=("当日情绪未进入历史极值区间：**次日方向无统计边际，本模块不表态**"
                               "（现有情绪评分与次日收益 IC≈0，经全历史检验无法超越基准率）。"),
                    ratios=r)

    prob = sum(h["prob"] for h in hits) / len(hits)
    edge = round((prob - base) * 100, 1) if (prob is not None and base is not None) else None
    names = "、".join(h["name"] for h in hits)
    return dict(
        available=True, triggered=True, evaluated=True, hits=hits, prob=round(prob, 4),
        base_rate=base, edge_pp=edge, strength_hint=strength, abstain=False,
        statement=(f"⚠️ **恐慌出清反弹信号触发**（{names} 达历史前 10% 分位）："
                   f"历史上该形态次日上涨概率 {prob:.1%}，基准 {base:.1%}，"
                   f"边际 +{edge}pp（样本 {hits[0]['n']} 天，z={hits[0]['z']}）。"
                   f"注意：这是**统计概率**，不是确定性预测。"),
        ratios=r,
    )


def calibration_summary() -> dict:
    """校准件摘要（供展示证据链）。"""
    cal = load_calibration()
    if not cal.get("available"):
        return dict(available=False, reason=cal.get("reason", ""))
    return dict(
        available=True,
        generated_at=cal.get("generated_at"),
        method=cal.get("method"),
        base_next_day_up_rate=cal.get("base_next_day_up_rate"),
        date_range=cal.get("date_range"),
        universe_note=cal.get("universe_note"),
        strength_ic=cal.get("strength_ic"),
        strength_note=cal.get("strength_note"),
        features={k: dict(name=v.get("name"), threshold=v.get("production_threshold"),
                          walk_forward=v.get("walk_forward"), by_year=v.get("by_year"),
                          why=v.get("why"), publishable=v.get("publishable"))
                  for k, v in (cal.get("features") or {}).items()},
    )
