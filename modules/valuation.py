"""modules/valuation.py — 估值分位深钻（H2）。

「PE 18 倍」这句话本身没有信息量——**贵不贵要跟自己的历史比、跟同行比**。
本模块把三件事做成可判读的结论（对标理杏仁 的 PE/PB Band 与分位、萝卜投研 的同业对比）：

- ``band_stats`` / ``pe_pb_band``  **PE / PB Band**：历史序列的 20/50/80 分位带、
  当前值所处**分位**与区间（低估 / 偏低 / 合理 / 偏高 / 高估）；
- ``industry_relative``            **行业相对分位**：个股估值在同行样本里的分位与排名；
- ``dupont``                       **杜邦分解**：ROE = 净利率 × 总资产周转率 × 权益乘数，
  并核对三项乘积与披露 ROE 是否自洽；
- ``peer_matrix``                  **同业矩阵**：多只同行的 PE / PB / ROE / 市值横向对比，
  逐列算中位数与排名。

━━━━━━━━━━━━━━━━━━━━━━━━━━━ 诚实红线 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 纯计算函数不触网，数据由调用方注入；
- 样本不足（序列 < ``_MIN_SAMPLES`` 点 / 同行 < 3 只 / 缺关键因子）一律
  ``status="unavailable"``，**绝不用 0 或「合理」把空缺糊过去**；
- PE ≤ 0（亏损）不参与分位计算——负数 PE 排序会得出「亏损越大越便宜」的荒谬结论；
- 杜邦乘积与披露 ROE 不一致时**如实标注口径差异**，不强行对齐。
"""

from __future__ import annotations

import logging
import math

__all__ = [
    "MIN_SAMPLES", "ZONE_ORDER", "ZONE_COLOR",
    "band_stats", "pe_pb_band", "industry_relative", "dupont", "peer_matrix",
    "fetch_valuation_series", "fetch_pe_pb_series", "fetch_dupont_inputs",
]

logger = logging.getLogger(__name__)

MIN_SAMPLES = 20  # 少于该样本数不给分位结论
_MIN_PEERS = 3

# 估值分位区间（分位值越大 = 越贵）
ZONE_ORDER = ["低估", "偏低", "合理", "偏高", "高估"]
# 估值语义配色：便宜=绿、合理=琥珀、贵=红（与行情「红涨绿跌」相互独立）
ZONE_COLOR = {"低估": "#1aa260", "偏低": "#1aa260", "合理": "#f5a623",
              "偏高": "#ee2a2a", "高估": "#ee2a2a", "不可用": "#8c8c8c"}


def _num(v):
    """转 float；失败/NaN 返回 ``None``（0 是合法值，保留）。"""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _percentile_of(values: list, value: float) -> float:
    """value 在 values 中的百分位（0-100）。``values`` 已保证非空。"""
    n = len(values)
    below = sum(1 for x in values if x <= value)
    return round(below / n * 100, 1)


def _quantile(sorted_vals: list, q: float):
    """线性插值分位数；``sorted_vals`` 非空且已升序。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _zone_of(pct: float | None) -> str:
    if pct is None:
        return "不可用"
    if pct <= 20:
        return "低估"
    if pct <= 40:
        return "偏低"
    if pct <= 60:
        return "合理"
    if pct <= 80:
        return "偏高"
    return "高估"


def band_stats(values, current=None, label: str = "", min_samples: int = MIN_SAMPLES) -> dict:
    """历史估值序列的分位带。

    ``values``：历史 PE/PB 序列（可含 None / 非正数 / 字符串）；``current``：当前值。

    PE/PB **只保留 > 0 的样本**（亏损股的负 PE 参与排序会得到「越亏越便宜」的错误结论）。
    """
    clean = []
    for v in (values or []):
        f = _num(v)
        if f is not None and f > 0:
            clean.append(f)
    n = len(clean)
    if n < min_samples:
        return {"status": "unavailable", "label": label, "n": n,
                "reason": f"历史样本不足（{n} < {min_samples}）"}

    s = sorted(clean)
    p20, p50, p80 = (_quantile(s, 0.2), _quantile(s, 0.5), _quantile(s, 0.8))
    cur = _num(current)
    pct = _percentile_of(s, cur) if (cur is not None and cur > 0) else None
    return {
        "status": "ok",
        "label": label,
        "n": n,
        "min": round(s[0], 2),
        "p20": round(p20, 2),
        "p50": round(p50, 2),
        "p80": round(p80, 2),
        "max": round(s[-1], 2),
        "current": round(cur, 2) if cur is not None else None,
        "percentile": pct,
        "zone": _zone_of(pct),
        "note": "历史分位基于可得样本区间，样本越短参考性越弱",
    }


def pe_pb_band(pe_series, pb_series, current_pe=None, current_pb=None) -> dict:
    """PE 与 PB 两条历史序列的分位带合并结果。"""
    return {
        "pe": band_stats(pe_series, current_pe, label="市盈率(TTM)"),
        "pb": band_stats(pb_series, current_pb, label="市净率"),
    }


def industry_relative(value, peers) -> dict:
    """个股估值在同行样本中的分位与排名（越小越便宜）。

    ``peers``：同行样本的估值序列（只保留 > 0 的有效值）。有效样本 <3 只 → 不可用。
    """
    cur = _num(value)
    clean = []
    for v in (peers or []):
        f = _num(v)
        if f is not None and f > 0:
            clean.append(f)
    if cur is None or cur <= 0:
        return {"status": "unavailable", "reason": "当前估值缺失或非正（亏损股不参与分位）"}
    if len(clean) < _MIN_PEERS:
        return {"status": "unavailable", "n": len(clean),
                "reason": f"同行有效样本不足（{len(clean)} < {_MIN_PEERS}）"}
    s = sorted(clean)
    pct = _percentile_of(s, cur)
    rank = sum(1 for x in s if x < cur) + 1   # 升序排名：1 = 最便宜
    median = _quantile(s, 0.5)
    return {
        "status": "ok",
        "n": len(s),
        "current": round(cur, 2),
        "median": round(median, 2),
        "min": round(s[0], 2),
        "max": round(s[-1], 2),
        "percentile": pct,
        "rank": rank,
        "zone": _zone_of(pct),
        "ratio_to_median": round(cur / median, 3) if median else None,
    }


def dupont(roe, net_margin, asset_turnover, equity_multiplier) -> dict:
    """杜邦分解：ROE(%) = 净利率(%) × 总资产周转率(次) × 权益乘数。

    任一因子缺失 → ``status="unavailable"`` 并列出缺失项（不猜、不默认 1.0）。
    三项乘积与披露 ROE 偏差 > max(5, |roe|×10%) 时给出**口径差异**提示，仍照常返回。
    """
    roe_v = _num(roe)
    nm = _num(net_margin)
    at = _num(asset_turnover)
    em = _num(equity_multiplier)
    missing = [name for name, v in
               (("ROE", roe_v), ("净利率", nm), ("总资产周转率", at), ("权益乘数", em)) if v is None]
    if missing:
        return {"status": "unavailable", "missing": missing,
                "reason": "缺关键因子：" + "、".join(missing)}

    implied = nm * at * em
    tol = max(5.0, abs(roe_v) * 0.10)
    consistent = abs(implied - roe_v) <= tol
    flags = []
    if em >= 2.5:
        flags.append("高杠杆驱动（权益乘数 ≥2.5，资产负债率约 ≥60%，ROE 含杠杆放大，需关注偿债风险）")
    if nm < 0:
        flags.append("净利率为负（当期亏损），ROE 由亏损与杠杆共同放大")
    elif nm < 5:
        flags.append("净利率偏低（<5%），盈利弹性小、抗成本波动能力弱")
    if at < 0.5:
        flags.append("总资产周转率偏低（<0.5 次），资产使用效率偏弱")
    if not flags:
        flags.append("三项因子均在常见区间内，未见单一因子极端驱动")
    return {
        "status": "ok",
        "roe": round(roe_v, 2),
        "net_margin": round(nm, 2),
        "asset_turnover": round(at, 3),
        "equity_multiplier": round(em, 3),
        "implied_roe": round(implied, 2),
        "consistent": consistent,
        "tol": round(tol, 2),
        "flags": flags,
        "note": ("" if consistent else
                 f"三项乘积 {implied:.2f}% 与披露 ROE {roe_v:.2f}% 偏差超出容差 "
                 f"{tol:.2f}，属口径差异（常见原因：净资产用期末值而非期初期末平均）"),
    }


def _median_of(vals: list):
    s = sorted(vals)
    return _quantile(s, 0.5)


def peer_matrix(peers: list, metrics=("pe", "pb", "roe")) -> dict:
    """同业矩阵：逐列中位数 + 每只标的的列内排名（缺值的单元格留空，不补 0）。

    ``peers``：``[{"code","name","pe","pb","roe","market_cap"}, ...]``。
    有效标的 <3 只 → ``status="unavailable"``。
    """
    rows_in = [p for p in (peers or []) if isinstance(p, dict)]
    if len(rows_in) < _MIN_PEERS:
        return {"status": "unavailable", "n": len(rows_in),
                "reason": f"同行样本不足（{len(rows_in)} < {_MIN_PEERS}）"}

    cols = [m for m in metrics]
    medians = {}
    for c in cols:
        vals = [v for v in (_num(p.get(c)) for p in rows_in) if v is not None]
        medians[c] = round(_median_of(vals), 3) if vals else None

    rows = []
    for p in rows_in:
        row = {"code": str(p.get("code") or ""), "name": str(p.get("name") or p.get("code") or "")}
        for c in cols:
            row[c] = _num(p.get(c))
        mc = _num(p.get("market_cap"))
        row["market_cap"] = mc
        # PE / PB 越小越便宜 → 升序排名（1 = 最低）；ROE 越大越好 → 降序排名
        for c, ascending in (("pe", True), ("pb", True), ("roe", False)):
            if c not in cols:
                continue
            v = row.get(c)
            if v is None:
                row[f"rank_{c}"] = None
                continue
            others = [x for x in (_num(q.get(c)) for q in rows_in) if x is not None]
            if ascending:
                row[f"rank_{c}"] = sum(1 for x in others if x < v) + 1
            else:
                row[f"rank_{c}"] = sum(1 for x in others if x > v) + 1
        row["n_valid"] = sum(1 for c in cols if row.get(c) is not None)
        rows.append(row)

    return {"status": "ok", "n": len(rows_in), "medians": medians,
            "metrics": cols, "rows": rows}


# ─────────────────────────── 取数层（best-effort） ───────────────────────────
def fetch_valuation_series(code: str, indicator: str, period: str = "近十年"):
    """拉个股估值历史序列（百度股市通）→ ``[(date, value), ...]``；失败 ``None``。"""
    try:
        import akshare as ak
        df = ak.stock_zh_valuation_baidu(symbol=str(code).strip().zfill(6),
                                        indicator=indicator, period=period)
    except Exception as e:  # noqa: BLE001
        logger.info("[valuation] %s 取数失败(%s): %s", indicator, code, e)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    dc = "date" if "date" in df.columns else df.columns[0]
    vc = "value" if "value" in df.columns else df.columns[-1]
    out = []
    for _, r in df.iterrows():
        v = _num(r.get(vc))
        if v is not None:
            out.append((str(r.get(dc))[:10], v))
    return out or None


def fetch_pe_pb_series(code: str, period: str = "近十年") -> dict:
    """同时拉 PE(TTM) 与 PB 序列 → ``{"pe": [...], "pb": [...], "span": "起~止"}``；全失败 ``None``。"""
    pe = fetch_valuation_series(code, "市盈率(TTM)", period)
    pb = fetch_valuation_series(code, "市净率", period)
    if pe is None and pb is None:
        return None
    dates = [d for d, _ in (pe or pb or [])]
    return {
        "pe": [v for _, v in (pe or [])],
        "pb": [v for _, v in (pb or [])],
        "pe_series": pe or [],
        "pb_series": pb or [],
        "span": (f"{min(dates)} ~ {max(dates)}" if dates else ""),
        "n_pe": len(pe or []),
        "n_pb": len(pb or []),
    }


def _pick_col(df, *cands):
    """按子串找列；找不到返回 ``None``（不猜列）。"""
    for c in df.columns:
        for cand in cands:
            if cand in str(c):
                return c
    return None


def fetch_dupont_inputs(code: str, start_year: str | None = None):
    """取杜邦三因子（同花顺财务指标，**官方口径**，非自行估算）→ 可直接喂给 ``dupont()``。

    返回 ``{"roe","net_margin","asset_turnover","equity_multiplier"}``；任一因子缺失返回 ``None``
    （由调用方转成「不可用」，不省略、不默认 1.0）。

    权益乘数优先由「股东权益比率」倒数得到（= 总资产/净资产），缺失时回退
    ``1/(1-资产负债率/100)``——两者都是会计恒等式，不引入额外假设。
    """
    from datetime import datetime
    sy = start_year or str(datetime.now().year - 1)
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator(symbol=str(code).strip().zfill(6), start_year=sy)
    except Exception as e:  # noqa: BLE001
        logger.info("[valuation] 杜邦因子取数失败(%s): %s", code, e)
        return None
    if df is None or getattr(df, "empty", True):
        return None
    dc = _pick_col(df, "日期")
    if dc is not None:
        df = df.sort_values(dc, ascending=False)
    row = df.iloc[0]
    c_roe = _pick_col(df, "净资产收益率(%)", "净资产收益率")
    c_nm = _pick_col(df, "销售净利率(%)", "销售净利率")
    c_at = _pick_col(df, "总资产周转率(次)", "总资产周转率")
    c_er = _pick_col(df, "股东权益比率(%)", "股东权益比率")
    c_alr = _pick_col(df, "资产负债率(%)", "资产负债率")
    roe = _num(row.get(c_roe)) if c_roe else None
    nm = _num(row.get(c_nm)) if c_nm else None
    at = _num(row.get(c_at)) if c_at else None
    em = None
    er = _num(row.get(c_er)) if c_er else None
    if er is not None and er > 0:
        em = round(100.0 / er, 4)
    else:
        alr = _num(row.get(c_alr)) if c_alr else None
        if alr is not None and alr < 100:
            em = round(1.0 / (1.0 - alr / 100.0), 4)
    if None in (roe, nm, at, em):
        return None
    return {"roe": roe, "net_margin": nm, "asset_turnover": at, "equity_multiplier": em}
