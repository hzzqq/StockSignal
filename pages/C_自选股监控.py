"""
页面C：自选股实时监控
────────────────────────
一览自选股实时现价与涨跌幅（A股红涨绿跌），并行拉取行情，异常自动回退本地源。
支持一键刷新、跳转「形态选股」对自选股做技术体检、跳转「个股分析」做深度诊断。
纯前端聚合，不改动任何主功能逻辑。
"""
import streamlit as st
import concurrent.futures as _cf
import requests
import pandas as pd
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import (
    require_auth, render_user_badge, api_get, safe_switch_page, clear_auth,
    api_delete, api_junk_stocks, api_remove_junk_stock, api_user_score,
    api_save_user_score, get_token, API_BASE, _rel_time,
)
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from streamlit_autorefresh import st_autorefresh

# A股配色：涨=红，跌=绿（统一走 page_widgets.UP/DOWN，避免三套常量漂移 #541-4）
from modules.page_widgets import UP as _UP, DOWN as _DOWN


# SSL 关闭补丁已收敛到 modules.ssl_helper（#404），此处复用公共上下文管理器
from modules.ssl_helper import ssl_bypass as _ssl_bypass
from modules.page_widgets import _empty_info, _toast
from modules.fundamental_helpers import calc_alr, fund_one


from modules.page_guard import safe_fragment

apply_page_config(page_title="自选股监控", page_icon="📡", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

# ── 交易时段自动刷新（实时跟踪）──
def _is_trading_now():
    # 统一走 modules.page_widgets.is_trading_now（#541-2 消除 4 份重复）
    from modules.page_widgets import is_trading_now as _itn
    return _itn()


dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("📡 自选股监控")
st.caption("实时跟踪自选股现价与涨跌幅；行情接口异常时自动回退本地源。数据仅供参考，非投资建议。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _quote_one(code: str, token: str | None = None):
    """并行取单只实时行情：优先后端 /api/quote，失败回退本地 fetcher。

    注意：本函数运行在线程池中，不能调用任何 st.xxx（包括 get_token/session_state），
    否则子线程无 ScriptRunContext 会拿不到登录态（token=None → 误判 401 登出）。
    因此 token 必须由主线程 get_token() 取出后作为参数传入。
    """
    try:
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
        return fetcher.get_stock_basic(code)[1] or ""
    except Exception:
        return ""


def _calc_alr(code: str):
    """委托 fundamental_helpers.calc_alr（#545-16 消除与 A_每日晨报 的逐字重复）。"""
    return calc_alr(code, fetcher)


def _fund_one(code: str):
    """委托 fundamental_helpers.fund_one（#545-16 消除重复）。"""
    return fund_one(code, fetcher)


# ═══════════════════════════════════════════════════════════════
# 主监控表（独立 fragment，交易时段自动刷新不影响整页）
# ═══════════════════════════════════════════════════════════════
@safe_fragment
def fragment_watchlist_monitor():
    # 交易时段自动刷新（仅本 fragment 重跑）
    if _is_trading_now():
        st_autorefresh(interval=60 * 1000, key="watchlist_autorefresh")

    sc, body = api_get("/api/watchlist", timeout=10)
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("加载自选股失败，请刷新重试。")
        return

    items = body.get("data", []) or []
    if not items:
        _empty_info("自选股为空，请先到「行情看板 / 我的」添加，或前往「形态选股」用自选股池扫描。")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("➡️ 去形态选股", use_container_width=True, key="wl_empty_go"):
                safe_switch_page("pages/B_形态选股.py")
        with c2:
            if st.button("📘 看新手教程", use_container_width=True, key="wl_empty_tut"):
                safe_switch_page("pages/Z_新手教程.py")
        return

    codes = [it.get("stock_code") for it in items if isinstance(it, dict) and it.get("stock_code")]
    # 强制用本地库解析名称，避免后端 stock_name 为空或错误地显示代码。
    # 并行解析（P1）：本地库命中为主、快且线程安全；网络兜底（BaoStock/akshare）
    # 罕见触发，4 线程并发只读查询风险可控，显著快于逐只串行。
    names = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        _fut_map = {ex.submit(fetcher.get_name_only, code): code for code in codes}
        for _fut in _cf.as_completed(_fut_map):
            _c = _fut_map[_fut]
            try:
                names[_c] = _fut.result() or _c
            except Exception:
                names[_c] = _c

    # 并行拉取实时行情
    with st.spinner(f"并行获取 {len(codes)} 只自选股实时行情…"):
        quotes = {}
        _tok = get_token()  # 主线程取 token，子线程无 ScriptRunContext 拿不到
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            for code, q in ex.map(lambda c: _quote_one(c, _tok), codes):
                quotes[code] = q

    # 线程内遇到 401 时不能直接跳转，统一在此处理
    if any(isinstance(q, dict) and q.get("__auth_error") for q in quotes.values()):
        clear_auth()
        st.warning("🔐 登录已过期，请重新登录")
        return

    # 并行拉取市盈率与资产负债率
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
            "pe_ttm": f"{pe:.2f}" if isinstance(pe, (int, float)) and not pd.isna(pe) else "—",
            "alr": f"{alr:.2f}%" if isinstance(alr, (int, float)) and not pd.isna(alr) else "—",
        })

    st.caption("交易时段每 60 秒自动刷新；涨跌颜色遵循 A股 惯例：红涨绿跌。点击下方选择框可跳转个股研究页。")
    # ── 渲染监控表 ──
    up_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] >= 0)
    down_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] < 0)
    st.markdown(
        f"#### 共 {len(rows)} 只自选股 ｜ "
        f"<span style='color:{_UP};font-weight:600;'>▲ {up_n}</span> ／ "
        f"<span style='color:{_DOWN};font-weight:600;'>▼ {down_n}</span>",
        unsafe_allow_html=True,
    )
    if quote_times:
        st.caption(f"🕒 行情更新于 {_rel_time(min(quote_times))}")

    # 行情全失败时给出明确空态提示（避免整表 — 而无说明，误以为无持仓）
    ok_n = sum(1 for r in rows if r["cur"] is not None)
    if codes and ok_n == 0:
        st.warning("⚠️ 实时行情暂时获取失败（接口/网络异常），已尝试回退本地源仍无数据；"
                   "下表为持仓快照，行情相关列显示 —，交易时段将自动刷新或稍后重试。")

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
        def _chg_color(v):
            try:
                x = float(v)
            except Exception:
                return ""
            if x > 0:
                return "color:{_UP};font-weight:600"
            if x < 0:
                return "color:{_DOWN};font-weight:600"
            return "color:#9aa0a6"
        _styled = display_df.style.map(_chg_color, subset=["涨跌额", "涨跌%"])
        st.dataframe(
            _styled,
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
                safe_switch_page("pages/个股研究.py")
    else:
        _empty_info("暂无可展示的实时行情（可能行情接口暂时未返回数据）。自选股列表非空但取数失败，稍候自动刷新，或检查网络后重试。")

    # ── 导出当前自选股快照为 CSV（含实时行情 + 估值）──
    if rows:
        export_df = pd.DataFrame(rows)[
            ["code", "name", "cur", "change_amt", "chg", "amplitude",
             "volume", "amount", "pe_ttm", "alr"]
        ].rename(columns={
            "code": "代码", "name": "名称", "cur": "现价",
            "change_amt": "涨跌额", "chg": "涨跌%", "amplitude": "振幅%",
            "volume": "成交量", "amount": "成交额",
            "pe_ttm": "市盈率TTM", "alr": "资产负债率",
        })
        csv_data = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "⬇️ 导出自选股 CSV",
            data=csv_data,
            file_name=f"自选股_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
            key="wl_export_csv",
        )

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 刷新行情", type="primary", use_container_width=True, key="wl_refresh"):
            # 不调用 st.rerun()：按钮点击已触发本 fragment 自然重跑
            pass
    with col_b:
        if st.button("🧭 用自选股做技术体检", use_container_width=True, key="wl_tech_check"):
            safe_switch_page("pages/B_形态选股.py")

    data_time = max(quote_times) if quote_times else "—"
    refresh_tag = " ｜ 🔴 交易时段每 60 秒自动刷新" if _is_trading_now() else ""
    st.caption(
        f"行情时间：{data_time} ｜ 本页刷新：{datetime.now().strftime('%H:%M:%S')}"
        f" ｜ 红涨绿跌（A股惯例）{refresh_tag}"
    )


fragment_watchlist_monitor()


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


def _kline_thread_safe(code: str, start: str, end: str, period: str = "daily", adjust: str = "qfq", token: str | None = None):
    """线程安全的 K 线获取：直接走 requests，避免 api_kline 在线程内调 safe_switch_page。

    token 须由主线程传入：子线程无 ScriptRunContext，get_token() 会返回 None → 误判 401。
    """
    try:
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


def _analyze_one(code: str, start: str, end: str, token: str | None = None):
    """获取单股 K 线并计算技术指标；失败返回 None。token 由主线程传入。"""
    try:
        records = _kline_thread_safe(code, start=start, end=end, period="daily", token=token)
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
            "name": fetcher.get_name_only(code),
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
    _tok = get_token()  # 主线程取 token，子线程无 ScriptRunContext 拿不到
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_analyze_one, c, start_s, end_s, _tok): c for c in codes}
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
        _empty_info("暂无数据")
        return

    display = df[["code", "name", "price", "change_pct", "short", "mid", "long",
                  "composite", "trend_score", "vol_ratio", "user_score"]].copy()
    display.rename(columns={
        "code": "代码", "name": "名称", "price": "现价", "change_pct": "涨跌%",
        "short": "短期", "mid": "中期", "long": "长期", "composite": "综合",
        "trend_score": "趋势分", "vol_ratio": "量比", "user_score": "用户打分",
    }, inplace=True)

    def _chg_color(v):
        try:
            x = float(v)
        except Exception:
            return ""
        if x > 0:
            return "color:{_UP};font-weight:600"
        if x < 0:
            return "color:{_DOWN};font-weight:600"
        return "color:#9aa0a6"
    _styled = display.style.map(_chg_color, subset=["涨跌%"])
    st.dataframe(_styled, use_container_width=True, height=360,
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
        safe_switch_page("pages/个股研究.py")

    # 批量改评分
    st.markdown("**✏️ 修改用户打分**")
    st.caption("评分范围 0–100，越高越看好；拖动滑块选择，无法输入越界值。")
    with st.form(key=f"{pool_key}_score_form"):
        c1, c2, c3 = st.columns([0.4, 0.4, 0.2])
        with c1:
            edit_code = st.selectbox("选择股票", ["—"] + opts, key=f"{pool_key}_edit_code")
        with c2:
            existing = None
            if edit_code and edit_code != "—":
                existing = api_user_score(edit_code.split()[0])
            edit_score = st.slider(
                "新评分", min_value=0, max_value=100,
                value=existing if existing is not None else 50,
                step=1, key=f"{pool_key}_edit_score",
                help="拖动选择 0–100 之间的整数",
            )
        with c3:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("保存", use_container_width=True)
        if submitted:
            if edit_code and edit_code != "—":
                code = edit_code.split()[0]
                name = edit_code.split(maxsplit=1)[1] if " " in edit_code else ""
                api_save_user_score(code, int(edit_score), name)
                _toast("评分已更新")
                # 不调用 st.rerun()：form 提交已触发本 fragment 自然重跑
            else:
                st.warning("请先选择一只股票")

    # 移除按钮
    if on_remove:
        st.markdown("**🗑️ 移除股票**")
        remove_opts = [f"{r['code']} {r['name']}" for _, r in df.iterrows()]
        rem = st.selectbox("选择要移除的股票", ["—"] + remove_opts, key=f"{pool_key}_remove")
        if rem and rem != "—":
            if st.button("确认移除", key=f"{pool_key}_remove_btn"):
                on_remove(rem.split()[0])


# 自选股
@safe_fragment
def fragment_pool_watchlist():
    with st.expander("📌 自选股列表", expanded=False):
        sc, body = api_get("/api/watchlist")
        wl_items = []
        if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
            wl_items = body.get("data", []) or []
        if not wl_items:
            _empty_info("自选股为空。先到「股票选取」页面点击「加入自选股」添加。")
        else:
            codes = [_norm_code(it["stock_code"]) for it in wl_items if isinstance(it, dict) and it.get("stock_code")]
            id_map = {_norm_code(it["stock_code"]): it.get("id") for it in wl_items
                      if isinstance(it, dict) and it.get("stock_code")}
            scores = _load_scores_map(codes)
            df_wl = _build_pool_df(codes, scores)

            def _remove_wl(code: str):
                item_id = id_map.get(_norm_code(code))
                if item_id:
                    api_delete(f"/api/watchlist/{item_id}", timeout=5)
                    _toast("已移除")
                    # 不调用 st.rerun()：移除按钮点击已触发本 fragment 自然重跑

            _render_pool_table(df_wl, "watchlist", _remove_wl)


fragment_pool_watchlist()


# 垃圾股
@safe_fragment
def fragment_pool_junk():
    with st.expander("🗑️ 垃圾股列表", expanded=False):
        junk_items = api_junk_stocks()
        if not junk_items:
            _empty_info("垃圾股为空。先到「股票选取」页面点击「加入垃圾股」添加。")
        else:
            codes = [_norm_code(it["stock_code"]) for it in junk_items if isinstance(it, dict) and it.get("stock_code")]
            id_map = {_norm_code(it["stock_code"]): it.get("id") for it in junk_items
                      if isinstance(it, dict) and it.get("stock_code")}
            scores = _load_scores_map(codes)
            df_jk = _build_pool_df(codes, scores)

            def _remove_jk(code: str):
                item_id = id_map.get(_norm_code(code))
                if item_id:
                    api_remove_junk_stock(item_id)
                    _toast("已移除")
                    # 不调用 st.rerun()：移除按钮点击已触发本 fragment 自然重跑

            _render_pool_table(df_jk, "junk", _remove_jk)


fragment_pool_junk()
