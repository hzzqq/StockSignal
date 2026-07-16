"""
页面 E：基本面分析
───────────────
个股综合基本面视图：
- 同业/板块横向对比
- 历史走势纵向对比（股价所处历史分位）
- 是否大盘主线（行业排名）
- 估值、市值、综合评分
- 【Batch8 #277 重写】业绩分析：营收 / 净利润 / 同比 / ROE / 毛利率 / 资产负债率 / 流动比率
  （结合市值、市盈率、资产负债表等数据，给出看得懂的解读）

数据以现有 StockFetcher 为主，缺失时降级展示，避免页面崩溃。
"""
import contextlib
import requests
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, safe_switch_page
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input
from modules.visualizer import UP_COLOR, DOWN_COLOR

apply_page_config(page_title="基本面分析", page_icon="🏛️", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🏛️ 基本面分析")
st.caption("个股估值、业绩、历史位置、行业横向对比与大盘主线判断（仅供参考，非投资建议）")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


# ═══════════════════════════════════════════════════════════════
# 财务报表解析（Batch8 #277）：业绩核心指标
# ═══════════════════════════════════════════════════════════════
@contextlib.contextmanager
def _ssl_bypass():
    """临时关闭 requests 的 SSL 校验（代理环境新浪财务报表直连证书链不可达）。"""
    import urllib3
    urllib3.disable_warnings()
    _orig = requests.Session.request

    def _patched(self, *a, **kw):
        kw["verify"] = False
        return _orig(self, *a, **kw)

    requests.Session.request = _patched
    try:
        yield
    finally:
        requests.Session.request = _orig


def _to_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("%", "").strip()
        if s in ("", "-", "--", "nan", "None"):
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _find_col(df, exact, suffixes):
    for c in df.columns:
        if str(c) in exact:
            return c
    for c in df.columns:
        for s in suffixes:
            if str(c).endswith(s):
                return c
    return None


@st.cache_data(show_spinner=False, ttl=1800)
def _calc_perf(code: str) -> dict:
    """解析利润表 + 资产负债表，返回业绩核心指标（单位已折算为易读形式）。

    返回字段：revenue_yi(营收亿元), revenue_yoy, net_profit_yi(净利润亿元),
    profit_yoy, gross_margin(毛利率%), roe(净资产收益率%), alr(资产负债率%),
    current_ratio(流动比率), equity_ratio(权益比率%)。任一缺失为 None。
    """
    out = {}
    inc_df = bal_df = None
    with _ssl_bypass():
        try:
            inc_df = fetcher.get_financial(code, "income")
        except Exception:
            inc_df = None
        try:
            bal_df = fetcher.get_financial(code, "balance")
        except Exception:
            bal_df = None

    # ── 利润表 ──
    if inc_df is not None and len(inc_df) >= 1:
        rev_c = _find_col(inc_df, {"营业总收入", "营业收入"}, ("营业总收入", "营业收入"))
        np_c = _find_col(inc_df, {"净利润", "归属母公司股东的净利润"}, ("净利润", "归属母公司股东的净利润"))
        cost_c = _find_col(inc_df, {"营业成本"}, ("营业成本",))
        r0 = inc_df.iloc[0]
        r1 = inc_df.iloc[1] if len(inc_df) >= 2 else None
        rev0 = _to_num(r0[rev_c]) if rev_c else None
        np0 = _to_num(r0[np_c]) if np_c else None
        cost0 = _to_num(r0[cost_c]) if cost_c else None
        rev1 = _to_num(r1[rev_c]) if (r1 is not None and rev_c) else None
        np1 = _to_num(r1[np_c]) if (r1 is not None and np_c) else None
        if rev0:
            out["revenue_yi"] = round(rev0 / 1e8, 2)
        if rev0 and rev1:
            out["revenue_yoy"] = round((rev0 - rev1) / abs(rev1) * 100, 2)
        if np0 is not None:
            out["net_profit_yi"] = round(np0 / 1e8, 2)
        if np0 is not None and np1 is not None and np1 != 0:
            out["profit_yoy"] = round((np0 - np1) / abs(np1) * 100, 2)
        if rev0 and cost0:
            out["gross_margin"] = round((rev0 - cost0) / rev0 * 100, 2)
        out["_np0"] = np0  # 原始元，供 ROE 计算

    # ── 资产负债表 ──
    if bal_df is not None and len(bal_df) >= 1:
        asset_c = _find_col(bal_df, {"资产总计", "资产合计"}, ("资产总计", "资产合计"))
        liab_c = _find_col(bal_df, {"负债合计", "负债总计"}, ("负债合计", "负债总计"))
        equity_c = _find_col(bal_df, {"所有者权益合计", "股东权益合计"}, ("所有者权益合计", "股东权益合计"))
        ca_c = _find_col(bal_df, {"流动资产合计"}, ("流动资产合计",))
        cl_c = _find_col(bal_df, {"流动负债合计"}, ("流动负债合计",))
        b0 = bal_df.iloc[0]
        av = _to_num(b0[asset_c]) if asset_c else None
        lv = _to_num(b0[liab_c]) if liab_c else None
        eq = _to_num(b0[equity_c]) if equity_c else None
        ca = _to_num(b0[ca_c]) if ca_c else None
        cl = _to_num(b0[cl_c]) if cl_c else None
        if av and lv:
            out["alr"] = round(lv / av * 100, 2)
        if av and eq:
            out["equity_ratio"] = round(eq / av * 100, 2)
        if ca and cl:
            out["current_ratio"] = round(ca / cl, 2)
        out["_eq0"] = eq  # 原始元，供 ROE 计算

    # ── ROE = 净利润 / 净资产 ──
    if out.get("_np0") is not None and out.get("_eq0"):
        out["roe"] = round(out["_np0"] / abs(out["_eq0"]) * 100, 2)
    return out


@st.cache_data(show_spinner=False, ttl=1800)
def _cached_daily(code: str, start: str, end: str):
    try:
        return fetcher.get_daily(code, start=start, end=end)
    except Exception:
        return None


def _to_float(x):
    try:
        return float(x) if x not in (None, "", "—") else None
    except Exception:
        return None


def _percentile(series: pd.Series, value: float) -> float | None:
    """计算 value 在 series 中的百分位（0-100）。"""
    if series is None or series.empty or value is None:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return float(np.clip((s <= value).mean() * 100, 0, 100))


def _pe_status(pe: float | None) -> str:
    if pe is None or pe <= 0:
        return "—"
    if pe < 15:
        return "低估区间"
    if pe < 30:
        return "合理区间"
    if pe < 50:
        return "偏高区间"
    return "高估区间"


def _tag(text: str, level: str) -> str:
    """语义化彩色标签：good/warn/bad/neu（仅用于基本面「好/坏」语义，非价格涨跌色）。"""
    colors = {"good": "#16a34a", "warn": "#d97706", "bad": "#dc2626", "neu": "#6b7280"}
    c = colors.get(level, "#6b7280")
    return (f'<span style="display:inline-block;font-size:12px;font-weight:600;'
            f'padding:2px 9px;border-radius:12px;background:{c}1a;color:{c};'
            f'border:1px solid {c}55;">{text}</span>')


def _sector_rank(sector_df: pd.DataFrame, industry: str) -> int | None:
    if sector_df is None or sector_df.empty or not industry:
        return None
    df = sector_df.copy()
    df["change_pct"] = pd.to_numeric(df.get("change_pct", 0), errors="coerce").fillna(0)
    df = df.sort_values("change_pct", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    hits = df[df["sector"].astype(str).str.contains(industry, na=False)]
    if not hits.empty:
        return int(hits.iloc[0]["rank"])
    return None


def _composite_score(
    price, pe, hist_pct_5y, sector_rank, sector_total, market_cap, perf
) -> tuple[int, str]:
    """返回 0-100 的综合评分与解读文本（Batch8 #277：新增盈利成长 + 偿债安全维度）。"""
    reasons = []
    perf = perf or {}
    # 1) 估值合理性(PE) 20 分
    pe_score = 10.0
    if pe is not None and pe > 0:
        if pe < 15:
            pe_score = 18.0
            reasons.append(f"✅ PE(TTM) {pe:.1f} 处于低估区间，安全边际较高")
        elif pe < 30:
            pe_score = 15.0
            reasons.append(f"✅ PE(TTM) {pe:.1f} 估值合理")
        elif pe < 50:
            pe_score = 8.0
            reasons.append(f"⚠️ PE(TTM) {pe:.1f} 估值偏高，需业绩支撑")
        else:
            pe_score = 3.0
            reasons.append(f"❌ PE(TTM) {pe:.1f} 估值偏高，注意回撤风险")
    else:
        reasons.append("ℹ️ 暂无有效 PE 数据")

    # 2) 历史位置 15 分
    hist_score = 7.5
    if hist_pct_5y is not None:
        if 40 <= hist_pct_5y <= 75:
            hist_score = 13.0
            reasons.append(f"✅ 5年价格分位 {hist_pct_5y:.1f}%，处于健康区间")
        elif hist_pct_5y < 20:
            hist_score = 9.0
            reasons.append(f"⚠️ 5年价格分位 {hist_pct_5y:.1f}%，处于历史低位（偏弱或超跌）")
        elif hist_pct_5y > 90:
            hist_score = 5.0
            reasons.append(f"⚠️ 5年价格分位 {hist_pct_5y:.1f}%，接近历史高位")
        else:
            hist_score = 10.0
            reasons.append(f"ℹ️ 5年价格分位 {hist_pct_5y:.1f}%")
    else:
        reasons.append("ℹ️ 暂无历史位置数据")

    # 3) 行业动能 20 分
    theme_score = 10.0
    if sector_rank is not None and sector_total > 0:
        if sector_rank <= 5:
            theme_score = 18.0
            reasons.append(f"✅ 行业排名 #{sector_rank} / {sector_total}，位于主线前列")
        elif sector_rank <= 20:
            theme_score = 14.0
            reasons.append(f"✅ 行业排名 #{sector_rank} / {sector_total}，动能较好")
        elif sector_rank <= sector_total * 0.5:
            theme_score = 10.0
            reasons.append(f"ℹ️ 行业排名 #{sector_rank} / {sector_total}，中等水平")
        else:
            theme_score = 5.0
            reasons.append(f"⚠️ 行业排名 #{sector_rank} / {sector_total}，相对落后")
    else:
        reasons.append("ℹ️ 暂无行业排名数据")

    # 4) 市值规模 15 分
    cap_score = 7.5
    if market_cap is not None and market_cap > 0:
        if market_cap >= 1000:
            cap_score = 13.0
            reasons.append(f"✅ 总市值 {market_cap:.1f} 亿，大盘蓝筹，抗风险强")
        elif market_cap >= 300:
            cap_score = 11.0
            reasons.append(f"✅ 总市值 {market_cap:.1f} 亿，中大盘")
        elif market_cap >= 50:
            cap_score = 8.0
            reasons.append(f"ℹ️ 总市值 {market_cap:.1f} 亿，中小盘")
        else:
            cap_score = 5.0
            reasons.append(f"⚠️ 总市值 {market_cap:.1f} 亿，小盘股波动大")
    else:
        reasons.append("ℹ️ 暂无市值数据")

    # 5) 盈利成长 20 分（结合营收/净利润同比）
    growth_score = 10.0
    rev_yoy = perf.get("revenue_yoy")
    pr_yoy = perf.get("profit_yoy")
    if rev_yoy is not None and pr_yoy is not None:
        if rev_yoy > 0 and pr_yoy > 0:
            growth_score = 18.0
            reasons.append(f"✅ 营收同比 +{rev_yoy:.1f}%、净利润同比 +{pr_yoy:.1f}%，业绩双增")
        elif rev_yoy > 0:
            growth_score = 13.0
            reasons.append(f"ℹ️ 营收同比 +{rev_yoy:.1f}%，但净利润同比 {pr_yoy:.1f}%")
        elif pr_yoy > 0:
            growth_score = 12.0
            reasons.append(f"⚠️ 营收同比 {rev_yoy:.1f}%，净利润同比 +{pr_yoy:.1f}%")
        else:
            growth_score = 5.0
            reasons.append(f"❌ 营收同比 {rev_yoy:.1f}%、净利润同比 {pr_yoy:.1f}%，业绩承压")
    elif rev_yoy is not None:
        growth_score = 12.0 if rev_yoy > 0 else 7.0
        reasons.append(f"ℹ️ 营收同比 {rev_yoy:+.1f}%（净利润同比暂无）")
    else:
        reasons.append("ℹ️ 暂无业绩同比数据")

    # 6) 偿债安全 10 分（资产负债率 + 流动比率）
    safe_score = 5.0
    alr = perf.get("alr")
    cr = perf.get("current_ratio")
    if alr is not None:
        if alr < 40:
            safe_score += 3.0
            reasons.append(f"✅ 资产负债率 {alr:.1f}%，偿债压力低")
        elif alr < 60:
            safe_score += 2.0
            reasons.append(f"ℹ️ 资产负债率 {alr:.1f}%，处于适中水平")
        else:
            safe_score += 0.0
            reasons.append(f"⚠️ 资产负债率 {alr:.1f}%，偏高，关注杠杆风险")
    if cr is not None:
        if cr >= 1.5:
            safe_score += 2.0
            reasons.append(f"✅ 流动比率 {cr:.2f}，短期偿债能力较强")
        elif cr >= 1:
            safe_score += 1.0
            reasons.append(f"ℹ️ 流动比率 {cr:.2f}，处于临界水平")
        else:
            safe_score += 0.0
            reasons.append(f"⚠️ 流动比率 {cr:.2f}，短期偿债偏紧")

    score = pe_score + hist_score + theme_score + cap_score + growth_score + safe_score
    score = int(round(np.clip(score, 0, 100)))
    return score, "<br>".join(reasons)


# ═══════════════════════════════════════════════════
# 选股
# ═══════════════════════════════════════════════════
picked = stock_search_input(
    label="选择股票",
    key="fa_stock",
    default="600519",
)
code = str(picked or "600519").zfill(6)

if code:
    # ═══════════════════════════════════════════════
    # 数据加载
    # ═══════════════════════════════════════════════
    with st.spinner("正在加载基本面数据…"):
        fund = fetcher.get_fundamentals(code) or {}
        name = fund.get("name") or code
        industry = (fund.get("industry") or "").strip() or "—"
        price = _to_float(fund.get("price"))
        pe_ttm = _to_float(fund.get("pe_ttm"))
        market_cap = _to_float(fund.get("market_cap"))

        # 业绩核心指标（利润表 + 资产负债表，含 SSL 旁路与缓存）
        try:
            perf = _calc_perf(code)
        except Exception:
            perf = {}

        end = datetime.now().date()
        start_5y = (end - timedelta(days=365 * 5 + 30)).strftime("%Y-%m-%d")
        try:
            hist_df = _cached_daily(code, start=start_5y, end=end.strftime("%Y-%m-%d"))
            if hist_df is not None and not hist_df.empty:
                hist_df = hist_df.copy()
                hist_df["close"] = pd.to_numeric(hist_df["close"], errors="coerce")
                hist_df = hist_df.dropna(subset=["close"]).reset_index(drop=True)
            else:
                hist_df = None
        except Exception:
            hist_df = None

        try:
            sector_df = fetcher.get_sector_list()
            if sector_df is None or sector_df.empty:
                sector_df = pd.DataFrame()
            else:
                sector_df = sector_df.copy()
                sector_df["change_pct"] = pd.to_numeric(sector_df.get("change_pct", 0), errors="coerce").fillna(0)
        except Exception:
            sector_df = pd.DataFrame()

    # ═══════════════════════════════════════════════
    # 概览卡片
    # ═══════════════════════════════════════════════
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("股票", f"{name}")
    with c2:
        st.metric("代码", code)
    with c3:
        st.metric("所属行业", industry)
    with c4:
        st.metric("最新价", f"¥{price:.2f}" if price else "—")
    with c5:
        st.metric("总市值", f"¥{market_cap:.1f}亿" if market_cap else "—",
                  help="公司总资产规模（单位：亿元人民币）；越大通常越稳健")

    # ═══════════════════════════════════════════════
    # 业绩分析（Batch8 #277 新增）
    # ═══════════════════════════════════════════════
    st.markdown("---")
    st.subheader("💹 业绩分析（结合市值 / 市盈率 / 资产负债表）")
    st.caption("读懂指标：营收/净利润看公司「赚多少、增长快不快」；ROE 看「股东每投 1 元赚回多少」；"
               "毛利率看「产品赚钱能力」；资产负债率/流动比率看「会不会还不起钱」。")

    rev_yoy = perf.get("revenue_yoy")
    pr_yoy = perf.get("profit_yoy")
    roe = perf.get("roe")
    gm = perf.get("gross_margin")
    alr = perf.get("alr")
    cr = perf.get("current_ratio")

    pc1, pc2, pc3, pc4 = st.columns(4)
    with pc1:
        st.metric("营业收入", f"{perf.get('revenue_yi', '—')} 亿",
                  delta=f"{rev_yoy:+.1f}%" if rev_yoy is not None else None,
                  delta_color="normal",
                  help="公司一定时期内的主营业务收入（单位：亿元）；同比>0 表示扩张")
        if rev_yoy is not None:
            st.markdown(_tag("营收同比 " + (f"+{rev_yoy:.1f}%" if rev_yoy >= 0 else f"{rev_yoy:.1f}%"),
                              "good" if rev_yoy >= 0 else "bad"), unsafe_allow_html=True)
    with pc2:
        st.metric("净利润", f"{perf.get('net_profit_yi', '—')} 亿",
                  delta=f"{pr_yoy:+.1f}%" if pr_yoy is not None else None,
                  delta_color="normal",
                  help="归属母公司股东的净利润（单位：亿元）；衡量公司真正赚到的钱")
        if pr_yoy is not None:
            st.markdown(_tag("净利同比 " + (f"+{pr_yoy:.1f}%" if pr_yoy >= 0 else f"{pr_yoy:.1f}%"),
                              "good" if pr_yoy >= 0 else "bad"), unsafe_allow_html=True)
    with pc3:
        st.metric("ROE（净资产收益率）", f"{roe:.2f}%" if roe is not None else "—",
                  help="净利润 / 净资产 ×100；反映股东投入的回报率，通常 >15% 较优")
        if roe is not None:
            st.markdown(_tag("盈利能力 " + ("强" if roe >= 15 else ("中" if roe >= 8 else "弱")),
                              "good" if roe >= 15 else ("warn" if roe >= 8 else "bad")), unsafe_allow_html=True)
    with pc4:
        st.metric("毛利率", f"{gm:.2f}%" if gm is not None else "—",
                  help="(营收-营业成本)/营收 ×100；越高说明产品溢价/成本控制越好")

    pc5, pc6 = st.columns(2)
    with pc5:
        st.metric("资产负债率", f"{alr:.2f}%" if alr is not None else "—",
                  help="总负债 / 总资产 ×100；越低偿债压力越小，但过低也可能杠杆利用不足")
        if alr is not None:
            st.markdown(_tag("偿债压力 " + ("低" if alr < 40 else ("中" if alr < 60 else "高")),
                              "good" if alr < 40 else ("warn" if alr < 60 else "bad")), unsafe_allow_html=True)
    with pc6:
        st.metric("流动比率", f"{cr:.2f}" if cr is not None else "—",
                  help="流动资产 / 流动负债；≥1.5 短期偿债能力较稳健，<1 偏紧")

    # 一句话业绩解读
    _perf_lines = []
    if rev_yoy is not None and pr_yoy is not None:
        if rev_yoy > 0 and pr_yoy > 0:
            _perf_lines.append(f"公司处于**扩张期**：营收同比 +{rev_yoy:.1f}%、净利润同比 +{pr_yoy:.1f}%，挣钱速度在加快。")
        elif rev_yoy > 0 and pr_yoy <= 0:
            _perf_lines.append(f"营收在涨（+{rev_yoy:.1f}%）但净利润下滑（{pr_yoy:.1f}%），可能存在「增收不增利」（成本上升或降价）。")
        elif rev_yoy <= 0 and pr_yoy > 0:
            _perf_lines.append(f"营收承压（{rev_yoy:.1f}%）但净利润反而增长（+{pr_yoy:.1f}%），降本增效或产品结构优化。")
        else:
            _perf_lines.append(f"营收（{rev_yoy:.1f}%）与净利润（{pr_yoy:.1f}%）双双下滑，业绩面临压力。")
    if roe is not None:
        _perf_lines.append(f"ROE {roe:.2f}%，股东回报率{'优秀' if roe >= 15 else ('一般' if roe >= 8 else '偏弱')}。")
    if alr is not None:
        _perf_lines.append(f"资产负债率 {alr:.2f}%，财务杠杆{'稳健' if alr < 40 else ('适中' if alr < 60 else '偏高')}。")
    if _perf_lines:
        st.info("📌 **一句话业绩解读**：" + " ".join(_perf_lines))
    else:
        st.info("ℹ️ 暂未获取到财报数据，业绩解读不可用（可检查网络或切换数据源）。")

    # ═══════════════════════════════════════════════
    # 历史位置（纵向对比）
    # ═══════════════════════════════════════════════
    st.markdown("---")
    st.subheader("📍 历史位置 · 纵向对比")
    st.caption("价格分位：当前价在对应周期内所有交易日收盘价中的相对高低。")
    with st.expander("📖 分位解读（数值越高代表当前价越贵）", expanded=False):
        st.info(
            "📌 **分位解读**（数值越高代表当前价越贵）：\n\n"
            "- **0%**：历史最低（最便宜）\n"
            "- **0–20%**：历史低位（相对便宜，可能超跌）\n"
            "- **20–40%**：偏低区间\n"
            "- **40–75%**：合理中枢（不贵也不便宜）\n"
            "- **75–90%**：偏高区间\n"
            "- **90–100%**：历史高位（相对较贵，注意风险）\n"
            "- **100%**：历史最高（最贵）\n\n"
            "💡 **例子**：若 5 年分位为 7.9%，表示当前价只比过去 5 年里约 8% 的交易日收盘价高，"
            "处于历史较低位置。"
        )
    if hist_df is not None and not hist_df.empty:
        current = float(hist_df["close"].iloc[-1])
        p_1y = _percentile(hist_df.tail(252)["close"], current) if len(hist_df) >= 60 else None
        p_3y = _percentile(hist_df.tail(756)["close"], current) if len(hist_df) >= 400 else None
        p_5y = _percentile(hist_df["close"], current)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("当前价", f"¥{current:.2f}")
        m2.metric("1年价格分位", f"{p_1y:.1f}%" if p_1y is not None else "—")
        m3.metric("3年价格分位", f"{p_3y:.1f}%" if p_3y is not None else "—")
        m4.metric("5年价格分位", f"{p_5y:.1f}%" if p_5y is not None else "—")

        fig_hist = go.Figure()
        fig_hist.add_trace(
            go.Scatter(
                x=hist_df["date"],
                y=hist_df["close"],
                mode="lines",
                name="收盘价",
                line=dict(color="#6366f1", width=1.4),
                fill="tozeroy",
                fillcolor="rgba(99,102,241,0.10)",
            )
        )
        fig_hist.add_hline(
            y=current,
            line=dict(color=UP_COLOR, dash="dash", width=1.5),
            annotation_text="当前价",
            annotation_position="top right",
        )
        fig_hist.update_layout(
            title=f"{name} 近5年走势与当前位置",
            xaxis_title="",
            yaxis_title="收盘价",
            height=360,
            margin=dict(l=40, r=40, t=40, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("暂无历史行情数据，无法计算历史分位。")

    # ═══════════════════════════════════════════════
    # 行业横向对比
    # ═══════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🏭 行业横向对比")
    if not sector_df.empty and industry != "—":
        top_n = 15
        top_sectors = sector_df.sort_values("change_pct", ascending=False).head(top_n).copy()
        bar_colors = [
            UP_COLOR if str(row["sector"]) == industry or industry in str(row["sector"]) else (DOWN_COLOR if row["change_pct"] < 0 else "#94a3b8")
            for _, row in top_sectors.iterrows()
        ]

        fig_sector = go.Figure()
        fig_sector.add_trace(
            go.Bar(
                x=top_sectors["sector"],
                y=top_sectors["change_pct"],
                marker_color=bar_colors,
                text=[f"{v:+.2f}%" for v in top_sectors["change_pct"]],
                textposition="outside",
            )
        )
        fig_sector.update_layout(
            title=f"行业涨跌幅 Top {top_n}（{industry} 高亮显示）",
            xaxis_tickangle=-45,
            yaxis_title="涨跌幅 %",
            height=420,
            margin=dict(l=40, r=20, t=50, b=100),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_sector, use_container_width=True)

        sector_row = sector_df[sector_df["sector"].astype(str).str.contains(industry, na=False)]
        if not sector_row.empty:
            sector_chg = float(sector_row.iloc[0]["change_pct"])
            avg_chg = float(sector_df["change_pct"].mean())
            delta = sector_chg - avg_chg
            sc1, sc2 = st.columns(2)
            with sc1:
                st.metric(f"{industry} 今日涨跌", f"{sector_chg:+.2f}%")
            with sc2:
                st.metric("相对全市场平均", f"{delta:+.2f}%", delta=f"{delta:+.2f}%",
                          help="当前行业涨跌幅减去全市场行业均值；>0 表示强于大盘")
        else:
            st.info("未在行业列表中精确匹配到当前股票行业。")
    else:
        st.info("暂无行业数据，无法横向对比。")

    # ═══════════════════════════════════════════════
    # 大盘主线判断
    # ═══════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🚩 大盘主线判断")
    rank = _sector_rank(sector_df, industry) if industry != "—" else None
    sector_total = len(sector_df) if not sector_df.empty else 0

    if rank is not None and sector_total > 0:
        is_main = rank <= 5
        main_html = (
            f'<div style="padding:14px 18px;border-radius:10px;'
            f'background:rgba(16,185,129,0.12);border-left:4px solid {UP_COLOR};'
            f'color:{"#e2e8f0" if dark else "#064e3b"};font-size:15px;">'
            f'✅ <b>{industry}</b> 今日行业排名 <b>#{rank} / {sector_total}</b>，'
            f'处于市场主线前列，资金关注度较高。</div>'
        ) if is_main else (
            f'<div style="padding:14px 18px;border-radius:10px;'
            f'background:rgba(245,158,11,0.12);border-left:4px solid #f59e0b;'
            f'color:{"#e2e8f0" if dark else "#78350f"};font-size:15px;">'
            f'⚠️ <b>{industry}</b> 今日行业排名 <b>#{rank} / {sector_total}</b>，'
            f'暂未进入主线 Top5，建议结合题材与资金面综合判断。</div>'
        )
        st.markdown(main_html, unsafe_allow_html=True)

        with st.expander("查看行业排名 Top10", expanded=False):
            top10 = sector_df.sort_values("change_pct", ascending=False).head(10).reset_index(drop=True)
            top10["排名"] = top10.index + 1
            display = top10[["排名", "sector", "change_pct"]].rename(
                columns={"sector": "行业", "change_pct": "涨跌幅"}
            )
            st.dataframe(
                display,
                use_container_width=True,
                column_config={"涨跌幅": st.column_config.NumberColumn(format="%.2f%%")},
                hide_index=True,
            )
    else:
        st.info("暂无行业排名，无法判断主线地位。")

    # ═══════════════════════════════════════════════
    # 综合评估
    # ═══════════════════════════════════════════════
    st.markdown("---")
    st.subheader("🎯 综合评估")
    score, reasons_html = _composite_score(
        price, pe_ttm, p_5y if hist_df is not None else None,
        rank, sector_total, market_cap, perf,
    )

    if score >= 75:
        score_color = UP_COLOR
        score_label = "较强"
    elif score >= 50:
        score_color = "#f59e0b"
        score_label = "中等"
    else:
        score_color = DOWN_COLOR
        score_label = "偏弱"

    sc1, sc2 = st.columns([0.25, 0.75])
    with sc1:
        st.markdown(
            f'<div style="text-align:center;padding:20px 10px;border-radius:12px;'
            f'background:{"rgba(26,26,46,0.6)" if dark else "#f3f4f6"};'
            f'border:1px solid {"rgba(255,255,255,0.08)" if dark else "#e5e7eb"};">'
            f'<div style="font-size:13px;opacity:.8;">综合评分</div>'
            f'<div style="font-size:48px;font-weight:800;color:{score_color};">{score}</div>'
            f'<div style="font-size:14px;color:{score_color};font-weight:600;">{score_label}</div></div>',
            unsafe_allow_html=True,
        )
    with sc2:
        st.markdown(
            f'<div style="padding:14px 18px;border-radius:10px;'
            f'background:{"rgba(26,26,46,0.4)" if dark else "#f9fafb"};'
            f'border:1px solid {"rgba(255,255,255,0.08)" if dark else "#e5e7eb"};'
            f'font-size:14px;line-height:1.8;">{reasons_html}</div>',
            unsafe_allow_html=True,
        )

    # 估值摘要
    st.markdown("---")
    st.subheader("📊 估值摘要")
    v1, v2, v3 = st.columns(3)
    with v1:
        st.metric("PE(TTM)", f"{pe_ttm:.2f}" if pe_ttm else "—",
                  help="市盈率 = 股价 / 每股收益；越低通常代表估值越低（但需结合成长性）")
    with v2:
        st.metric("PE 状态", _pe_status(pe_ttm),
                  help="根据 PE 粗略划分低估/合理/偏高区间，仅供参考")
    with v3:
        st.metric("总市值", f"¥{market_cap:.1f}亿" if market_cap else "—",
                  help="单位：亿元人民币")

    # 个股跳转
    st.markdown("---")
    if st.button("🔍 查看该股票详细 K 线与技术面 →", type="primary", use_container_width=True):
        st.query_params["pick_stock"] = code
        safe_switch_page("pages/1_股票选取.py")
else:
    st.info("请在上方选择一只股票开始分析。")
