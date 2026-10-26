# -*- coding: utf-8 -*-
"""modules/position_allocator.py — T-326 方向B：个股→组合落地（仓位分配器）。

把市场仓位决策落到具体标的：市场仓位 pct × 个股评分 → 个股目标权重。
纯建议层：只读不写盘（绝不直写 portfolio.csv），建议 ≠ 交易。

═════════════════════════ spec（冻结）══════════════════════════
契约 allocate(market_pct, stocks, cap_pct=DEFAULT_CAP_PCT, mode="score") -> dict：
- 输入
  - market_pct：市场仓位 0~100（唯一来源 data/daily_snapshot.json position.pct，
    不做实时臆算——无快照一律 unavailable，老板 2026-10-26 拍板）；
  - stocks：[{"code","name","score"}]，score 0~100 或 None（缺失）；
  - cap_pct：单票上限（默认 20.0）；
  - mode："score"（按评分比例）｜"equal"（等权，明示降级）。
- 输出 ok：{"status":"ok", "allocations":[{"code","name","score","weight","pct"}],
  "excluded":[{"code","name","reason"}], "meta":{mode,cap_pct,target_pct,sum_pct,
  n_alloc,n_excluded,capped,overflow_pct,degraded}}
  - Σ(allocations.pct) = market_pct（受 cap 约束时如实少配，overflow_pct 交代缺口）；
  - 单票 pct ≤ cap_pct（waterfill：超限截断 → 剩余按权重重分给未到 cap 的）；
  - round(2) 后 Σ 与目标差 ≤ 0.05×n（测试钉）。
- unavailable（诚实语义，绝不编造）：
  - market_pct None/非数/越界(≤0 或 >100)；stocks 空；mode 未知；
  - score 模式下全部评分缺失/无效（不编造分配依据）；有效评分合计为 0。
- 评分缺失（个别 None/无效/越界）→ 该标的剔除进 excluded 并注明原因，
  绝不用伪分数顶替。
- 等权模式 meta.degraded=True（明示降级：无评分源可用，非隐式行为）。
═══════════════════════════════════════════════════════════════

数据面 loader（薄层，全部诚实降级）：
- load_market_pct(data_dir)   → (pct, meta)   快照 position.pct；
- load_recommend_stocks(...)  → (stocks, meta) 荐股引擎 composite（load_latest_recommendation）；
- load_user_scores()          → (stocks, meta) REST GET /api/user-scores；
- load_watchlist_stocks()     → (stocks, meta) 自选池（等权池，score=None）；
- build_allocation(source, data_dir) 三源编排：recommend / user / equal。

A 股红涨绿跌语义与本模块无关（无涨跌展示）；页面侧 metric 一律 delta_color="off"。
"""
from __future__ import annotations

import json
import logging
import math
import os

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

DEFAULT_CAP_PCT = 20.0
_EPS = 1e-9

_VALID_MODES = ("score", "equal")


def _unavail(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason}


def _norm_score(raw):
    """评分归一：可解析为 [0,100] 有限数 → float；None/无效 → None（不编造）。"""
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v < 0 or v > 100:
        return None
    return v


def _waterfill(weights: list, total: float, cap: float) -> list:
    """按权重把 total 分配到各槽，单槽 ≤ cap（超限截断后剩余按权重重分）。

    返回与 weights 等长的 pct 列表（未 round）。迭代每轮至少封顶一个槽，必然终止。
    """
    n = len(weights)
    result = [0.0] * n
    remaining = total
    idx = set(range(n))
    while idx:
        wsum = sum(weights[i] for i in idx)
        if wsum <= _EPS:
            break
        share = {i: remaining * weights[i] / wsum for i in idx}
        over = [i for i in idx if share[i] > cap + _EPS]
        if not over:
            for i in idx:
                result[i] = max(share[i], 0.0)
            break
        for i in over:
            result[i] = cap
            remaining -= cap
            idx.discard(i)
        if remaining <= _EPS:
            break
    return result


def allocate(market_pct, stocks, cap_pct: float = DEFAULT_CAP_PCT, mode: str = "score") -> dict:
    """市场仓位 × 个股评分 → 个股目标权重（纯函数，无 IO，见模块 spec）。"""
    # ── 市场仓位校验（唯一真值来源=当日快照，越界即 unavailable）──
    try:
        pct = float(market_pct)
    except (TypeError, ValueError):
        return _unavail(f"市场仓位不可得：{market_pct!r}（非数值，不臆算）")
    if not math.isfinite(pct) or pct <= 0 or pct > 100:
        return _unavail(f"市场仓位越界：{market_pct!r}（须 0<pct≤100，不臆算）")
    if mode not in _VALID_MODES:
        return _unavail(f"未知评分模式：{mode!r}")

    try:
        cap = float(cap_pct)
    except (TypeError, ValueError):
        return _unavail(f"单票上限非法：{cap_pct!r}")
    if not math.isfinite(cap) or cap <= 0 or cap > 100:
        return _unavail(f"单票上限越界：{cap_pct!r}（须 0<cap≤100）")

    # ── 标的与评分归一 ──
    norm = []
    for s in (stocks or []):
        if not isinstance(s, dict):
            continue
        code = s.get("code") or s.get("ticker")
        if not code:
            continue
        norm.append({"code": str(code), "name": str(s.get("name") or code),
                     "score": _norm_score(s.get("score"))})
    if not norm:
        return _unavail("无可分配标的（标的池为空）")

    excluded = []
    if mode == "equal":
        kept = norm                       # 等权模式不需要评分
    else:
        kept = []
        for s in norm:
            if s["score"] is None:
                excluded.append({"code": s["code"], "name": s["name"],
                                 "reason": "评分缺失/无效（不编造，剔除分配）"})
            else:
                kept.append(s)
        if not kept:
            return _unavail("全部标的评分缺失/无效，无分配依据（不编造）")
        if sum(s["score"] for s in kept) <= _EPS:
            return _unavail("有效评分合计为 0，无法按比例分配（不编造）")

    # ── 权重与分配 ──
    weights = [1.0] * len(kept) if mode == "equal" else [s["score"] for s in kept]
    pcts = _waterfill(weights, pct, cap)
    capped = []
    for s, p, w in zip(kept, pcts, weights):
        s["pct"] = round(p, 2)
        s["weight"] = round(p / 100.0, 4)
        s["_raw"] = w
        if p >= cap - _EPS:
            capped.append(s["code"])

    allocations = [{"code": s["code"], "name": s["name"], "score": s["score"],
                    "weight": s["weight"], "pct": s["pct"]} for s in kept]
    sum_pct = round(sum(a["pct"] for a in allocations), 2)
    target = round(pct, 2)
    overflow = round(max(0.0, target - cap * len(kept)), 2)

    meta = {
        "mode": "equal_weight" if mode == "equal" else "score",
        "degraded": mode == "equal",          # 等权＝明示降级（无评分源可用）
        "cap_pct": cap,
        "target_pct": target,
        "sum_pct": sum_pct,
        "n_alloc": len(allocations),
        "n_excluded": len(excluded),
        "capped": capped,
        "overflow_pct": overflow,
    }
    return {"status": "ok", "allocations": allocations,
            "excluded": excluded, "meta": meta}


# ══════════════════════════════════════════════════════
# 数据面 loader（薄层，诚实降级，不臆算）
# ══════════════════════════════════════════════════════
def load_market_pct(data_dir: str = None) -> tuple:
    """读当日市场快照的 position.pct（0~100）；无快照→(None, meta)，不实时臆算。"""
    d = data_dir or _DEFAULT_DATA_DIR
    path = os.path.join(d, "daily_snapshot.json")
    try:
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
    except FileNotFoundError:
        return None, {"status": "unavailable",
                      "reason": "无当日市场快照（data/daily_snapshot.json 不存在，每交易日收盘后归档）——不实时臆算"}
    except Exception as e:  # noqa: BLE001
        return None, {"status": "unavailable", "reason": f"快照读取失败：{type(e).__name__}"}
    if not isinstance(snap, dict):
        return None, {"status": "unavailable", "reason": "快照结构异常"}
    pos = snap.get("position") or {}
    raw = pos.get("pct")
    if raw is None:
        return None, {"status": "unavailable", "reason": "快照缺失 position.pct（不臆算）"}
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return None, {"status": "unavailable", "reason": f"position.pct 非数值：{raw!r}"}
    return pct, {"status": "ok", "snapshot_date": snap.get("date"),
                 "temperature": snap.get("temperature"), "band": pos.get("band")}


def load_recommend_stocks(data_dir: str = None) -> tuple:
    """荐股引擎综合分池（composite 0~100）；引擎 unavailable → ([], meta)。"""
    from modules.recommend_engine import load_latest_recommendation
    rec = load_latest_recommendation(data_dir)
    if rec.get("status") != "ok":
        return [], {"status": "unavailable",
                    "reason": f"荐股引擎数据不可用：{rec.get('reason') or '未知原因'}"}
    stocks = []
    for p in (rec.get("picks") or []):
        if not isinstance(p, dict):
            continue
        code = p.get("code") or p.get("ticker")
        if not code:
            continue
        stocks.append({"code": str(code), "name": str(p.get("name") or code),
                       "score": p.get("composite")})
    return stocks, {"status": "ok", "generated_at": rec.get("generated_at"),
                    "data_as_of": rec.get("data_as_of")}


def load_user_scores() -> tuple:
    """用户 StockScore 池（REST GET /api/user-scores，0~100）。"""
    from modules.session import api_get
    try:
        code_, body = api_get("/api/user-scores", timeout=5)
    except Exception as e:  # noqa: BLE001
        return [], {"status": "unavailable", "reason": f"评分接口请求失败：{type(e).__name__}"}
    if code_ != 200 or not isinstance(body, dict):
        return [], {"status": "unavailable", "reason": f"评分接口返回异常（HTTP {code_}）"}
    data = body.get("data")
    if not isinstance(data, list):
        return [], {"status": "unavailable", "reason": "评分接口数据结构异常"}
    stocks = []
    for r in data:
        if not isinstance(r, dict) or not r.get("stock_code"):
            continue
        stocks.append({"code": str(r["stock_code"]),
                       "name": str(r.get("stock_name") or r["stock_code"]),
                       "score": r.get("score")})
    if not stocks:
        return [], {"status": "unavailable", "reason": "尚无用户评分标的（先在个股研究页给股票打分）"}
    return stocks, {"status": "ok"}


def load_watchlist_stocks() -> tuple:
    """自选池（等权模式标的池，score=None）。"""
    from modules.session import get_watchlist
    try:
        wl = get_watchlist()
    except Exception as e:  # noqa: BLE001
        return [], {"status": "unavailable", "reason": f"自选池读取失败：{type(e).__name__}"}
    stocks = []
    for r in (wl or []):
        if not isinstance(r, dict):
            continue
        code = r.get("code") or r.get("stock_code") or r.get("ticker")
        if not code:
            continue
        stocks.append({"code": str(code),
                       "name": str(r.get("name") or r.get("stock_name") or code),
                       "score": None})
    if not stocks:
        return [], {"status": "unavailable", "reason": "自选池为空（先在行情看板添加自选）"}
    return stocks, {"status": "ok"}


# 三源注册表：source → (loader, mode, 展示名)
_SOURCES = {
    "recommend": (load_recommend_stocks, "score", "荐股引擎综合分"),
    "user": (load_user_scores, "score", "用户 StockScore"),
    "equal": (load_watchlist_stocks, "equal", "等权（明示降级）"),
}


def build_allocation(source: str, data_dir: str = None,
                     cap_pct: float = DEFAULT_CAP_PCT) -> dict:
    """三源编排：市场仓位（快照）× 指定评分源 → 分配结果。

    市场仓位不可得 → unavailable（不实时臆算）；评分源不可得 → unavailable。
    ok 时 meta 附 market / source 两块溯源信息。
    """
    src = _SOURCES.get(source)
    if src is None:
        return _unavail(f"未知评分源：{source!r}（可选：recommend/user/equal）")
    loader, mode, label = src

    pct, pmeta = load_market_pct(data_dir)
    if pct is None:
        return _unavail(pmeta.get("reason") or "市场仓位不可得")

    # recommend 的 loader 需要 data_dir（荐股文件可注入测试）；其余走 session 无参
    if source == "recommend":
        stocks, smeta = load_recommend_stocks(data_dir)
    else:
        stocks, smeta = loader()
    if smeta.get("status") != "ok" or not stocks:
        return _unavail(f"市场仓位可得（{pct:g}%），但评分源「{label}」不可用："
                        f"{smeta.get('reason') or '无标的'}")

    result = allocate(pct, stocks, cap_pct=cap_pct, mode=mode)
    if result.get("status") != "ok":
        return result
    meta = result["meta"]
    meta["market"] = pmeta
    meta["source"] = {"key": source, "label": label, **smeta}
    if meta.get("degraded"):
        meta["degraded_note"] = ("等权明示降级：未使用任何评分信号（标的池无逐票评分可用），"
                                 "权重仅为均分参考，不构成强弱排序。")
    return result
