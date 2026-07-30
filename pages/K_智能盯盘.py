"""
页面 K：智能盯盘聚合页（Smart Watch Board）

单屏实时聚合用户自选股的三类异动信号：
  1. 板块资金异动   —— 行业资金流向 TOP10（净流入红 / 净流出绿）
  2. 自选股涨跌榜   —— 并行抓取实时行情，按涨跌%排序，逐只跳转
  3. 个股资金流异动 —— 自选股主力净流入（真实优先 / 量价估算兜底）
  4. 预警触发       —— 规则扫描：涨跌超阈值 / 主力资金强异动

约定：
  - A股配色：净流入/上涨=红(UP)，净流出/下跌=绿(DOWN)
  - 交易时段（9:30-11:30 / 13:00-15:00）内各 fragment 自动 60s 刷新
  - 所有区块优雅降级：空数据→st.info，异常→st.error，不崩溃整页
"""
import streamlit as st
import pandas as pd
import concurrent.futures as cf
from datetime import datetime
from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, safe_switch_page, api_get, api_post, api_delete
from modules.fundflow import get_industry_fund_flow, get_individual_fund_flow
from modules.fetcher import StockFetcher
from modules.page_widgets import _empty_info, UP, DOWN, is_trading_now, _fmt_yi
from modules.page_guard import safe_fragment

apply_page_config(page_title="智能盯盘", page_icon="👁️", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("👁️ 智能盯盘聚合")
st.caption("⚠️ 数据仅供参考，不构成投资建议")

# ── 加法式：最近浏览 / 收藏 的 session 初始化（纯前端）──
if "_wl_recent" not in st.session_state:
    st.session_state._wl_recent = []
if "_wl_fav" not in st.session_state:
    st.session_state._wl_fav = []
lk1, lk2 = st.columns([1, 1])
with lk1:
    st.page_link("pages/3_事件追踪.py", label="🔔 事件追踪", icon="🔔")
with lk2:
    st.page_link("pages/个股研究.py", label="🔍 个股研究", icon="🔍")

try:
    from modules.autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

# ───────────────────────── 常量 / 配色 ─────────────────────────
MAIN_NET_STRONG = 1e8  # 主力净流入"强异动"阈值：1亿(元)

st.caption(
    "📡 聚合看板：板块资金异动 · 自选股涨跌榜 · 个股资金流异动 · 规则预警。"
    "交易时段内每 60 秒自动刷新；非交易时段数据刷新放缓。"
)


# ───────────────────────── 工具函数 ─────────────────────────


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()




def _quote_one(code):
    """线程安全：抓取单只实时行情。返回 (code, quote_dict|None)。"""
    try:
        q = fetcher.get_realtime_quote(code)
        return code, q
    except Exception:
        return code, None


def _ff_one(code):
    """线程安全：抓取单只主力资金流。返回 (code, result_dict)。"""
    try:
        r = get_individual_fund_flow(code)
        if not isinstance(r, dict):
            r = {"source": "none", "main_net": None}
        return code, r
    except Exception:
        return code, {"source": "none", "main_net": None}


def _quote_fields(q):
    """从行情 dict 防御性解析 现价/涨跌%/涨跌额/振幅。兼容多种字段命名。"""
    if not isinstance(q, dict):
        return None, None, None, None
    cur = q.get("cur")
    if cur is None:
        cur = q.get("current")
    prev = q.get("prev_close")
    if prev is None:
        prev = q.get("pre_close")
    chg = q.get("chg")
    change_amt = q.get("change_amt")
    amplitude = q.get("amplitude")
    try:
        cur = float(cur) if cur is not None else None
    except Exception:
        cur = None
    try:
        prev = float(prev) if prev is not None else None
    except Exception:
        prev = None
    if cur is None or prev in (None, 0):
        return cur, None, None, amplitude
    if chg is None:
        chg = (cur - prev) / prev * 100 if prev else 0.0
    if change_amt is None:
        change_amt = cur - prev
    if amplitude is None:
        high = q.get("high")
        low = q.get("low")
        try:
            high = float(high) if high is not None else None
            low = float(low) if low is not None else None
            amplitude = (high - low) / prev * 100 if (high and low) else None
        except Exception:
            amplitude = None
    try:
        chg = float(chg)
    except Exception:
        chg = None
    try:
        change_amt = float(change_amt)
    except Exception:
        change_amt = None
    try:
        amplitude = float(amplitude) if amplitude is not None else None
    except Exception:
        amplitude = None
    return cur, chg, change_amt, amplitude


def _color_chg(val):
    """Styler 回调：按涨跌%正负上色。"""
    try:
        v = float(val)
    except Exception:
        return ""
    if v > 0:
        return f"color:{UP};font-weight:600;"
    if v < 0:
        return f"color:{DOWN};font-weight:600;"
    return ""


def _color_net(val):
    """Styler 回调：按主力净流入正负上色。"""
    try:
        v = float(val)
    except Exception:
        return ""
    if v > 0:
        return f"color:{UP};font-weight:600;"
    if v < 0:
        return f"color:{DOWN};font-weight:600;"
    return ""


@st.cache_data(ttl=15, show_spinner=False)
def _fetch_watchlist():
    """抓取自选股列表，返回 [(code, name), ...]，全程防御。

    模块级缓存：本页 4 个 fragment（涨跌榜 / 个股资金流 / 预警 / 关注列表）都会取自选股，
    交易时段每 60s 自动刷新会重复请求；缓存 15s 收敛为单次调用（不含 st.rerun/switch_page，线程安全）。
    """
    try:
        sc, body = api_get("/api/watchlist", timeout=10)
    except Exception as e:
        return None, f"网络错误: {e}"
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        return [], f"加载自选股失败（code={sc}）。"
    items = body.get("data", []) or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = it.get("stock_code") or it.get("code")
        if not code:
            continue
        name = it.get("stock_name") or it.get("name") or str(code)
        out.append((str(code), str(name)))
    return out, None


@st.cache_data(ttl=15, show_spinner=False)
def _fetch_watchlist_full():
    """抓取自选股完整列表（含 id / note），供关注列表管理面板使用。

    同 _fetch_watchlist，模块级缓存避免与关注列表 fragment 的其它取数重复请求。
    """
    try:
        sc, body = api_get("/api/watchlist", timeout=10)
    except Exception as e:
        return None, f"网络错误: {e}"
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        return [], f"加载自选股失败（code={sc}）。"
    items = []
    for it in (body.get("data", []) or []):
        if not isinstance(it, dict):
            continue
        code = it.get("stock_code") or it.get("code")
        if not code:
            continue
        items.append({
            "id": it.get("id"),
            "code": str(code),
            "name": it.get("stock_name") or it.get("name") or str(code),
            "note": it.get("note") or "",
        })
    return items, None


def _grade_chg(chg):
    """异动分级：|涨跌幅| ≥7% 强 / ≥3% 中 / 其余 弱。返回 (tier, color, label)。"""
    try:
        a = abs(float(chg))
    except Exception:
        return "weak", "#888888", "弱"
    if a >= 7:
        return ("strong", UP if chg > 0 else DOWN, "强")
    if a >= 3:
        return ("mid", UP if chg > 0 else DOWN, "中")
    return ("weak", "#888888", "弱")


def _grade_net(net):
    """资金异动分级：|净额| ≥5亿 强 / ≥1亿 中 / 其余 弱。返回 (tier, color, label)。"""
    try:
        v = abs(float(net))
    except Exception:
        return "weak", "#888888", "弱"
    if v >= 5e8:
        return ("strong", UP if net > 0 else DOWN, "强")
    if v >= 1e8:
        return ("mid", UP if net > 0 else DOWN, "中")
    return ("weak", "#888888", "弱")


def _resolve_name(code, *candidates):
    """统一解析真实股票名称：优先用非代码本身的候选（行情名 / 后端名），
    否则回退 fetcher 在线解析，最后兜底为代码本身。

    解决「关注列表只显示 6 位代码、不显示名称」的问题：后端 watchlist 未存名称时
    名称会等于代码，这里自动改为用 fetcher 解析真实名称。
    """
    code_s = str(code).strip()
    for c in candidates:
        if c and str(c).strip() and str(c).strip() != code_s:
            return str(c).strip()
    try:
        n = fetcher.get_name_only(code)
        if n and str(n).strip() and str(n).strip() != code_s:
            return str(n).strip()
    except Exception:
        pass
    return code_s


# ───────────────────────── 1. 板块资金异动 ─────────────────────────
@safe_fragment("板块资金异动")
def fragment_sector():
    st.markdown("### 🏭 板块资金异动")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, key="sector_auto")

    try:
        with st.spinner("⏳ 正在加载行业资金流向…"):
            df = get_industry_fund_flow()
    except Exception as e:
        st.error(f"行业资金流向加载失败：{e}")
        if st.button("🔄 重试", key="btn_sector_retry"):
            st.rerun(scope="fragment")
        return

    try:
        import plotly.graph_objects as go
    except Exception as e:
        st.error(f"绘图组件加载失败：{e}")
        return

    if df is None or df.empty:
        _empty_info("暂无行业资金流向数据")
        return

    if "净额" not in df.columns or "行业" not in df.columns:
        _empty_info("行业资金流向数据字段缺失，暂无法展示。")
        return

    try:
        df["净额"] = pd.to_numeric(df["净额"], errors="coerce")
        if "涨跌幅" in df.columns:
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    except Exception:
        pass

    top = df.dropna(subset=["净额"]).sort_values("净额", ascending=False).head(10).copy()
    if top.empty:
        _empty_info("暂无有效的行业净额数据")
        return

    # 加法式：图表类型切换（柱状 / 折线 / 面积，不改数据）
    _ctype = st.radio("图表类型", ["柱状", "折线", "面积"], index=0, key="sector_chart_type", horizontal=True)
    colors = [UP if v >= 0 else DOWN for v in top["净额"]]
    if _ctype == "折线":
        fig = go.Figure(go.Scatter(
            x=top["净额"], y=top["行业"], mode="markers+lines",
            marker=dict(color=colors, size=10), line=dict(color="#3498db", width=2),
            hovertemplate="%{y}<br>净额：%{x:.2f}亿<extra></extra>",
        ))
    elif _ctype == "面积":
        fig = go.Figure(go.Scatter(
            x=top["净额"], y=top["行业"], mode="lines",
            line=dict(color="#3498db", width=2), fill="tozerox",
            fillcolor="rgba(150,150,150,0.18)",
            hovertemplate="%{y}<br>净额：%{x:.2f}亿<extra></extra>",
        ))
    else:
        fig = go.Figure(go.Bar(
            x=top["净额"], y=top["行业"],
            orientation="h", marker_color=colors,
            hovertemplate="%{y}<br>净额：%{x:.2f}亿<extra></extra>",
        ))
    fig = go.Figure(fig)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=20, t=30, b=20), height=380,
        title="净流入 TOP10 行业（亿元）",
        font=dict(color="#e6e6e6" if dark else "#1a1a1a"),
        xaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec"),
        yaxis=dict(gridcolor="#2a2a3a" if dark else "#ececec", autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("净流入行业领涨：横条越长代表当日主力净流入越多（红=净流入 / 绿=净流出）。")
    st.caption("数据来源：东方财富 / 同花顺 行业资金流向")

    show_cols = [c for c in ["行业", "涨跌幅", "流入资金", "流出资金", "净额", "领涨股", "领涨股涨跌幅"] if c in top.columns]
    if not show_cols:
        _empty_info("板块明细列名与预期不符，暂无法以表格展示（图表仍可用）。")
        return
    st.dataframe(
        top[show_cols], use_container_width=True, hide_index=True,
        column_config={
            "净额": st.column_config.NumberColumn("净额(亿)", format="%.2f"),
            "涨跌幅": st.column_config.NumberColumn("涨跌幅%", format="%.2f"),
            "流入资金": st.column_config.NumberColumn("流入(亿)", format="%.2f"),
            "流出资金": st.column_config.NumberColumn("流出(亿)", format="%.2f"),
        },
    )


# ───────────────────────── 2. 自选股涨跌榜 ─────────────────────────
@safe_fragment("自选股涨跌榜")
def fragment_watchlist():
    st.markdown("### 📈 自选股涨跌榜")
    st.caption("涨跌% = (现价-昨收)/昨收×100%，红涨绿跌；并行抓取实时行情后按涨跌%排序，可逐只跳转行情看板。")

    # 加法式：最近浏览历史（纯前端 chips，点击填入筛选）
    _rv = st.session_state.get("_wl_recent", [])
    if _rv:
        st.caption("🕘 最近浏览（点击填入筛选）")
        _rcs = st.columns(min(len(_rv), 6))
        for _i, _t in enumerate(_rv[:6]):
            with _rcs[_i]:
                if st.button(_t, key=f"wl_recent_{_i}"):
                    st.session_state["wl_filter_q"] = _t
                    st.rerun(scope="fragment")
    # ── 自定义筛选 ──
    fq, frng, falert = st.columns([2, 2, 1])
    wl_q = fq.text_input("🔍 名称/代码筛选", value="", key="wl_filter_q", placeholder="留空=全部")
    wl_rng = frng.slider("涨跌%范围", -10.0, 10.0, (-10.0, 10.0), 0.5, key="wl_filter_rng")
    wl_only_alert = falert.checkbox("仅看预警", value=False, key="wl_only_alert",
                                          help="只显示触发涨跌异动阈值（预警页设置）的标的。")
    # 加法式 UX：一键清空自选股涨跌榜的筛选条件（点击即重跑本 fragment，控件 key 反映重置值）
    if st.button("🔄 清空筛选", key="wl_reset",
                 help="清空名称/代码筛选、涨跌区间与「仅看预警」，恢复全部标的"):
        st.session_state["wl_filter_q"] = ""
        st.session_state["wl_filter_rng"] = (-10.0, 10.0)
        st.session_state["wl_only_alert"] = False
    # 加法式：手动刷新（fragment 内 scope="fragment" 局部重跑）
    if st.button("🔄 刷新", key="wl_manual_refresh", help="手动刷新本板块实时行情"):
        st.rerun(scope="fragment")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, key="wl_auto")

    items, err = _fetch_watchlist()
    if err is not None:
        st.error(err)
        return
    if not items:
        _empty_info("自选股为空，暂无盯盘项。请先添加关注的股票（可前往「形态选股」或行情看板一键关注），添加后本页将自动聚合异动信号。")
        if st.button("➡️ 去形态选股添加", key="wl_empty_go"):
            safe_switch_page("pages/B_形态选股.py")
        # 加法式：示例数据预览（只读，无数据时展示样例结构）
        if st.button("👀 查看示例", key="wl_sample"):
            _sample = pd.DataFrame([
                {"代码": "600519", "名称": "贵州茅台", "现价": 1680.00, "涨跌%": 2.35, "涨跌额": 38.50},
                {"代码": "000858", "名称": "五粮液", "现价": 152.30, "涨跌%": -1.20, "涨跌额": -1.85},
                {"代码": "601318", "名称": "中国平安", "现价": 48.60, "涨跌%": 0.42, "涨跌额": 0.20},
            ])
            st.dataframe(_sample, use_container_width=True, hide_index=True)
        return

    codes = [c for c, _ in items]
    names = {c: n for c, n in items}

    with st.spinner(f"并行获取 {len(codes)} 只自选股实时行情…"):
        quotes = {}
        try:
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                for code, q in ex.map(_quote_one, codes):
                    quotes[code] = q
        except Exception as e:
            st.error(f"行情并行抓取失败：{e}")
            if st.button("🔄 重试", key="btn_wl_retry"):
                st.rerun(scope="fragment")
            return

    # 守卫：若全部标的实时行情均不可用（接口受限/网络异常），给出友好空态而非静默空表
    if not quotes or all(q is None for q in quotes.values()):
        _empty_info("实时行情暂不可用（接口受限或网络异常），稍后重试即可；可前往行情看板确认数据源状态。")
        return

    rows = []
    for code in codes:
        q = quotes.get(code)
        cur, chg, change_amt, amplitude = _quote_fields(q)
        name = _resolve_name(code, (q.get("name") if q else None), names.get(code))
        rows.append({
            "代码": code,
            "名称": name,
            "现价": round(cur, 2) if cur is not None else None,
            "涨跌%": round(chg, 2) if chg is not None else None,
            "涨跌额": round(change_amt, 2) if change_amt is not None else None,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("涨跌%", ascending=False, na_position="last").reset_index(drop=True)

    # ── 应用自定义筛选 ──
    if wl_q:
        q = wl_q.strip().lower()
        df = df[df.apply(
            lambda r: (q in str(r["代码"]).lower()) or (q in str(r["名称"]).lower()), axis=1)]
    lo, hi = wl_rng
    df = df[(df["涨跌%"].fillna(-999) >= lo) & (df["涨跌%"].fillna(999) <= hi)]
    if wl_only_alert:
        thr = float(st.session_state.get("smart_alert_threshold", 3.0))
        df = df[df["涨跌%"].fillna(0).abs() >= thr]

    if df.empty:
        _empty_info("筛选后无匹配标的（可放宽筛选条件）。")
        return

    try:
        styled = df.style.map(_color_chg, subset=["涨跌%"])
        st.dataframe(styled, use_container_width=True, hide_index=True,
                     column_config={
                         "现价": st.column_config.NumberColumn(format="%.2f"),
                         "涨跌%": st.column_config.NumberColumn(format="%.2f%%"),
                         "涨跌额": st.column_config.NumberColumn(format="%.2f"),
                     })
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={
                         "现价": st.column_config.NumberColumn(format="%.2f"),
                         "涨跌%": st.column_config.NumberColumn(format="%.2f%%"),
                         "涨跌额": st.column_config.NumberColumn(format="%.2f"),
                     })

    st.caption(f"📊 当前显示 {len(df)} / 总计 {len(codes)} 只自选股")
    st.caption("数据来源：东方财富 / 新浪财经 实时行情")

    # 逐只跳转
    with st.expander("📌 逐只跳转至行情看板", expanded=False):
        # 加法式：分页/加载更多（仅显示前 N 只，避免长列表刷屏）
        _jump_key = "wl_jump_n"
        if _jump_key not in st.session_state:
            st.session_state[_jump_key] = 10
        _jump_total = len(rows)
        _jump_show = min(st.session_state[_jump_key], _jump_total)
        for r in rows[:_jump_show]:
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1.2])
            c1.write(f"`{r['代码']}`")
            c2.write(r["名称"])
            cc = UP if (r["涨跌%"] or 0) > 0 else (DOWN if (r["涨跌%"] or 0) < 0 else "#888")
            c3.markdown(f"<span style='color:{cc};font-weight:600;'>{r['涨跌%'] if r['涨跌%'] is not None else '—'}%</span>", unsafe_allow_html=True)
            with c4:
                # 加法式：收藏/星标（纯前端 session 集合）
                _fav = st.session_state.get("_wl_fav", [])
                _is = r["代码"] in _fav
                if st.button(("⭐" if _is else "☆"), key=f"wl_fav_{r['代码']}", help="收藏/取消收藏"):
                    if _is:
                        st.session_state._wl_fav = [x for x in _fav if x != r["代码"]]
                    else:
                        st.session_state._wl_fav = _fav + [r["代码"]]
                    st.rerun(scope="fragment")
                # 跳转并记入最近浏览
                if st.button("跳转", key=f"wl_go_{r['代码']}"):
                    _rv = st.session_state.get("_wl_recent", [])
                    if r["代码"] not in _rv:
                        st.session_state._wl_recent = ([r["代码"]] + _rv)[:8]
                    st.session_state["pick_stock_confirmed"] = r["代码"]
                    st.session_state["pick_stock_query"] = r["代码"]
                    safe_switch_page("pages/个股研究.py")
        if _jump_show < _jump_total:
            if st.button("显示更多 ▼", key="wl_jump_more"):
                st.session_state[_jump_key] = min(st.session_state[_jump_key] + 10, _jump_total)

        # 加法式：我的收藏（纯前端，列出已收藏标的并支持跳转）
        _fav = st.session_state.get("_wl_fav", [])
        if _fav:
            with st.expander(f"⭐ 我的收藏（{len(_fav)}）", expanded=False):
                for _fc in _fav:
                    _f1, _f2 = st.columns([3, 1])
                    _f1.write(f"`{_fc}`")
                    if _f2.button("跳转", key=f"wl_fav_go_{_fc}"):
                        st.session_state["pick_stock_confirmed"] = _fc
                        st.session_state["pick_stock_query"] = _fc
                        safe_switch_page("pages/个股研究.py")


# ───────────────────────── 3. 个股资金流异动 ─────────────────────────
@safe_fragment("个股资金流异动")
def fragment_individual_ff():
    st.markdown("### 💰 个股资金流异动")
    # ── 自定义筛选 ──
    d1, d2 = st.columns([2, 1])
    iff_dir = d1.selectbox("资金方向", ["全部", "仅净流入", "仅净流出"],
                           index=["全部", "仅净流入", "仅净流出"].index(
                               st.session_state.get("pref_iff_dir", "全部")),
                           key="iff_dir")
    # 加法式：偏好记忆（session 级记住上次选择，下次自动套用）
    st.session_state["pref_iff_dir"] = iff_dir
    iff_strong = d2.checkbox("仅看强异动(≥1亿)", value=False, key="iff_strong")
    iff_q = st.text_input("🔍 名称/代码筛选", value="", key="iff_filter_q", placeholder="留空=全部")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, key="iff_auto")

    items, err = _fetch_watchlist()
    if err is not None:
        st.error(err)
        return
    if not items:
        _empty_info("自选股为空，暂无盯盘项，暂无法展示个股资金流。请先添加关注的股票（可前往「形态选股」一键关注）。")
        if st.button("➡️ 去形态选股添加", key="iff_empty_go"):
            safe_switch_page("pages/B_形态选股.py")
        return

    codes = [c for c, _ in items]
    names = {c: n for c, n in items}

    with st.spinner(f"并行获取 {len(codes)} 只自选股主力资金流…"):
        ff_map = {}
        try:
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                for code, r in ex.map(_ff_one, codes):
                    ff_map[code] = r
        except Exception as e:
            st.error(f"资金流并行抓取失败：{e}")
            if st.button("🔄 重试", key="btn_iff_retry"):
                st.rerun(scope="fragment")
            return

    rows = []
    for code in codes:
        r = ff_map.get(code, {})
        main_net = r.get("main_net")
        source = r.get("source", "none")
        name = _resolve_name(code, names.get(code))
        rows.append({
            "代码": code,
            "名称": name,
            "主力净流入(亿)": round(main_net / 1e8, 3) if isinstance(main_net, (int, float)) else None,
            "来源": "实时" if source == "akshare" else ("估算" if source == "estimate" else "无数据"),
        })

    df = pd.DataFrame(rows)
    valid = df.dropna(subset=["主力净流入(亿)"]).copy() if not df.empty else df
    if valid.empty:
        _empty_info("当前自选股暂无可用主力资金流数据（接口受限）。")
        return

    valid = valid.sort_values("主力净流入(亿)", ascending=False).reset_index(drop=True)
    # 加法式：列表内搜索/筛选框（纯前端过滤）
    if iff_q.strip():
        q = iff_q.strip().lower()
        valid = valid[valid.apply(
            lambda r: (q in str(r["代码"]).lower()) or (q in str(r["名称"]).lower()), axis=1)]
    if iff_dir == "仅净流入":
        valid = valid[valid["主力净流入(亿)"] > 0]
    elif iff_dir == "仅净流出":
        valid = valid[valid["主力净流入(亿)"] < 0]
    if iff_strong:
        valid = valid[valid["主力净流入(亿)"].abs() >= 1.0]
    if valid.empty:
        _empty_info("按当前筛选条件无匹配标的。")
        return
    top_in = valid.head(5)
    top_out = valid.sort_values("主力净流入(亿)").head(5)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**🔺 主力净流入 TOP**")
        try:
            styled = top_in.style.map(_color_net, subset=["主力净流入(亿)"])
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         column_config={"主力净流入(亿)": st.column_config.NumberColumn(format="%.3f")})
        except Exception:
            st.dataframe(top_in, use_container_width=True, hide_index=True,
                         column_config={"主力净流入(亿)": st.column_config.NumberColumn(format="%.3f")})
    with col_r:
        st.markdown("**🔻 主力净流出 TOP**")
        try:
            styled = top_out.style.map(_color_net, subset=["主力净流入(亿)"])
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         column_config={"主力净流入(亿)": st.column_config.NumberColumn(format="%.3f")})
        except Exception:
            st.dataframe(top_out, use_container_width=True, hide_index=True,
                         column_config={"主力净流入(亿)": st.column_config.NumberColumn(format="%.3f")})

    st.caption(f"📊 当前展示 {len(valid)} / 总计 {len(codes)} 只自选股的资金流异动")
    st.caption("数据来源：东方财富 / 新浪财经 主力资金流")

    if any(r.get("source") == "estimate" for r in ff_map.values()):
        st.caption("⚠️ 标注「估算」的数据为量价模型（Chaikin 风格）估算的主力净流入，"
                   "仅反映近期量价博弈方向，非交易所逐笔主力数据。")


# ───────────────────────── 4. 预警触发 ─────────────────────────
@safe_fragment("预警触发扫描")
def fragment_alerts():
    st.markdown("### 🚨 预警触发（规则扫描）")
    if st_autorefresh is not None and is_trading_now():
        st_autorefresh(interval=60000, key="alert_auto")

    threshold = st.slider(
        "涨跌异动阈值 (%)", min_value=0.5, max_value=10.0, value=3.0, step=0.5,
        key="smart_alert_threshold",
        help="自选股当日涨跌%绝对值超过该阈值即触发「异动预警」。",
    )
    st.caption("规则扫描：自选股当日|涨跌%|≥阈值 触发异动预警；主力净流入/流出绝对值≥1亿 触发资金异动，按强/中/弱分级。")

    items, err = _fetch_watchlist()
    if err is not None:
        st.error(err)
        return
    if not items:
        _empty_info("自选股为空，暂无盯盘项，暂无可扫描标的。请先添加关注的股票，预警扫描才能生效。")
        return

    codes = [c for c, _ in items]
    names = {c: n for c, n in items}

    with st.spinner("并行扫描行情与资金流…"):
        quotes = {}
        ff_map = {}
        try:
            # 性能微优化：行情与资金流合并到单一线程池并行抓取，
            # 避免创建两个线程池的额外开销，且两者同时进行更省时
            with cf.ThreadPoolExecutor(max_workers=6) as ex:
                futs_q = {ex.submit(_quote_one, c): "q" for c in codes}
                futs_f = {ex.submit(_ff_one, c): "f" for c in codes}
                for fut in cf.as_completed(list(futs_q) + list(futs_f)):
                    res = fut.result()
                    if futs_q.get(fut) == "q":
                        quotes[res[0]] = res[1]
                    else:
                        ff_map[res[0]] = res[1]
        except Exception as e:
            st.error(f"预警扫描失败：{e}")
            if st.button("🔄 重试", key="btn_alert_retry"):
                st.rerun(scope="fragment")
            return

    alerts = []
    for code in codes:
        q = quotes.get(code)
        cur, chg, change_amt, _ = _quote_fields(q)
        name = _resolve_name(code, names.get(code))
        # 涨跌异动
        if chg is not None and abs(chg) >= threshold:
            tier, color, label = _grade_chg(chg)
            alerts.append({
                "类型": "异动预警",
                "代码": code,
                "名称": name,
                "说明": f"涨跌 {chg:+.2f}% ≥ 阈值 {threshold:.1f}%（{label}）",
                "tier": tier, "color": color,
            })
        # 资金异动
        r = ff_map.get(code, {})
        main_net = r.get("main_net")
        if isinstance(main_net, (int, float)) and abs(main_net) >= MAIN_NET_STRONG:
            tier, color, label = _grade_net(main_net)
            alerts.append({
                "类型": "资金异动",
                "代码": code,
                "名称": name,
                "说明": f"主力{'净流入' if main_net > 0 else '净流出'} {_fmt_yi(main_net)}（{label}）",
                "tier": tier, "color": color,
            })

    if not alerts:
        st.success("当前无触发预警 ✅（阈值 ±%.1f%%，主力强异动阈值 %s）" % (threshold, _fmt_yi(MAIN_NET_STRONG)))
        return

    from collections import Counter
    cnt = Counter(a["tier"] for a in alerts)
    st.warning(
        f"共触发 {len(alerts)} 条预警："
        f"🔴 强 {cnt.get('strong', 0)} ｜ 🟡 中 {cnt.get('mid', 0)} ｜ 🟢 弱 {cnt.get('weak', 0)}"
    )
    for a in alerts:
        color = a["color"]
        icon = {"strong": "🔴", "mid": "🟡", "weak": "🟢"}[a["tier"]]
        st.markdown(
            f'<div style="border-left:4px solid {color};background:rgba(128,128,128,0.08);'
            f'padding:8px 12px;margin:6px 0;border-radius:6px;">'
            f'{icon} <b>[{a["类型"]}]</b> `{a["代码"]}` {a["名称"]} ｜ {a["说明"]}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ───────────────────────── 0. 我的关注列表（管理） ─────────────────────────
@safe_fragment("关注列表")
def fragment_watch_manage():
    st.markdown("### ⭐ 我的关注列表")
    items, err = _fetch_watchlist_full()
    if err is not None:
        st.error(err)
        return
    # 添加关注
    a1, a2 = st.columns([3, 1])
    add_q = a1.text_input("➕ 添加关注（6 位代码）", value="", key="wl_add_q",
                              placeholder="如 600519",
                              help="输入 6 位数字代码（如 600519）后点击「添加」；也可在行情看板或形态选股中一键关注。")
    # 加法式：输入内联校验（实时提示，不阻塞提交）
    if add_q and add_q.strip():
        _q = add_q.strip()
        if not _q.isdigit():
            st.warning("⚠️ 请输入纯数字代码（如 600519），当前含非数字字符。")
        elif len(_q) != 6:
            st.warning(f"⚠️ 代码应为 6 位，当前为 {len(_q)} 位。")
    if a2.button("添加", key="wl_add_btn", use_container_width=True):
        raw = (add_q or "").strip()
        if not raw:
            st.warning("请输入代码")
        elif raw.isdigit():
            code = raw.zfill(6)
            sc, body = api_post("/api/watchlist", payload={"stock_code": code})
            if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
                st.toast(f"已添加 {code}")
            else:
                st.error(f"添加失败（{sc}）")
        else:
            st.warning("请输入 6 位数字代码（如 600519）")
    if not items:
        _empty_info("自选股为空，暂无盯盘项。可在「形态选股」或行情看板添加关注，也可直接在上方输入框添加 6 位代码。")
        if st.button("➡️ 去形态选股添加", key="wm_empty_go"):
            safe_switch_page("pages/B_形态选股.py")
        return
    st.caption(f"共 {len(items)} 只关注 · 实时涨跌 + 跳转 / 移除")

    # 加法式：危险写操作（取消关注全部）用 st.confirm 包裹，避免误触
    if st.button("🗑️ 取消关注全部", key="wm_clear_all"):
        if st.confirm("确定取消关注全部自选股？此操作不可撤销。", key="wm_clear_all_cfm"):
            _ok = 0
            _fail = 0
            for it in items:
                wid = it.get("id")
                if wid is not None:
                    dc, _ = api_delete(f"/api/watchlist/{wid}")
                    if dc == 200:
                        _ok += 1
                    else:
                        _fail += 1
            st.toast(f"已取消关注 {_ok} 只" + (f"，失败 {_fail} 只" if _fail else ""))

    # 实时涨跌 + 跳转 / 移除
    codes = [it["code"] for it in items]
    with st.spinner(f"获取 {len(codes)} 只实时行情…"):
        quotes = {}
        try:
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                for code, q in ex.map(_quote_one, codes):
                    quotes[code] = q
        except Exception:
            quotes = {}
    for it in items:
        code = it["code"]
        q = quotes.get(code)
        cur, chg, _, _ = _quote_fields(q)
        c1, c2, c3, c4, c5 = st.columns([1.3, 1.5, 1, 1, 1])
        c1.write(f"`{code}`")
        c2.write(_resolve_name(code, it.get("name")))
        cc = UP if (chg or 0) > 0 else (DOWN if (chg or 0) < 0 else "#888888")
        c3.markdown(
            f"<span style='color:{cc};font-weight:600;'>{chg:+.2f}%</span>" if chg is not None
            else "—", unsafe_allow_html=True)
        if c4.button("跳转", key=f"wm_go_{code}"):
            st.session_state["pick_stock_confirmed"] = code
            st.session_state["pick_stock_query"] = code
            safe_switch_page("pages/个股研究.py")
        _ck = f"wm_rm_cfm_{code}"
        if st.session_state.get(_ck):
            if c5.button("确认移除", key=f"wm_rm_cfm_btn_{code}", type="primary"):
                wid = it.get("id")
                if wid is not None:
                    dc, _ = api_delete(f"/api/watchlist/{wid}")
                    if dc == 200:
                        st.toast(f"已移除 {code}")
                    else:
                        st.error(f"移除失败（{dc}）")
                st.session_state.pop(_ck, None)
            if c5.button("取消", key=f"wm_rm_cancel_{code}"):
                st.session_state.pop(_ck, None)
        else:
            if c5.button("移除", key=f"wm_rm_{code}"):
                st.session_state[_ck] = True

    # 加法式：批量选择 + 操作（纯前端勾选，调用既有 api 取消关注选中）
    with st.expander("☑️ 批量管理（勾选后取消关注）", expanded=False):
        _sel = []
        for it in items:
            _code = it["code"]
            if st.checkbox(f"{_code} {_resolve_name(_code, it.get('name'))}", key=f"batch_{_code}"):
                _sel.append(_code)
        if st.button("🗑️ 取消关注选中", key="batch_remove_btn"):
            _ok = 0
            for it in items:
                if it["code"] in _sel and it.get("id") is not None:
                    dc, _ = api_delete(f"/api/watchlist/{it['id']}")
                    if dc == 200:
                        _ok += 1
            st.toast(f"已取消关注 {_ok} 只")


# ───────────────────────── 页面主体 ─────────────────────────
fragment_watch_manage()
st.markdown("---")
fragment_sector()
st.markdown("---")
fragment_watchlist()
st.markdown("---")
fragment_individual_ff()
st.markdown("---")
fragment_alerts()

# ── 加法式：可折叠使用说明（集合式帮助，纯提示）──
with st.expander("💡 使用说明", expanded=False):
    st.markdown("""
    **智能盯盘使用指引**
    - **板块资金异动**：行业主力净流入 TOP10（红=净流入 / 绿=净流出）。
    - **自选股涨跌榜**：实时行情按涨跌%排序，可筛选 / 逐只跳转。
    - **个股资金流异动**：主力净流入 TOP / 净流出 TOP。
    - **预警触发**：按阈值扫描涨跌与资金异动。
    - **我的关注列表**：添加 / 移除自选股。
    - ⚠️ 数据仅供参考，不构成投资建议。
    """)

# ── 加法式：键盘快捷键提示（纯提示，无实际绑定）──
with st.expander("⌨️ 快捷键", expanded=False):
    st.markdown("""
    本页为 Streamlit Web 应用，未绑定全局快捷键，以下为操作提示：
    - **回车**：在表单 / 输入框内按回车可触发提交。
    - **Tab**：在控件间切换焦点。
    - **浏览器 F5 / Cmd·Ctrl+R**：刷新整页（将丢失未保存的会话状态）。
    - 各板块「🔄 刷新」按钮可局部刷新对应模块。
    """)

# ── 加法式：快捷回到顶部（长页面底部注入固定按钮，平滑滚动父页面）──
st.components.v1.html(
    '<button onclick="parent.window.scrollTo({top:0,behavior:\'smooth\'});" '
    'style="position:fixed;right:24px;bottom:12px;z-index:9999;'
    'background:#3498db;color:#fff;border:none;border-radius:20px;'
    'padding:8px 14px;font-size:13px;cursor:pointer;'
    'box-shadow:0 2px 8px rgba(0,0,0,.3);">↑ 回到顶部</button>',
    height=40,
)
