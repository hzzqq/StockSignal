"""
页面：智能选股（策略库）
移植自 stock-selecter skill 的 11 种策略（ROE/高股息/低估值/费雪成长/长期低位/
近期放量/趋势/形态/布林带下轨/筹码集中/现金流质量/MACD底背离），
数据源切换为 StockSignal 自带 fetcher + akshare，支持单策略与多策略 AND/OR/SCORE 组合。

数据说明：
- 技术面 6 策略（macd/trend/bollinger/volume_surge/low_position/pattern）仅依赖行情数据，
  速度快、可全市场扫描。
- 基本面 5 策略（roe/dividend/valuation/growth/cashflow_quality/shareholder_concentration）
  依赖 akshare 财务接口，扫描需联网且较慢，建议用于「自选股 / 板块」小池。
"""
import pandas as pd
import streamlit as st
from datetime import datetime

from modules.page_utils import render_standard_page
from modules.session import api_get, get_user_setting, save_user_setting
from modules.fetcher import StockFetcher
from modules.stock_screener import StockScreener, STRATEGY_NAMES_CN, ALL_STRATEGIES, DEFAULT_PARAMS
from modules.page_widgets import _empty_info

dark = render_standard_page(
    title="智能选股", icon="🎯",
    caption="移植自 stock-selecter 策略库：11 种量化策略，支持单策略与多策略 AND/OR/综合评分组合。结果仅供参考，非投资建议。",
)

STRATEGY_DESC = {
    "roe": "净资产收益率≥阈值且 ROA 健康、毛利率高、负债率低的优质盈利股",
    "macd": "周线下跌 + MACD 底背离 + 放量反转的抄底信号",
    "dividend": "高股息率 + 连续分红 + ROE 支撑的红利股",
    "valuation": "低 PE/PB/PEG + 相对行业折价 + 高 ROE 的低估绩优股",
    "growth": "营收/利润高增 + 高毛利 + ROE 强 + 连续环比增长的费雪成长股",
    "low_position": "价格处于历史低位区间 + RSI 超卖的布局区",
    "volume_surge": "异常放量 + RSI 不高 + 底部反弹的启动信号",
    "trend": "均线多头排列 + 线性趋势强 + ADX 高的一目了然强势股",
    "pattern": "金叉/看涨吞没/早晨之星/双底/头肩底/杯柄/旗形突破等 K 线形态",
    "bollinger": "股价触及布林带下轨 + RSI 超卖的反弹博弈点",
    "shareholder_concentration": "股东户数连续减少（筹码集中）+ ROE 支撑",
    "cashflow_quality": "经营现金流持续高于净利润（盈利质量过硬）+ 商誉排雷",
}
TECH = {"macd", "trend", "bollinger", "volume_surge", "low_position", "pattern"}


def _section_title(text, accent="#5b6cff"):
    st.markdown(
        f"<div style='display:inline-block;background:{accent};color:#fff;"
        f"padding:4px 12px;border-radius:8px;font-weight:600;font-size:14px;'"
        f">{text}</div>", unsafe_allow_html=True)


st.markdown("""
<style>
button[data-testid="stBaseButton-primary"] {
    box-shadow: 0 1px 3px rgba(0,0,0,0.18);
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
button[data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(0,0,0,0.22);
}
.stMultiSelect [data-baseweb=tag] { max-width: 160px; }
</style>
""", unsafe_allow_html=True)

fetcher = StockFetcher()
screener = StockScreener()

# ───────────────────────── 股票池来源 ─────────────────────────
with st.container(border=True):
    _section_title("📂 股票池来源")
    source = st.radio("股票池来源", ["我的自选股", "指定板块", "全市场前 N 只"],
                      horizontal=True, label_visibility="collapsed")
    universe_codes, sector_name, limit_n = None, None, 250
    if source == "我的自选股":
        sc, body = api_get("/api/watchlist", timeout=10)
        if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
            universe_codes = [str(w.get("stock_code")).strip().zfill(6)
                              for w in (body.get("data", []) or []) if isinstance(w, dict) and w.get("stock_code")]
            if universe_codes:
                st.caption(f"✅ 已从自选股加载 **{len(universe_codes)}** 只")
            else:
                st.warning("自选股为空，请先到「我的 / 自选股」添加，或切换其它来源。")
        else:
            st.error("❌ 加载自选股失败，可切换为「全市场前 N 只」继续。")
    elif source == "指定板块":
        try:
            sdf = fetcher.get_sector_list()
            if sdf is not None and not sdf.empty:
                cols = [c for c in ("name", "industry", "板块名称") if c in sdf.columns]
                names = sdf[cols[0]].dropna().astype(str).unique().tolist() if cols else []
            else:
                names = []
        except Exception:
            names = []
        if names:
            sector_name = st.selectbox("选择板块", names)
            st.caption(f"将扫描「{sector_name}」板块内的全部标的。")
        else:
            st.warning("板块列表为空（可能网络不可用），请切换其它来源。")
    else:
        limit_n = st.number_input("扫描前 N 只（全市场）", min_value=20, max_value=1500,
                                   value=250, step=10,
                                   help="技术面策略可设较大；含基本面策略时建议 ≤300，否则耗时较长。")
        st.caption(f"将从全市场股票库中取前 **{limit_n}** 只扫描（本地库顺序，非市值排序）。")

# ───────────────────────── 策略选择 ─────────────────────────
with st.container(border=True):
    _section_title("🧬 选股策略", accent="#8b5bff")
    st.caption("勾选要运行的策略；多选时可下方选择组合模式（AND 交集 / OR 并集 / 综合评分）。")
    cols = st.columns(3)
    selected = []
    if "screener_sel" not in st.session_state:
        # 默认勾选技术面快策略 + ROE，兼顾速度与覆盖
        st.session_state["screener_sel"] = ["trend", "low_position", "macd", "roe"]
    for i, key in enumerate(ALL_STRATEGIES):
        with cols[i % 3]:
            default_on = key in st.session_state["screener_sel"]
            if st.checkbox(f"{STRATEGY_NAMES_CN[key]}", value=default_on,
                           key=f"cb_{key}", help=STRATEGY_DESC[key]):
                selected.append(key)
    if not selected:
        _empty_info("请至少勾选 1 个策略。")
    else:
        has_fund = any(k not in TECH for k in selected)
        if has_fund and source != "我的自选股" and source != "指定板块":
            st.warning("⚠️ 已选基本面策略依赖 akshare 财务接口，全市场扫描可能耗时数分钟；"
                       "建议改用「自选股 / 指定板块」小池，或仅选技术面策略。", icon="⏱️")

# ───────────────────────── 组合模式 + 参数 ─────────────────────────
with st.container(border=True):
    _section_title("⚙️ 组合与参数", accent="#10b981")
    c1, c2, c3 = st.columns(3)
    with c1:
        mode = st.radio("多策略组合模式", ["and", "or", "score"],
                        horizontal=True, disabled=len(selected) < 2,
                        help="and=命中全部策略的交集；or/score=命中任一的并集，按命中数与评分排序")
    with c2:
        top_n = st.number_input("最终保留前 N 只（0=不限）", min_value=0, max_value=500,
                                value=50, step=10)
    with c3:
        workers = st.slider("并发线程数", 1, 8, 4,
                            help="提高并发可加速扫描，但过高可能触发接口限流。")

    with st.expander("🔧 高级阈值（可选，留默认即使用策略推荐值）"):
        adv = {}
        if "roe" in selected:
            adv["roe.roe_threshold"] = st.slider("ROE 策略 · ROE 下限(%)", 0.0, 40.0,
                                                 float(DEFAULT_PARAMS["roe"]["roe_threshold"]), 1.0)
        if "dividend" in selected:
            adv["dividend.min_dv_ratio"] = st.slider("高股息 · 股息率下限(%)", 0.0, 10.0,
                                                     float(DEFAULT_PARAMS["dividend"]["min_dv_ratio"]), 0.5)
        if "valuation" in selected:
            adv["valuation.max_pe"] = st.slider("低估值 · PE 上限", 5.0, 60.0,
                                                float(DEFAULT_PARAMS["valuation"]["max_pe"]), 1.0)
            adv["valuation.max_pb"] = st.slider("低估值 · PB 上限", 1.0, 10.0,
                                                float(DEFAULT_PARAMS["valuation"]["max_pb"]), 0.5)
        if "growth" in selected:
            adv["growth.min_revenue_growth"] = st.slider("成长 · 营收增速下限(%)", 0.0, 100.0,
                                                         float(DEFAULT_PARAMS["growth"]["min_revenue_growth"]), 5.0)
            adv["growth.min_profit_growth"] = st.slider("成长 · 利润增速下限(%)", 0.0, 100.0,
                                                        float(DEFAULT_PARAMS["growth"]["min_profit_growth"]), 5.0)
        if "low_position" in selected:
            adv["low_position.low_position_pct"] = st.slider("长期低位 · 底部分位上限(%)", 5.0, 50.0,
                                                            float(DEFAULT_PARAMS["low_position"]["low_position_pct"]), 1.0)
        if "volume_surge" in selected:
            adv["volume_surge.volume_surge_ratio"] = st.slider("放量 · 放量倍数下限", 1.0, 5.0,
                                                              float(DEFAULT_PARAMS["volume_surge"]["volume_surge_ratio"]), 0.1)
        if "trend" in selected:
            adv["trend.adx_min"] = st.slider("趋势 · ADX 下限", 10.0, 50.0,
                                             float(DEFAULT_PARAMS["trend"]["adx_min"]), 1.0)

# ───────────────────────── 运行 ─────────────────────────
with st.container(border=True):
    _section_title("🚀 运行选股", accent="#f59e0b")
    run_disabled = (not selected) or \
        (source == "我的自选股" and not universe_codes) or \
        (source == "指定板块" and not sector_name)
    if st.button("🚀 开始选股", type="primary", use_container_width=True, disabled=run_disabled):
        with st.spinner("选股中…（技术面较快；含基本面策略且股票池较大时可能需数分钟）"):
            result = screener.run(
                strategy_names=selected, mode=mode, params=adv, top_n=top_n,
                limit=limit_n if source == "全市场前 N 只" else None,
                sector=sector_name if source == "指定板块" else None,
                watchlist=universe_codes if source == "我的自选股" else None,
                workers=workers,
            )
        if not result.get("success"):
            st.error(result.get("message", "选股失败"))
        elif result.get("count", 0) == 0:
            md = result.get("metadata", {})
            per = md.get("per_strategy_counts", {})
            detail = "；".join(f"{STRATEGY_NAMES_CN.get(k,k)} 命中 {v} 只" for k, v in per.items())
            _empty_info(f"未命中任何标的。各策略扫描量：{detail}。"
                        f"可放宽阈值、减少策略数量，或检查网络/股票池。")
        else:
            st.success(f"✅ {result['message']}")
            res = result["results"]
            # 展示 DataFrame
            if len(selected) == 1:
                skey = selected[0]
                rows = []
                for r in res:
                    row = {"代码": r.get("code"), "名称": r.get("name"),
                           "行业": r.get("industry", "未知"), "评分": r.get("score")}
                    for k, v in r.items():
                        if k in ("code", "name", "industry", "strategy", "score", "scores"):
                            continue
                        if isinstance(v, list):
                            v = "、".join(map(str, v))
                        row[k] = round(v, 2) if isinstance(v, float) else v
                    rows.append(row)
                df = pd.DataFrame(rows)
            else:
                rows = []
                for r in res:
                    row = {"代码": r.get("code"), "名称": r.get("name"),
                           "行业": r.get("industry", "未知"),
                           "命中策略": "、".join(r.get("strategies_hit", [])),
                           "综合评分": r.get("total_score", r.get("score"))}
                    for sname, sc in (r.get("scores", {}) or {}).items():
                        row[STRATEGY_NAMES_CN.get(sname, sname)] = round(sc, 1)
                    rows.append(row)
                df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, height=520)
            csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("⬇️ 导出结果 CSV", data=csv,
                               file_name=f"智能选股_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
            with st.expander("📌 数据来源与说明"):
                st.markdown(
                    "- 技术面策略（MACD底背离 / 趋势 / 布林带下轨 / 近期放量 / 长期低位 / K线形态）"
                    "使用 StockSignal 自带行情数据（`StockFetcher`），无外部依赖。\n"
                    "- 基本面策略（ROE / 高股息 / 低估值 / 费雪成长 / 现金流质量 / 筹码集中）"
                    "使用 akshare 财务接口，需联网；单只失败会自动跳过，不影响整体。\n"
                    "- 评分越高代表该策略维度越优；多策略 AND 为交集（最严格），OR/综合评分为并集。"
                )
    else:
        if source == "我的自选股" and not universe_codes:
            _empty_info("自选股为空，请选择其它来源或先添加自选。")
        elif source == "指定板块" and not sector_name:
            _empty_info("请先选择板块。")
        else:
            _empty_info("勾选策略后点击「开始选股」。技术面策略可全市场快速扫描；"
                        "基本面策略建议用于自选股 / 板块小池。")
