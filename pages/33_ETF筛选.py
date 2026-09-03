"""
ETF / 基金筛选器
------------------
按类型、关键字、涨跌幅、成交额等条件筛选 A 股 ETF / 基金，并支持排序与对比。

  • 优先取 akshare 实时 ETF 行情（fund_etf_spot_em）
  • 网络不可用时降级到内置常见 ETF 样本，保证筛选器始终可用
  • 各取数区块独立隔离（safe_section）
"""
import streamlit as st
import pandas as pd

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric
import modules.scroll_nav as sn
from modules.page_guard import safe_section

from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info, UP, DOWN

from modules.ui_kit import xc_success_box, xc_warn_box
dark = render_standard_page(
    title="ETF / 基金筛选器", icon="🧰",
    caption="按类型、关键字、涨跌幅与成交额筛选；红涨绿跌。数据受限时自动降级到样本。",
)
sf_card("🧰 ETF / 基金筛选器", "按类型、关键字、涨跌幅与成交额筛选 A 股 ETF / 基金，支持排序与对比；数据受限时自动降级到样本，保证筛选器始终可用。", icon="🔎")

# 页面间快捷跳转（#Batch19-5）：相关页面一键直达
_pl1, _pl2, _pl3 = st.columns(3)
with _pl1:
    st.page_link("pages/24_个股研究.py", label="📈 个股研究", icon="📈")
with _pl2:
    st.page_link("pages/46_自选股监控.py", label="⭐ 自选股监控", icon="⭐")
with _pl3:
    st.page_link("pages/47_价格预警.py", label="🔔 价格预警", icon="🔔")

# 可折叠使用说明 / 快捷键提示（#Batch20-5 / #Batch20-9）：集合式帮助，纯前端折叠
with st.expander("💡 使用说明 / 常见问题"):
    st.markdown(
        "- **筛选条件**：按关键字 / 类型 / 涨跌幅区间 / 最小成交额过滤 ETF，并可排序。\n"
        "- **走势图**：可切换「线 / 柱 / 面积」三种图表类型查看涨跌幅分布。\n"
        "- **收藏与批量**：用多选框勾选若干 ETF，可批量加入收藏或移出。\n"
        "- **手动刷新**：点击「🔄 刷新行情」重新拉取实时数据（失败自动降级样本）。\n"
        "- **风险提示**：筛选器仅为信息聚合，不构成任何投资建议。"
    )
with st.expander("⌨️ 快捷键提示"):
    st.markdown(
        "- 本页以鼠标 / 触控操作为主，无全局键盘快捷键。\n"
        "- 长表格滚动后点击「↑ 回到顶部」可一键回顶。\n"
        "- 走势图类型用「线 / 柱 / 面积」单选按钮即时切换。"
    )


# 内置样本（网络不可用时使用），覆盖主流宽基 / 行业 / 债券 / 货币 ETF
SAMPLE = [
    ("510300", "沪深300ETF", "宽基", 3.92, 0.45, 2850.0, 0.15, "沪深300"),
    ("510500", "中证500ETF", "宽基", 5.78, -0.32, 1020.0, 0.15, "中证500"),
    ("510050", "上证50ETF", "宽基", 2.63, 0.71, 1560.0, 0.15, "上证50"),
    ("159915", "创业板ETF", "宽基", 2.18, 1.12, 980.0, 0.15, "创业板指"),
    ("588000", "科创50ETF", "宽基", 1.02, -1.05, 760.0, 0.15, "科创50"),
    ("512660", "军工ETF", "行业", 1.05, 2.31, 142.0, 0.50, "中证军工"),
    ("512010", "医药ETF", "行业", 0.62, -0.88, 210.0, 0.50, "沪深300医药"),
    ("515030", "新能源ETF", "行业", 0.98, 1.56, 88.0, 0.50, "中证新能源"),
    ("512760", "芯片ETF", "行业", 1.12, 3.04, 176.0, 0.50, "中证半导体"),
    ("515790", "光伏ETF", "行业", 1.34, -2.10, 132.0, 0.50, "中证光伏"),
    ("561230", "化工ETF", "行业", 0.92, 0.66, 12.0, 0.50, "中证细分化工"),
    ("518880", "黄金ETF", "商品", 5.46, 0.42, 320.0, 0.50, "上海金"),
    ("511260", "十年国债ETF", "债券", 115.3, 0.03, 28.0, 0.15, "上证10年国债"),
    ("511380", "可转债ETF", "债券", 11.02, -0.12, 56.0, 0.30, "中证转债"),
    ("511990", "货币ETF", "货币", 100.0, 0.01, 1200.0, 0.15, "货币"),
    ("159919", "沪深300ETF(深)", "宽基", 3.91, 0.44, 680.0, 0.15, "沪深300"),
    ("159949", "创业板50ETF", "宽基", 0.96, 1.34, 220.0, 0.15, "创业板50"),
    ("513050", "中概互联网ETF", "行业", 1.08, 2.78, 410.0, 0.60, "中国互联网50"),
    ("513100", "纳指ETF", "QDII", 1.36, 1.21, 130.0, 0.60, "纳斯达克100"),
    ("159920", "恒生ETF", "QDII", 1.18, 0.92, 156.0, 0.60, "恒生指数"),
]


@st.cache_data(ttl=180, show_spinner=False)
def _load_etfs():
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            df = df.rename(columns={
                "代码": "代码", "名称": "名称", "最新价": "最新价",
                "涨跌幅": "涨跌幅", "成交额": "成交额", "换手率": "换手率",
            })
            df["类型"] = "ETF"
            df["跟踪指数"] = ""
            df["管理费"] = ""
            keep = [c for c in ["代码", "名称", "类型", "最新价", "涨跌幅", "成交额", "换手率", "跟踪指数", "管理费"] if c in df.columns]
            return df[keep].copy(), "akshare 实时ETF行情"
    except Exception:
        pass
    # 降级：内置样本
    d = pd.DataFrame(SAMPLE, columns=["代码", "名称", "类型", "最新价", "涨跌幅", "成交额", "管理费", "跟踪指数"])
    return d, "内置样本（网络不可用）"


@safe_fragment
def _etf_filter_fragment():
    with safe_section("ETF 行情", hint="实时行情接口可能受网络限制，已自动降级到样本数据。"):
        with st.spinner("⏳ 正在加载 ETF 行情…"):
            df, src = _load_etfs()
        xc_success_box(f"数据来源：{src}　·　共 {len(df)} 只", icon="📡")
        # 手动刷新（#Batch20-1）：清缓存并重跑本 fragment 重新拉取行情
        if st.button("🔄 刷新行情", key="etf_manual_refresh"):
            _load_etfs.clear()
            st.rerun(scope="fragment")
        # 空态守卫：接口与降级样本均未返回记录时显式提示，避免「共 0 只」后
        # 筛选控件/结果区一片空白、用户不知发生了什么
        if df is None or df.empty:
            _empty_info("行情数据为空（实时接口与内置样本均未返回记录），暂无可筛选标的；请稍后重试或检查网络。")
            return

        # ── 筛选器 ──
        # 偏好记忆（#Batch20-10）：session 内记住上次筛选偏好，下次自动套用
        for _pk, _sk in [("etf_rem_type", "etf_type"), ("etf_rem_amt", "etf_amt"),
                         ("etf_rem_chg", "etf_chg"), ("etf_rem_kw", "etf_kw"),
                         ("etf_rem_sort", "etf_sort"), ("etf_rem_asc", "etf_asc")]:
            if _sk not in st.session_state and st.session_state.get(_pk) is not None:
                st.session_state[_sk] = st.session_state[_pk]
        st.markdown("### 🎚️ 筛选条件")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            kw = st.text_input("关键字 / 代码", placeholder="如 沪深300 / 510300", key="etf_kw",
                              help="支持 ETF 名称或代码模糊匹配，留空表示不按关键字过滤")
        with f2:
            types = ["全部"] + sorted(df["类型"].dropna().unique().tolist())
            ftype = st.selectbox("类型", types, key="etf_type",
                                  help="按 ETF 类型筛选；「全部」展示所有类型")
        with f3:
            chg_range = st.slider("涨跌幅区间(%)", -10.0, 10.0, (-10.0, 10.0), key="etf_chg",
                                   help="只保留涨跌幅落在该区间内的标的")
        with f4:
            min_amt = st.number_input("最小成交额(亿)", min_value=0.0, value=0.0, step=10.0, key="etf_amt",
                                      help="只保留成交额不低于该数值（亿元）的标的；0 表示不限制")

        # 加法式 UX：一键清空全部筛选条件（点击即重跑本 fragment，控件 key 反映重置值）
        if st.button("🔄 清空筛选", key="etf_reset",
                     help="一键清空关键字 / 类型 / 涨跌区间 / 成交额等筛选条件，恢复全部标的"):
            st.session_state["etf_kw"] = ""
            st.session_state["etf_type"] = "全部"
            st.session_state["etf_chg"] = (-10.0, 10.0)
            st.session_state["etf_amt"] = 0.0

        res = df.copy()
        if kw:
            # 守卫：上游列结构异常时 名称/代码 列可能缺失，先判定存在再筛选
            if "名称" in res.columns and "代码" in res.columns:
                res = res[res["名称"].astype(str).str.contains(kw, case=False, na=False) |
                         res["代码"].astype(str).str.contains(kw, case=False, na=False)]
            else:
                xc_warn_box("⚠️ 当前数据缺少「名称/代码」列，关键词筛选暂不可用。")
        if ftype != "全部":
            res = res[res["类型"] == ftype]
        # 列结构可能因上游接口变动而缺失，先判定存在再做数值化与区间过滤，避免 KeyError 崩溃
        if "涨跌幅" in res.columns:
            res["涨跌幅"] = pd.to_numeric(res["涨跌幅"], errors="coerce")
            res = res[(res["涨跌幅"] >= chg_range[0]) & (res["涨跌幅"] <= chg_range[1])]
        if "成交额" in res.columns:
            res["成交额"] = pd.to_numeric(res["成交额"], errors="coerce")
            if min_amt > 0:
                res = res[res["成交额"] / 1e8 >= min_amt]

        # 排序（所有可排序列均缺失时降级提示，避免 st.selectbox 空选项报错）
        sort_opts = [c for c in ["涨跌幅", "成交额", "最新价", "管理费"] if c in res.columns]
        if sort_opts:
            sort_col = st.selectbox("排序字段", sort_opts, key="etf_sort",
                                    help="选择排序依据；与下方「升序」复选框组合使用")
            asc = st.checkbox("升序", key="etf_asc")
            if sort_col in res.columns:
                res = res.sort_values(sort_col, ascending=asc, na_position="last")
        else:
            _empty_info("可用排序字段缺失（行情列结构异常），已跳过排序。")
        # 记忆当前筛选偏好（#Batch20-10）：session 级自动套用
        st.session_state["etf_rem_type"] = ftype
        st.session_state["etf_rem_amt"] = min_amt
        st.session_state["etf_rem_chg"] = chg_range
        st.session_state["etf_rem_kw"] = kw
        if sort_opts:
            st.session_state["etf_rem_sort"] = sort_col
            st.session_state["etf_rem_asc"] = asc

        st.markdown(f"### 📋 筛选结果（{len(res)} 只）")
        # 指标/字段说明 tooltip（#Batch19-6）：关键列含义解释
        st.caption("ℹ️ 字段说明：涨跌幅=当日涨跌幅(%)；成交额=单位为亿元；管理费=年化费率(%)；跟踪指数=标的指数。")
        if res.empty:
            _empty_info("没有符合条件的标的，放宽筛选条件试试。")
            # 示例数据预览（#Batch19-9）：无结果时只读展示样本标的
            if st.button("👀 查看示例标的", key="etf_sample"):
                _samp = pd.DataFrame(SAMPLE, columns=["代码", "名称", "类型", "最新价", "涨跌幅", "成交额", "管理费", "跟踪指数"])
                st.dataframe(_samp, width="stretch", hide_index=True, height=300)
        else:
            disp = res.copy()
            # 结果标记/徽章（#Batch19-10）：中性色标签，不动红涨绿跌配色
            if "涨跌幅" in disp.columns:
                def _tag(v):
                    try:
                        v = float(v)
                    except Exception:
                        return ""
                    if v >= 2:
                        return "🔥 热门"
                    if v <= -2:
                        return "❄️ 冷门"
                    return ""
                disp["标签"] = disp["涨跌幅"].apply(_tag)
            if "涨跌幅" in disp.columns:
                # 深层守卫：上游接口偶发把涨跌幅作为带单位字符串返回，
                # 着色时 v >= 0 对字符串会抛 TypeError；先强转数值再判定
                disp["涨跌幅"] = pd.to_numeric(disp["涨跌幅"], errors="coerce")

                def _color_chg(v):
                    if pd.isna(v):
                        return ""
                    return f"color:{UP if v >= 0 else DOWN}"
                sty = disp.style.map(_color_chg, subset=["涨跌幅"])
            else:
                sty = disp.style
            st.dataframe(sty, width="stretch", hide_index=True, height=560)

            # 图表类型切换（#Batch20-8）：走势图 line/柱/面积，session_state 控制，不改数据
            st.markdown("### 📈 涨跌幅走势（按成交额 Top 15）")
            _ct_opts = ["线", "柱", "面积"]
            _ct = st.radio("图表类型", _ct_opts, horizontal=True, key="etf_chart_radio",
                           index=_ct_opts.index(st.session_state.get("etf_chart_type", "线")))
            st.session_state["etf_chart_type"] = _ct
            _chart_df = res.copy()
            if "涨跌幅" in _chart_df.columns and "成交额" in _chart_df.columns:
                _chart_df["成交额"] = pd.to_numeric(_chart_df["成交额"], errors="coerce")
                _chart_df = _chart_df.dropna(subset=["涨跌幅", "成交额"]).sort_values("成交额", ascending=False).head(15)
                _chart_series = _chart_df.set_index("名称")["涨跌幅"]
                if _ct == "线":
                    st.line_chart(_chart_series)
                elif _ct == "柱":
                    st.bar_chart(_chart_series)
                else:
                    st.area_chart(_chart_series)
            else:
                st.caption("当前数据缺少「涨跌幅 / 成交额」列，暂无法绘制走势图。")

            # 收藏 / 批量选择 + 操作（#Batch20-3 / #Batch20-6）：前端星标集合 + 批量按钮
            _codes = res["代码"].astype(str).tolist() if "代码" in res.columns else []
            if _codes:
                _sel = st.multiselect("☑ 选择 ETF（可批量收藏）", _codes, key="etf_batch_sel",
                                      help="勾选若干 ETF，下方可批量加入收藏")
                _favs = st.session_state.setdefault("etf_fav_set", set())
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("⭐ 批量收藏", key="etf_batch_fav", width="stretch"):
                        _favs.update(_sel)
                with b2:
                    if st.button("➖ 移出收藏", key="etf_batch_unfav", width="stretch"):
                        _favs.difference_update(_sel)
                with b3:
                    if st.button("🧹 清空选择", key="etf_batch_clear", width="stretch"):
                        st.session_state["etf_batch_sel"] = []
            _favs = st.session_state.get("etf_fav_set", set())
            if _favs:
                st.caption(f"⭐ 已收藏 {len(_favs)} 只：" + "、".join(sorted(_favs)))

            # 相关推荐块（#Batch20-4）：底部相关 ETF 推荐
            _rec = res.copy()
            if "成交额" in _rec.columns and "涨跌幅" in _rec.columns:
                _rec["成交额"] = pd.to_numeric(_rec["成交额"], errors="coerce")
                _rec["涨跌幅"] = pd.to_numeric(_rec["涨跌幅"], errors="coerce")
                _rec = _rec.dropna(subset=["成交额"]).sort_values("成交额", ascending=False).head(3)
                if not _rec.empty:
                    sf_card("🧰 相关 ETF 推荐（按成交额）", "")
                    for _i, (_, rr) in enumerate(_rec.iterrows()):
                        st.markdown(
                            f"**{rr.get('名称', '?')}**  \n`{rr.get('代码', '?')}`  \n"
                            f"涨跌幅 {float(rr.get('涨跌幅', 0) or 0):.2f}%  ·  "
                            f"最新价 {rr.get('最新价', '—')}"
                        )

        st.caption("提示：本筛选器仅为信息聚合，不构成任何投资建议。")


_etf_filter_fragment()

# 快捷回到顶部（#Batch18-6）：长表格滚动后一键回顶，由 session_state 触发 JS 滚动
if st.button("↑ 回到顶部", key="etf_back_to_top"):
    st.session_state["_etf_scroll_top"] = True
if st.session_state.get("_etf_scroll_top"):
    sn.back_to_top_button()
    st.session_state["_etf_scroll_top"] = False
