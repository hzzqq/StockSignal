"""
页面A：每日晨报 / 复盘笔记
- 每日晨报：聚合板块涨跌概览、自选股快照、相关新闻，生成开盘前速览。
- 复盘笔记：当日复盘记录，本地按日期持久化（data/review_notes_<date>.md）。
"""
import os
import streamlit as st
import pandas as pd
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

# 顶部三大指数迷你卡片
from modules.widgets import render_index_mini_cards
render_index_mini_cards(cols_per_row=3)


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

# ───────────────────────── 自选股快照（可折叠） ─────────────────────────
sc, body = api_get("/api/watchlist")
watchlist = []
if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
    watchlist = body.get("data", []) or []

selected_code = None
selected_name = None
with st.expander("📌 自选股快照", expanded=True):
    if not watchlist:
        st.info("自选股为空。先到「我的 / 自选股」添加，晨报才会包含持仓快照。")
    else:
        st.caption("👉 点击表格中某一行，可在下方「相关新闻速览」查看该股票的专属新闻。")
        snap = []
        for w in watchlist[:30]:
            code = w["stock_code"]
            rt = api_quote(code)
            name = w.get("stock_name") or code
            if isinstance(rt, dict) and rt.get("current"):
                cur = float(rt["current"])
                prev = float(rt.get("prev_close") or cur)
                high = float(rt.get("high") or 0)
                low = float(rt.get("low") or 0)
                volume = int(rt.get("volume") or 0)
                amount = float(rt.get("amount") or 0)
                chg = (cur - prev) / prev * 100 if prev else 0.0
                change_amt = cur - prev if prev else 0.0
                amplitude = (high - low) / prev * 100 if prev else 0.0
                snap.append({
                    "名称": name, "代码": code, "现价": cur,
                    "涨跌额": change_amt, "涨跌%": chg,
                    "振幅%": amplitude, "成交量": volume, "成交额": amount,
                })
            else:
                snap.append({"名称": name, "代码": code, "现价": None, "涨跌额": None, "涨跌%": None, "振幅%": None, "成交量": None, "成交额": None})
        if snap:
            snap_df = pd.DataFrame(snap)
            event = st.dataframe(
                snap_df,
                use_container_width=True,
                height=320,
                on_select="rerun",
                selection_mode="single-row",
                key="morning_snap",
                column_config={
                    "现价": st.column_config.NumberColumn(format="¥%.2f"),
                    "涨跌额": st.column_config.NumberColumn(format="%.2f"),
                    "涨跌%": st.column_config.NumberColumn(format="%.2f%%"),
                    "振幅%": st.column_config.NumberColumn(format="%.2f%%"),
                    "成交量": st.column_config.NumberColumn(format="%d"),
                    "成交额": st.column_config.NumberColumn(format="%.0f"),
                },
            )
            try:
                sel_rows = event.selection.rows if event and event.selection else []
            except Exception:
                sel_rows = []
            if sel_rows:
                r = snap_df.iloc[sel_rows[0]]
                selected_code = str(r["代码"])
                selected_name = str(r["名称"])

st.divider()

# ───────────────────────── 相关新闻速览（可折叠，按选中股票过滤） ─────────────────────────
_news_title = f"📰 相关新闻速览 — {selected_name}（{selected_code}）" if selected_code else "📰 相关新闻速览"
with st.expander(_news_title, expanded=bool(selected_code)):
    if not watchlist:
        st.info("添加自选股后，此处展示相关新闻。")
    elif not selected_code:
        st.info("👆 请在上方「自选股快照」中点击某一行，查看该股票的相关新闻。")
    else:
        with st.spinner(f"加载 {selected_name} 相关新闻…"):
            try:
                news_df = NewsFetcher().fetch(keyword=selected_name, source="auto", limit=15)
            except Exception:
                news_df = None
        if news_df is not None and not news_df.empty:
            for _, r in news_df.head(12).iterrows():
                title = r.get("title", "")
                url = r.get("url") or r.get("link") or ""
                date_s = r.get("date", "")
                source_s = r.get("source", "")
                if url:
                    st.markdown(f"- {date_s}  **[{title}]({url})**  _{source_s}_")
                else:
                    st.markdown(f"- {date_s}  **{title}**  _{source_s}_")
        else:
            st.info(f"暂无与 {selected_name} 相关的新闻。")

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
