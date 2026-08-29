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
from datetime import datetime

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LADDER_DIR = os.path.join(_ROOT, "data")
LADDER_FILE = os.path.join(LADDER_DIR, "shepherd_ladder_history.json")
_lock = threading.Lock()


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
        tmp = LADDER_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
        os.replace(tmp, LADDER_FILE)   # 原子替换，避免写一半崩掉
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
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        return _save_history(hist)


def ladder_promotion_rates() -> dict:
    """算各档晋级率（跨日递推）。

    晋级率定义：某档 n（≥2板）的晋级率 = 当日 n板家数 / 昨日 (n-1)板家数。
      · 2板晋级率 = 当日2板家数 / 昨日首板家数（最能代表接力意愿）
      · 3板晋级率 = 当日3板 / 昨日2板，以此类推
    仅当存在「今日」与「昨日」两条快照时才有意义。

    返回：
      ready       bool（有任一档晋级率可算才有意义）
      days        int（历史天数）
      latest      dict（最新快照）
      latest_date str
      rates       {tier_label: rate_or_None}，tier_label 形如 "2b"(首板→二板) / "3b" / …
      overall     float|None（综合晋级率：优先取首板→二板，缺失则取可用档均值）
    """
    empty = dict(ready=False, days=0, latest=None, latest_date=None, rates={}, overall=None)
    hist = load_history()
    if not hist:
        return empty
    dates = sorted(hist.keys())
    if len(dates) < 2:
        return dict(ready=False, days=len(dates), latest=hist[dates[-1]],
                    latest_date=dates[-1], rates={}, overall=None)
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
                rates=rates, overall=overall)


def current_promo_as_indicators() -> dict:
    """把最新综合晋级率打包成 forecast 派生指标 {ladder_promo: rate}。

    缺历史（未积累≥2日）时返回 {}（不污染 today，forecast 不会出现该驱动）。
    """
    pr = ladder_promotion_rates()
    if not pr.get("ready") or pr.get("overall") is None:
        return {}
    return {"ladder_promo": pr["overall"]}
