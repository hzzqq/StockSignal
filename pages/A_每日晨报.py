"""
页面A：每日晨报 / 复盘笔记
- 每日晨报：聚合板块涨跌概览、自选股快照、相关新闻，生成开盘前速览。
- 复盘笔记：当日复盘记录，本地按日期持久化（data/review_notes_<date>.md）。
"""
import os
import streamlit as st
from datetime import datetime, date

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, api_quote, get_user
from modules.fetcher import StockFetcher
from modules.news import NewsFetcher

apply_page_config(page_title="每日晨报", page_icon="🌅", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🌅 每日晨报 / 复盘笔记")
today = date.today().strftime("%Y-%m-%d")
st.caption(f"生成日期：{today}（数据来源：板块行情 + 自选股 + 新闻；开盘前速览，非投资建议）")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()

# ───────────────────────── 板块概览 ─────────────────────────
with st.spinner("加载板块行情…"):
    try:
        sector_df = fetcher.get_sector_list()
    except Exception:
        sector_df = None

if sector_df is not None and not sector_df.empty and "change_pct" in sector_df.columns:
    up = int((sector_df["change_pct"] > 0).sum())
    down = int((sector_df["change_pct"] < 0).sum())
    flat = len(sector_df) - up - down
    c1, c2, c3 = st.columns(3)
    c1.metric("上涨板块", up, delta=None)
    c2.metric("下跌板块", down, delta=None)
    c3.metric("平/无数据", flat, delta=None)
    top_up = sector_df.sort_values("change_pct", ascending=False).head(5)
    top_dn = sector_df.sort_values("change_pct", ascending=True).head(5)
    colu, cold = st.columns(2)
    with colu:
        st.markdown("**🟢 领涨板块**")
        for _, r in top_up.iterrows():
            st.markdown(f"- {r.get('sector','?')}  `{r['change_pct']:+.2f}%`")
    with cold:
        st.markdown("**🔴 领跌板块**")
        for _, r in top_dn.iterrows():
            st.markdown(f"- {r.get('sector','?')}  `{r['change_pct']:+.2f}%`")
else:
    st.warning("⚠️ 暂未获取到板块行情（交易时间或网络恢复后自动可用）。")

st.divider()

# ───────────────────────── 自选股快照 ─────────────────────────
st.markdown("#### 📌 自选股快照")
sc, body = api_get("/api/watchlist")
watchlist = []
if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
    watchlist = body.get("data", []) or []

if not watchlist:
    st.info("自选股为空。先到「我的 / 自选股」添加，晨报才会包含持仓快照。")
else:
    snap = []
    for w in watchlist[:30]:
        code = w["stock_code"]
        rt = api_quote(code)
        if isinstance(rt, dict) and rt.get("current"):
            cur = float(rt["current"])
            prev = float(rt.get("prev_close") or cur)
            chg = (cur - prev) / prev * 100 if prev else 0.0
            snap.append({
                "名称": w.get("stock_name") or code,
                "代码": code,
                "现价": f"{cur:.2f}",
                "涨跌%": f"{chg:+.2f}%",
            })
        else:
            snap.append({"名称": w.get("stock_name") or code, "代码": code, "现价": "—", "涨跌%": "—"})
    if snap:
        st.dataframe(snap, use_container_width=True, height=320)

st.divider()

# ───────────────────────── 相关新闻 ─────────────────────────
st.markdown("#### 📰 相关新闻速览")
if watchlist:
    names = [w.get("stock_name") or w["stock_code"] for w in watchlist[:8]]
    try:
        news_df = NewsFetcher().fetch(keyword=" ".join(names), source="auto", limit=15)
    except Exception:
        news_df = None
    if news_df is not None and not news_df.empty:
        for _, r in news_df.head(10).iterrows():
            st.markdown(f"- {r.get('date','')}  **{r.get('title','')}**  _{r.get('source','')}_")
    else:
        st.info("暂无相关新闻。")
else:
    st.info("添加自选股后，此处展示相关新闻。")

st.divider()

# ───────────────────────── 复盘笔记 ─────────────────────────
st.markdown("#### 📝 复盘笔记")
NOTES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(NOTES_DIR, exist_ok=True)
notes_path = os.path.join(NOTES_DIR, f"review_notes_{today}.md")

if os.path.exists(notes_path):
    try:
        with open(notes_path, "r", encoding="utf-8") as f:
            saved = f.read()
    except Exception:
        saved = ""
else:
    saved = ""

note = st.text_area(
    "今日复盘（支持 Markdown）",
    value=saved,
    height=220,
    key="review_note",
    placeholder="记录今日盘面、操作与明日计划…",
)
c_save, c_clear = st.columns([1, 1])
with c_save:
    if st.button("💾 保存今日复盘", type="primary", use_container_width=True):
        try:
            with open(notes_path, "w", encoding="utf-8") as f:
                f.write(note)
            st.success(f"✅ 已保存到 {os.path.basename(notes_path)}")
        except Exception as e:
            st.error(f"❌ 保存失败：{e}")
with c_clear:
    if st.button("🗑️ 清空", use_container_width=True):
        st.session_state["review_note"] = ""
        st.rerun()
