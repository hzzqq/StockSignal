"""
页面B：技术形态选股器
在用户自选股 / 手动输入的股票池中扫描技术形态（金叉、突破、背离等），
输出命中标的与多维技术评分，辅助盘前筛选。纯前端计算，不改动任何主功能。
"""
import streamlit as st
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.search_ui import multi_stock_search_input

apply_page_config(page_title="形态选股", page_icon="🧭", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🧭 技术形态选股器")
st.caption("在股票池中扫描技术形态并给出多维技术评分；结果仅供参考，非投资建议。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()

# ───────────────────────── 选择股票池 ─────────────────────────
source = st.radio("股票池来源", ["我的自选股", "手动输入代码"], horizontal=True)

universe = []
if source == "我的自选股":
    sc, body = api_get("/api/watchlist")
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        universe = [w["stock_code"] for w in (body.get("data", []) or [])]
    if not universe:
        st.warning("自选股为空，请先到「我的 / 自选股」添加，或切换为「手动输入代码」。")
else:
    raw = multi_stock_search_input(label="输入多只股票（代码/名称，逗号分隔）", key="screener_stocks")
    if raw:
        universe = [c.strip() for c in str(raw).replace("，", ",").split(",") if c.strip()]

keyword = st.text_input("形态关键词筛选（留空=显示所有命中形态，如：金叉 / 突破 / 背离）", "").strip()

if st.button("🚀 开始扫描", type="primary", use_container_width=True) and universe:
    universe = universe[:40]  # 安全上限，避免过慢
    results = []
    prog = st.progress(0, text="扫描中…")
    for i, code in enumerate(universe):
        try:
            today = datetime.now().date()
            start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            end = today.strftime("%Y-%m-%d")
            df = fetcher.get_daily(code, start=start, end=end)
            df = DataCleaner.full_pipeline(df)
            if df is None or df.empty or len(df) < 20:
                continue
            tech = technical_full_analysis(df)
            composite = SignalEngine().price_score(df)
            patterns = tech.get("patterns", []) or []
            if isinstance(patterns, str):
                patterns = [patterns]
            pat_str = "；".join(str(p) for p in patterns) if patterns else "—"
            if keyword:
                if not any(keyword.lower() in str(p).lower() for p in (patterns or [])):
                    continue
            results.append({
                "代码": code,
                "名称": fetcher.get_stock_name(code) or code,
                "技术评分": int(round(composite)),
                "形态": pat_str,
            })
        except Exception:
            continue
        prog.progress((i + 1) / len(universe), text=f"扫描中… {i+1}/{len(universe)}")
    prog.empty()

    if not results:
        st.info("未命中任何形态（或股票池无数据）。")
    else:
        st.success(f"✅ 扫描完成，命中 {len(results)} 只")
        results.sort(key=lambda r: r["技术评分"], reverse=True)
        st.dataframe(results, use_container_width=True, height=480)
elif not universe:
    st.info("请选择股票池后点击「开始扫描」。")
