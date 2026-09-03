"""连板梯队全景共享渲染组件。

把 50_市场情绪.py 里的「连板梯队全景」区块抽成独立共享函数，
避免 god module 膨胀，并让 50_ 与未来页面复用同一套渲染逻辑。

设计要点：
- 自包含、惰性导入：函数体内才 import streamlit / plotly / modules，
  这样 50_ 无需为这个区块额外挂 import，测试也能按需触发。
- 不在此做任何网络抓取之外的副作用之外的落盘；落盘用 shepherd_ladder
  的 record_ladder_snapshot（已受 SS_DATA_DIR 隔离保护，测试不污染真实 data）。
- 与 54_今日决策面板 的 render_ladder_table 不同：本函数是「完整区块」
  （抓取 + 落盘 + 诊断 + 晋级率 + 代表股 + 柱状图），用于市场情绪页首屏；
  render_ladder_table 只是决策面板里的一张只读表。
"""

from __future__ import annotations


def render_ladder_block(dark: bool, top_per_level: int = 3) -> bool:
    """渲染连板梯队全景区块。

    返回 True 表示成功渲染（有梯队数据），False 表示无数据/抓取失败。
    `dark`：当前是否暗色主题，用于柱状图字体配色。
    """
    import streamlit as st
    import plotly.graph_objects as go
    from modules import shepherd_ladder as _sl
    from modules.shepherd import get_zt_ladder

    try:
        with st.spinner("加载连板梯队…"):
            lad = get_zt_ladder(top_per_level=top_per_level)
    except Exception:  # noqa: BLE001
        lad = None
    if not (lad and lad.get("levels")):
        return False

    # 落盘各档家数（供跨日晋级率递推；缺历史时后续晋级率优雅为 None）
    # 日期必须用 trading_date()（实时梯队所属的交易日），不能用数据源日期/now()。
    try:
        _sl.record_ladder_snapshot(_sl.trading_date(),
                                   lad.get("distribution"), lad.get("max_boards"), lad.get("total_connect"))
    except Exception:  # noqa: BLE001
        pass

    total = int(lad.get("total_connect") or 0)
    mx = int(lad.get("max_boards") or 0)

    # 梯队诊断：厚度 + 高度 + 断层
    if total >= 30 and mx >= 6:
        diag, dcolor = "梯队极厚 + 高度打开 → 主升确认，接力环境健康（注意盛极而衰）", "#ee2a2a"
    elif total >= 15:
        diag, dcolor = "梯队厚 → 赚钱效应线状扩散，接力顺畅", "#f59e0b"
    elif total >= 5:
        diag, dcolor = "梯队正常 → 有一定接力，但补涨梯队不够厚", "#3b82f6"
    else:
        diag, dcolor = "梯队断层 / 独苗行情 → 主线缺乏补涨，持续性差", "#00d486"

    # 断层检测：最高板往下到 2 板之间若有空档 = 接力资金缺席
    have = {int(l["boards"]) for l in lad["levels"]}
    gaps = [b for b in range(2, mx) if b not in have]
    if gaps:
        diag += f"；⚠️ **梯队断层**：{mx}板与2板之间缺 {'/'.join(str(g) + '板' for g in sorted(gaps, reverse=True))}，接力资金缺席"

    with st.container(border=True):
        st.markdown("**🪜 连板梯队全景**（最高板往下每一档的代表股，梯队厚度=赚钱效应能否扩散）")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("最高板", f"{mx} 板")
        with c2:
            st.metric("连板总家数(≥2板)", f"{total} 家")
        with c3:
            st.metric("梯队档位", f"{len(lad['levels'])} 档")
        st.markdown(
            f"<div style='border-left:3px solid {dcolor};padding-left:10px;"
            f"font-size:13px;color:{dcolor}'>{diag}</div>",
            unsafe_allow_html=True,
        )

        # 连板晋级率（跨日递推，需≥2日历史；比「家数」更细的接力信号）
        try:
            _pr = _sl.ladder_promotion_rates()
            # 用 overall 而非 rates["2b"]：2b 可能算不出（昨日缺首板档），
            # 此时 overall 已回落到可用档均值；直接格式化 None 会抛 TypeError。
            if _pr.get("ready") and _pr.get("overall") is not None:
                ov = float(_pr["overall"])
                p2 = _pr["rates"].get("2b")
                label = "首板→二板" if p2 is not None else "综合"
                _pr_txt = (f"📈 **连板晋级率（{label}）{ov:.1f}%**　"
                           f"历史 {_pr['days']} 日"
                           "　· 晋级率越高=接力意愿越强，梯队越能自我维持")
                st.markdown(
                    f"<div style='margin-top:6px;font-size:12px;opacity:.85'>{_pr_txt}</div>",
                    unsafe_allow_html=True,
                )
        except Exception:  # noqa: BLE001
            pass

        # 逐档代表股（封单大的优先）
        for lv in lad["levels"]:
            bs, cnt = int(lv["boards"]), int(lv["count"])
            names = []
            for s in lv.get("stocks", []):
                nm = s.get("name") or "—"
                cd = str(s.get("code") or "")[-6:]
                ind = s.get("industry") or ""
                seal = float(s.get("seal") or 0)
                seal_txt = f"封{seal / 1e8:.2f}亿" if seal > 0 else ""
                names.append(f"`{nm}({cd})` {ind} {seal_txt}".strip())
            line = f"**{bs}板** · {cnt}家：　" + "｜".join(names) if names else f"**{bs}板** · {cnt}家"
            st.markdown(line)

        # 连板分布柱状图（含首板）
        dist = lad.get("distribution") or []
        if dist:
            dx = [str(b) for b, _ in dist]
            dy = [c for _, c in dist]
            fig = go.Figure(go.Bar(
                x=dx, y=dy, marker_color="#ee2a2a", opacity=0.85,
                hovertemplate="%{x}板：%{y} 家<extra></extra>",
            ))
            fig.update_layout(
                height=230, margin=dict(l=10, r=10, t=28, b=10),
                title="连板数分布（含首板）",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6e6e6" if dark else "#1a1a1a", size=11),
                xaxis=dict(title="连板数", gridcolor="#2a2a3a" if dark else "#ececec"),
                yaxis=dict(title="家数", gridcolor="#2a2a3a" if dark else "#ececec"),
            )
            st.plotly_chart(fig, width="stretch",
                            config={"displaylogo": False, "responsive": True, "displayModeBar": False},
                            key="zt_ladder_bar")
        st.caption("杨哥：梯队「厚」= 赚钱效应线状扩散，接力顺畅；梯队「断层」= 接力资金缺席，"
                   "主线只是一只独苗。结合最高板高度判断情绪空间：高度打开 + 梯队厚 = 主升确认。")
    return True
