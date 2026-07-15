"""
页面B：技术形态选股器
在用户自选股 / 手动输入的股票池中扫描技术形态（金叉、突破、背离等），
输出命中标的与多维技术评分，辅助盘前筛选。纯前端计算，不改动任何主功能。
"""
import streamlit as st
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, api_kline
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

import concurrent.futures as _cf


def _norm_code(c: str) -> str:
    """规整股票代码：去掉 sh/sz/bj 等交易所前缀，保留 6 位纯数字代码。"""
    c = str(c).strip().lower()
    for p in ("sh", "sz", "bj"):
        if c.startswith(p):
            c = c[len(p):]
    return c.upper()

# ───────────────────────── 选择股票池 ─────────────────────────
source = st.radio("股票池来源", ["我的自选股", "手动输入代码"], horizontal=True)

universe = []
if source == "我的自选股":
    sc, body = api_get("/api/watchlist", timeout=10)
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        universe = [_norm_code(w["stock_code"]) for w in (body.get("data", []) or []) if w.get("stock_code")]
        if universe:
            st.caption(
                f"✅ 已从自选股加载 **{len(universe)}** 只："
                f"{', '.join(universe[:12])}{' …' if len(universe) > 12 else ''}"
            )
        else:
            st.warning("自选股为空，请先到「我的 / 自选股」添加，或切换为「手动输入代码」。")
    else:
        msg = body.get("message", "") if isinstance(body, dict) else ""
        st.error(f"❌ 加载自选股失败（HTTP {sc}）{msg}；可切换为「手动输入代码」继续。")
else:
    raw = multi_stock_search_input(label="输入多只股票（代码/名称，逗号分隔）", key="screener_stocks")
    if raw:
        universe = [_norm_code(c) for c in str(raw).replace("，", ",").split(",") if c.strip()]

keyword = st.text_input("形态关键词筛选（留空=显示所有命中形态，如：金叉 / 突破 / 背离）", "").strip()


def _scan_fetch_one(code: str, start: str, end: str):
    """并行抓取单只股票日线：优先后端 K 线接口（带缓存与多源回落），失败回退本地 fetcher。"""
    try:
        recs = api_kline(code, start=start, end=end) or fetcher.get_daily(code, start=start, end=end)
        df = pd.DataFrame(recs) if recs else None
        df = DataCleaner.full_pipeline(df)
        if df is None or df.empty or len(df) < 20:
            return code, None
        return code, df
    except Exception:
        return code, None


if st.button("🚀 开始扫描", type="primary", use_container_width=True) and universe:
    universe = universe[:40]  # 安全上限，避免过慢
    today = datetime.now().date()
    start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    # 并行抓取 K 线（网络 I/O 是瓶颈），再逐只做技术分析
    with st.spinner(f"并行抓取 {len(universe)} 只股票日线…"):
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            fetched = list(ex.map(lambda c: _scan_fetch_one(c, start, end), universe))

    results = []
    prog = st.progress(0, text="分析形态中…")
    for i, (code, df) in enumerate(fetched):
        try:
            if df is None:
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
        prog.progress((i + 1) / len(fetched), text=f"分析形态中… {i+1}/{len(fetched)}")
    prog.empty()

    if not results:
        st.info("未命中任何形态（或股票池无可用日线数据，可尝试「手动输入代码」或检查网络）。")
    else:
        st.success(f"✅ 扫描完成，命中 {len(results)} 只")
        results.sort(key=lambda r: r["技术评分"], reverse=True)
        st.dataframe(results, use_container_width=True, height=480)
elif not universe:
    st.info("请选择股票池后点击「开始扫描」。")
