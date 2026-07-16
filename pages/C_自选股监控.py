"""
页面C：自选股实时监控
────────────────────────
一览自选股实时现价与涨跌幅（A股红涨绿跌），并行拉取行情，异常自动回退本地源。
支持一键刷新、跳转「形态选股」对自选股做技术体检、跳转「个股分析」做深度诊断。
纯前端聚合，不改动任何主功能逻辑。
"""
import streamlit as st
import concurrent.futures as _cf
import contextlib
import requests
import pandas as pd
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import (
    require_auth, render_user_badge, api_get, safe_switch_page, clear_auth,
    api_delete, api_junk_stocks, api_remove_junk_stock, api_user_score,
    api_save_user_score, api_kline, get_token, API_BASE,
)
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from streamlit_autorefresh import st_autorefresh

# A股配色：涨=红，跌=绿
_UP = "#f6465d"
_DOWN = "#2ebd85"


@contextlib.contextmanager
def _ssl_bypass():
    """临时关闭 requests.Session.request 的 SSL 验证。

    本机系统代理会做 TLS 拦截，akshare 部分（如新浪财务报表）走 requests
    直连 quotes.sina.cn 时会因证书链不可达而 SSLCertVerificationError。
    注意 fetcher._ak_ssl_context 只 patch 了 Session.get，而 akshare 的
    requests.get 走的是 Session.request，故这里直接 patch Session.request。
    仅在该次批量抓取内生效，退出后恢复，避免污染全局。
    """
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
    """把单元格值安全转 float；空/非法返回 None。"""
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

apply_page_config(page_title="自选股监控", page_icon="📡", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

# ── 交易时段自动刷新（实时跟踪）──
def _is_trading_now():
    now = datetime.now()
    if now.weekday() >= 5:  # 周六日休市
        return False
    t = now.time()
    m1 = (datetime.strptime("09:30", "%H:%M").time()
          <= t <= datetime.strptime("11:30", "%H:%M").time())
    m2 = (datetime.strptime("13:00", "%H:%M").time()
          <= t <= datetime.strptime("15:00", "%H:%M").time())
    return m1 or m2

if _is_trading_now():
    st_autorefresh(interval=60 * 1000, key="watchlist_autorefresh")

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("📡 自选股监控")
st.caption("实时跟踪自选股现价与涨跌幅；行情接口异常时自动回退本地源。数据仅供参考，非投资建议。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _quote_one(code: str):
    """并行取单只实时行情：优先后端 /api/quote，失败回退本地 fetcher。

    注意：本函数运行在线程池中，不能调用任何 st.xxx（包括 safe_switch_page），
    否则会抛出 NoSessionContext。因此认证过期时直接返回 None，由页面级逻辑统一处理。
    """
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(f"{API_BASE}/api/quote?ticker={code}", headers=headers, timeout=5)
        if resp.status_code == 401:
            return code, {"__auth_error": True}
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict) and body.get("status") == "ok":
                data = body.get("data")
                if isinstance(data, dict) and data.get("current"):
                    return code, data
    except Exception:
        pass
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict) and q.get("current"):
            return code, q
    except Exception:
        pass
    return code, None


@st.cache_data(show_spinner=False, ttl=3600)
def _resolve_name(code: str) -> str:
    """本地库兜底解析股票中文名；返回空串表示未知。"""
    try:
        return fetcher.get_name(code)[1] or ""
    except Exception:
        return ""


def _calc_alr(code: str):
    """从资产负债表解析资产负债率(%) = 负债合计 / 资产总计 × 100；失败返回 None。

    akshare 新浪资产负债表实际结构：index=报告期(最新在 0 行)，columns=科目名
    （含「资产总计」「负债合计」）。同时兼容「行=科目、首列=科目名」的旧结构。
    """
    try:
        df = fetcher.get_financial(code, "balance")
        if df is None or len(df) == 0:
            return None

        def _find_col(exact, suffix):
            # 先精确匹配，避免「流动资产合计」误命中「资产合计」这类子串
            for c in df.columns:
                if str(c) in exact:
                    return c
            for c in df.columns:
                if str(c).endswith(suffix):
                    return c
            return None

        asset_c = _find_col({"资产总计", "资产合计"}, ("资产总计", "资产合计"))
        liab_c = _find_col({"负债合计", "负债总计"}, ("负债合计", "负债总计"))

        # 结构 A（akshare 实际）：列=科目，最新报告期=第 0 行
        if asset_c is not None and liab_c is not None:
            av = _to_num(df.iloc[0][asset_c])
            lv = _to_num(df.iloc[0][liab_c])
            if av and lv:
                return round(lv / av * 100, 2)

        # 结构 B（兜底）：行=科目，首列=科目名
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

# 线程内遇到 401 时不能直接跳转，统一在此处理
if any(isinstance(q, dict) and q.get("__auth_error") for q in quotes.values()):
    clear_auth()
    st.warning("🔐 登录已过期，请重新登录")
    st.stop()

# ── 并行拉取市盈率与资产负债率 ──
fund_map = {}
if codes:
    with st.spinner("并行获取市盈率与资产负债率…"):
        # 新浪财务报表在代理环境需临时关闭 SSL 校验，仅本次批量抓取内生效
        with _ssl_bypass():
            with _cf.ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(_fund_one, c): c for c in codes}
                for fut in _cf.as_completed(futs):
                    c = futs[fut]
                    try:
                        _, pe, alr = fut.result(timeout=15)
                    except Exception:
                        pe = alr = None
                    fund_map[c] = (pe, alr)

rows = []
quote_times = []
for code in codes:
    q = quotes.get(code)
    if q and q.get("current"):
        cur = float(q["current"])
        prev = float(q.get("prev_close") or 0)
        open_ = float(q.get("open") or 0)
        high = float(q.get("high") or 0)
        low = float(q.get("low") or 0)
        volume = int(q.get("volume") or 0)
        amount = float(q.get("amount") or 0)
        chg = (cur - prev) / prev * 100 if prev else 0.0
        change_amt = cur - prev if prev else 0.0
        amplitude = (high - low) / prev * 100 if prev else 0.0
        name = (q.get("name") if q.get("name") else None) or names.get(code) or _resolve_name(code) or code
        qt = q.get("datetime")
        if qt:
            quote_times.append(str(qt))
    else:
        cur = chg = change_amt = amplitude = volume = amount = None
        name = names.get(code) or _resolve_name(code) or code
    pe, alr = fund_map.get(code, (None, None))
    rows.append({
        "code": code, "name": name, "cur": cur, "chg": chg,
        "change_amt": change_amt, "amplitude": amplitude,
        "volume": volume, "amount": amount,
        "pe_ttm": f"{pe:.2f}" if isinstance(pe, (int, float)) else "—",
        "alr": f"{alr:.2f}%" if isinstance(alr, (int, float)) else "—",
    })

# ── 渲染监控表 ──
up_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] >= 0)
down_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] < 0)
st.markdown(
    f"#### 共 {len(rows)} 只自选股 ｜ "
    f"<span style='color:{_UP};font-weight:600;'>▲ {up_n}</span> ／ "
    f"<span style='color:{_DOWN};font-weight:600;'>▼ {down_n}</span>",
    unsafe_allow_html=True,
)

if rows:
    df_rt = pd.DataFrame(rows)
    display_df = df_rt[["name", "code", "cur", "change_amt", "chg", "amplitude",
                          "volume", "amount", "pe_ttm", "alr"]].copy()
    display_df.rename(columns={
        "name": "名称", "code": "代码", "cur": "现价",
        "change_amt": "涨跌额", "chg": "涨跌%", "amplitude": "振幅%",
        "volume": "成交量", "amount": "成交额",
        "pe_ttm": "市盈率(TTM)", "alr": "资产负债率",
    }, inplace=True)
    st.dataframe(
        display_df,
        use_container_width=True,
        height=max(200, min(480, 40 + len(rows) * 38)),
        column_config={
            "现价": st.column_config.NumberColumn(format="¥%.2f"),
            "涨跌额": st.column_config.NumberColumn(format="%.2f"),
            "涨跌%": st.column_config.NumberColumn(format="%.2f%%"),
            "振幅%": st.column_config.NumberColumn(format="%.2f%%"),
            "成交量": st.column_config.NumberColumn(format="%d"),
            "成交额": st.column_config.NumberColumn(format="%.0f"),
        },
    )
    # 点击行跳转（用 selectbox 选择）
    opts = [f"{r['code']} {r['name']}" for r in rows if r['cur'] is not None]
    if opts:
        sel = st.selectbox("选择股票查看 K 线", ["— 请选择 —"] + opts, key="watch_rt_jump")
        if sel and sel != "— 请选择 —":
            code = sel.split()[0]
            st.session_state["pick_stock_confirmed"] = code
            st.session_state["pick_stock_query"] = code
            safe_switch_page("pages/1_股票选取.py")
else:
    st.info("暂无数据。")

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    if st.button("🔄 刷新行情", type="primary", use_container_width=True):
        st.rerun()
with col_b:
    if st.button("🧭 用自选股做技术体检", use_container_width=True):
        safe_switch_page("pages/B_形态选股.py")

data_time = max(quote_times) if quote_times else "—"
refresh_tag = " ｜ 🔴 交易时段每 60 秒自动刷新" if _is_trading_now() else ""
st.caption(
    f"行情时间：{data_time} ｜ 本页刷新：{datetime.now().strftime('%H:%M:%S')}"
    f" ｜ 红涨绿跌（A股惯例）{refresh_tag}"
)


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


def _kline_thread_safe(code: str, start: str, end: str, period: str = "daily", adjust: str = "qfq"):
    """线程安全的 K 线获取：直接走 requests，避免 api_kline 在线程内调 safe_switch_page。"""
    try:
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params = f"symbol={code}&start={start}&period={period}&adjust={adjust}"
        if end:
            params += f"&end={end}"
        resp = requests.get(f"{API_BASE}/api/kline?{params}", headers=headers, timeout=8)
        if resp.status_code == 401:
            return {"__auth_error": True}
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict) and body.get("status") == "ok":
                data = body.get("data")
                if isinstance(data, list) and data:
                    return data
    except Exception:
        pass
    return None


def _analyze_one(code: str, start: str, end: str):
    """获取单股 K 线并计算技术指标；失败返回 None。"""
    try:
        records = _kline_thread_safe(code, start=start, end=end, period="daily")
        if isinstance(records, dict) and records.get("__auth_error"):
            return {"__auth_error": True}
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


def _build_pool_df(codes: list, scores_map: dict) -> pd.DataFrame | None:
    """并行计算股票池技术指标。返回 None 表示线程内检测到 401 认证过期。"""
    end = datetime.now().date()
    start = end - timedelta(days=120)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    rows = []
    auth_error = False
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_analyze_one, c, start_s, end_s): c for c in codes}
        for fut in _cf.as_completed(futs):
            res = fut.result()
            if isinstance(res, dict) and res.get("__auth_error"):
                auth_error = True
                continue
            if res:
                code = res["code"]
                res["user_score"] = scores_map.get(code)
                rows.append(res)
    if auth_error:
        return None
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _render_pool_table(df: pd.DataFrame | None, pool_key: str, on_remove):
    """渲染可排序、可跳转、可改评分的股票池表格。"""
    if df is None:
        st.warning("🔐 登录状态已过期，请刷新页面或重新登录。")
        return
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
