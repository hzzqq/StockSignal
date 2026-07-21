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

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge
from modules.page_guard import safe_section

from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info, UP, DOWN

apply_page_config(page_title="ETF筛选", page_icon="🧰", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("🧰 ETF / 基金筛选器")
st.caption("按类型、关键字、涨跌幅与成交额筛选；红涨绿跌。数据受限时自动降级到样本。")


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
        df, src = _load_etfs()
        st.success(f"数据来源：{src}　·　共 {len(df)} 只", icon="📡")

        # ── 筛选器 ──
        st.markdown("### 🎚️ 筛选条件")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            kw = st.text_input("关键字 / 代码", placeholder="如 沪深300 / 510300", key="etf_kw")
        with f2:
            types = ["全部"] + sorted(df["类型"].dropna().unique().tolist())
            ftype = st.selectbox("类型", types, key="etf_type")
        with f3:
            chg_range = st.slider("涨跌幅区间(%)", -10.0, 10.0, (-10.0, 10.0), key="etf_chg")
        with f4:
            min_amt = st.number_input("最小成交额(亿)", min_value=0.0, value=0.0, step=10.0, key="etf_amt")

        res = df.copy()
        if kw:
            res = res[res["名称"].astype(str).str.contains(kw, case=False, na=False) |
                     res["代码"].astype(str).str.contains(kw, case=False, na=False)]
        if ftype != "全部":
            res = res[res["类型"] == ftype]
        res["涨跌幅"] = pd.to_numeric(res["涨跌幅"], errors="coerce")
        res = res[(res["涨跌幅"] >= chg_range[0]) & (res["涨跌幅"] <= chg_range[1])]
        if "成交额" in res.columns:
            res["成交额"] = pd.to_numeric(res["成交额"], errors="coerce")
            if min_amt > 0:
                res = res[res["成交额"] / 1e8 >= min_amt]

        # 排序
        sort_col = st.selectbox("排序字段", [c for c in ["涨跌幅", "成交额", "最新价", "管理费"] if c in res.columns], key="etf_sort")
        asc = st.checkbox("升序", key="etf_asc")
        if sort_col in res.columns:
            res = res.sort_values(sort_col, ascending=asc, na_position="last")

        st.markdown(f"### 📋 筛选结果（{len(res)} 只）")
        if res.empty:
            _empty_info("没有符合条件的标的，放宽筛选条件试试。")
        else:
            disp = res.copy()
            if "涨跌幅" in disp.columns:
                def _color_chg(v):
                    if pd.isna(v):
                        return ""
                    return f"color:{UP if v >= 0 else DOWN}"
                sty = disp.style.map(_color_chg, subset=["涨跌幅"]) if "涨跌幅" in disp.columns else disp.style
            else:
                sty = disp.style
            st.dataframe(sty, use_container_width=True, hide_index=True, height=560)

        st.caption("提示：本筛选器仅为信息聚合，不构成任何投资建议。")


_etf_filter_fragment()
