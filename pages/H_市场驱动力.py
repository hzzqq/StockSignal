"""
页面 H：市场驱动力（核心指标与大盘趋势关联性全景图）

从「资金流向监控」拆分出的独立模块：21 指标按 资金/情绪/估值/宏观/技术 分 5 维
归一化子图面板，每维含上证(参考线)统一归一化到起点=100 叠加，规避量纲差异失真。
数据层见 modules/market_drivers.py。
"""
import streamlit as st

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.market_drivers import get_market_drivers, plot_drivers_panel, DIMS
from modules.linear_trends import to_trend_csv, plot_correlation_heatmap, _slice_date_range
from modules.page_widgets import _section_title, _trend_controls, _in_trading_hours, _empty_info

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

from modules.page_guard import safe_fragment

apply_page_config(page_title="市场驱动力", page_icon="🧮", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🧮 市场驱动力（五维归一化子图）")
st.caption("21 指标按 资金 / 情绪 / 估值 / 宏观 / 技术 分 5 维分组子图，每个子图含上证参考线，"
           "全部统一归一化到起点=100 叠加，规避量纲差异（融资余额万亿级 vs RSI 0-100 不会压扁）。")
st.page_link("pages/P_市场情绪.py", label="🌡️ 看《市场情绪》广度与情绪温度计（互补视角）", icon="🔗")


def _render_drivers_meta(meta):
    """渲染五维指标接入状态（哪些已接入 / 哪些暂未接入及原因）。"""
    if not meta:
        return
    lines = []
    for d in DIMS:
        info = meta.get(d)
        if not info:
            continue
        av = info.get("available") or []
        un = info.get("unavailable") or []
        if av and not un:
            lines.append(f"**{d}**：{len(av)} 项已接入 ✅")
        elif av and un:
            reasons = "；".join(f"{k}({r})" for k, r in un)
            lines.append(f"**{d}**：{len(av)} 项已接入 ✅ ｜ 暂未接入：{reasons}")
        else:
            reasons = "；".join(f"{k}({r})" for k, r in un)
            lines.append(f"**{d}**：暂未接入（{reasons}）")
    if lines:
        st.caption("📌 维度接入状态：" + "　".join(lines))


@safe_fragment
def fragment_drivers_panel():
    _section_title("🧭 核心指标与大盘趋势关联性全景图（五维归一化子图）", accent="#2b8aef")
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=60000, limit=200, key="drv_auto")
    try:
        with st.spinner("正在加载市场驱动力数据（约 180 天五维归一化）…"):
            df, meta = get_market_drivers(days=180)
    except Exception as e:
        st.error(f"市场驱动力数据加载失败：{e}")
        return
    if df is None or df.empty:
        _empty_info("暂无市场驱动力数据（网络/代理受限或数据源暂未接入）。")
        _render_drivers_meta(meta)
        return

    # 维度选择（五维分组子图）
    sel_dims = st.multiselect(
        "显示维度", options=DIMS, default=DIMS,
        format_func=lambda d: d, key="drv_dims",
        help="资金 / 情绪 / 估值 / 宏观 / 技术 五维分组子图",
    )
    # 交互控件：区间预设 + 序列多选（面板恒为归一化叠加，关闭均线/原始切换）
    series_options = [(c, c) for c in df.columns if c not in ("date", "ref")]
    # 加法式空态守卫（更深一层）：df 虽非空（仅含 date/ref 列）却没有可用指标序列时，
    # 跳过面板/热力图渲染，给出友好空态而非空白图或异常；meta 仍展示维度接入状态。
    if not series_options:
        _empty_info("暂无可用于驱动力的指标序列（数据仅含日期/参考列），面板暂不可绘制。")
        _render_drivers_meta(meta)
        return
    dr, _ma, sel, _m, _mt = _trend_controls(
        "drv", days_default=180, preset_default="近180天",
        series_options=series_options, show_ma=False,
    )
    # 加法式空态守卫（Batch15）：用户在区间控件中清空序列选择时 sel 为空，
    # 此时绘制会得到空白/异常图；提前给出友好提示，不影响下方数据表与热力图。
    if not sel:
        st.info("请在上方区间控件中至少选择一个指标序列，以绘制驱动力面板。")
    else:
        try:
            fig = plot_drivers_panel(
                df, meta=meta, dark_mode=dark,
                dims=sel_dims or DIMS, date_range=dr, selected=sel,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="drv_panel")
        except Exception as e:
            st.warning(f"驱动力面板图渲染失败：{e}")

    # 加法式可访问性（第十四批）：plotly 图表对读屏软件不友好，补充一段文字版「涨跌概览」
    # 作为图表替代文本，让无法看图的用户也能获取各指标区间内累计变化的关键信息。
    try:
        _ind_cols = [c for c in df.columns if c not in ("date", "ref")]
        _sub = df.dropna(subset=["date"]).set_index("date")
        _chg = {}
        for _c in _ind_cols:
            _s = _sub[_c].dropna()
            if len(_s) >= 2:
                _chg[_c] = float(_s.iloc[-1] - _s.iloc[0])
        if _chg:
            _up = sorted(_chg.items(), key=lambda kv: kv[1], reverse=True)[:3]
            _dn = sorted(_chg.items(), key=lambda kv: kv[1])[:3]
            st.caption(
                "📊 图表文字版概览（各指标区间内累计变化，单位：点）："
                "　↑ " + "，".join(f"{k} +{v:.1f}" for k, v in _up)
                + "　↓ " + "，".join(f"{k} {v:.1f}" for k, v in _dn)
            )
    except Exception:
        pass

    # 数据表联动（随区间 / 序列筛选）
    with st.expander("📋 数据表（随区间 / 序列联动）"):
        tbl = _slice_date_range(df, dr)
        if sel:
            keep = [c for c in sel if c in tbl.columns]
            tbl = tbl[["date"] + keep] if keep else tbl[["date"]]
        st.dataframe(tbl, use_container_width=True, hide_index=True)
    # 导出 CSV
    try:
        csv = to_trend_csv(df, names_map=None, selected=sel, date_range=dr)
        st.download_button("⬇️ 导出 CSV", data=csv, file_name="市场驱动力全景.csv", mime="text/csv")
    except Exception as e:
        st.warning(f"CSV 导出失败：{e}")
    # 相关性热力图
    try:
        st.plotly_chart(plot_correlation_heatmap(df, names_map=None, selected=sel,
                                                 date_range=dr, dark_mode=dark),
                        use_container_width=True, config={"displayModeBar": False}, key="drv_corr")
    except Exception as e:
        st.warning(f"相关性热力图渲染失败：{e}")
    _render_drivers_meta(meta)
    st.caption("📈 《核心指标与大盘趋势关联性全景图》（五维归一化子图）：资金/情绪/估值/宏观/技术分 5 个子图，"
               "每个子图内所有指标与上证指数**统一归一化到起点=100** 叠加，规避量纲差异导致的失真"
               "（融资余额万亿级 vs RSI 0-100 不会压扁）；上证作虚线参考线，看指标与大盘的领先/背离。"
               "对应命名：日常监测《大盘指数-多因子归一化叠加走势图》/《大盘指数多维度驱动力关联监测图》，"
               "研报《指数驱动力分组子图监测面板（Python可视化）》，PPT《核心指标与大盘趋势关联性全景图》。")


# ───────────────────────── 页面主体 ─────────────────────────
fragment_drivers_panel()
