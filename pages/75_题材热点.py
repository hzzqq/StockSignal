"""页面 75：题材热点追踪（G7）

对标钱来终端的题材视角：**Squarified treemap 热力图**（面积=板块总市值，颜色=涨跌幅，
A 股红涨绿跌）+ 题材**生命周期**（发酵 / 高潮 / 退潮 / 平淡）。

差异化：不只看「哪个题材涨」，还把题材按热度分位打上生命周期标签，帮判断「是启动、
是高潮、还是在退潮」，并与领涨股联动。

数据源：东财概念板块实时快照（akshare ``stock_board_concept_name_em``，缓存 120s）。

诚实性红线：
  · 生命周期为**启发式分类**（涨跌幅 + 换手率分位），非预测；退潮/高潮为事后描述；
  · 取不到快照时明示「未就绪」，不用陈旧数据假装实时。
"""
from __future__ import annotations

import logging
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from modules import event_graph as evg
from modules.page_utils import render_standard_page
from modules.theme_heat import LIFECYCLE_ORDER, col_of, load_concepts
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)

# A 股红涨绿跌配色（负=绿，0=灰，正=红）
_LIFE_COLOR = {"高潮": "#dc2626", "发酵": "#f97316", "退潮": "#16a34a", "平淡": "#64748b", "未知": "#94a3b8"}

# 事件传导（H3）的 session 状态键；方向配色由 modules/event_graph.DIR_COLOR 提供（有单测）
_EVG_STATE = "evg_payload"


def _evg_fetch_titles(limit: int = 60) -> list:
    """抓近期市场新闻标题 → ``[(标题, 日期)]``。

    取不到 → 返回 ``[]``（页面明示「无标题」），**不用陈旧标题顶替**。
    ``auto_save=False``：本次只是页面内分析，不往新闻库写重复记录。
    """
    from modules.news import EventMiner

    df = EventMiner().mine_events(limit=limit, auto_save=False)
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for _, r in df.iterrows():
        title = str(r.get("title") or "").strip()
        date = str(r.get("date") or "").strip()[:10]
        if title:
            out.append((title, date))
    return out


def _evg_render(res: dict) -> None:
    """渲染传导结果：KPI + 口径 + 缺成分股警示 + 关联排行。

    行的构造 / 配色 / 截断全部走 ``evg.display_rows()``（纯函数，另有单测覆盖），
    这里只负责拼 HTML 与 Streamlit 组件。
    """
    entries = res.get("entries") or []
    k1, k2, k3 = st.columns(3)
    with k1:
        sf_metric("关联标的", str(len(entries)), "文本共现命中")
    with k2:
        sf_metric("命中概念", str(len(res.get("concepts_hit") or [])), "东财真实概念板块")
    with k3:
        top = entries[0] if entries else {}
        sf_metric("最贴近标的", str(top.get("name") or "—"), f"关联度 {top.get('score', 0)}")

    st.caption(f"口径：{res.get('basis', '')}")

    miss = res.get("members_unavailable") or []
    if miss:
        st.warning("以下概念**取不到成分股**（接口失败，不等于「无成分股」），已从结果中排除："
                   + "、".join(str(x) for x in miss))

    head = ("<div style='display:grid;grid-template-columns:30px 1.3fr 62px 52px 1.5fr 2.2fr;"
            "gap:8px;padding:6px 0;font-size:11px;opacity:.6;"
            "border-bottom:1px solid rgba(148,163,184,.3)'>"
            "<span>#</span><span>标的</span><span>关联度</span><span>方向</span>"
            "<span>命中概念</span><span>证据标题</span></div>")
    rows = head
    shown = evg.display_rows(res, limit=30)
    for i, r in enumerate(shown, 1):
        badge = ("<span style='color:#f59e0b;font-size:10px;margin-left:5px;"
                 "border:1px solid rgba(245,158,11,.5);border-radius:3px;padding:0 3px'>点名</span>"
                 if r["direct"] else "")
        rows += (
            "<div style='display:grid;grid-template-columns:30px 1.3fr 62px 52px 1.5fr 2.2fr;"
            "gap:8px;padding:5px 0;font-size:12px;align-items:center;"
            "border-bottom:1px solid rgba(148,163,184,.12)'>"
            f"<span style='opacity:.5'>{i}</span>"
            f"<span><b>{r['name']}</b>{badge}"
            f"<span style='opacity:.5;font-size:11px'> {r['code']}</span></span>"
            f"<span><b>{r['score']}</b></span>"
            f"<span style='color:{r['dir_color']}'>{r['direction']}</span>"
            f"<span style='opacity:.85;font-size:11px'>{r['concepts']}</span>"
            f"<span style='opacity:.6;font-size:11px'>{r['evidence']}</span></div>"
        )
    st.markdown(rows, unsafe_allow_html=True)
    if len(entries) > len(shown):
        st.caption(f"仅展示前 {len(shown)} 名（共 {len(entries)} 个关联标的）。")

    st.caption(f"⚠️ {res.get('disclaimer', '')}")


dark = render_standard_page(
    title="题材热点追踪", icon="🧱",
    caption="概念板块 treemap 热力图（面积=总市值，颜色=涨跌幅，红涨绿跌）+ 生命周期"
            "（发酵/高潮/退潮/平淡）。启发式分类，非预测。数据源东财概念板块快照。",
)

try:
    df = load_concepts()
except Exception as e:  # noqa: BLE001
    logger.warning(f"[theme-heat] 概念快照获取失败: {e}")
    st.error("⚠️ 概念板块数据获取失败（网络不可用或接口异常），请稍后重试。")
    st.stop()

if df is None or df.empty:
    st.info("📭 概念板块快照未就绪（可能非交易时段或接口暂不可用）。")
    st.stop()

name_c = col_of(df, "name")
if not name_c:
    st.info("📭 数据源缺少板块名称字段，无法绘制热力图。")
    st.stop()

chg = df["_chg"]
n_up = int((chg > 0).sum())
n_down = int((chg < 0).sum())
top_name = str(df.loc[chg.idxmax(), name_c]) if len(df) else "—"
top_chg = float(chg.max()) if len(df) else 0.0

# ── ① KPI ──────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    sf_metric("概念板块数", str(len(df)), "东财概念")
with c2:
    sf_metric("上涨板块", str(n_up), "红盘")
with c3:
    sf_metric("下跌板块", str(n_down), "绿盘")
with c4:
    sf_metric("领涨题材", top_name, f"{top_chg:+.2f}%")

st.markdown("---")

# ── ② treemap 热力图 ──────────────────────────────────────────────────
section_header("题材热力图", "方块面积=板块总市值，颜色=涨跌幅（红涨绿跌）", icon="🗺️")
mv_c = col_of(df, "mv")
vals = df[mv_c] if mv_c else (chg.abs() + 1.0)
mx = max(abs(float(chg.min() or 0)), abs(float(chg.max() or 0)), 1.0)
fig_tm = go.Figure(go.Treemap(
    labels=df[name_c].astype(str).tolist(),
    parents=[""] * len(df),
    values=(vals.fillna(0) if hasattr(vals, "fillna") else vals),
    marker=dict(
        colors=chg, cmin=-mx, cmax=mx, cmid=0, showscale=True,
        colorscale=[[0.0, "#16a34a"], [0.5, "#94a3b8"], [1.0, "#dc2626"]],
        colorbar=dict(title="涨跌幅%"),
    ),
    text=[f"{v:+.1f}%" for v in chg],
    textinfo="label+text",
    hovertemplate="%{label}<br>涨跌幅 %{text}<extra></extra>",
))
fig_tm.update_layout(template="plotly_dark" if dark else "plotly_white",
                     height=520, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(fig_tm, width="stretch")

st.markdown("---")

# ── ③ 生命周期分布 + 明细 ─────────────────────────────────────────────
cc1, cc2 = st.columns([2, 3])
with cc1:
    section_header("生命周期分布", "按涨跌幅+换手分位启发式分类", icon="🔄")
    life = df["_life"].value_counts()
    order = [x for x in LIFECYCLE_ORDER if life.get(x, 0) > 0]
    fig_life = go.Figure(go.Bar(
        x=[life.get(x, 0) for x in order], y=order, orientation="h",
        marker_color=[_LIFE_COLOR.get(x, "#94a3b8") for x in order],
        text=[life.get(x, 0) for x in order], textposition="outside",
    ))
    fig_life.update_layout(template="plotly_dark" if dark else "plotly_white",
                          height=300, margin=dict(l=10, r=10, t=20, b=10),
                          xaxis_title="板块数", showlegend=False)
    st.plotly_chart(fig_life, width="stretch")

with cc2:
    section_header("热度榜（涨幅 Top 20）", "含生命周期标签与领涨股", icon="🏆")
    leader_c = col_of(df, "leader")
    top = df.sort_values("_chg", ascending=False).head(20)
    rows = ""
    for _, r in top.iterrows():
        nm = str(r.get(name_c, ""))
        ch = float(r["_chg"])
        lf = str(r.get("_life", ""))
        lead = str(r.get(leader_c, "")) if leader_c else ""
        rows += (
            "<div style='display:flex;justify-content:space-between;padding:5px 0;"
            "border-bottom:1px solid rgba(148,163,184,.15);font-size:13px'>"
            f"<span>{nm} <span style='opacity:.55;font-size:11px'>{lead}</span></span>"
            "<span>"
            f"<span style='color:{_LIFE_COLOR.get(lf, '#94a3b8')};font-size:11px;margin-right:8px'>{lf}</span>"
            f"<b style='color:{'#dc2626' if ch >= 0 else '#16a34a'}'>{ch:+.2f}%</b></span></div>"
        )
    st.markdown(rows, unsafe_allow_html=True)

st.markdown("---")

# ── ④ 事件传导图谱（H3）──────────────────────────────────────────────
section_header("事件传导图谱", "从「一条消息」走到「谁可能受影响」——文本共现关联度，非收益预测", icon="🧭")

st.caption("按需生成：抓取近期市场新闻标题 → 识别标题里**真正命中**的概念题材 → 展开东财真实成分股 "
           "→ 按「文本共现强度」排序（概念命中 ×1；个股与概念同标题被点名 ×3）。"
           "**关联度高只说明这条消息在文本上更贴近它，不代表受益程度，更不是收益预测。**")

_evg_payload = st.session_state.get(_EVG_STATE)

_b1, _b2 = st.columns([1, 3])
with _b1:
    if st.button("🔍 生成传导图谱", type="primary", key="evg_run"):
        with st.spinner("抓取新闻标题并解析概念（约 10–20 秒）…"):
            _ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                _titles = _evg_fetch_titles()
                if not _titles:
                    # 「没抓到标题」与「概念数据取不到」是两回事，分开讲，别混成一句
                    st.session_state[_EVG_STATE] = {
                        "res": None, "n_titles": 0, "n_concepts": 0, "ts": _ts,
                        "notice": "未取到任何新闻标题（网络不可用或新闻接口异常）——不做传导推断。",
                    }
                else:
                    _idx = evg.build_index_for_titles(_titles)
                    st.session_state[_EVG_STATE] = {
                        "res": evg.build_transmission(_titles, _idx),
                        "n_titles": len(_titles),
                        "n_concepts": len(_idx),
                        "ts": _ts,
                        "error": None,
                    }
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[theme-heat] 事件传导生成失败: {e}")
                st.session_state[_EVG_STATE] = {"res": None, "ts": _ts, "error": str(e)}
        _evg_payload = st.session_state.get(_EVG_STATE)
with _b2:
    if _evg_payload and not _evg_payload.get("error"):
        st.caption(f"最近一次生成：{_evg_payload.get('ts', '—')}｜新闻标题 "
                   f"{_evg_payload.get('n_titles', 0)} 条｜取到成分股的概念 {_evg_payload.get('n_concepts', 0)} 个")

if not _evg_payload:
    st.info("👆 点击上方按钮生成。默认**不自动抓取**——避免每次进入页面都空等网络。")
elif _evg_payload.get("error"):
    st.error(f"⚠️ 生成失败：{_evg_payload['error']}")
elif _evg_payload.get("notice"):
    st.warning(f"⚠️ {_evg_payload['notice']}")
else:
    _res = _evg_payload.get("res") or {}
    _status = _res.get("status")
    if _status == "unavailable":
        st.warning(f"⚠️ 传导不可用：{_res.get('reason', '未取到真实概念数据')} "
                   "—— 不展示任何**臆造的题材关联表**。")
    elif _status == "empty":
        st.info(f"📭 {_res.get('reason', '标题里没有命中任何已知概念')}"
                f"（已分析 {_res.get('n_titles', 0)} 条标题）")
    else:
        _evg_render(_res)

st.markdown("---")

st.caption("⚠️ 说明：生命周期为启发式分类（涨跌幅 + 换手率分位），是对**当下状态**的描述，"
           "非预测；「高潮」不代表继续，「退潮」不代表必然反弹。不构成投资建议。")
