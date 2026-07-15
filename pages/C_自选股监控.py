"""
页面C：自选股实时监控
────────────────────────
一览自选股实时现价与涨跌幅（A股红涨绿跌），并行拉取行情，异常自动回退本地源。
支持一键刷新、跳转「形态选股」对自选股做技术体检、跳转「个股分析」做深度诊断。
纯前端聚合，不改动任何主功能逻辑。
"""
import streamlit as st
import concurrent.futures as _cf
import pandas as pd
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import (
    require_auth, render_user_badge, api_get, api_quote, safe_switch_page,
    api_delete, api_junk_stocks, api_remove_junk_stock, api_user_score,
    api_save_user_score, api_kline,
)
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine

# A股配色：涨=红，跌=绿
_UP = "#f6465d"
_DOWN = "#2ebd85"

apply_page_config(page_title="自选股监控", page_icon="📡", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("📡 自选股监控")
st.caption("实时跟踪自选股现价与涨跌幅；行情接口异常时自动回退本地源。数据仅供参考，非投资建议。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _quote_one(code: str):
    """并行取单只实时行情：优先后端 /api/quote，失败回退本地 fetcher。"""
    rt = api_quote(code)
    if isinstance(rt, dict) and rt.get("current"):
        return code, rt
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict) and q.get("current"):
            return code, q
    except Exception:
        pass
    return code, None


# ── 加载自选股 ──
sc, body = api_get("/api/watchlist", timeout=10)
if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
    st.error("加载自选股失败，请刷新重试。")
    st.stop()

items = body.get("data", []) or []
if not items:
    st.info("自选股为空，请先到「行情看板 / 我的」添加，或前往「形态选股」用自选股池扫描。")
    if st.button("➡️ 去形态选股", use_container_width=True):
        safe_switch_page("pages/B_形态选股.py")
    st.stop()

codes = [it["stock_code"] for it in items]
names = {it["stock_code"]: it.get("stock_name") or it["stock_code"] for it in items}

# ── 并行拉取实时行情 ──
with st.spinner(f"并行获取 {len(codes)} 只自选股实时行情…"):
    quotes = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        for code, q in ex.map(_quote_one, codes):
            quotes[code] = q

rows = []
for code in codes:
    q = quotes.get(code)
    if q and q.get("current"):
        cur = float(q["current"])
        prev = float(q.get("prev_close") or 0)
        chg = (cur - prev) / prev * 100 if prev else 0.0
        name = q.get("name") or names[code]
    else:
        cur, chg, name = None, None, names[code]
    rows.append({"code": code, "name": name, "cur": cur, "chg": chg})

# ── 渲染监控表 ──
up_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] >= 0)
down_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] < 0)
st.markdown(
    f"#### 共 {len(rows)} 只自选股 ｜ "
    f"<span style='color:{_UP};font-weight:600;'>▲ {up_n}</span> ／ "
    f"<span style='color:{_DOWN};font-weight:600;'>▼ {down_n}</span>",
    unsafe_allow_html=True,
)

for r in rows:
    c1, c2, c3, c4 = st.columns([3, 2, 2.4, 1.6])
    with c1:
        st.markdown(f"**{r['name']}** &nbsp;<code>{r['code']}</code>")
    with c2:
        st.markdown(f"**{r['cur']:.2f}**" if r["cur"] is not None else "—")
    with c3:
        if r["chg"] is not None:
            color = _UP if r["chg"] >= 0 else _DOWN
            arrow = "▲" if r["chg"] >= 0 else "▼"
            st.markdown(
                f'<span class="sf-pill" style="color:{color};border-color:{color}55;'
                f'background:{color}1a;">{arrow} {r["chg"]:+.2f}%</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span class="sf-pill mid">行情不可用</span>', unsafe_allow_html=True)
    with c4:
        if st.button("诊断", key=f"diag_{r['code']}", use_container_width=True):
            safe_switch_page("pages/2_个股分析.py")

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    if st.button("🔄 刷新行情", type="primary", use_container_width=True):
        st.rerun()
with col_b:
    if st.button("🧭 用自选股做技术体检", use_container_width=True):
        safe_switch_page("pages/B_形态选股.py")

st.caption(f"数据时间：{datetime.now().strftime('%H:%M:%S')} ｜ 红涨绿跌（A股惯例）")


# ═══════════════════════════════════════════════════════════════
# 股票池管理（自选股 / 垃圾股 / 用户打分）
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📂 股票池管理")


def _norm_code(c: str) -> str:
    if not c:
        return ""
    c = str(c).strip().lower()
    for p in ("sh", "sz", "bj"):
        if c.startswith(p):
            c = c[len(p):]
    return c[-6:] if len(c) > 6 else c


def _analyze_one(code: str, start: str, end: str):
    """获取单股 K 线并计算技术指标；失败返回 None。"""
    try:
        records = api_kline(code, start=start, end=end, period="daily", timeout=8)
        d = pd.DataFrame(records) if records else fetcher.get_kline(code, start=start, end=end, period="daily")
        if d is None or d.empty:
            return None
        d = DataCleaner.full_pipeline(d)
        if len(d) < 5:
            return None
        profile = SignalEngine().technical_profile(d)
        analysis = technical_full_analysis(d)
        latest = d.iloc[-1]
        prev = d.iloc[-2]
        cur = float(latest["close"])
        chg = (cur / float(prev["close"]) - 1) * 100 if prev["close"] else 0.0
        vol_ratio = analysis.get("volume", {}).get("vol_ratio", 1.0)
        return {
            "code": code,
            "name": fetcher.get_stock_name(code) or code,
            "price": cur,
            "change_pct": chg,
            "short": profile["short"],
            "mid": profile["mid"],
            "long": profile["long"],
            "composite": profile["composite"],
            "trend_score": analysis.get("trend", {}).get("trend_score", 50),
            "vol_ratio": vol_ratio,
        }
    except Exception:
        return None


def _load_scores_map(codes: list) -> dict:
    """批量拉取当前用户对所有 code 的打分。"""
    scores = {}
    try:
        status, body = api_get("/api/user-scores", timeout=5)
        if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
            for r in body.get("data", []):
                if isinstance(r, dict):
                    scores[_norm_code(r.get("stock_code", ""))] = int(r.get("score", 0))
    except Exception:
        pass
    return scores


def _build_pool_df(codes: list, scores_map: dict) -> pd.DataFrame:
    """并行计算股票池技术指标。"""
    end = datetime.now().date()
    start = end - timedelta(days=120)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    rows = []
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_analyze_one, c, start_s, end_s): c for c in codes}
        for fut in _cf.as_completed(futs):
            res = fut.result()
            if res:
                code = res["code"]
                res["user_score"] = scores_map.get(code)
                rows.append(res)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _render_pool_table(df: pd.DataFrame, pool_key: str, on_remove):
    """渲染可排序、可跳转、可改评分的股票池表格。"""
    if df.empty:
        st.info("暂无数据。")
        return

    display = df[["code", "name", "price", "change_pct", "short", "mid", "long",
                  "composite", "trend_score", "vol_ratio", "user_score"]].copy()
    display.rename(columns={
        "code": "代码", "name": "名称", "price": "现价", "change_pct": "涨跌%",
        "short": "短期", "mid": "中期", "long": "长期", "composite": "综合",
        "trend_score": "趋势分", "vol_ratio": "量比", "user_score": "用户打分",
    }, inplace=True)

    st.dataframe(display, use_container_width=True, height=360,
                 column_config={
                     "涨跌%": st.column_config.NumberColumn(format="%.2f%%"),
                     "现价": st.column_config.NumberColumn(format="¥%.2f"),
                     "量比": st.column_config.NumberColumn(format="%.2fx"),
                 })

    # 跳转选择
    opts = [f"{r['code']} {r['name']}" for _, r in df.iterrows()]
    selected = st.selectbox("点击选择股票跳转 K 线", ["— 请选择 —"] + opts, key=f"{pool_key}_jump")
    if selected and selected != "— 请选择 —":
        code = selected.split()[0]
        st.session_state["pick_stock_confirmed"] = code
        st.session_state["pick_stock_query"] = code
        safe_switch_page("pages/1_股票选取.py")

    # 批量改评分（按键输入）
    st.markdown("**✏️ 修改用户打分**")
    c1, c2, c3 = st.columns([0.4, 0.4, 0.2])
    with c1:
        edit_code = st.selectbox("选择股票", ["—"] + opts, key=f"{pool_key}_edit_code")
    with c2:
        existing = None
        if edit_code and edit_code != "—":
            existing = api_user_score(edit_code.split()[0])
        edit_score = st.number_input(
            "新评分", min_value=0, max_value=100,
            value=existing if existing is not None else 50,
            step=1, key=f"{pool_key}_edit_score",
        )
    with c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("保存", key=f"{pool_key}_save_score", use_container_width=True):
            if edit_code and edit_code != "—":
                code = edit_code.split()[0]
                name = edit_code.split(maxsplit=1)[1] if " " in edit_code else ""
                api_save_user_score(code, int(edit_score), name)
                st.success("评分已更新")
                st.rerun()

    # 移除按钮
    if on_remove:
        st.markdown("**🗑️ 移除股票**")
        remove_opts = [f"{r['code']} {r['name']}" for _, r in df.iterrows()]
        rem = st.selectbox("选择要移除的股票", ["—"] + remove_opts, key=f"{pool_key}_remove")
        if rem and rem != "—":
            if st.button("确认移除", key=f"{pool_key}_remove_btn"):
                on_remove(rem.split()[0])


# 自选股
with st.expander("📌 自选股列表", expanded=False):
    sc, body = api_get("/api/watchlist")
    wl_items = []
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        wl_items = body.get("data", []) or []
    if not wl_items:
        st.info("自选股为空。先到「股票选取」页面点击「加入自选股」添加。")
    else:
        codes = [_norm_code(it["stock_code"]) for it in wl_items]
        id_map = {_norm_code(it["stock_code"]): it["id"] for it in wl_items}
        scores = _load_scores_map(codes)
        df_wl = _build_pool_df(codes, scores)

        def _remove_wl(code: str):
            item_id = id_map.get(_norm_code(code))
            if item_id:
                api_delete(f"/api/watchlist/{item_id}", timeout=5)
                st.success("已移除")
                st.rerun()

        _render_pool_table(df_wl, "watchlist", _remove_wl)

# 垃圾股
with st.expander("🗑️ 垃圾股列表", expanded=False):
    junk_items = api_junk_stocks()
    if not junk_items:
        st.info("垃圾股为空。先到「股票选取」页面点击「加入垃圾股」添加。")
    else:
        codes = [_norm_code(it["stock_code"]) for it in junk_items]
        id_map = {_norm_code(it["stock_code"]): it["id"] for it in junk_items}
        scores = _load_scores_map(codes)
        df_jk = _build_pool_df(codes, scores)

        def _remove_jk(code: str):
            item_id = id_map.get(_norm_code(code))
            if item_id:
                api_remove_junk_stock(item_id)
                st.success("已移除")
                st.rerun()

        _render_pool_table(df_jk, "junk", _remove_jk)
