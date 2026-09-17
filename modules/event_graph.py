"""modules/event_graph.py — 事件传导图谱（H3）。

**从「一条新闻」走到「谁可能受影响」**：识别标题里的**概念/题材**，把概念展开成真实
成分股，再按「文本共现强度」给受益标的排序——对标财联社题材雷达、芝麻 AI 的产业链受益股。

━━━━━━━━━━━━━━━━━━━━━━━━━━━ 口径（务必看清） ━━━━━━━━━━━━━━━━━━━━━━━━━━━
本模块给出的是**关联度**，不是收益预测。打分只有两个来源：

1. **直接点名（权重 3）**：个股名与概念同时出现在同一标题里；
2. **概念外溢（权重 1）**：标题命中概念，但未点名该股。

所以「分高」只说明**这条消息在文本上更贴近它**，不代表它一定受益，更不代表会涨。
页面必须显示 ``basis`` 与 ``disclaimer``。

━━━━━━━━━━━━━━━━━━━━━━━━━━━ 诚实红线 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 纯计算函数不触网；概念名单与成分股是**真实数据**（东财概念板块），不手工编造产业链；
- 概念名单取不到 → ``status="unavailable"``，**不退回内置的臆造题材表**；
- 命中的概念若拿不到成分股 → 该概念单列 ``members_unavailable``，不猜成员。
"""

from __future__ import annotations

import logging

__all__ = [
    "NEUTRAL", "BULLISH", "BEARISH",
    "MIN_NAME_LEN", "DIR_COLOR", "EVIDENCE_LEN",
    "event_direction", "match_concepts", "build_transmission",
    "dir_color", "display_rows",
    "fetch_concept_names", "fetch_concept_members",
]

logger = logging.getLogger(__name__)

NEUTRAL, BULLISH, BEARISH = "中性", "利好", "利空"

# 个股名短于该长度时不参与「直接点名」判定（「东」「方」这类子串会制造大量假命中）
MIN_NAME_LEN = 3

# 认不出方向时的兜底词表；优先复用项目既有词库（modules._news_io）
_FALLBACK_BULLISH = ("中标", "涨停", "扭亏", "预增", "突破", "签约", "获批", "提价",
                     "增持", "回购", "订单", "放量", "创新高", "涨价", "量产")
_FALLBACK_BEARISH = ("立案", "处罚", "亏损", "预减", "下滑", "跌停", "退市", "违规",
                     "减持", "质押", "违约", "降薪", "裁员", "召回", "闪崩", "创新低")


def _word_lists():
    """优先用项目既有情绪词库，取不到再用内置兜底（不联网、不抛）。"""
    try:
        from modules._news_io import NEGATIVE_WORDS, POSITIVE_WORDS
        pos = tuple(str(w) for w in POSITIVE_WORDS) if POSITIVE_WORDS else ()
        neg = tuple(str(w) for w in NEGATIVE_WORDS) if NEGATIVE_WORDS else ()
        if pos and neg:
            return pos, neg
    except Exception:  # noqa: BLE001
        pass
    return _FALLBACK_BULLISH, _FALLBACK_BEARISH


def event_direction(text) -> str:
    """标题情感方向：利好 / 利空 / 中性（词表命中数相同时按中性处理，不硬猜）。"""
    s = str(text or "")
    if not s:
        return NEUTRAL
    pos, neg = _word_lists()
    n_pos = sum(1 for w in pos if w and w in s)
    n_neg = sum(1 for w in neg if w and w in s)
    if n_pos > n_neg:
        return BULLISH
    if n_neg > n_pos:
        return BEARISH
    return NEUTRAL


def match_concepts(text, concept_names) -> list:
    """在文本里找出命中的概念名（**长串优先**，重叠的不重复计）。

    先按长度降序匹配，命中后把该片段从待匹配文本里「挖掉」，避免
    「半导体设备」命中后「半导体」再次命中同一次提及。
    """
    s = str(text or "")
    if not s:
        return []
    names = sorted({str(n) for n in (concept_names or []) if n and len(str(n)) >= 2},
                   key=len, reverse=True)
    hits = []
    remaining = s
    for n in names:
        if n in remaining:
            hits.append(n)
            remaining = remaining.replace(n, "\u3000")
    return hits


def build_transmission(titles, concept_index) -> dict:
    """把一批标题 + 概念成分股索引 → 受益标的排行。

    ``concept_index``：``{概念名: [{"code","name"}, ...]}``。
    ``titles``：``[(标题, 日期)]`` 或 ``[标题]``。

    返回 ``{"status","basis","disclaimer","entries":[...],"members_unavailable":[...]}``。
    """
    if not isinstance(concept_index, dict) or not concept_index:
        return {"status": "unavailable",
                "reason": "概念成分股索引不可用（未取到真实概念数据）",
                "entries": [], "members_unavailable": []}

    norm = []
    for t in (titles or []):
        if isinstance(t, (list, tuple)):
            norm.append((str(t[0] or ""), str(t[1]) if len(t) > 1 and t[1] else ""))
        elif t:
            norm.append((str(t), ""))
    if not norm:
        return {"status": "unavailable", "reason": "没有可分析的标题",
                "entries": [], "members_unavailable": []}

    names = list(concept_index.keys())
    acc: dict = {}
    missing_members: set = set()
    hit_concepts: set = set()

    for title, date in norm:
        matched = match_concepts(title, names)
        if not matched:
            continue
        direction = event_direction(title)
        for c in matched:
            hit_concepts.add(c)
            members = concept_index.get(c)
            if not members:
                missing_members.add(c)
                continue
            for m in members:
                if not isinstance(m, dict):
                    continue
                code = str(m.get("code") or "").strip()
                mname = str(m.get("name") or "").strip()
                if not code:
                    continue
                direct = bool(mname) and len(mname) >= MIN_NAME_LEN and mname in title
                rec = acc.setdefault(code, {"code": code, "name": mname or code,
                                            "score": 0, "concepts": set(),
                                            "evidence": [], "direct": False,
                                            "directions": {BULLISH: 0, BEARISH: 0}})
                rec["score"] += 3 if direct else 1
                rec["direct"] = rec["direct"] or direct
                rec["concepts"].add(c)
                if direction != NEUTRAL:
                    rec["directions"][direction] += 1
                if title not in rec["evidence"]:
                    rec["evidence"].append(title[:80])
                if date and date not in (rec.get("dates") or []):
                    rec.setdefault("dates", []).append(date)

    entries = []
    for rec in acc.values():
        d = rec.pop("directions")
        if d[BULLISH] > d[BEARISH]:
            rec["direction"] = BULLISH
        elif d[BEARISH] > d[BULLISH]:
            rec["direction"] = BEARISH
        else:
            rec["direction"] = NEUTRAL
        rec["concepts"] = sorted(rec["concepts"])
        rec["evidence"] = rec["evidence"][:3]
        entries.append(rec)
    entries.sort(key=lambda r: (-r["score"], r["code"]))

    return {
        "status": "ok" if entries else "empty",
        "reason": "" if entries else "标题里没有命中任何已知概念",
        "basis": "关联度 = 文本共现（概念命中 ×1；个股与概念同标题点名 ×3）",
        "disclaimer": "关联度仅为文本统计，不代表受益程度，更不是收益预测；请自行判断。",
        "n_titles": len(norm),
        "concepts_hit": sorted(hit_concepts),
        "members_unavailable": sorted(missing_members),
        "entries": entries,
    }


# ───────────────────── 展示层（纯函数：配色/拼接/截断可单测） ─────────────────────
# A 股习惯：利好偏红、利空偏绿、中性/未知灰（与全站口径一致，不要在这里反着写）
DIR_COLOR = {BULLISH: "#dc2626", BEARISH: "#16a34a", NEUTRAL: "#94a3b8"}

# 证据标题在界面上的截断长度
EVIDENCE_LEN = 64


def dir_color(direction) -> str:
    """方向 → 颜色（利好=红、利空=绿，其余一律灰）。"""
    return DIR_COLOR.get(str(direction), DIR_COLOR[NEUTRAL])


def display_rows(res, limit: int = 30, evidence_len: int = EVIDENCE_LEN) -> list:
    """把 ``build_transmission`` 的结果转成**展示行**（纯函数，无副作用、不触网）。

    只做呈现——配色 / 概念拼接 / 标题截断 / 缺字段兜底；**不改分数、不新增标的信息**。
    非 dict 的行直接跳过（不猜）；``evidence`` 取第一条并截断。
    """
    out = []
    for r in ((res or {}).get("entries") or []):
        if not isinstance(r, dict):
            continue
        code = str(r.get("code") or "")
        d = str(r.get("direction") or NEUTRAL)
        ev = r.get("evidence") or []
        first = str(ev[0]) if ev else ""
        out.append({
            "name": str(r.get("name") or code or "—"),
            "code": code,
            "score": r.get("score", 0),
            "direction": d,
            "dir_color": dir_color(d),
            "concepts": "、".join(str(c) for c in (r.get("concepts") or [])) or "—",
            "evidence": first[:evidence_len],
            "direct": bool(r.get("direct")),
        })
        if len(out) >= limit:
            break
    return out


# ─────────────────────────── 取数层（best-effort） ───────────────────────────
def fetch_concept_names():
    """东财概念板块**名称列表**；失败返回 ``None``（不退回内置题材表）。"""
    try:
        from modules.fetcher import StockFetcher
        df = StockFetcher().get_concept_list()
    except Exception as e:  # noqa: BLE001
        logger.info("[event_graph] 概念列表取数失败: %s", e)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    col = None
    for c in df.columns:
        if "名称" in str(c) or str(c).lower() in ("name", "concept", "板块名称"):
            col = c
            break
    if col is None:
        return None
    return [str(v).strip() for v in df[col].tolist() if str(v).strip()]


def fetch_concept_members(concept: str):
    """概念成分股 → ``[{"code","name"}, ...]``；失败返回 ``None``（不等于「无成分股」）。"""
    try:
        from modules.fetcher import StockFetcher
        df = StockFetcher().get_concept_stocks(concept)
    except Exception as e:  # noqa: BLE001
        logger.info("[event_graph] 概念成分取数失败(%s): %s", concept, e)
        return None
    if df is None:
        return None
    if getattr(df, "empty", True):
        return []
    c_code = next((c for c in df.columns if "代码" in str(c) or str(c).lower() == "code"), None)
    c_name = next((c for c in df.columns if "名称" in str(c) or str(c).lower() == "name"), None)
    if c_code is None:
        return None
    out = []
    for _, r in df.iterrows():
        code = str(r.get(c_code) or "").strip()
        if not code:
            continue
        out.append({"code": code.zfill(6) if code.isdigit() else code,
                    "name": (str(r.get(c_name)).strip() if c_name else "")})
    return out


def build_index_for_titles(titles, max_concepts: int = 8, fetch_members=None) -> dict:
    """只对**标题里真正命中**的概念去拉成分股（避免把几百个概念全拉一遍）。

    ``fetch_members`` 可注入（默认 ``fetch_concept_members``），便于离线测试。
    """
    fn = fetch_members or fetch_concept_members
    names = fetch_concept_names()
    if not names:
        return {}
    probe = [str(t[0] if isinstance(t, (list, tuple)) else t or "") for t in (titles or [])]
    hit: list = []
    for t in probe:
        for c in match_concepts(t, names):
            if c not in hit:
                hit.append(c)
    idx: dict = {}
    for c in hit[:max_concepts]:
        members = fn(c)
        if members:
            idx[c] = members
    return idx
