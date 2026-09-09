"""
市场魔方
--------
把板块数据做成「可旋转的多维魔方」——致敬「市场魔方助手」的移动端交互：
板块不是一张平面表，而是 X=涨跌幅 / Y=资金净额 / Z=涨停家数 三个维度构成的立方体，
鼠标可直接旋转观察；颜色代表综合强度，点哪个板块就下钻看它的领涨股、资金流、板块热度。

本页是 12_板块轮动 的「魔方升级版」：

  🧊 魔方主图   —— 3D 散点立方体：每点=一个行业板块，三轴即三维，颜色=综合强度
  🎛 观察面     —— 旋转魔方看不同「面」：综合强度 / 涨跌幅 / 资金净额 / 涨停热度
  🟥 Bento 概览 —— 最强主线 / 资金共识 / 情绪温度计 / 轮动节奏
  🔍 板块下钻   —— 点魔方任一点（或下拉选），看该板块领涨股、净流入、涨停家数、行业内排名

数据三路独立取（板块涨跌 / 行业资金流 / 涨停行业分布），逐路优雅降级：
单源抖动只缺那一维，绝不黑屏；页面顶部「维度健康」显性标注每路可用性（可观测，不静默）。
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
from modules.shepherd import get_zt_industry_distribution
from modules.page_guard import safe_section, safe_fragment, render_data_degradation_banner
from modules.page_widgets import _empty_info, UP, DOWN

dark = render_standard_page(
    title="市场魔方",
    icon="🧊",
    caption="把板块数据旋转成多维魔方：X=涨跌幅 / Y=资金净额 / Z=涨停家数，颜色=综合强度。"
            "点任一点下钻看领涨股与资金流。红涨绿跌。",
)

sf_card(
    "市场魔方 · 导读",
    "板块不是平面表，而是三维立方体——鼠标拖拽即可旋转观察。颜色深浅=综合强度（涨跌幅×资金×热度）。"
    "单源数据抖动只缺一维，不会黑屏；顶部「维度健康」显式标注每路可用性。",
    icon="🧊",
)

FETCHER = StockFetcher()


# ───────────────────────── 数据层：三路独立 + 逐维降级 ─────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_cube(mode: str):
    """返回 (merged_df, health_dict, src_text)。

    merged_df 列：行业, 涨跌幅, 净额, 流入资金, 流出资金, 领涨股, 领涨股涨跌幅, 涨停家数
    health: {sector:bool, flow:bool, zt:bool}  —— 每路是否取到真实数据（可观测降级）
    """
    health = {"sector": False, "flow": False, "zt": False}

    # ① 基础：行业/概念板块涨跌列表（akshare）
    base = pd.DataFrame()
    try:
        if mode == "概念板块":
            raw = FETCHER.get_concept_list()
        else:
            raw = FETCHER.get_sector_list()
        if raw is not None and not raw.empty:
            base = _tolerant_sector_df(raw)
            health["sector"] = True
    except Exception:
        base = pd.DataFrame()

    if base.empty:
        return pd.DataFrame(), health, "无数据"

    merged = base.copy()
    merged["净额"] = np.nan
    merged["流入资金"] = np.nan
    merged["流出资金"] = np.nan
    merged["领涨股"] = ""
    merged["领涨股涨跌幅"] = np.nan
    merged["涨停家数"] = 0

    # ② 行业资金流（akshare 东财）：含涨跌幅+净额+领涨股（仅行业模式有意义）
    if mode != "概念板块":
        try:
            ff = get_industry_fund_flow()
            if ff is not None and not ff.empty:
                ff2 = ff.copy()
                ff2["行业"] = ff2["行业"].astype(str).str.strip()
                merged["行业"] = merged["行业"].astype(str).str.strip()
                merged = merged.merge(
                    ff2[["行业", "涨跌幅", "净额", "流入资金", "流出资金", "领涨股", "领涨股涨跌幅"]],
                    on="行业", how="left", suffixes=("", "_ff"),
                )
                # 资金流里的数值更全，优先用；缺失回落到板块涨跌列表
                for col in ["涨跌幅", "净额", "流入资金", "流出资金", "领涨股", "领涨股涨跌幅"]:
                    ffcol = col + "_ff"
                    if ffcol in merged.columns:
                        if col == "领涨股":
                            merged[col] = merged[ffcol].fillna(merged[col])
                        else:
                            merged[col] = pd.to_numeric(merged[ffcol], errors="coerce").fillna(
                                pd.to_numeric(merged[col], errors="coerce"))
                        merged.drop(columns=[ffcol], inplace=True)
                health["flow"] = True
        except Exception:
            pass

    # ③ 涨停行业分布（shepherd）：板块热度/广度
    if mode != "概念板块":
        try:
            zt = get_zt_industry_distribution(15)
            if zt is not None and not zt.empty:
                zt2 = zt.copy()
                zt2["行业"] = zt2["行业"].astype(str).str.strip()
                merged["行业"] = merged["行业"].astype(str).str.strip()
                merged = merged.merge(zt2[["行业", "涨停家数"]], on="行业", how="left", suffixes=("", "_zt"))
                # 优先用涨停分布，回落到默认 0
                _zt_col = "涨停家数_zt" if "涨停家数_zt" in merged.columns else "涨停家数"
                merged["涨停家数"] = pd.to_numeric(merged.get(_zt_col), errors="coerce").fillna(
                    pd.to_numeric(merged.get("涨停家数"), errors="coerce")).fillna(0)
                if "涨停家数_zt" in merged.columns:
                    merged.drop(columns=["涨停家数_zt"], inplace=True)
                health["zt"] = True
        except Exception:
            pass

    # 数值化
    for c in ["涨跌幅", "净额", "流入资金", "流出资金", "领涨股涨跌幅", "涨停家数"]:
        if c in merged.columns:
            merged[c] = pd.to_numeric(merged[c], errors="coerce")

    src = "行业板块" if mode != "概念板块" else "概念板块"
    if health["flow"]:
        src += " + 资金流"
    if health["zt"]:
        src += " + 涨停分布"
    return merged, health, src


def _tolerant_sector_df(df):
    """把任意板块/概念列表 df 规整成 (行业, 涨跌幅)。"""
    d = df.copy()
    name_col = next((c for c in ("行业", "sector", "板块", "名称", "概念", "concept") if c in d.columns), None)
    chg_col = next((c for c in ("涨跌幅", "change_pct", "涨跌幅(%)", "涨幅%") if c in d.columns), None)
    if name_col is None:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["行业"] = d[name_col].astype(str).str.strip()
    if chg_col is not None:
        out["涨跌幅"] = pd.to_numeric(d[chg_col], errors="coerce")
    else:
        out["涨跌幅"] = np.nan
    return out.dropna(subset=["行业"]).drop_duplicates("行业").reset_index(drop=True)


def _composite(m: pd.DataFrame):
    """综合强度：涨跌幅 0.5 + 资金净额 0.3 + 涨停家数 0.2（各自归一化到[-1,1]）。"""
    chg = m["涨跌幅"].fillna(0)
    net = m["净额"].fillna(0)
    zt = m["涨停家数"].fillna(0)
    def _n(s):
        mx = s.abs().max()
        return s / mx if mx and mx > 0 else s * 0
    c = 0.5 * _n(chg) + 0.3 * _n(net) + 0.2 * _n(zt)
    return c.clip(-1, 1)


# ───────────────────────── 魔方主图 ─────────────────────────
def _cube_fig(m: pd.DataFrame, face: str, dark: bool):
    comp = _composite(m)
    x = m["涨跌幅"].fillna(0)
    y = (m["净额"].fillna(0) / 1e8)          # 亿元
    z = m["涨停家数"].fillna(0)

    if face == "涨跌幅":
        color = m["涨跌幅"].fillna(0)
        cmin, cmax, title = -max(abs(color).max(), 0.1), max(abs(color).max(), 0.1), "涨跌幅%"
    elif face == "资金净额":
        color = y
        am = max(abs(color).max(), 0.1)
        cmin, cmax, title = -am, am, "资金净额(亿)"
    elif face == "涨停热度":
        color = z
        cmin, cmax, title = 0, max(color.max(), 1), "涨停家数"
    else:  # 综合强度
        color = comp
        cmin, cmax, title = -1, 1, "综合强度"

    size = (m["流入资金"].fillna(0).abs() / 1e8).clip(lower=0)
    size = 6 + 10 * (size / size.max() if size.max() > 0 else size * 0)

    fig = go.Figure(go.Scatter3d(
        x=x, y=y, z=z,
        mode="markers",
        customdata=m["行业"],
        marker=dict(
            size=size,
            color=color,
            colorscale=[[0, DOWN], [0.5, "#8a8a8a"], [1, UP]],
            cmin=cmin, cmax=cmax,
            opacity=0.9,
            line=dict(width=0.5, color="white" if dark else "#333"),
        ),
        text=m["行业"],
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            "涨跌幅 %{x:.2f}%<br>"
            "净额 %{y:.2f}亿<br>"
            "涨停 %{z:.0f}家<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=620,
        margin=dict(t=10, l=10, r=10, b=10),
        template="plotly_dark" if dark else "plotly_white",
        scene=dict(
            xaxis_title="涨跌幅 %",
            yaxis_title="资金净额(亿)",
            zaxis_title="涨停家数",
            bgcolor="rgba(0,0,0,0)" if dark else "rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)" if dark else "rgba(0,0,0,0)",
    )
    return fig


# ───────────────────────── Bento 概览 ─────────────────────────
def _bento(m: pd.DataFrame, health: dict):
    comp = _composite(m)
    md = m.copy()
    md["_comp"] = comp
    md = md.dropna(subset=["涨跌幅"])
    if md.empty:
        st.caption("暂无足够数据生成概览。")
        return

    up = int((md["涨跌幅"] > 0).sum())
    down = int((md["涨跌幅"] < 0).sum())
    total = len(md)
    avg = md["涨跌幅"].mean()

    # 最强主线
    lead = md.loc[md["_comp"].idxmax()]
    # 资金共识（净额最大且>0）
    net_ok = md[md["净额"] > 0] if md["净额"].notna().any() else md.iloc[0:0]
    consensus = net_ok.loc[net_ok["净额"].idxmax()] if not net_ok.empty else None
    # 轮动节奏
    inflow_cnt = int((md["净额"] > 0).sum()) if md["净额"].notna().any() else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🏆 最强主线", f"{lead['行业']}", help=f"综合强度 {lead['_comp']:.2f}｜涨跌 {lead['涨跌幅']:+.2f}%")
    with c2:
        if consensus is not None:
            st.metric("💰 资金共识", f"{consensus['行业']}", help=f"净流入 {consensus['净额']/1e8:+.1f}亿",
                      delta=f"{consensus['净额']/1e8:+.1f}亿")
        else:
            st.metric("💰 资金共识", "—", help="资金流维度暂缺")
    with c3:
        temp = up / total * 100 if total else 0
        st.metric("🌡 情绪温度", f"{temp:.0f}%", help=f"上涨板块 {up}/{total}｜均值 {avg:+.2f}%",
                  delta=f"{avg:+.2f}%")
    with c4:
        if md["净额"].notna().any() and total:
            ratio = inflow_cnt / total * 100
            verdict = "偏强轮动" if (avg > 0.5 and inflow_cnt > total * 0.6) else (
                "偏弱轮动" if (avg < -0.5 and inflow_cnt < total * 0.4) else "震荡分化")
            st.metric("🔄 轮动节奏", verdict, help=f"资金净流入行业 {inflow_cnt}/{total}（{ratio:.0f}%）")
        else:
            st.metric("🔄 轮动节奏", "—", help="资金流维度暂缺")


# ───────────────────────── 板块下钻 ─────────────────────────
def _drill(m: pd.DataFrame, picked: str):
    row = m[m["行业"] == picked]
    if row.empty:
        _empty_info(f"未找到板块「{picked}」的详情。")
        return
    r = row.iloc[0]
    st.markdown(f"#### 🔍 {picked} 板块详情")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("涨跌幅", f"{r['涨跌幅']:+.2f}%" if pd.notna(r['涨跌幅']) else "—")
    with col2:
        if pd.notna(r.get("净额")):
            st.metric("主力净额", f"{r['净额']/1e8:+.2f}亿", delta=f"{r['净额']/1e8:+.2f}亿")
        else:
            st.metric("主力净额", "—")
    with col3:
        zt = int(r["涨停家数"]) if pd.notna(r["涨停家数"]) else 0
        st.metric("涨停家数", f"{zt} 家")

    # 领涨股
    if r.get("领涨股"):
        lead_txt = f"{r['领涨股']}"
        if pd.notna(r.get("领涨股涨跌幅")):
            lead_txt += f"　{r['领涨股涨跌幅']:+.2f}%"
        st.markdown(f"**🚀 领涨股**：{lead_txt}")
    else:
        st.caption("领涨股维度暂缺（资金流源未返回）。")

    # 行业内排名
    comp = _composite(m)
    md = m.copy()
    md["_comp"] = comp
    md = md.dropna(subset=["涨跌幅"]).sort_values("_comp", ascending=False).reset_index(drop=True)
    rank = md.index[md["行业"] == picked].tolist()
    if rank:
        rk = rank[0] + 1
        st.caption(f"综合强度排名：全市场第 **{rk}/{len(md)}** 名（{(1-rk/len(md))*100:.0f}% 分位）。")

    st.page_link("pages/20_个股分析.py", label="→ 去个股分析（查领涨股详情）", icon="🔎")
    st.page_link("pages/12_板块轮动.py", label="→ 板块轮动热力图（平面视图）", icon="🔥")


# ───────────────────────── 主渲染 ─────────────────────────
@safe_fragment("市场魔方")
def fragment_cube():
    trading_autorefresh(key="cube_autorefresh")

    mode = st.radio(
        "板块范围", ["行业板块", "概念板块"], horizontal=True, key="cube_mode",
        help="行业板块含资金流+涨停热度三维；概念板块仅涨跌幅（资金流/涨停维度暂未覆盖）。",
    )

    merged, health, src = _load_cube(mode)

    st.caption(f"🕒 最后刷新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（交易时段内每 60 秒自动刷新）· 数据：{src}")

    if merged.empty:
        _empty_info("板块数据暂时不可用，请稍后重试；也可切换数据源或检查网络连接。")
        if st.button("➡️ 去行情看板查看", key="cube_empty_go", help="跳转到行情看板查看实时板块涨跌。"):
            safe_switch_page("pages/10_行情看板.py")
        return

    # 维度健康（可观测降级）
    _h = []
    _h.append("✅ 板块涨跌" if health["sector"] else "⚠️ 板块涨跌缺失")
    _h.append("✅ 资金流" if health["flow"] else "⚠️ 资金流缺失(降级为涨跌幅)")
    _h.append("✅ 涨停分布" if health["zt"] else "⚠️ 涨停分布缺失(降级为0)")
    st.caption("　".join(_h))

    # 数据源健康（多源可观测：akshare / 新浪 / 东财 / BaoStock / 本地缓存）
    # 复用 fetcher.data_source_health()：纯本地/静态探测，不发网络请求，离线秒回。
    with st.expander("🩺 数据源健康（多源降级链状态）", expanded=False):
        try:
            _hs = FETCHER.data_source_health()
            _sum = _hs.get("summary", "")
            st.caption(f"综合：{_sum}（探测不发网络请求，仅看依赖/缓存就绪度）")
            for _name, _v in _hs.get("sources", {}).items():
                _ok = _v.get("ok")
                _icon = "✅" if _ok else "⚠️"
                st.markdown(f"{_icon} **{_v.get('label', _name)}** — {_v.get('detail', '')}")
        except Exception:
            st.caption("数据源健康探测暂不可用（不影响板块渲染）。")

    # Bento 概览
    _bento(merged, health)

    st.divider()
    # 观察面（旋转魔方）
    face = st.radio(
        "🎛 观察面（旋转魔方看不同维度）",
        ["综合强度", "涨跌幅", "资金净额", "涨停热度"],
        horizontal=True, key="cube_face",
        help="切换魔方着色维度，相当于旋转魔方看不同「面」。3D 图本身也可用鼠标拖拽旋转。",
    )

    fig = _cube_fig(merged, face, dark)
    st.plotly_chart(
        fig, width="stretch", on_select="rerun", key="cube",
        config={"displaylogo": False, "responsive": True, "displayModeBar": False},
    )
    st.caption("🖱 拖拽旋转立方体；单击任一板块点可在下方下钻。X=涨跌幅 / Y=资金净额 / Z=涨停家数。")

    # 下钻：优先用魔方点击选择，否则下拉
    sel = st.session_state.get("cube", {}).get("selection", {}).get("points", [])
    chosen = None
    if sel:
        cd = sel[0].get("customdata")
        chosen = cd[0] if isinstance(cd, (list, tuple)) else cd
    options = list(merged["行业"])
    idx = options.index(chosen) if chosen in options else 0
    picked = st.selectbox("选择板块查看详情", options, index=idx, key="cube_pick")
    _drill(merged, picked)

    st.divider()
    render_data_degradation_banner()


fragment_cube()
