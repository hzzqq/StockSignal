"""lib/ladder_engine.py — 连板龙头共振的自带引擎（纯标准库，可独立运行）。

逻辑对齐 modules/shepherd_ladder.py：读取每日连板梯队分布，跨日递推各档晋级率。
唯一可发布口径：首板→二板晋级率是接力意愿最纯粹的度量；样本不足时置信度="low"，
不驱动决策。

数据边界：
  · 只读取 StockSignal 仓库的 data/shepherd_ladder_history.json（通过 STOCKSIGNAL_ROOT）
    或 SS_LADDER_FILE 环境变量指向的文件；
  · 不写任何文件、不网络外呼、不读密钥；
  · 数据缺失/损坏时返回 available=False，诚实说明原因，不编造晋级率。
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

_ENV_LADDER = "SS_LADDER_FILE"
_ENV_ROOT = "STOCKSIGNAL_ROOT"
_DEFAULT_ROOT = "E:/project/ks/StockSignal"

# 与 StockSignal 侧对齐：样本不足 MIN_PROMO_DAYS 时只展示、不 action
MIN_PROMO_DAYS = 10


def _candidate_paths() -> list[str]:
    paths = []
    env = os.environ.get(_ENV_LADDER)
    if env:
        paths.append(env)
    root = os.environ.get(_ENV_ROOT, _DEFAULT_ROOT)
    if root:
        paths.append(os.path.join(root, "data", "shepherd_ladder_history.json"))
    return paths


def _find_history() -> str | None:
    for p in _candidate_paths():
        if p and os.path.exists(p):
            return p
    return None


def _int_keys(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        try:
            out[int(k)] = int(v)
        except Exception:
            pass
    return out


def _load_history(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"读取梯队历史失败：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("梯队历史格式错误：期望 dict")
    for d, entry in data.items():
        if isinstance(entry, dict) and "distribution" in entry:
            entry["distribution"] = _int_keys(entry["distribution"])
    return data


def _promo_confidence(days: int) -> str:
    if days >= 20:
        return "high"
    if days >= MIN_PROMO_DAYS:
        return "medium"
    if days >= 2:
        return "low"
    return "none"


def _actionable(days: int, overall) -> bool:
    return days >= MIN_PROMO_DAYS and overall is not None


def ladder_promotion_rates(as_of: str | None = None) -> dict:
    """计算各档晋级率与综合晋级率。

    返回：
      available   bool
      ready       bool（有任一档可算）
      days        int（历史天数）
      latest_date str|None
      latest      dict|None
      rates       dict{tier_label: rate_or_None}
      overall     float|None（优先首板→二板）
      actionable  bool（是否可信到可驱动决策）
      confidence  str(high/medium/low/none)
      source      str（实际读取的文件路径或原因）
    """
    path = _find_history()
    if not path:
        return dict(available=False, ready=False, days=0, latest_date=None, latest=None,
                    rates={}, overall=None, actionable=False, confidence="none",
                    source="未找到 shepherd_ladder_history.json；请设置 STOCKSIGNAL_ROOT 或 SS_LADDER_FILE")
    try:
        hist = _load_history(path)
    except ValueError as e:
        return dict(available=False, ready=False, days=0, latest_date=None, latest=None,
                    rates={}, overall=None, actionable=False, confidence="none",
                    source=f"读取失败：{e}")

    empty = dict(available=True, ready=False, days=0, latest_date=None, latest=None,
                 rates={}, overall=None, actionable=False, confidence="none", source=path)
    if not hist:
        return empty

    dates = sorted(d for d, e in hist.items()
                   if isinstance(e, dict) and not e.get("suspect"))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    if not dates:
        return empty

    if len(dates) < 2:
        return dict(available=True, ready=False, days=len(dates),
                    latest=hist[dates[-1]], latest_date=dates[-1],
                    rates={}, overall=None, actionable=False,
                    confidence=_promo_confidence(len(dates)), source=path)

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

    days = len(dates)
    return dict(available=True, ready=any(v is not None for v in rates.values()),
                days=days, latest=latest, latest_date=dates[-1],
                rates=rates, overall=overall,
                actionable=_actionable(days, overall),
                confidence=_promo_confidence(days), source=path)


def evaluate(today_distribution: dict | None = None,
             as_of: str | None = None) -> dict:
    """ skill 统一入口。若传入 today_distribution，会合并到历史末尾再算；否则读历史。 """
    if today_distribution is not None:
        # 简单合并：把传入分布作为最新日（as_of 或今天），让引擎可脱离文件运行演示
        path = _find_history()
        hist = {}
        if path:
            try:
                hist = _load_history(path)
            except Exception:  # noqa: BLE001
                hist = {}
        from datetime import datetime
        date = as_of or datetime.now().strftime("%Y-%m-%d")
        dist = {}
        for k, v in (today_distribution or {}).items():
            try:
                dist[int(k)] = int(v)
            except Exception:
                pass
        if dist:
            hist[date] = {
                "date": date,
                "distribution": dist,
                "max_boards": max(dist.keys()),
                "total_connect": sum(v for k, v in dist.items() if k >= 2),
            }
            # 写回临时？不，只用于本次计算
            # 为保持计算一致性，把 hist 传给内部函数
            # 但 ladder_promotion_rates 内部从文件读，这里需要绕过
            # 所以下面直接复用核心逻辑
            dates = sorted(hist.keys())
            if len(dates) >= 2:
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
                days = len(dates)
                return dict(available=True, ready=True, days=days, latest=latest,
                            latest_date=dates[-1], rates=rates, overall=overall,
                            actionable=_actionable(days, overall),
                            confidence=_promo_confidence(days), source=path or "inline-demo")
        # fallback 到无历史
        return dict(available=False, ready=False, days=0, latest_date=None, latest=None,
                    rates={}, overall=None, actionable=False, confidence="none",
                    source="传入分布但历史不足 2 日，无法算晋级率")
    return ladder_promotion_rates(as_of=as_of)
