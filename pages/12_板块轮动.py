"""
板块轮动热力图
----------------
用一张热力图 + 排行榜 + 资金轮动视图，直观呈现行业板块的「强弱」与「资金流向」。

  🔥 热力图   —— 行业按涨跌幅着色（红涨绿跌），按资金净流入定大小
  📊 排行榜   —— 涨幅/跌幅行业 TOP10
  🔄 资金轮动 —— 行业资金净流入排行 + 强弱象限（涨跌幅 × 净额）

数据优先取行业资金流（含涨跌幅+净额），失败时降级到板块涨跌列表。
各取数区块独立隔离（safe_section）。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from datetime import datetime

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric
from modules.session import trading_autorefresh, safe_switch_page
from modules.fundflow import get_industry_fund_flow
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, safe_fragment, render_data_degradation_banner
from modules.page_widgets import _empty_info, UP, DOWN

from modules.ui_kit import xc_success_box, xc_warn_box
dark = render_standard_page(
    title="板块轮动热力图", icon="🔥",
    caption="红涨绿跌；热力图块大小代表资金净流入，颜色代表涨跌幅。各视图独立取数。",
)

sf_card(
    "板块轮动导读",
    "一张热力图 + 排行榜 + 资金轮动视图，直观呈现行业强弱与资金流向。红涨绿跌，块大小代表资金净流入。",
    icon="🔥",
)

FETCHER = StockFetcher()


@st.cache_data(ttl=300, show_spinner=False)
def _load_flow():
    try:
        df = get_industry_fund_flow()
        if df is not None and not df.empty:
            return df, "行业资金流(akshare)"
    except Exception:
        pass
    # 降级：仅涨跌幅
    try:
        s = FETCHER.get_sector_list()
        if s is not None and not s.empty:
            s = s.rename(columns={"sector": "行业", "change_pct": "涨跌幅"})
            s["净额"] = np.nan
            return s, "板块涨跌列表"
    except Exception:
        pass
    return pd.DataFrame(), "无数据"


def _norm_num(series):
    return pd.to_numeric(series, errors="coerce")


def _heatmap(df):
    d = df.copy()
    if "行业" not in d.columns or "涨跌幅" not in d.columns:
        _empty_info("板块数据字段不完整（缺少「行业」或「涨跌幅」），暂无法渲染（接口字段变更或网络异常）。")
        return
    d["涨跌幅"] = _norm_num(d["涨跌幅"])
    d["净额"] = _norm_num(d.get("净额"))
    d = d.dropna(subset=["涨跌幅"]).drop_duplicates("行业")
    if d.empty:
        _empty_info("暂无板块数据。")
        return
    maxabs = max(abs(d["涨跌幅"]).max(), 0.1)
    # 大小：净额（缺失则用 1）
    sizes = d["净额"].abs().fillna(1)
    if sizes.sum() == 0 or sizes.isna().all():
        sizes = pd.Series([1] * len(d))
    fig = go.Figure(go.Treemap(
        labels=d["行业"],
        parents=[""] * len(d),
        values=sizes,
        marker=dict(
            colors=d["涨跌幅"],
            colorscale=[[0, DOWN], [0.5, "#cccccc"], [1, UP]],
            cmin=-maxabs, cmax=maxabs, cmid=0,
            colorbar=dict(title="涨跌幅%", tickfont=dict(color="white" if dark else "black")),
            line=dict(width=1, color="white" if dark else "#333"),
        ),
        text=[f"{v:+.2f}%" for v in d["涨跌幅"]],
        texttemplate="<b>%{label}</b><br>%{text}",
        textfont=dict(size=12, color="white" if dark else "black"),
        hovertemplate="<b>%{label}</b><br>涨跌幅 %{text}<extra></extra>",
    ))
    fig.update_layout(
        height=560, margin=dict(t=10, l=10, r=10, b=10),
        template="plotly_dark" if dark else "plotly_white",
    )
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})


def _ranking(df):
    d = df.copy()
    if "行业" not in d.columns or "涨跌幅" not in d.columns:
        _empty_info("板块数据字段不完整（缺少「行业」或「涨跌幅」），暂无法渲染（接口字段变更或网络异常）。")
        return
    d["涨跌幅"] = _norm_num(d["涨跌幅"])
    d = d.dropna(subset=["涨跌幅"]).drop_duplicates("行业")
    if d.empty:
        _empty_info("暂无板块数据。")
        return
    d = d.sort_values("涨跌幅", ascending=False)
    top = d.head(10)
    bot = d.tail(10).sort_values("涨跌幅")
    col1, col2 = st.columns(2)
    y_common = dict(template="plotly_dark" if dark else "plotly_white",
                    height=360, margin=dict(t=30, l=80, r=20, b=20))
    with col1:
        st.markdown("#### 🚀 涨幅 TOP10")
        fig = go.Figure(go.Bar(
            x=top["涨跌幅"], y=top["行业"], orientation="h",
            marker=dict(color=top["涨跌幅"], colorscale=[[0, DOWN], [1, UP]]),
            text=[f"{v:+.2f}%" for v in top["涨跌幅"]], textposition="auto",
        ))
        fig.update_layout(**y_common, xaxis_title="涨跌幅%")
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})
    with col2:
        st.markdown("#### 📉 跌幅 TOP10")
        fig = go.Figure(go.Bar(
            x=bot["涨跌幅"], y=bot["行业"], orientation="h",
            marker=dict(color=bot["涨跌幅"], colorscale=[[0, DOWN], [1, UP]]),
            text=[f"{v:+.2f}%" for v in bot["涨跌幅"]], textposition="auto",
        ))
        fig.update_layout(**y_common, xaxis_title="涨跌幅%")
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})


def _rotation(df):
    d = df.copy()
    if "行业" not in d.columns or "涨跌幅" not in d.columns:
        _empty_info("板块数据字段不完整（缺少「行业」或「涨跌幅」），暂无法渲染（接口字段变更或网络异常）。")
        return
    d["涨跌幅"] = _norm_num(d["涨跌幅"])
    d["净额"] = _norm_num(d.get("净额"))
    d = d.dropna(subset=["涨跌幅"]).drop_duplicates("行业")
    if d.empty:
        _empty_info("暂无板块数据。")
        return
    # 资金净流入排行（有净额时）
    if d["净额"].notna().any():
        dd = d.dropna(subset=["净额"]).sort_values("净额", ascending=False)
        top_in = dd.head(12)
        top_out = dd.tail(12).sort_values("净额")
        col1, col2 = st.columns(2)
        y_common = dict(template="plotly_dark" if dark else "plotly_white",
                        height=420, margin=dict(t=30, l=90, r=20, b=20))
        with col1:
            st.markdown("#### 💰 资金净流入 TOP12")
            fig = go.Figure(go.Bar(
                x=top_in["净额"] / 1e8, y=top_in["行业"], orientation="h",
                marker=dict(color=UP),
                text=[f"{v/1e8:.1f}亿" for v in top_in["净额"]], textposition="auto",
            ))
            fig.update_layout(**y_common, xaxis_title="净额(亿元)")
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})
        with col2:
            st.markdown("#### 💸 资金净流出 TOP12")
            fig = go.Figure(go.Bar(
                x=top_out["净额"] / 1e8, y=top_out["行业"], orientation="h",
                marker=dict(color=DOWN),
                text=[f"{v/1e8:.1f}亿" for v in top_out["净额"]], textposition="auto",
            ))
            fig.update_layout(**y_common, xaxis_title="净额(亿元)")
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})
    # 强弱象限：涨跌幅 × 净额
    st.markdown("#### 🔄 强弱象限（涨跌幅 × 资金净额）")
    quad = d.dropna(subset=["净额"]) if d["净额"].notna().any() else d.assign(净额=0)
    fig = go.Figure(go.Scatter(
        x=quad["涨跌幅"], y=quad["净额"] / 1e8,
        mode="markers+text", text=quad["行业"], textposition="top center",
        textfont=dict(size=10, color="white" if dark else "black"),
        marker=dict(
            size=12,
            color=quad["涨跌幅"],
            colorscale=[[0, DOWN], [1, UP]],
            line=dict(width=1, color="white" if dark else "#333"),
        ),
        hovertemplate="<b>%{text}</b><br>涨跌幅 %{x:.2f}%<br>净额 %{y:.2f}亿<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#888")
    fig.add_vline(x=0, line_dash="dot", line_color="#888")
    fig.update_layout(
        height=480, template="plotly_dark" if dark else "plotly_white",
        xaxis_title="涨跌幅%", yaxis_title="资金净额(亿元)", margin=dict(t=20, l=60, r=20, b=40),
    )
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})
    st.caption("右上象限＝价量齐升的领涨主线；左下象限＝价量齐跌的弱势板块。")


# ───────────────────────── 主渲染 ─────────────────────────
@safe_fragment("板块轮动")
def fragment_sectors():
    trading_autorefresh(key="sector_autorefresh")
    # ───────────────────────── 主渲染 ─────────────────────────
    with safe_section("板块数据", hint="行业资金流接口可能受网络限制；可稍后重试。"):
        df, src = _load_flow()
        st.caption(f"🕒 最后刷新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（交易时段内每 60 秒自动刷新）")
        if df.empty:
            _empty_info("板块数据暂时不可用，请稍后重试；也可切换数据源或检查网络连接。")
            if st.button("➡️ 去行情看板查看", key="sector_empty_go",
                         help="跳转到行情看板查看实时板块涨跌。"):
                safe_switch_page("pages/10_行情看板.py")
        else:
            xc_success_box(f"数据来源：{src}　·　共 {len(df)} 个行业", icon="📡")
            render_data_degradation_banner()
            tab1, tab2, tab3 = st.tabs(["🔥 热力图", "📊 排行榜", "🔄 资金轮动"])
            with tab1:
                _heatmap(df)
            with tab2:
                _ranking(df)
            with tab3:
                _rotation(df)
            st.divider()
            st.markdown("#### 🧭 板块轮动解读")
            # 动态摘要：从当前数据中提取关键信号
            _d = df.copy()
            _d["涨跌幅"] = _norm_num(_d.get("涨跌幅", pd.Series(dtype=float)))
            _d["净额"] = _norm_num(_d.get("净额", pd.Series(dtype=float)))
            if not _d.empty and _d["涨跌幅"].notna().any():
                _top_gain = _d.nlargest(3, "涨跌幅")[["行业", "涨跌幅"]] if (_d["涨跌幅"].dropna() > 0).any() else None
                _top_loss = _d.nsmallest(3, "涨跌幅")[["行业", "涨跌幅"]]
                _net_top = None
                if _d["净额"].notna().any():
                    _net_tmp = _d.dropna(subset=["净额"])
                    if not _net_tmp.empty:
                        _net_top = _net_tmp.nlargest(3, "净额")[["行业", "净额"]]

                _cols = st.columns(3)
                with _cols[0]:
                    if _top_gain is not None and not _top_gain.empty:
                        st.markdown("**🟢 领涨前三**")
                        for _, r in _top_gain.iterrows():
                            st.text(f"{r['行业']}: {r['涨跌幅']:+.2f}%")
                    else:
                        st.markdown("**🟢 领涨前三**")
                        st.caption("无上涨板块")
                with _cols[1]:
                    if _top_loss is not None and not _top_loss.empty:
                        st.markdown("**🔴 领跌前三**")
                        for _, r in _top_loss.iterrows():
                            st.text(f"{r['行业']}: {r['涨跌幅']:+.2f}%")
                with _cols[2]:
                    if _net_top is not None and not _net_top.empty:
                        st.markdown("**💰 净流入前三**")
                        for _, r in _net_top.iterrows():
                            st.text(f"{r['行业']}: {r['净额']/1e8:+.1f}亿")
                    else:
                        st.markdown("**💰 净流入前三**")
                        st.caption("无资金流数据")

                # 轮动判断
                _avg = _d["涨跌幅"].mean()
                _inflow_cnt = (_d["净额"] > 0).sum() if _d["净额"].notna().any() else 0
                if _avg > 0.5 and _inflow_cnt > len(_d) * 0.6:
                    st.info("📈 **偏强轮动**：多数板块上涨且资金净流入，市场情绪偏多，关注领涨主线持续性。")
                elif _avg < -0.5 and _inflow_cnt < len(_d) * 0.4:
                    xc_warn_box("📉 **偏弱轮动**：多数板块下跌且资金净流出，注意风险控制，等待企稳信号。")
                else:
                    st.caption("⚖️ **震荡分化**：板块涨跌互现、资金方向不一，结构性行情为主，关注个别强势板块机会。")

                st.caption("🔥 热力图：块越大=资金净流入越多，颜色越红=涨幅越大；"
                           "📊 排行榜：看哪些行业领涨/领跌；"
                           "🔄 资金轮动：右上象限（价量齐升）是当前主线，资金从绿（净流出）板块流向红（净流入）板块即为轮动。"
                           "交易时段内本区块每 60 秒自动刷新。")
            else:
                st.caption("暂无足够数据生成轮动解读，请稍后刷新或检查数据源连接。")


fragment_sectors()


# ───────────────────────── 国产替代研究（行业级总览） ─────────────────────────
@safe_fragment("国产替代")
def fragment_domestic_substitution():
    sf_card(
        "🇨🇳 国产替代研究（行业总览）",
        "套用「半导体材料国产替代研究模板」的 10 维框架，下沉到行业级，盘点 A 股各主线的国产化率、龙头标的与投资逻辑。",
        icon="🇨🇳",
    )
    st.caption(
        "📐 框架（模板 10 维，下沉到行业级）：① 赛道定位 ② 国产化率 ③ 细分环节瓶颈 "
        "④ 全球 vs 国内格局 ⑤ 国内龙头 ⑥ 产业进化周期 ⑦ 趋势 / 催化 "
        "⑧ 风险 ⑨ 配置思路 ⑩ 信号归因。",
    )

    _data = [
        {
            "name": "半导体设备",
            "rate": "整体约 20–35%（清洗/刻蚀/沉积 >30%；光刻机 <3%；量测/CMP 偏低）",
            "segments": "刻蚀、薄膜沉积（PECVD/PVD/ALD）、清洗、CMP、量测、去胶、离子注入",
            "pattern": "全球由 Applied Materials / Lam / ASML / TEL 主导；国内在成熟制程环节已批量导入。",
            "leaders": "北方华创(平台型)、中微公司(刻蚀/沉积)、拓荆科技(沉积)、盛美上海(清洗)、华海清科(CMP)、中科飞测(量测)",
            "stage": "① 成熟制程(28nm+)放量 → ② 先进制程验证 → ③ 平台化整合 → ④ 全球一极",
            "trend": "晶圆厂逆周期扩产 + 自主可控刚需；HBM/先进封装带动新设备需求。",
            "tag": "刚需·高确定性",
        },
        {
            "name": "半导体材料",
            "rate": "硅片/靶材 ~30–40%；电子特气 ~30%；抛光垫/液 ~25%；ArF 光刻胶 <5%；CMP 抛光垫偏低",
            "segments": "硅片、电子特气、光刻胶、CMP 材料、湿电子化学品、靶材、掩模版",
            "pattern": "日美欧（信越/SUMCO/陶氏/默克）占主导；国内靶材/特气突破较快，光刻胶最薄弱。",
            "leaders": "沪硅产业(硅片)、鼎龙股份(抛光垫/CMP)、华特气体(特气)、安集科技(抛光液)、彤程新材(光刻胶)",
            "stage": "① 成熟材料替代 → ② 先进制程材料验证 → ③ 品类扩张 → ④ 全球份额",
            "trend": "晶圆厂扩产拉动 + 验证窗口打开；ArF 浸没式光刻胶为最关键瓶颈。",
            "tag": "瓶颈·高弹性",
        },
        {
            "name": "芯片设计 / 算力芯片",
            "rate": "消费 MCU/CIS ~40–60%；CPU/GPU/AI 算力芯片 <10%；FPGA 偏低",
            "segments": "CPU、GPU、AI 加速芯片、FPGA、存储控制器、CIS、射频、模拟",
            "pattern": "海外（英伟达/AMD/Intel/高通）主导算力；国内在 ARM 服务器 CPU、端侧 AI 快速追赶。",
            "leaders": "海光信息(CPU)、寒武纪(AI)、澜起科技(内存接口)、韦尔股份(CIS)、兆易创新(存储/MCU)",
            "stage": "① 消费/细分替代 → ② 服务器 CPU 放量 → ③ AI 算力突破 → ④ 生态成型",
            "trend": "AI 算力本土化刚需 + 信创采购；先进制程代工受限是天花板。",
            "tag": "算力·高景气",
        },
        {
            "name": "工业软件 / 信创",
            "rate": "办公/ERP ~60–70%；CAD/CAE ~10–15%；EDA <5%；工业控制偏低",
            "segments": "EDA、CAD/CAE、ERP、办公、数据库、中间件、工业控制",
            "pattern": "海外（Synopsys/Cadence/达索/西门子）把持研发类工具；办公/管理软件国产化最快。",
            "leaders": "华大九天(EDA)、中望软件(CAD)、用友网络(ERP)、金山办公(办公)、达梦数据(数据库)",
            "stage": "① 办公/管理替代 → ② 研发工具攻坚 → ③ 生态耦合 → ④ 全流程自主",
            "trend": "信创 2.0 下沉 + 党政机关/央国企采购；EDA/CAE 为最长坡。",
            "tag": "自主·长坡",
        },
        {
            "name": "医疗器械",
            "rate": "监护/超声中低端 ~50–70%；高端影像/CT/MRI ~20–30%；内窥镜/起搏器偏低",
            "segments": "影像（CT/MRI/DR）、超声、监护、内窥镜、IVD、植介入、放疗",
            "pattern": "GPS（GE/飞利浦/西门子）占高端；迈瑞等在中低端已完成替代并出海。",
            "leaders": "迈瑞医疗(平台)、联影医疗(影像)、开立医疗(超声)、澳华内镜(软镜)、惠泰医疗(电生理)",
            "stage": "① 中低端替代 → ② 高端突破 → ③ 出海 → ④ 全球竞争",
            "trend": "设备更新政策 + 县域医疗下沉；高端影像/内镜为突破前沿。",
            "tag": "出海·稳健",
        },
        {
            "name": "高端数控机床 / 机器人核心部件",
            "rate": "中低端机床 ~60–70%；五轴联动/高端数控系统 ~10–15%；RV 减速器 ~30%",
            "segments": "五轴机床、数控系统、RV/谐波减速器、伺服、丝杠、轴承",
            "pattern": "日德（发那科/西门子/THK/哈默纳科）主导高端；国内系统/减速器快速追赶。",
            "leaders": "科德数控(五轴)、华中数控(系统)、绿的谐波(谐波)、双环传动(RV)、秦川机床(齿轮)",
            "stage": "① 部件突破 → ② 整机集成 → ③ 高端量产 → ④ 进口替代",
            "trend": "人形机器人量产 + 设备更新 + 军工自主；丝杠/减速器弹性大。",
            "tag": "机器人·高弹性",
        },
        {
            "name": "航空航天发动机 / 新材料",
            "rate": "军用航发 ~50–70%；商用航发 <10%；高温合金/碳纤维 ~30–40%",
            "segments": "航空发动机、高温合金、碳纤维、钛合金、隐身材料",
            "pattern": "全球（GE/罗罗/赛峰）垄断商用；国内军用自主，商用在研。",
            "leaders": "航发动力(发动机)、抚顺特钢(高温合金)、中航高科(复材)、光威复材(碳纤维)",
            "stage": "① 军用自主 → ② 民机验证 → ③ 商业化 → ④ 全球配套",
            "trend": "军机换装 + C919 量产拉动材料；商用航发为终极瓶颈。",
            "tag": "军工·长周期",
        },
        {
            "name": "汽车芯片 / 功率半导体",
            "rate": "IGBT ~35–45%；SiC ~20–30%；车规 MCU ~15–20%；车规 SoC 偏低",
            "segments": "IGBT、SiC 模组、MOSFET、车规 MCU、电源管理、传感器",
            "pattern": "英飞凌/意法/安森美主导；国内在 IGBT/SiC 已规模上车。",
            "leaders": "斯达半导(IGBT)、比亚迪半导、时代电气(IGBT)、士兰微、新洁能",
            "stage": "① 中低压替代 → ② 车规突破 → ③ SiC 领先 → ④ 全球份额",
            "trend": "新能源车渗透 + 800V/SiC 放量；车规认证是壁垒。",
            "tag": "已领先·高景气",
        },
        {
            "name": "面板 / OLED 显示",
            "rate": "LCD ~70–80%（全球主导）；OLED 柔性 ~40–50%；IT/OLED 偏低",
            "segments": "LCD、刚性 OLED、柔性 OLED、IT 用 OLED、Micro LED",
            "pattern": "韩系退出 LCD；国内京东方/华星主导大尺寸，OLED 追赶韩系。",
            "leaders": "京东方A(大尺寸)、TCL科技/华星(大尺寸)、维信诺(OLED)、深天马(车载/IT)",
            "stage": "① LCD 主导 → ② OLED 追赶 → ③ IT/OLED 突破 → ④ 全品类领先",
            "trend": "韩退中进 + IT/OLED 迭代；折叠屏/车载为新增长。",
            "tag": "已主导·稳份额",
        },
    ]

    _tbl = pd.DataFrame([
        {
            "赛道": d["name"],
            "国产化率(区间·机构口径)": d["rate"],
            "代表龙头": "、".join(d["leaders"].split("、")[:3]),
            "投资逻辑": d["tag"],
        }
        for d in _data
    ])
    try:
        st.dataframe(_tbl, width="stretch", hide_index=True, height=340)
    except Exception as _e:
        xc_warn_box(f"国产替代总览表渲染失败：{_e}")

    for d in _data:
        with st.expander(f"📌 {d['name']}　·　{d['tag']}", expanded=False, key=f"ds_{d['name']}"):
            st.markdown(
                f"**细分环节**：{d['segments']}\n\n"
                f"**国产化率（区间·机构口径）**：{d['rate']}\n\n"
                f"**全球 vs 国内格局**：{d['pattern']}\n\n"
                f"**国内龙头标的**：{d['leaders']}\n\n"
                f"**产业进化周期**：{d['stage']}\n\n"
                f"**趋势 / 催化**：{d['trend']}",
            )

    st.markdown("#### 🧭 核心结论（国产替代主线）")
    st.markdown(
        "- **已主导 / 领先**：LCD 面板、功率半导体(IGBT)、中低端医疗器械 —— 配置看份额与出海。\n"
        "- **加速突破（当前主线）**：半导体设备先进制程、车规芯片/SiC、机器人核心部件 —— 高弹性高确定性。\n"
        "- **最深瓶颈（长周期）**：光刻机、ArF 光刻胶、EDA/CAE、商用航发 —— 看攻坚进度与政策。\n"
        "- **底层逻辑**：自主可控刚需 + 逆周期扩产 + 信创采购，构成跨周期的国产替代贝塔。",
    )
    st.caption(
        "⚠️ 免责声明与口径提示：以上为公开研报与机构口径的区间估计（非精确值，单位/口径不一），"
        "仅作行业研究框架演示，不构成任何投资建议。实际投资须结合个股基本面、估值与风险。",
    )


fragment_domestic_substitution()
