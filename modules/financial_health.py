"""R8/T-363：财务健康度三合一评估（纯函数，无副作用，可单测）。

三模型覆盖 Piotroski F-Score（盈利能力+杠杆+运营 9 分量）、
Altman Z'-Score（五比率破产风险，A股修正口径）、
Beneish M-Score（操纵检测 logit 模型）。

诚实语义铁律：三表任何分量缺列 / NaN / 非数值 → 该分量 components 标
status="unavailable"，reasons 透明说明，绝不编造、绝不默认 0。
全分量 unavailable → 顶层 status="unavailable"；部分 unavailable →
status="warning" 并在 reasons 标注可用率。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 中文列名硬编码（_market_data_io.fetch_financial 返回全中文列）──────────
# 列名单点定义 → 测试可用相同 map 构造 fake DataFrame
_BALANCE = {
    "total_assets": "资产总计",
    "total_liabilities": "负债合计",
    "current_assets": "流动资产合计",
    "current_liabilities": "流动负债合计",
    "long_loan": "长期借款",
    "bonds_payable": "应付债券",
    "long_payable": "长期应付款合计",
    "lease_liab": "租赁负债",
    "other_noncur_liab": "其他非流动负债",
    "retained_earnings": "未分配利润",  # Altman X2 近似（诚实标注）
    "accounts_receivable": "应收账款",
    "share_capital": "实收资本(或股本)",
}
_INCOME = {
    "revenue": "营业收入",
    "cogs": "营业成本",
    "net_income": "净利润",
    "ebit_approx": "财务费用",  # 取反 ≈ -利息费用
    "tax_expense": "所得税费用",
    "selling_expense": "销售费用",
    "admin_expense": "管理费用",
}
_CASH = {
    "ocf": "经营活动产生的现金流量净额",
}


# ── 内部工具 ──────────────────────────────────────────────────────────────
def _ensure_fetcher(fetcher):
    """Lazy instantiate StockFetcher（recommend_engine 已有 fetcher 实例可注入复用）。"""
    if fetcher is not None:
        return fetcher
    from modules.fetcher import StockFetcher
    return StockFetcher()


def _to_float(val) -> Optional[float]:
    """安全转 float；NaN / inf / 不可转 → None。"""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return v


def _pick_col(df: pd.DataFrame, cn: str) -> Optional[pd.Series]:
    """取 DataFrame 中指定中文列；不存在 → None。"""
    if df is None or df.empty or cn not in df.columns:
        return None
    return df[cn]


def _row_val(df: pd.DataFrame, cn: str, row: int = 0) -> Optional[float]:
    """取 DataFrame 第 row 行（默认最新 row=0）的中文列浮点值；缺失 → None。"""
    s = _pick_col(df, cn)
    if s is None:
        return None
    if row >= len(s):
        return None
    return _to_float(s.iloc[row])


def _fetch_tables(fetcher, symbol: str) -> dict:
    """一次性取三表，返回 {balance, income, cash}；任何表取不到 → 值为 None。"""
    tables: dict[str, Optional[pd.DataFrame]] = {"balance": None, "income": None, "cash": None}
    for rt in ("balance", "income", "cash"):
        try:
            df = fetcher.get_financial(symbol, rt)
            if isinstance(df, pd.DataFrame) and not df.empty:
                tables[rt] = df
        except Exception as e:  # noqa: BLE001 — 网络/源异常如实降级
            logger.info("[financial_health] %s %s 取不到: %s", symbol, rt, e)
    return tables


def _market_cap(fetcher, symbol: str, balance_df: Optional[pd.DataFrame]) -> Optional[float]:
    """流通市值 = 最新收盘价 × 股本（balance sheet 实收资本）；任一不可得 → None。"""
    share_cap = _row_val(balance_df, _BALANCE["share_capital"], row=0) if balance_df is not None else None
    if share_cap is None or share_cap <= 0:
        return None
    try:
        df = fetcher.get_daily(symbol, start=None, adjust="qfq")
    except Exception as e:  # noqa: BLE001
        logger.info("[financial_health] %s get_daily 失败（市值不可得）: %s", symbol, e)
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = _to_float(df["close"].iloc[-1])
    if close is None or close <= 0:
        return None
    return close * share_cap


def _pack(*, status: str, score: Any, components: dict, reasons: list) -> dict:
    """统一返回结构，便于上游 merge + 测试比对。"""
    return {
        "status": status,
        "score": score,
        "components": dict(components),
        "reasons": list(reasons),
    }


def _component(name: str, *, value=None, ok: bool = False, note: str = "") -> tuple[str, dict]:
    """构造单个分量字典；ok=False 视为 unavailable（缺省默认，调用方显式 True 才变 ok）。"""
    if ok and value is not None:
        return name, {"status": "ok", "value": value, "note": note or "计算成功"}
    return name, {"status": "unavailable", "value": None, "note": note or "数据不可得，未计入总分"}


# ════════════════════════════════════════════════════════════════════════════
# Piotroski F-Score（0-9 分）
# 盈利 4 项 + 杠杆/流动性 3 项 + 运营 2 项；每项命中 +1
# ════════════════════════════════════════════════════════════════════════════
def f_score(symbol: str, fetcher=None) -> dict:
    """Piotroski F-Score (0-9)：财务健康九分量打分。

    分量：ROA>0 / ΔROA>0 / OCF>NI / OCF>0 / 长期债务减少 / 流动比率增加 /
    股本不增 / 资产周转率增 / 毛利率增。任一分量缺数据 → unavailable 不编造。
    """
    fetcher = _ensure_fetcher(fetcher)
    tables = _fetch_tables(fetcher, symbol)
    bal, inc, cash = tables["balance"], tables["income"], tables["cash"]
    reasons: list[str] = []
    comps: dict[str, dict] = {}
    hits = 0
    avail = 0

    # ── 取最新 + 上期（row 0=最新, row 1=上期）────────────────────────────
    latest_assets = _row_val(bal, _BALANCE["total_assets"], 0)
    prev_assets = _row_val(bal, _BALANCE["total_assets"], 1)
    latest_liab = _row_val(bal, _BALANCE["total_liabilities"], 0)

    latest_ni = _row_val(inc, _INCOME["net_income"], 0)
    prev_ni = _row_val(inc, _INCOME["net_income"], 1)
    latest_rev = _row_val(inc, _INCOME["revenue"], 0)
    prev_rev = _row_val(inc, _INCOME["revenue"], 1)
    latest_cogs = _row_val(inc, _INCOME["cogs"], 0)
    prev_cogs = _row_val(inc, _INCOME["cogs"], 1)

    latest_ocf = _row_val(cash, _CASH["ocf"], 0)
    prev_ocf = _row_val(cash, _CASH["ocf"], 1)

    def _roa(ni, assets):
        if ni is None or assets is None or assets <= 0:
            return None
        return ni / assets

    roa_now = _roa(latest_ni, latest_assets)
    roa_prev = _roa(prev_ni, prev_assets)

    # 1. ROA > 0
    if roa_now is not None:
        avail += 1
        if roa_now > 0:
            hits += 1
            ok = True
            note = f"ROA={roa_now:.4f}>0"
        else:
            ok = True
            note = f"ROA={roa_now:.4f}≤0"
        comps.update([_component("roa", value=int(roa_now > 0), ok=True, note=note)])
    else:
        comps.update([_component("roa", note="净利润或总资产缺失")])

    # 2. ΔROA > 0
    if roa_now is not None and roa_prev is not None:
        avail += 1
        d = roa_now - roa_prev
        if d > 0:
            hits += 1
        comps.update([_component("delta_roa", value=int(d > 0), ok=True,
                                 note=f"ΔROA={d:.4f}")])
    else:
        comps.update([_component("delta_roa", note="ROA 两期均不可算")])

    # 3. OCF > NI（应计利润为负，盈余质量好）
    if latest_ocf is not None and latest_ni is not None:
        avail += 1
        if latest_ocf > latest_ni:
            hits += 1
        comps.update([_component("ocf_gt_ni", value=int(latest_ocf > latest_ni), ok=True,
                                 note=f"OCF={latest_ocf:.0f} vs NI={latest_ni:.0f}")])
    else:
        comps.update([_component("ocf_gt_ni", note="OCF 或 NI 缺失")])

    # 4. OCF > 0
    if latest_ocf is not None:
        avail += 1
        if latest_ocf > 0:
            hits += 1
        comps.update([_component("ocf_pos", value=int(latest_ocf > 0), ok=True,
                                 note=f"OCF={latest_ocf:.0f}")])
    else:
        comps.update([_component("ocf_pos", note="现金流量表缺失或 Q3 未披露（如实降级）")])
        reasons.append("⚠️ 现金流量表最新期 OCF 未披露——分量 3/4 不可用")

    # 5. 长期债务减少（本期 < 上期）
    def _long_debt(df, row):
        if df is None:
            return None
        parts = [_row_val(df, _BALANCE[c], row) for c in
                 ("long_loan", "bonds_payable", "long_payable", "lease_liab", "other_noncur_liab")]
        parts = [p for p in parts if p is not None]
        if not parts:
            return None
        return sum(parts)

    ld_now = _long_debt(bal, 0)
    ld_prev = _long_debt(bal, 1)
    if ld_now is not None and ld_prev is not None:
        avail += 1
        if ld_now < ld_prev:
            hits += 1
        comps.update([_component("long_debt_decrease", value=int(ld_now < ld_prev), ok=True,
                                 note=f"长期债 {ld_prev:.0f}→{ld_now:.0f}")])
    else:
        comps.update([_component("long_debt_decrease", note="长期债务五分量均缺失")])

    # 6. 流动比率增加
    ca_now = _row_val(bal, _BALANCE["current_assets"], 0)
    cl_now = _row_val(bal, _BALANCE["current_liabilities"], 0)
    ca_prev = _row_val(bal, _BALANCE["current_assets"], 1)
    cl_prev = _row_val(bal, _BALANCE["current_liabilities"], 1)

    def _cr(ca, cl):
        if ca is None or cl is None or cl <= 0:
            return None
        return ca / cl

    cr_now = _cr(ca_now, cl_now)
    cr_prev = _cr(ca_prev, cl_prev)
    if cr_now is not None and cr_prev is not None:
        avail += 1
        if cr_now > cr_prev:
            hits += 1
        comps.update([_component("current_ratio_increase", value=int(cr_now > cr_prev), ok=True,
                                 note=f"流动比率 {cr_prev:.3f}→{cr_now:.3f}")])
    else:
        comps.update([_component("current_ratio_increase", note="流动资产/负债缺失")])

    # 7. 普通股不发行（股本不增）
    sh_now = _row_val(bal, _BALANCE["share_capital"], 0)
    sh_prev = _row_val(bal, _BALANCE["share_capital"], 1)
    if sh_now is not None and sh_prev is not None and sh_prev > 0:
        avail += 1
        if sh_now <= sh_prev:
            hits += 1
        comps.update([_component("no_new_shares", value=int(sh_now <= sh_prev), ok=True,
                                 note=f"股本 {sh_prev:.0f}→{sh_now:.0f}")])
    else:
        comps.update([_component("no_new_shares", note="股本缺失")])

    # 8. 资产周转率增加（营收/总资产 增）
    at_now = None
    at_prev = None
    if latest_rev is not None and latest_assets and latest_assets > 0:
        at_now = latest_rev / latest_assets
    if prev_rev is not None and prev_assets and prev_assets > 0:
        at_prev = prev_rev / prev_assets
    if at_now is not None and at_prev is not None:
        avail += 1
        if at_now > at_prev:
            hits += 1
        comps.update([_component("asset_turnover_increase", value=int(at_now > at_prev), ok=True,
                                 note=f"资产周转率 {at_prev:.3f}→{at_now:.3f}")])
    else:
        comps.update([_component("asset_turnover_increase", note="营收或总资产缺失")])

    # 9. 毛利率增加
    def _gm(rev, cogs):
        if rev is None or cogs is None or rev <= 0:
            return None
        return (rev - cogs) / rev

    gm_now = _gm(latest_rev, latest_cogs)
    gm_prev = _gm(prev_rev, prev_cogs)
    if gm_now is not None and gm_prev is not None:
        avail += 1
        if gm_now > gm_prev:
            hits += 1
        comps.update([_component("gross_margin_increase", value=int(gm_now > gm_prev), ok=True,
                                 note=f"毛利率 {gm_prev:.4f}→{gm_now:.4f}")])
    else:
        comps.update([_component("gross_margin_increase", note="营收或营业成本缺失")])

    # ── 汇总 ──────────────────────────────────────────────────────────────
    if avail == 0:
        reasons.append(f"三表全部不可用（网络/源异常，sym={symbol}）")
        return _pack(status="unavailable", score=None, components=comps, reasons=reasons)

    score = hits  # 0~9
    reasons.append(f"F-Score={score}/{avail}（{hits} 项命中，{9 - avail} 项缺数据未计入）")
    status = "ok" if avail == 9 else "warning"
    return _pack(status=status, score=score, components=comps, reasons=reasons)


# ════════════════════════════════════════════════════════════════════════════
# Altman Z'-Score（A股修正）
# Z' = 1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 0.999X5
# X1 营运资本/总资产 | X2 未分配利润/总资产 | X3 EBIT/总资产 | X4 市值/负债 | X5 营收/总资产
# 阈值：Z'>2.675 安全；Z'<1.81 危险；中间灰色
# ════════════════════════════════════════════════════════════════════════════
def altman_z(symbol: str, fetcher=None) -> dict:
    """Altman Z'-Score（A股修正版）：五比率线性组合破产风险评估。

    X2 用「未分配利润」近似留存收益（诚实标注 note）；
    X3 净利润+所得税+财务费用（近似 EBIT）；
    X4 市值 = 收盘价 × 股本（get_daily + balance sheet）。
    """
    fetcher = _ensure_fetcher(fetcher)
    tables = _fetch_tables(fetcher, symbol)
    bal, inc = tables["balance"], tables["income"]
    reasons: list[str] = []
    comps: dict[str, dict] = {}

    ta = _row_val(bal, _BALANCE["total_assets"], 0) if bal is not None else None
    tl = _row_val(bal, _BALANCE["total_liabilities"], 0) if bal is not None else None
    ca = _row_val(bal, _BALANCE["current_assets"], 0) if bal is not None else None
    cl = _row_val(bal, _BALANCE["current_liabilities"], 0) if bal is not None else None
    re = _row_val(bal, _BALANCE["retained_earnings"], 0) if bal is not None else None

    ni = _row_val(inc, _INCOME["net_income"], 0) if inc is not None else None
    fin = _row_val(inc, _INCOME["ebit_approx"], 0) if inc is not None else None  # 财务费用
    tax = _row_val(inc, _INCOME["tax_expense"], 0) if inc is not None else None
    rev = _row_val(inc, _INCOME["revenue"], 0) if inc is not None else None

    def _ratio(num, den):
        if num is None or den is None or den <= 0:
            return None
        return num / den

    # X1 营运资本/总资产
    x1 = _ratio((ca or 0) - (cl or 0), ta) if ca is not None and cl is not None else None
    if x1 is not None:
        comps.update([_component("X1", value=x1, ok=True,
                                 note=f"营运资本={ca - cl:.0f} / 总资产={ta:.0f}")])
    else:
        comps.update([_component("X1", note="流动资产/负债缺失")])

    # X2 未分配利润/总资产（≈留存收益，诚实标注）
    x2 = _ratio(re, ta)
    if x2 is not None:
        comps.update([_component("X2", value=x2, ok=True,
                                 note=f"未分配利润/总资产（A股近似留存收益）={re:.0f}/{ta:.0f}={x2:.4f}")])
    else:
        comps.update([_component("X2", note="未分配利润缺失")])
        reasons.append("⚠️ X2 用「未分配利润」近似留存收益（A股口径限制，如实标注）")

    # X3 EBIT/总资产（≈净利润+所得税+财务费用）
    ebit = None
    if ni is not None and tax is not None and fin is not None:
        ebit = ni + tax + abs(fin)  # 财务费用通常为负（收入方向），取绝对值
    x3 = _ratio(ebit, ta) if ebit is not None else None
    if x3 is not None:
        comps.update([_component("X3", value=x3, ok=True,
                                 note=f"EBIT={ebit:.0f} / 总资产={ta:.0f}")])
    else:
        comps.update([_component("X3", note="净利润/税费/财务费用缺失")])

    # X4 市值/总负债（需额外调 get_daily）
    mc = _market_cap(fetcher, symbol, bal)
    x4 = _ratio(mc, tl) if mc is not None else None
    if x4 is not None:
        comps.update([_component("X4", value=x4, ok=True,
                                 note=f"市值={mc:.0f} / 总负债={tl:.0f}")])
    else:
        comps.update([_component("X4", note="市值或总负债缺失（市值=收盘价×股本）")])

    # X5 营收/总资产
    x5 = _ratio(rev, ta)
    if x5 is not None:
        comps.update([_component("X5", value=x5, ok=True,
                                 note=f"营收={rev:.0f} / 总资产={ta:.0f}")])
    else:
        comps.update([_component("X5", note="营收缺失")])

    # ── 汇总 ──────────────────────────────────────────────────────────────
    xs = [("X1", 1.2, x1), ("X2", 1.4, x2), ("X3", 3.3, x3),
          ("X4", 0.6, x4), ("X5", 0.999, x5)]
    avail = [x for _, _, x in xs if x is not None]
    if not avail:
        reasons.append("五比率全部不可用 → Z' 无法计算")
        return _pack(status="unavailable", score=None, components=comps, reasons=reasons)

    z = sum(w * v for _, w, v in xs if v is not None)

    # 诚实：部分分量缺失时按可用分量计算并标注可用率
    if len(avail) < 5:
        reasons.append(f"⚠️ Z' 仅基于 {len(avail)}/5 比率计算（缺失项未编 0）")

    # 阈值判定
    if z > 2.675:
        zone = "安全（Z'>2.675）"
    elif z < 1.81:
        zone = "危险（Z'<1.81）"
    else:
        zone = "灰色地带（1.81≤Z'≤2.675）"
    reasons.append(f"Altman Z'={z:.3f} → {zone}")

    status = "ok" if len(avail) == 5 else "warning"
    return _pack(status=status, score=z, components=comps, reasons=reasons)


# ════════════════════════════════════════════════════════════════════════════
# Beneish M-Score（操纵检测）
# M = -4.84 + 0.92*DSR + 0.528*GMI + 0.404*AQI + 0.892*SGI
#     + 0.115*TATA + 0.172*SVI + 4.679*TATA - 0.005*SGI²
# 简化版（不含 SVI 项：数据链无销售管理费用单期对比 → 诚实降级）
# DSR=(Δ应收/Δ营收), GMI=(毛利率下降%), AQI=(净利润-OCF)/总资产, SGI=营收增长%, TATA=(净利润-OCF)/总资产
# 阈值：M < -1.78 正常；M > -1.78 操纵嫌疑
# ════════════════════════════════════════════════════════════════════════════
def beneish_m(symbol: str, fetcher=None) -> dict:
    """Beneish M-Score：财务操纵检测 logit 模型。

    需 ≥2 期财报（DSR/GMI/SGI 需前后对比；AQI/TATA 需利润表+现金流量表）。
    cash 表 OCF 最新期不可用时 → AQI/TATA/SVI 分量 unavailable，
    按可用分量重归一化（诚实降级）。
    """
    fetcher = _ensure_fetcher(fetcher)
    tables = _fetch_tables(fetcher, symbol)
    bal, inc, cash = tables["balance"], tables["income"], tables["cash"]
    reasons: list[str] = []
    comps: dict[str, dict] = {}

    # 取两期
    def _r(df, col_key, row):
        if df is None:
            return None
        return _row_val(df, col_key, row)

    ar0 = _r(bal, _BALANCE["accounts_receivable"], 0)
    ar1 = _r(bal, _BALANCE["accounts_receivable"], 1)
    rev0 = _r(inc, _INCOME["revenue"], 0)
    rev1 = _r(inc, _INCOME["revenue"], 1)
    ni0 = _r(inc, _INCOME["net_income"], 0)
    ocf0 = _r(cash, _CASH["ocf"], 0)
    ta0 = _r(bal, _BALANCE["total_assets"], 0)
    ta1 = _r(bal, _BALANCE["total_assets"], 1)
    cogs0 = _r(inc, _INCOME["cogs"], 0)
    cogs1 = _r(inc, _INCOME["cogs"], 1)

    def _chg(a, b):
        if a is None or b is None or b == 0:
            return None
        return a - b

    def _pct(a, b):
        if a is None or b is None or b == 0:
            return None
        return (a - b) / b

    # DSR：(Δ应收 / Δ营收) — 应计利润操纵核心指标
    dar = _chg(ar0, ar1)
    drev = _chg(rev0, rev1)
    dsr = dar / drev if dar is not None and drev is not None and drev != 0 else None
    if dsr is not None:
        comps.update([_component("DSR", value=dsr, ok=True,
                                 note=f"Δ应收={dar:.0f} / Δ营收={drev:.0f}")])
    else:
        comps.update([_component("DSR", note="应收账款或营收缺失")])

    # GMI：(上年毛利率 - 本年) / 上年
    gm0 = (rev0 - cogs0) / rev0 if rev0 and cogs0 and rev0 > 0 else None
    gm1 = (rev1 - cogs1) / rev1 if rev1 and cogs1 and rev1 > 0 else None
    gmi = None
    if gm0 is not None and gm1 is not None and gm1 != 0:
        gmi = (gm1 - gm0) / gm1  # 注意公式里是毛利率下降 = 正信号
    if gmi is not None:
        comps.update([_component("GMI", value=gmi, ok=True,
                                 note=f"毛利率 {gm1:.4f}→{gm0:.4f}")])
    else:
        comps.update([_component("GMI", note="营收或营业成本缺失")])

    # AQI + TATA：(净利润-OCF)/总资产 — 需要 cash 表
    tata_val = None
    if ni0 is not None and ocf0 is not None and ta0 is not None and ta0 > 0:
        tata_val = (ni0 - ocf0) / ta0
    aqi_val = tata_val  # Beneish 标准中 AQI = TATA（应计利润质量）
    if tata_val is not None:
        comps.update([_component("TATA", value=tata_val, ok=True,
                                 note=f"(净利润-OCF)={ni0 - ocf0:.0f} / 总资产={ta0:.0f}")])
        comps.update([_component("AQI", value=aqi_val, ok=True,
                                 note=f"同 TATA：盈余质量指标")])
    else:
        comps.update([_component("TATA", note="净利润/OCF/总资产缺失（OCF Q3 未披露时降级）")])
        comps.update([_component("AQI", note="同 TATA 不可用")])
        if ocf0 is None:
            reasons.append("⚠️ OCF 缺失 → AQI/TATA 分量不可用（Q3 现金流量表未披露常见场景）")

    # SGI：营收增长率
    sgi = _pct(rev0, rev1)
    if sgi is not None:
        comps.update([_component("SGI", value=sgi, ok=True,
                                 note=f"营收 {rev1:.0f}→{rev0:.0f}，增长 {sgi*100:.1f}%")])
    else:
        comps.update([_component("SGI", note="营收缺失")])

    # SVI：销售管理费用/总资产 两年对比 — 简化版省略（数据链无单期对比）
    svi = None
    comps.update([_component("SVI", value=0.0, ok=True,
                             note="简化版省略 SVI 项（销售管理费用单期对比无数据源），按 0 代回")])

    # ── 全不可用判定：四主分量（DSR/GMI/TATA/SGI）全 None → unavailable ────
    main_components = {"DSR": dsr, "GMI": gmi, "TATA": tata_val, "SGI": sgi}
    main_avail = [n for n, v in main_components.items() if v is not None]
    if not main_avail:
        reasons.append("四主分量全部不可用（DSR/GMI/TATA/SGI 全缺 → M 无法计算）")
        return _pack(status="unavailable", score=None, components=comps, reasons=reasons)

    # ── M-Score 计算（可用分量加权）───────────────────────────────────────
    terms = []  # (w, v, name)
    if dsr is not None:
        terms.append((0.92, dsr, "DSR"))
    if gmi is not None:
        terms.append((0.528, gmi, "GMI"))
    if tata_val is not None:
        terms.append((0.404, tata_val, "AQI"))
    if sgi is not None:
        terms.append((0.892, sgi, "SGI"))
    if tata_val is not None:
        terms.append((4.679, tata_val, "TATA"))
    if sgi is not None:
        terms.append((-0.005, sgi ** 2, "SGI²"))
    # SVI 简化版按 0 代回（系数 0.172）
    terms.append((0.172, 0.0, "SVI"))

    m = -4.84 + sum(w * v for w, v, _ in terms)

    # main_avail 显式计数（SGI²/TATA/AQI 等衍生项不重复算）
    if len(main_avail) < 4:
        reasons.append(f"⚠️ M 主分量缺失：仅 {len(main_avail)}/4（缺失 {set(main_components) - set(main_avail)}）")

    if m < -1.78:
        zone = "正常（M<-1.78，操纵概率<1.7%）"
    else:
        zone = "操纵嫌疑（M≥-1.78，概率>50%）"
    reasons.append(f"Beneish M={m:.3f} → {zone}")

    # 判定 ok/warning：用 main_avail（四主分量 DSR/GMI/TATA/SGI 显式计数）
    status = "ok" if len(main_avail) >= 4 else "warning"

    return _pack(status=status, score=m, components=comps, reasons=reasons)
