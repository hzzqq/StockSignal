"""modules/stock_risk.py — 个股风险扫描（H6）。

一键体检（``pages/34_体检扫描.py``）回答的是「这只票好不好」；本模块回答的是
**「这只票有没有雷」**——商誉 / 质押 / 解禁 / 减持 / 诉讼处罚 / ST，六个维度各自
给出 高 / 中 / 低 / 未知 风险等级，并可汇总成一张「排雷体检表」。

对标：芝麻 AI 的年报红绿标注、同花顺 i问财 的风险项、理杏仁 的商誉占比提醒。
此前 StockSignal 只有零星的关键词命中（``_news_io.NEGATIVE_WORDS``）与选股标签
（``stock_screener`` 的 ``max_goodwill_pct``），**没有任何一处把风险事件汇总成
可判读的仪表盘**。

━━━━━━━━━━━━━━━━━━━━━━━━━━━ 诚实红线（重要） ━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 纯计算函数（``*_risk`` / ``build_risk_report``）**不触网、不读库**，数据由调用方
   注入，全部可单测。取数函数（``fetch_*`` / ``scan_stock``）best-effort 触网。
2. **「没查到」≠「安全」，必须显式区分**。取数失败一律返回 ``None``，对应
   ``level = "unknown"``；而「取到了、但确实没有风险记录」才判「低风险」。
   把没拉到的数据说成低风险，是这套系统里最危险的一类造假。
3. 阈值是**启发式**（对照公开研究里常用的量级），只用于「值不值得看一眼」的粗筛，
   不是投资建议，也不是预测。
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "RISK_HIGH", "RISK_MEDIUM", "RISK_LOW", "RISK_UNKNOWN",
    "LEVEL_CN", "LEVEL_COLOR", "LEVEL_RANK",
    "DIMENSIONS",
    "goodwill_risk", "pledge_risk", "unlock_risk",
    "reduction_risk", "litigation_risk", "st_risk",
    "build_risk_report",
    "fetch_st_set", "fetch_hold_management",
    "fetch_pledge", "fetch_unlock_queue", "fetch_balance_sheet",
    "fetch_announcement_titles", "scan_stock", "scan_many",
]

# ─────────────────────────── 风险等级 ───────────────────────────
RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"
RISK_UNKNOWN = "unknown"

LEVEL_CN = {RISK_HIGH: "高", RISK_MEDIUM: "中", RISK_LOW: "低", RISK_UNKNOWN: "未知"}
# 风险配色：高=红、中=琥珀、低=绿、未知=灰（与行情「红涨绿跌」相互独立）
LEVEL_COLOR = {
    RISK_HIGH: "#ee2a2a",
    RISK_MEDIUM: "#f5a623",
    RISK_LOW: "#1aa260",
    RISK_UNKNOWN: "#8c8c8c",
}
# 越大越危险（用于取最坏等级）
LEVEL_RANK = {RISK_UNKNOWN: 0, RISK_LOW: 1, RISK_MEDIUM: 2, RISK_HIGH: 3}

# 六个风险维度：(key, 中文名, 单位说明)
DIMENSIONS = [
    ("goodwill", "商誉", "商誉 / 净资产"),
    ("pledge", "质押", "未解押占总股本"),
    ("unlock", "解禁", "未来 90 日占流通市值"),
    ("reduction", "减持", "近 90 日董监高净变动占总股本"),
    ("litigation", "诉讼处罚", "近 1 年公告关键词"),
    ("st", "ST/退市", "证券简称"),
]

# 各维度阈值（越大越危险）
THRESHOLDS = {
    "goodwill": (30.0, 10.0),     # 商誉/净资产 ≥30% 高、≥10% 中
    "pledge": (30.0, 15.0),       # 未解押占总股本 ≥30% 高、≥15% 中
    "unlock": (20.0, 10.0),       # 未来 90 日解禁占流通市值 ≥20% 高、≥10% 中
    "reduction": (1.0, 0.3),      # 近 90 日净减持占总股本 ≥1% 高、≥0.3% 中
}

_UNLOCK_HORIZON_DAYS = 90
_REDUCTION_LOOKBACK_DAYS = 90
_ANN_LOOKBACK_DAYS = 365


def _num(v):
    """尽力转数值；转不了或非有限值返回 None（``0`` 是合法值，保留）。"""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        f = float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _level_from(value, dim: str) -> str:
    """按维度阈值把数值转成风险等级；``None`` → 未知。"""
    if value is None:
        return RISK_UNKNOWN
    hi, mid = THRESHOLDS.get(dim, (float("inf"), float("inf")))
    if value >= hi:
        return RISK_HIGH
    if value >= mid:
        return RISK_MEDIUM
    return RISK_LOW


def _comp(level, value=None, note="", detail=None) -> dict:
    return {"level": level, "value": value, "note": note, "detail": detail or []}


# ─────────────────────────── 1. 商誉 ───────────────────────────
def goodwill_risk(bs: dict | None) -> dict:
    """商誉 / 净资产 占比 → 风险等级。

    ``bs`` 形如 ``{"goodwill": 数值或 None, "equity": 数值, "report_date": "20260630"}``；
    ``bs is None`` 表示**取数失败** → 未知（不是低风险）。

    报表里 ``goodwill`` 为空但净资产有效，说明**该报表没有商誉科目**（未做并购），
    此时按 0 处理判「低」，并在 note 里写清楚，避免把「无商誉」误报成「查不到」。
    """
    if not isinstance(bs, dict):
        return _comp(RISK_UNKNOWN, None, "资产负债表取数失败")
    equity = _num(bs.get("equity"))
    rd = bs.get("report_date") or ""
    if equity is None or equity <= 0:
        return _comp(RISK_UNKNOWN, None, f"净资产不可用（报告期 {rd}）".strip())
    raw_gw = bs.get("goodwill")
    gw = _num(raw_gw)
    if gw is None:
        return _comp(RISK_LOW, 0.0,
                     f"报告期 {rd} 资产负债表未见商誉（无并购商誉减值风险）".strip())
    ratio = round(gw / equity * 100, 2)
    return _comp(_level_from(ratio, "goodwill"), ratio,
                 f"商誉 {gw / 1e8:.2f} 亿 / 净资产 {equity / 1e8:.2f} 亿（报告期 {rd}）".strip(),
                 detail=[{"商誉(亿)": round(gw / 1e8, 2),
                          "净资产(亿)": round(equity / 1e8, 2),
                          "占比(%)": ratio, "报告期": rd}])


# ─────────────────────────── 2. 质押 ───────────────────────────
def pledge_risk(pledges: list | None) -> dict:
    """股权质押：未解押股份占总股本比例 → 风险等级。

    ``pledges is None`` → 取数失败 → 未知；``pledges == []`` → 确实无质押记录 → 低。
    """
    if pledges is None:
        return _comp(RISK_UNKNOWN, None, "质押明细取数失败")
    active = [p for p in pledges
              if isinstance(p, dict) and str(p.get("status") or "") != "已解押"]
    if not active:
        return _comp(RISK_LOW, 0.0, "未见未解押股份")
    ratios = [r for r in (_num(p.get("ratio_total")) for p in active) if r is not None]
    if not ratios:
        return _comp(RISK_UNKNOWN, None, "质押明细缺『占总股本比例』字段")
    max_ratio = round(max(ratios), 2)
    n = len(active)
    return _comp(_level_from(max_ratio, "pledge"), max_ratio,
                 f"{n} 笔未解押，单笔最高占总股本 {max_ratio}%",
                 detail=[{"股东": p.get("holder"), "占总股本(%)": _num(p.get("ratio_total")),
                          "状态": p.get("status"), "质押结束": p.get("end_date")}
                         for p in active[:10]])


# ─────────────────────────── 3. 解禁 ───────────────────────────
def unlock_risk(queue: list | None, today=None, horizon_days: int = _UNLOCK_HORIZON_DAYS) -> dict:
    """限售解禁：未来 ``horizon_days`` 天内解禁占流通市值比例 → 风险等级。

    ``queue is None`` → 取数失败 → 未知；窗口内无解禁 → 低。
    """
    if queue is None:
        return _comp(RISK_UNKNOWN, None, "解禁明细取数失败")
    base = today or datetime.now()
    if isinstance(base, str):
        try:
            base = datetime.strptime(base[:10], "%Y-%m-%d")
        except ValueError:
            base = datetime.now()
    upcoming = []
    for q in queue:
        if not isinstance(q, dict):
            continue
        d = q.get("date")
        if not d:
            continue
        try:
            dd = datetime.strptime(str(d)[:10], "%Y-%m-%d")
        except ValueError:
            continue
        delta = (dd - base).days
        if 0 <= delta <= horizon_days:
            upcoming.append({**q, "_days": delta})
    if not upcoming:
        return _comp(RISK_LOW, 0.0, f"未来 {horizon_days} 日无解禁")
    pcts = [p for p in (_num(q.get("pct_float")) for q in upcoming) if p is not None]
    if not pcts:
        return _comp(RISK_UNKNOWN, None, "解禁明细缺『占流通市值比例』字段")
    max_pct = round(max(pcts), 2)
    soon = min(upcoming, key=lambda q: q["_days"])
    return _comp(_level_from(max_pct, "unlock"), max_pct,
                 f"未来 {horizon_days} 日内 {len(upcoming)} 批解禁，最大占流通市值 {max_pct}%"
                 f"（最近一批 {soon['_days']} 天后）",
                 detail=[{"解禁日": q.get("date"), "距今天数": q.get("_days"),
                          "占流通市值(%)": _num(q.get("pct_float")),
                          "限售类型": q.get("type")} for q in
                         sorted(upcoming, key=lambda x: x["_days"])[:10]])


# ─────────────────────────── 4. 减持 ───────────────────────────
def reduction_risk(rows: list | None, today=None,
                   lookback_days: int = _REDUCTION_LOOKBACK_DAYS) -> dict:
    """董监高持股变动：窗口内净减持占总股本比例 → 风险等级（净增持则降低危险度）。

    ``rows is None`` → 取数失败 → 未知；窗口内无变动记录 → 低。
    """
    if rows is None:
        return _comp(RISK_UNKNOWN, None, "董监高持股变动取数失败")
    base = today or datetime.now()
    if isinstance(base, str):
        try:
            base = datetime.strptime(base[:10], "%Y-%m-%d")
        except ValueError:
            base = datetime.now()
    cutoff = base - timedelta(days=lookback_days)
    win = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = r.get("date")
        if not d:
            continue
        try:
            dd = datetime.strptime(str(d)[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if dd >= cutoff:
            win.append(r)
    if not win:
        return _comp(RISK_LOW, 0.0, f"近 {lookback_days} 日无董监高持股变动")
    pct_sum = 0.0
    amt_sum = 0.0
    has_pct = False
    for r in win:
        p = _num(r.get("change_pct"))
        cp = _num(r.get("change_pct_signed"))
        if cp is not None:
            pct_sum += cp
            has_pct = True
        elif p is not None and str(r.get("direction")) == "减":
            pct_sum -= abs(p)
            has_pct = True
        a = _num(r.get("change_amount"))
        if a is not None:
            amt_sum += a
    net_pct = round(pct_sum, 3) if has_pct else None
    if net_pct is None:
        return _comp(RISK_UNKNOWN, None, "董监高变动记录缺『变动比例』字段")
    # 净增持（>0）按无减持处理
    risk_val = max(0.0, -net_pct)
    note = (f"近 {lookback_days} 日净增持 {net_pct:+.3f}% 总股本" if net_pct > 0
            else f"近 {lookback_days} 日净减持 {abs(net_pct):.3f}% 总股本"
                 f"（合计金额 {amt_sum / 1e4:,.0f} 万元）")
    return _comp(_level_from(risk_val, "reduction"), net_pct, note,
                 detail=[{"日期": r.get("date"), "人员": r.get("person"),
                          "职务": r.get("title"), "变动股数": _num(r.get("change_shares")),
                          "变动比例(%)": _num(r.get("change_pct_signed")),
                          "原因": r.get("reason")}
                         for r in sorted(win, key=lambda x: str(x.get("date")), reverse=True)[:10]])


# ─────────────────────────── 5. 诉讼 / 处罚 ───────────────────────────
# 关键词 → 风险等级。命中多个取最坏。
_LITIGATION_KW = {
    "立案调查": RISK_HIGH, "被立案": RISK_HIGH, "行政处罚": RISK_HIGH,
    "退市风险": RISK_HIGH, "涉嫌犯罪": RISK_HIGH, "强制退市": RISK_HIGH,
    "违规": RISK_MEDIUM, "警示函": RISK_MEDIUM, "监管函": RISK_MEDIUM,
    "诉讼": RISK_MEDIUM, "仲裁": RISK_MEDIUM, "被起诉": RISK_MEDIUM,
    "公开谴责": RISK_MEDIUM, "债务违约": RISK_HIGH,
    "问询函": RISK_LOW, "关注函": RISK_LOW, "监管关注": RISK_LOW,
}


def litigation_risk(titles: list | None) -> dict:
    """公告标题关键词扫描 → 风险等级。

    ``titles is None`` → 取数失败 → 未知；取到了但零命中 → **低**，但 note 里如实写明
    「未见公开的诉讼/处罚类公告」——**不等于「没有诉讼」**（未公开的不在公告里）。
    """
    if titles is None:
        return _comp(RISK_UNKNOWN, None, "公告取数失败")
    if not titles:
        return _comp(RISK_LOW, 0.0, "近 1 年未取到公告（无记录 ≠ 无风险）")
    hits = []
    worst = RISK_LOW
    for t in titles:
        s = str(t or "")
        for kw, lv in _LITIGATION_KW.items():
            if kw in s and LEVEL_RANK[lv] > LEVEL_RANK[worst]:
                worst = lv
            if kw in s:
                hits.append({"关键词": kw, "标题": s})
                break
    if not hits:
        return _comp(RISK_LOW, 0.0,
                     f"近 1 年 {len(titles)} 条公告未见公开的诉讼/处罚类标题")
    kws = sorted({h["关键词"] for h in hits})
    return _comp(worst, len(hits),
                 f"近 1 年 {len(hits)} 条公告命中风险关键词：{'、'.join(kws)}",
                 detail=hits[:10])


# ─────────────────────────── 6. ST / 退市 ───────────────────────────
def st_risk(name: str | None, is_st: bool | None = None) -> dict:
    """证券简称识别 ST / *ST / 退市 → 风险等级。

    ``is_st`` 由市场级 ST 名单直接给出时优先采用（更可靠）；都给不出 → 未知。
    """
    if isinstance(is_st, bool):
        if is_st:
            return _comp(RISK_HIGH, None, f"在 ST/风险警示名单内（{name or ''}）".strip())
        return _comp(RISK_LOW, None, f"不在 ST/风险警示名单内（{name or ''}）".strip())
    if not name:
        return _comp(RISK_UNKNOWN, None, "无证券简称，无法判定 ST 状态")
    n = str(name).upper().replace(" ", "")
    if "ST" in n:
        return _comp(RISK_HIGH, None, f"证券简称含 ST 标识（{name}）")
    if "退" in str(name):
        return _comp(RISK_HIGH, None, f"证券简称含退市标识（{name}）")
    return _comp(RISK_LOW, None, f"证券简称无 ST/退市标识（{name}）")


# ─────────────────────── 汇总：风险体检报告 ───────────────────────
def _score_from_levels(levels: list) -> int:
    """已知等级 → 0-100 风险分（100 = 无风险）。高 -35、中 -15、低 -0。"""
    score = 100
    for lv in levels:
        if lv == RISK_HIGH:
            score -= 35
        elif lv == RISK_MEDIUM:
            score -= 15
    return max(0, score)


def build_risk_report(components: dict) -> dict:
    """把六维风险组件汇总成一份报告。

    ``components``：``{dim_key: {"level":..., "value":..., "note":..., "detail":[...]}}``。

    返回含 ``overall_level``（最坏已知等级）/ ``n_high`` / ``n_medium`` / ``n_low`` /
    ``n_unknown`` / ``coverage_pct`` / ``reliable`` / ``risk_score`` / ``notes``。

    诚实红线：**全部维度都未知时 overall 就是「未知」**，绝不在零覆盖下给一个绿色结论；
    ``reliable`` 只有在已知维度占比 ≥60% 时才为 True，页面据此决定是否展示综合结论。
    """
    comps = components if isinstance(components, dict) else {}
    levels = []
    n_high = n_medium = n_low = n_unknown = 0
    for _key, _cn, _unit in DIMENSIONS:
        c = comps.get(_key)
        lv = (c or {}).get("level") if isinstance(c, dict) else RISK_UNKNOWN
        if lv not in LEVEL_RANK:
            lv = RISK_UNKNOWN
        levels.append(lv)
        if lv == RISK_HIGH:
            n_high += 1
        elif lv == RISK_MEDIUM:
            n_medium += 1
        elif lv == RISK_LOW:
            n_low += 1
        else:
            n_unknown += 1

    known = [lv for lv in levels if lv != RISK_UNKNOWN]
    if not known:
        overall = RISK_UNKNOWN
    else:
        overall = max(known, key=lambda lv: LEVEL_RANK[lv])

    total = len(DIMENSIONS)
    coverage = round(len(known) / total * 100, 1) if total else 0.0
    notes = []
    for key, cn, _unit in DIMENSIONS:
        c = comps.get(key)
        if isinstance(c, dict) and c.get("level") == RISK_UNKNOWN and c.get("note"):
            notes.append(f"{cn}：{c['note']}")
    return {
        "overall_level": overall,
        "n_high": n_high,
        "n_medium": n_medium,
        "n_low": n_low,
        "n_unknown": n_unknown,
        "coverage_pct": coverage,
        "reliable": coverage >= 60.0,
        "risk_score": _score_from_levels(known),
        "components": comps,
        "notes": notes,
    }


# ─────────────────────────── 取数层（best-effort） ───────────────────────────
_CACHE_TTL = 3600  # 市场级数据集缓存 1 小时
_market_cache: dict = {}


def _cache_get(key: str):
    hit = _market_cache.get(key)
    if not hit:
        return None
    ts, data = hit
    if (datetime.now() - ts).total_seconds() > _CACHE_TTL:
        return None
    return data


def _cache_put(key: str, data):
    _market_cache[key] = (datetime.now(), data)
    return data


def _sina_symbol(code: str) -> str:
    """6 位代码 → 新浪所需的市场前缀（``sh``/``sz``/``bj``）。"""
    c = str(code).strip().zfill(6)
    if c.startswith(("60", "68", "90", "51", "58")):
        return "sh" + c
    if c.startswith(("00", "30", "20", "15", "16", "12")):
        return "sz" + c
    if c.startswith(("43", "83", "87", "88", "92")):
        return "bj" + c
    return "sh" + c


def fetch_st_set():
    """ST / 风险警示股票代码集合 → ``set[str]``；失败返回 ``None``。"""
    cached = _cache_get("st_set")
    if cached is not None:
        return cached
    try:
        import akshare as ak
        df = ak.stock_zh_a_st_em()
    except Exception as e:  # noqa: BLE001
        logger.info("[stock_risk] ST 名单取数失败: %s", e)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    col = None
    for c in df.columns:
        if "代码" in str(c):
            col = c
            break
    if col is None:
        return None
    codes = {str(v).strip().zfill(6) for v in df[col].tolist()}
    return _cache_put("st_set", codes)


def fetch_hold_management():
    """全市场董监高持股变动明细（DataFrame）；失败返回 ``None``（市场级，仅拉一次）。"""
    cached = _cache_get("hold_mgmt")
    if cached is not None:
        return cached
    try:
        import akshare as ak
        df = ak.stock_hold_management_detail_em()
    except Exception as e:  # noqa: BLE001
        logger.info("[stock_risk] 董监高持股变动取数失败: %s", e)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    return _cache_put("hold_mgmt", df)


def _pick_col(df: pd.DataFrame, *cands: str):
    """按子串找列名；找不到返回 None（不猜列——猜错列等于编造风险方向）。"""
    for c in df.columns:
        for cand in cands:
            if cand in str(c):
                return c
    return None


def fetch_pledge(code: str):
    """个股质押明细 → 归一化 ``list[dict]``；失败 ``None``；无记录 ``[]``。"""
    try:
        import akshare as ak
        df = ak.stock_gpzy_individual_pledge_ratio_detail_em(symbol=str(code).strip().zfill(6))
    except Exception as e:  # noqa: BLE001
        logger.info("[stock_risk] 质押取数失败(%s): %s", code, e)
        return None
    if df is None:
        return None
    if getattr(df, "empty", True):
        return []
    c_holder = _pick_col(df, "股东名称", "股东")
    c_ratio = _pick_col(df, "占总股本比例")
    c_status = _pick_col(df, "状态")
    c_end = _pick_col(df, "质押结束日期")
    out = []
    for _, r in df.iterrows():
        out.append({
            "holder": r.get(c_holder) if c_holder else None,
            "ratio_total": _num(r.get(c_ratio)) if c_ratio else None,
            "status": r.get(c_status) if c_status else None,
            "end_date": str(r.get(c_end))[:10] if c_end else None,
        })
    return out


def fetch_unlock_queue(code: str):
    """个股限售解禁队列 → 归一化 ``list[dict]``；失败 ``None``；无记录 ``[]``。"""
    try:
        import akshare as ak
        df = ak.stock_restricted_release_queue_em(symbol=str(code).strip().zfill(6))
    except Exception as e:  # noqa: BLE001
        logger.info("[stock_risk] 解禁取数失败(%s): %s", code, e)
        return None
    if df is None:
        return None
    if getattr(df, "empty", True):
        return []
    c_date = _pick_col(df, "解禁时间")
    c_pct = _pick_col(df, "占流通市值比例")
    c_type = _pick_col(df, "限售股类型")
    out = []
    for _, r in df.iterrows():
        # akshare 该接口比例为**小数**（0.2007 = 20.07%），统一归一成百分数
        raw = _num(r.get(c_pct)) if c_pct else None
        out.append({
            "date": str(r.get(c_date))[:10] if c_date else None,
            "pct_float": round(raw * 100, 4) if raw is not None else None,
            "type": r.get(c_type) if c_type else None,
        })
    return out


def fetch_balance_sheet(code: str):
    """资产负债表关键项 → ``{"goodwill","equity","report_date"}``；失败 ``None``。"""
    try:
        import akshare as ak
        df = ak.stock_financial_report_sina(stock=_sina_symbol(code), symbol="资产负债表")
    except Exception as e:  # noqa: BLE001
        logger.info("[stock_risk] 资产负债表取数失败(%s): %s", code, e)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    c_date = _pick_col(df, "报告日")
    if c_date is not None:
        df = df.sort_values(c_date, ascending=False)
    row = df.iloc[0]
    c_gw = _pick_col(df, "商誉")
    c_eq = _pick_col(df, "归属于母公司股东权益合计", "所有者权益(或股东权益)合计", "所有者权益")
    return {
        "goodwill": _num(row.get(c_gw)) if c_gw else None,
        "equity": _num(row.get(c_eq)) if c_eq else None,
        "report_date": str(row.get(c_date))[:10] if c_date else None,
    }


def fetch_announcement_titles(code: str):
    """近 1 年个股公告标题 → ``list[str]``；失败 ``None``（用于诉讼/处罚关键词扫描）。"""
    try:
        from modules.news import NewsFetcher
        df = NewsFetcher()._fetch_eastmoney_announcements(str(code).strip().zfill(6), limit=100)
    except Exception as e:  # noqa: BLE001
        logger.info("[stock_risk] 公告取数失败(%s): %s", code, e)
        return None
    if df is None:
        return None
    if getattr(df, "empty", True):
        return []
    if "title" in df.columns:
        return [str(t) for t in df["title"].tolist() if t]
    return None


def _hold_rows_for(code: str):
    """从市场级董监高明细里抽出该股近 90 日记录（归一化）；数据不可用返回 ``None``。"""
    df = fetch_hold_management()
    if df is None:
        return None
    c_code = _pick_col(df, "代码")
    if c_code is None:
        return None
    sub = df[df[c_code].astype(str).str.zfill(6) == str(code).strip().zfill(6)]
    if getattr(sub, "empty", True):
        return []
    c_date = _pick_col(sub, "日期")
    c_sh = _pick_col(sub, "变动股数")
    c_pct = _pick_col(sub, "变动比例")
    c_amt = _pick_col(sub, "变动金额")
    c_reason = _pick_col(sub, "变动原因")
    c_name = _pick_col(sub, "董监高人员姓名", "变动人")
    c_title = _pick_col(sub, "职务")
    out = []
    for _, r in sub.iterrows():
        sh = _num(r.get(c_sh)) if c_sh else None
        pct = _num(r.get(c_pct)) if c_pct else None
        signed = None
        if pct is not None:
            # 变动比例在源数据里为绝对值，方向由变动股数决定
            signed = pct if (sh is None or sh >= 0) else -pct
        out.append({
            "date": str(r.get(c_date))[:10] if c_date else None,
            "person": r.get(c_name) if c_name else None,
            "title": r.get(c_title) if c_title else None,
            "change_shares": sh,
            "change_pct_signed": signed,
            "change_amount": _num(r.get(c_amt)) if c_amt else None,
            "reason": r.get(c_reason) if c_reason else None,
            "direction": "增" if (sh is not None and sh >= 0) else "减",
        })
    return out


def scan_stock(code: str, name: str | None = None, st_set=None) -> dict:
    """对单只股票做六维风险扫描，返回 ``{"code","name","components","report","errors"}``。

    ``st_set`` 可外部注入（批量扫描时避免每只都重拉 ST 名单）。
    """
    c = str(code).strip().zfill(6)
    comps: dict = {}
    errors: list = []

    if st_set is None:
        st_set = fetch_st_set()
    is_st = None
    if isinstance(st_set, set):
        is_st = c in st_set
    comps["st"] = st_risk(name, is_st)

    try:
        comps["goodwill"] = goodwill_risk(fetch_balance_sheet(c))
    except Exception as e:  # noqa: BLE001
        comps["goodwill"] = _comp(RISK_UNKNOWN, None, f"商誉扫描异常: {e}")
        errors.append(f"goodwill: {e}")

    try:
        comps["pledge"] = pledge_risk(fetch_pledge(c))
    except Exception as e:  # noqa: BLE001
        comps["pledge"] = _comp(RISK_UNKNOWN, None, f"质押扫描异常: {e}")
        errors.append(f"pledge: {e}")

    try:
        comps["unlock"] = unlock_risk(fetch_unlock_queue(c))
    except Exception as e:  # noqa: BLE001
        comps["unlock"] = _comp(RISK_UNKNOWN, None, f"解禁扫描异常: {e}")
        errors.append(f"unlock: {e}")

    try:
        comps["reduction"] = reduction_risk(_hold_rows_for(c))
    except Exception as e:  # noqa: BLE001
        comps["reduction"] = _comp(RISK_UNKNOWN, None, f"减持扫描异常: {e}")
        errors.append(f"reduction: {e}")

    try:
        comps["litigation"] = litigation_risk(fetch_announcement_titles(c))
    except Exception as e:  # noqa: BLE001
        comps["litigation"] = _comp(RISK_UNKNOWN, None, f"诉讼扫描异常: {e}")
        errors.append(f"litigation: {e}")

    return {
        "code": c,
        "name": name or c,
        "components": comps,
        "report": build_risk_report(comps),
        "errors": errors,
    }


def scan_many(codes_with_names, max_workers: int = 4, progress=None) -> list:
    """批量扫描。``codes_with_names`` 可为 ``[(code, name), ...]`` 或 ``{code: name}``。

    ``progress`` 可选回调 ``progress(done, total)``，便于页面显示进度。
    """
    import concurrent.futures

    items = list(codes_with_names.items()) if isinstance(codes_with_names, dict) \
        else list(codes_with_names)
    if not items:
        return []
    total = len(items)
    st_set = fetch_st_set()  # 市场级，只拉一次
    out = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(scan_stock, code, name, st_set): code for code, name in items}
        for fut in concurrent.futures.as_completed(futs):
            try:
                out.append(fut.result())
            except Exception as e:  # noqa: BLE001
                code = futs[fut]
                out.append({"code": code, "name": code, "components": {},
                            "report": build_risk_report({}), "errors": [str(e)]})
            done += 1
            if callable(progress):
                try:
                    progress(done, total)
                except Exception:
                    pass
    out.sort(key=lambda r: (LEVEL_RANK.get(r["report"]["overall_level"], 0),
                            r["report"]["risk_score"]))
    return out
