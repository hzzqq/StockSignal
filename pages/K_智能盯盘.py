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
from modules.session import require_auth, render_user_badge, safe_switch_page, api_get
from modules.fundflow import get_industry_fund_flow, get_individual_fund_flow
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input

apply_page_config(page_title="智能盯盘", page_icon="👁️", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("👁️ 智能盯盘聚合")

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

# ───────────────────────── 常量 / 配色 ─────────────────────────
UP = "#ee2a2a"      # 红：涨 / 净流入
DOWN = "#1aa260"    # 绿：跌 / 净流出
MAIN_NET_STRONG = 1e8  # 主力净流入"强异动"阈值：1亿(元)

st.caption(
    "📡 聚合看板：板块资金异动 · 自选股涨跌榜 · 个股资金流异动 · 规则预警。"
    "交易时段内每 60 秒自动刷新；非交易时段数据刷新放缓。"
)


# ───────────────────────── 工具函数 ─────────────────────────
def _in_trading_hours():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (570 <= hm <= 690) or (780 <= hm <= 900)


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _fmt_yi(x):
    """金额(元) → 亿/万 文本，降级为 —。"""
    try:
        x = float(x)
    except Exception:
        return "—"
    if x == 0:
        return "0"
    if abs(x) >= 1e8:
        return f"{x / 1e8:.2f}亿"
    if abs(x) >= 1e4:
        return f"{x / 1e4:.1f}万"
    return f"{x:.0f}"


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


def _fetch_watchlist():
    """抓取自选股列表，返回 [(code, name), ...]，全程防御。"""
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


# ───────────────────────── 1. 板块资金异动 ─────────────────────────
@st.fragment
def fragment_sector():
    st.markdown("### 🏭 板块资金异动")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, key="sector_auto")

    try:
        df = get_industry_fund_flow()
    except Exception as e:
        st.error(f"行业资金流向加载失败：{e}")
        return

    import plotly.graph_objects as go

    if df is None or df.empty:
        st.info("暂无行业资金流向数据。")
        return

    try:
        df["净额"] = pd.to_numeric(df["净额"], errors="coerce")
        df["涨跌幅"] = pd.to_numeric(df.get("涨跌幅"), errors="coerce")
    except Exception:
        pass

    top = df.dropna(subset=["净额"]).sort_values("净额", ascending=False).head(10).copy()
    if top.empty:
        st.info("暂无有效的行业净额数据。")
        return

    colors = [UP if v >= 0 else DOWN for v in top["净额"]]
    fig = go.Bar(
        x=top["净额"], y=top["行业"],
        orientation="h", marker_color=colors,
        hovertemplate="%{y}<br>净额：%{x:.2f}亿<extra></extra>",
    )
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

    show_cols = [c for c in ["行业", "涨跌幅", "流入资金", "流出资金", "净额", "领涨股", "领涨股涨跌幅"] if c in top.columns]
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
@st.fragment
def fragment_watchlist():
    st.markdown("### 📈 自选股涨跌榜")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, key="wl_auto")

    items, err = _fetch_watchlist()
    if err is not None:
        st.error(err)
        return
    if not items:
        st.info("自选股为空，请先添加关注的股票。")
        if st.button("➡️ 去形态选股添加", key="wl_empty_go"):
            safe_switch_page("pages/B_形态选股.py")
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
            return

    rows = []
    for code in codes:
        q = quotes.get(code)
        cur, chg, change_amt, amplitude = _quote_fields(q)
        if q and q.get("name"):
            name = q.get("name")
        else:
            name = names.get(code) or fetcher.get_stock_name(code) or code
        rows.append({
            "代码": code,
            "名称": name,
            "现价": round(cur, 2) if cur is not None else None,
            "涨跌%": round(chg, 2) if chg is not None else None,
            "涨跌额": round(change_amt, 2) if change_amt is not None else None,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("涨跌%", ascending=False, na_position="last").reset_index(drop=True)

    if df.empty:
        st.info("暂无行情数据。")
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

    # 逐只跳转
    with st.expander("📌 逐只跳转至行情看板", expanded=False):
        for r in rows:
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1.2])
            c1.write(f"`{r['代码']}`")
            c2.write(r["名称"])
            cc = UP if (r["涨跌%"] or 0) > 0 else (DOWN if (r["涨跌%"] or 0) < 0 else "#888")
            c3.markdown(f"<span style='color:{cc};font-weight:600;'>{r['涨跌%'] if r['涨跌%'] is not None else '—'}%</span>", unsafe_allow_html=True)
            if c4.button("跳转", key=f"wl_go_{r['代码']}"):
                st.session_state["pick_stock_confirmed"] = r["代码"]
                st.session_state["pick_stock_query"] = r["代码"]
                safe_switch_page("pages/1_股票选取.py")


# ───────────────────────── 3. 个股资金流异动 ─────────────────────────
@st.fragment
def fragment_individual_ff():
    st.markdown("### 💰 个股资金流异动")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, key="iff_auto")

    items, err = _fetch_watchlist()
    if err is not None:
        st.error(err)
        return
    if not items:
        st.info("自选股为空，暂无法展示个股资金流。")
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
            return

    rows = []
    for code in codes:
        r = ff_map.get(code, {})
        main_net = r.get("main_net")
        source = r.get("source", "none")
        name = names.get(code) or fetcher.get_stock_name(code) or code
        rows.append({
            "代码": code,
            "名称": name,
            "主力净流入(亿)": round(main_net / 1e8, 3) if isinstance(main_net, (int, float)) else None,
            "来源": "实时" if source == "akshare" else ("估算" if source == "estimate" else "无数据"),
        })

    df = pd.DataFrame(rows)
    valid = df.dropna(subset=["主力净流入(亿)"]).copy() if not df.empty else df
    if valid.empty:
        st.info("当前自选股暂无可用主力资金流数据（接口受限）。")
        return

    valid = valid.sort_values("主力净流入(亿)", ascending=False).reset_index(drop=True)
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

    if any(r.get("source") == "estimate" for r in ff_map.values()):
        st.caption("⚠️ 标注「估算」的数据为量价模型（Chaikin 风格）估算的主力净流入，"
                   "仅反映近期量价博弈方向，非交易所逐笔主力数据。")


# ───────────────────────── 4. 预警触发 ─────────────────────────
@st.fragment
def fragment_alerts():
    st.markdown("### 🚨 预警触发（规则扫描）")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, key="alert_auto")

    threshold = st.slider(
        "涨跌异动阈值 (%)", min_value=0.5, max_value=10.0, value=3.0, step=0.5,
        key="smart_alert_threshold",
        help="自选股当日涨跌%绝对值超过该阈值即触发「异动预警」。",
    )

    items, err = _fetch_watchlist()
    if err is not None:
        st.error(err)
        return
    if not items:
        st.info("自选股为空，暂无可扫描标的。")
        return

    codes = [c for c, _ in items]
    names = {c: n for c, n in items}

    with st.spinner("并行扫描行情与资金流…"):
        quotes = {}
        ff_map = {}
        try:
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                for code, q in ex.map(_quote_one, codes):
                    quotes[code] = q
            with cf.ThreadPoolExecutor(max_workers=4) as ex:
                for code, r in ex.map(_ff_one, codes):
                    ff_map[code] = r
        except Exception as e:
            st.error(f"预警扫描失败：{e}")
            return

    alerts = []
    for code in codes:
        q = quotes.get(code)
        cur, chg, change_amt, _ = _quote_fields(q)
        name = names.get(code) or fetcher.get_stock_name(code) or code
        # 涨跌异动
        if chg is not None and abs(chg) >= threshold:
            alerts.append({
                "类型": "异动预警",
                "代码": code,
                "名称": name,
                "说明": f"涨跌 {chg:+.2f}% ≥ 阈值 {threshold:.1f}%",
                "severity": "up" if chg > 0 else "down",
            })
        # 资金异动
        r = ff_map.get(code, {})
        main_net = r.get("main_net")
        if isinstance(main_net, (int, float)) and abs(main_net) >= MAIN_NET_STRONG:
            alerts.append({
                "类型": "资金异动",
                "代码": code,
                "名称": name,
                "说明": f"主力{'净流入' if main_net > 0 else '净流出'} {_fmt_yi(main_net)}",
                "severity": "up" if main_net > 0 else "down",
            })

    if not alerts:
        st.success("当前无触发预警 ✅（阈值 ±%.1f%%，主力强异动阈值 %s）" % (threshold, _fmt_yi(MAIN_NET_STRONG)))
        return

    st.warning(f"共触发 {len(alerts)} 条预警：")
    for a in alerts:
        color = UP if a["severity"] == "up" else DOWN
        icon = "🔴" if a["severity"] == "up" else "🟢"
        st.markdown(
            f'<div style="border-left:4px solid {color};background:rgba(128,128,128,0.08);'
            f'padding:8px 12px;margin:6px 0;border-radius:6px;">'
            f'{icon} <b>[{a["类型"]}]</b> `{a["代码"]}` {a["名称"]} ｜ {a["说明"]}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ───────────────────────── 页面主体 ─────────────────────────
fragment_sector()
st.markdown("---")
fragment_watchlist()
st.markdown("---")
fragment_individual_ff()
st.markdown("---")
fragment_alerts()
