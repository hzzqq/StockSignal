"""
页面A：每日晨报 / 复盘笔记
- 每日晨报：聚合板块涨跌概览、自选股快照、相关新闻，生成开盘前速览。
- 复盘笔记：当日复盘记录，本地按日期持久化（data/review_notes_<date>.md）。
"""
import os
import contextlib
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, api_quote
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


# ── 自选股快照：市盈率 / 资产负债率 解析（复用 C 页已验证逻辑）──
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


def _calc_alr(code: str):
    """资产负债率(%) = 负债合计 / 资产总计 × 100；失败返回 None。"""
    try:
        df = fetcher.get_financial(code, "balance")
        if df is None or len(df) == 0:
            return None

        def _find_col(exact, suffix):
            for c in df.columns:
                if str(c) in exact:
                    return c
            for c in df.columns:
                if str(c).endswith(suffix):
                    return c
            return None

        asset_c = _find_col({"资产总计", "资产合计"}, ("资产总计", "资产合计"))
        liab_c = _find_col({"负债合计", "负债总计"}, ("负债合计", "负债总计"))
        if asset_c is not None and liab_c is not None:
            av = _to_num(df.iloc[0][asset_c])
            lv = _to_num(df.iloc[0][liab_c])
            if av and lv:
                return round(lv / av * 100, 2)
        item_col = df.columns[0]
        av = lv = None
        for _, row in df.iterrows():
            it = str(row[item_col])
            if av is None and any(k in it for k in ("资产总计", "资产合计")):
                vals = [x for x in (_to_num(v) for v in row[1:]) if x is not None]
                if vals:
                    av = vals[-1]
            if lv is None and any(k in it for k in ("负债合计", "负债总计")):
                vals = [x for x in (_to_num(v) for v in row[1:]) if x is not None]
                if vals:
                    lv = vals[-1]
        if av and lv:
            return round(lv / av * 100, 2)
    except Exception:
        return None
    return None


def _fund_one(code: str):
    """线程内并行取 (市盈率TTM, 资产负债率%)；任一项失败返回 None。"""
    pe = alr = None
    try:
        f = fetcher.get_fundamentals(code)
        if isinstance(f, dict):
            pe = f.get("pe_ttm")
    except Exception:
        pe = None
    try:
        alr = _calc_alr(code)
    except Exception:
        alr = None
    return code, pe, alr


def _quote_one(code: str):
    """线程内取实时行情（本地 fetcher，规避线程内后端 token 调用）。"""
    try:
        return code, fetcher.get_realtime_quote(code)
    except Exception:
        return code, None


@st.cache_data(show_spinner=False, ttl=300)
def _cached_sector():
    """板块列表跨重跑/跨页面会话级缓存，减少重复网络请求。"""
    try:
        return fetcher.get_sector_list()
    except Exception:
        return None

# ───────────────────────── 板块概览 ─────────────────────────
@st.fragment
def fragment_sector_summary():
    with st.spinner("加载板块行情…"):
        try:
            sector_df = _cached_sector()
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


fragment_sector_summary()

# ───────────────────────── 自选股快照 + 相关新闻（独立 fragment，交互不阻塞整页） ─────────────────────────
@st.fragment
def fragment_watchlist_and_news():
    sc, body = api_get("/api/watchlist")
    watchlist = []
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        watchlist = body.get("data", []) or []

    # 并行预拉市盈率 / 资产负债率（失败留 —，不阻塞快照渲染）
    wl_codes = [w["stock_code"] for w in watchlist[:30]]
    fund_map = {}
    if wl_codes:
        try:
            with st.spinner("并行获取自选股市盈率与资产负债率…"):
                with _ssl_bypass():
                    with ThreadPoolExecutor(max_workers=4) as ex:
                        futs = {ex.submit(_fund_one, c): c for c in wl_codes}
                        for fut in as_completed(futs):
                            c = futs[fut]
                            try:
                                _, pe, alr = fut.result(timeout=15)
                            except Exception:
                                pe = alr = None
                            fund_map[c] = (pe, alr)
        except Exception:
            pass

    # 并行预拉实时行情（避免逐个串行请求拖慢页面加载）
    quotes_map = {}
    if wl_codes:
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                for c, q in ex.map(_quote_one, wl_codes):
                    quotes_map[c] = q
        except Exception:
            quotes_map = {}

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
                rt = quotes_map.get(code)
                # 名称优先用自选股库已存名称，其次本地股票库解析，最后回退代码
                name = w.get("stock_name") or fetcher.get_name_only(code)
                pe, alr = fund_map.get(code, (None, None))
                _pe_s = f"{pe:.2f}" if isinstance(pe, (int, float)) else "—"
                _alr_s = f"{alr:.2f}%" if isinstance(alr, (int, float)) else "—"
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
                        "市盈率": _pe_s, "资产负债率": _alr_s,
                    })
                else:
                    snap.append({"名称": name, "代码": code, "现价": None, "涨跌额": None, "涨跌%": None,
                                 "振幅%": None, "成交量": None, "成交额": None,
                                 "市盈率": _pe_s, "资产负债率": _alr_s})
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
                        "市盈率": st.column_config.NumberColumn(format="%.2f"),
                        "资产负债率": st.column_config.NumberColumn(format="%.2f%%"),
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

    # 相关新闻速览（与快照同 fragment，行选择只重跑本 fragment）
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


fragment_watchlist_and_news()

# ───────────────────────── 复盘笔记 ─────────────────────────
@st.fragment
def fragment_review_notes():
    st.markdown("#### 📝 复盘笔记")
    import re as _re

    NOTES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    REVIEW_IMG_DIR = os.path.join(NOTES_DIR, "review_images")
    os.makedirs(NOTES_DIR, exist_ok=True)
    os.makedirs(REVIEW_IMG_DIR, exist_ok=True)

    if "review_img_counter" not in st.session_state:
        st.session_state["review_img_counter"] = 0

    def _notes_path(d):
        return os.path.join(NOTES_DIR, f"review_notes_{d}.md")

    # ── 子模块 1：工具栏（日期、查询、图片上传）──
    def _render_toolbar():
        note_date = st.date_input("复盘日期", value=date.today(), key="review_date")
        note_date_s = note_date.strftime("%Y-%m-%d")
        notes_path = _notes_path(note_date_s)

        # 初次进入默认载入当日复盘（若已存在）
        if "review_note" not in st.session_state:
            if os.path.exists(notes_path):
                try:
                    with open(notes_path, "r", encoding="utf-8") as f:
                        st.session_state["review_note"] = f.read()
                except Exception:
                    st.session_state["review_note"] = ""
            else:
                st.session_state["review_note"] = ""

        c_q, c_img = st.columns([0.5, 0.5])
        with c_q:
            if st.button("🔍 查询", type="primary", use_container_width=True, key="review_query"):
                if os.path.exists(notes_path):
                    try:
                        with open(notes_path, "r", encoding="utf-8") as f:
                            st.session_state["review_note"] = f.read()
                    except Exception:
                        st.session_state["review_note"] = ""
                else:
                    st.session_state["review_note"] = ""
                    st.info(f"📭 {note_date_s} 暂无复盘记录，可直接在下方新建。")
                st.session_state["review_queried"] = note_date_s
                # 不调用 st.rerun()：本 fragment 内的交互只会触发本 fragment 重跑，不影响整页
        with c_img:
            uploaded = st.file_uploader(
                "📷 添加图片到复盘",
                type=["png", "jpg", "jpeg", "gif", "webp"],
                key=f"review_img_{st.session_state['review_img_counter']}",
                help="上传后自动把图片链接插入到复盘文本末尾",
            )
            if uploaded is not None:
                safe_name = f"review_{note_date_s}_{uploaded.name}"
                img_path = os.path.join(REVIEW_IMG_DIR, safe_name)
                with open(img_path, "wb") as f:
                    f.write(uploaded.getbuffer())
                rel = f"review_images/{safe_name}"
                cur = st.session_state.get("review_note", "")
                st.session_state["review_note"] = (cur + f"\n\n![{uploaded.name}]({rel})\n").strip() + "\n"
                st.session_state["review_img_counter"] += 1
                st.success(f"✅ 已插入图片：{uploaded.name}")
                # 动态 key 已自动清空上传框，避免反复插入同一张图
        return note_date_s

    # ── 子模块 2：编辑器（文本框 + 保存/清空）──
    def _render_editor(note_date_s):
        note = st.text_area(
            f"复盘内容（{note_date_s}，支持 Markdown）",
            height=220,
            key="review_note",
            placeholder="记录今日盘面、操作与明日计划…",
        )
        c_save, c_clear = st.columns([1, 1])
        with c_save:
            if st.button("💾 保存复盘", type="primary", use_container_width=True, key="review_save"):
                try:
                    with open(_notes_path(note_date_s), "w", encoding="utf-8") as f:
                        f.write(note)
                    st.success(f"✅ 已保存到 review_notes_{note_date_s}.md")
                except Exception as e:
                    st.error(f"❌ 保存失败：{e}")
        with c_clear:
            if st.button("🗑️ 清空", use_container_width=True, key="review_clear"):
                st.session_state["review_note"] = ""
                # 不调用 st.rerun()：清空操作触发本 fragment 自然重跑

    # ── 子模块 3：查询结果展示区（仅在点击查询后展开）──
    def _render_preview():
        if not st.session_state.get("review_queried"):
            return
        st.markdown("---")
        st.markdown(f"#### 📄 复盘内容预览（{st.session_state['review_queried']}）")
        _content = st.session_state.get("review_note", "")
        _img_re = _re.compile(r"!\[.*?\]\((review_images/[^)]+)\)")
        for _m in _img_re.finditer(_content):
            _ip = os.path.join(NOTES_DIR, _m.group(1))
            if os.path.exists(_ip):
                st.image(_ip, width=420)
        if _content.strip():
            st.markdown(_content, unsafe_allow_html=True)
        else:
            st.info("（空白）")

    note_date_s = _render_toolbar()
    _render_editor(note_date_s)
    _render_preview()


fragment_review_notes()
