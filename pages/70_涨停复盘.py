"""页面 70：涨停复盘 × 龙头识别

对标自 Money-Come-Terminal（钱来终端）的「龙头战法打板系统」与 tick-stock-panel 的
连板梯队，但**不是照抄**——在它的打板视角之上，叠加本项目独有的三样东西做交叉验证：

  1. 首次封板时间线（早板 > 上午板 > 午板 > 尾板）：钱来只做分类，我们把「封板时刻」
     当独立维度画出来——早盘一字/秒板代表资金决心，尾盘偷袭板多是跟风。
  2. 龙头多维评分（连板高度 + 封单强度 + 板块地位 + 成交额）：钱来有「多维龙头评分」，
     我们把它做成**可解释的加权分解**（每项 0-100 可单独看），不黑箱。
  3. 与《市场状态机》五档 + 牧羊人炸板率交叉验证：钱来是纯打板工具，我们有情绪周期。

数据源：东财涨停池（akshare stock_zt_pool_em，经 shepherd._zt_pool_detail_cached 缓存
10 分钟）。字段含 连板数/所属行业/封板资金/首次封板时间/炸板次数/成交额/换手率。

诚实性红线（本页可见）：
  · 非交易日或数据未就绪时明确提示，不用陈旧数据假装「今日」。
  · 龙头评分为**启发式加权**，不是预测模型；不承诺次日涨跌。
  · 该接口只覆盖当日涨停池，历史复盘需逐日切换日期（不编造跨日序列）。
"""
import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules.page_utils import render_standard_page
from modules.shepherd import _trading_days, _zt_pool_detail_cached, get_zt_ladder
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)

# ── 列名候选（东财字段偶有增删，按候选表匹配而非硬编码）──────────────────
COL = {
    "code": ["代码"],
    "name": ["名称"],
    "boards": ["连板数"],
    "industry": ["所属行业"],
    "seal": ["封板资金"],
    "amount": ["成交额"],
    "first_seal": ["首次封板时间"],
    "last_seal": ["最后封板时间"],
    "broken": ["炸板次数"],
    "turnover": ["换手率"],
    "float_mv": ["流通市值"],
    "chg": ["涨跌幅"],
}

# 时间线分档（A 股：9:30 开盘 / 11:30 午休 / 13:00 复盘 / 15:00 收盘）
TIME_BANDS = [
    ("早板", 0, 10 * 60),          # 09:30-10:00：秒板/一字，资金决心最强
    ("上午板", 10 * 60, 11 * 60 + 30),
    ("午板", 13 * 60, 14 * 60),    # 13:00-14:00
    ("尾板", 14 * 60, 15 * 60 + 1),  # 14:00-15:00：多为跟风/偷袭
]
BAND_COLOR = {"早板": "#dc2626", "上午板": "#f97316", "午板": "#f59e0b", "尾板": "#94a3b8"}


def _col(df, key):
    """按候选列名取列；命中返回列名，否则 None（老接口/字段变更时优雅降级）。"""
    for c in COL.get(key, []):
        if c in df.columns:
            return c
    return None


def _num(df, key, default=0.0):
    c = _col(df, key)
    if not c:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[c], errors="coerce").fillna(default)


def _parse_hm(v):
    """把东财封板时间解析为「距 0 点分钟数」。兼容 '093000' / '09:30:00' / 93000。"""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return None
    s = s.replace(":", "").replace(".", "")
    if not s.isdigit():
        return None
    s = s.zfill(6)
    hh, mm = int(s[0:2]), int(s[2:4])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh * 60 + mm


def _band_of(minutes):
    if minutes is None:
        return "未知"
    for name, lo, hi in TIME_BANDS:
        if lo <= minutes < hi:
            return name
    return "其他"


def _ordinal_rank_pct(series):
    """百分位排名（0-100）。用排名而非 min-max，避免单只巨量封单把其余压成一条线。"""
    if series is None or len(series) == 0:
        return series
    n = len(series)
    if n <= 1:
        return pd.Series([100.0] * n, index=series.index)
    return series.rank(pct=True, method="average") * 100.0


def _leader_breakdown(df, ind_count):
    """龙头多维评分（可解释加权）。返回含各分项 0-100 的 DataFrame。

    权重（合计 1.0）：连板高度 0.35 / 封单强度 0.25 / 板块地位 0.20 / 成交额 0.20。
    高度权重最高——梯队高度是龙头最本质的属性；封单强度代表「愿不愿意锁仓」；
    板块地位（同行业涨停家数）代表「是不是板块旗手」；成交额代表资金容量。
    """
    out = df.copy()
    boards = _num(df, "boards", 1.0)
    seal = _num(df, "seal", 0.0)
    amount = _num(df, "amount", 0.0)
    ind = df[_col(df, "industry")].astype(str) if _col(df, "industry") else pd.Series([""] * len(df), index=df.index)
    ind_n = ind.map(ind_count).fillna(0)

    s_height = (boards / max(boards.max(), 1.0)) * 100.0
    s_seal = _ordinal_rank_pct(seal)
    s_ind = (ind_n / max(ind_n.max(), 1.0)) * 100.0
    s_amt = _ordinal_rank_pct(amount)

    out["_s_height"] = s_height.round(1)
    out["_s_seal"] = s_seal.round(1)
    out["_s_ind"] = s_ind.round(1)
    out["_s_amt"] = s_amt.round(1)
    out["_score"] = (
        0.35 * s_height + 0.25 * s_seal + 0.20 * s_ind + 0.20 * s_amt
    ).round(1)
    out["_ind_n"] = ind_n.astype(int)
    return out


def _score_bar(label, value, color):
    pct = max(0.0, min(100.0, float(value or 0)))
    return (
        "<div style='margin:4px 0'>"
        "<div style='display:flex;justify-content:space-between;font-size:11px;margin-bottom:1px'>"
        f"<span style='opacity:.75'>{label}</span>"
        f"<span style='color:{color};font-weight:700'>{pct:.0f}</span></div>"
        f"<div style='height:6px;background:{_hex_to_rgba(color,0.16)};border-radius:4px'>"
        f"<span style='display:block;height:100%;width:{pct:.1f}%;background:{color};border-radius:4px'></span>"
        "</div></div>"
    )


def _load_pool(date):
    """取涨停池明细并派生列。返回 (df, source_date) 或 (None, date)。"""
    df = _zt_pool_detail_cached(date)
    if df is None or df.empty:
        return None, date
    d = df.copy()
    cfs = _col(d, "first_seal")
    d["_first_min"] = d[cfs].map(_parse_hm) if cfs else None
    d["_band"] = d["_first_min"].map(_band_of)
    d["_boards_i"] = _num(d, "boards", 1.0).astype(int)
    return d, date


def _pick_default_date():
    """默认取最近一个有数据的交易日（最多回溯 4 个交易日，避免长网络等待）。"""
    try:
        days = _trading_days(6)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[zt-review] 交易日历获取失败: {e}")
        return None
    for d in reversed(days[-4:] if len(days) >= 4 else days):
        try:
            df = _zt_pool_detail_cached(d)
            if df is not None and not df.empty:
                return d
        except Exception:  # noqa: BLE001
            continue
    return days[-1] if days else None


dark = render_standard_page(
    title="涨停复盘 × 龙头识别", icon="🧾",
    caption="首板/二板/三板/高位板分类 + 首次封板时间线（早板＞尾板）+ 炸板追踪 + 龙头多维评分，"
            "并与市场状态/情绪温度交叉验证。数据源东财涨停池。",
)

# ── 日期选择 ────────────────────────────────────────────────────────────
try:
    _days = _trading_days(6)
except Exception:  # noqa: BLE001
    _days = []
_default = _pick_default_date()
if _default is None and _days:
    _default = _days[-1]

if not _days:
    st.error("无法获取交易日历（网络不可用）。请稍后重试。")
    st.stop()

_pick = st.selectbox(
    "复盘日期（最近交易日）",
    options=list(reversed(_days)),
    index=0,
    format_func=lambda x: f"{x[:4]}-{x[4:6]}-{x[6:]}",
    key="zt_review_date",
)

try:
    df, src_date = _load_pool(_pick)
except Exception as e:  # noqa: BLE001
    logger.warning(f"[zt-review] 涨停池获取失败: {e}")
    st.error("⚠️ 涨停池数据获取失败（网络不可用或接口异常），请稍后重试。")
    st.stop()
if df is None or df.empty:
    st.info(
        f"📭 **{_pick[:4]}-{_pick[4:6]}-{_pick[6:]}** 无涨停池数据——"
        "可能是非交易日、盘前（当日数据尚未生成）或接口暂不可用。可切换上方日期查看其他交易日。"
    )
    st.stop()

n_total = len(df)
boards_s = df["_boards_i"]
n_first = int((boards_s <= 1).sum())
n_connect = int((boards_s >= 2).sum())
max_boards = int(boards_s.max()) if n_total else 0

# 涨停池内「炸板次数 > 0」＝当日曾开板（烂板/反复板）
broken_s = _num(df, "broken", 0.0)
n_broken = int((broken_s > 0).sum())

# 炸板率（杨哥口径）优先取牧羊人真值源，取不到再退化用涨停池内比例
fail_ratio = None
limit_up_cnt = n_total
cycle = temp = None
try:
    from modules.shepherd import get_shepherd_indicators
    _dfi, _meta = get_shepherd_indicators(days=5)
    if _dfi is not None and not _dfi.empty:
        row = _dfi.iloc[-1]
        fr = row.get("zt_fail_ratio")
        fail_ratio = float(fr) if fr is not None and fr == fr else None
        lu = row.get("limit_up")
        if lu is not None and lu == lu:
            limit_up_cnt = int(lu)
except Exception as e:  # noqa: BLE001
    logger.warning(f"[zt-review] 牧羊人指标不可用: {e}")

try:
    from modules.shepherd import load_latest_snapshot
    _snap = load_latest_snapshot()
    if _snap:
        cycle = _snap.get("cycle")
        temp = _snap.get("temperature")
except Exception as e:  # noqa: BLE001
    logger.warning(f"[zt-review] 快照不可用: {e}")

st.caption(
    f"数据日期 **{src_date[:4]}-{src_date[4:6]}-{src_date[6:]}** · "
    f"涨停池 {n_total} 只（本页统计口径为涨停池内）"
    + (f" · 全市场涨停 {limit_up_cnt} 只" if limit_up_cnt != n_total else "")
)

# ── ① 顶层 KPI ─────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    sf_metric("涨停家数", str(limit_up_cnt), f"池内 {n_total}")
with c2:
    sf_metric("连板家数", str(n_connect), f"最高 {max_boards} 板")
with c3:
    sf_metric("首板家数", str(n_first), "接力基础盘")
with c4:
    fr_txt = f"{fail_ratio:.1f}%" if fail_ratio is not None else "—"
    sf_metric("炸板率", fr_txt, "炸板/(涨停+炸板)")
with c5:
    st.metric("池内曾开板", str(n_broken), help="涨停池内「炸板次数>0」的标的数（当日曾开板）")

st.markdown("---")

# ── ② 首次封板时间线（本页差异化维度）──────────────────────────────────
section_header(
    "首次封板时间线", "早板（09:30-10:00）资金决心最强；尾板（14:00 后）多为跟风/偷袭", icon="⏱️"
)
band_counts = df["_band"].value_counts()
band_order = [b for b, _, _ in TIME_BANDS] + ["其他", "未知"]
band_vals = [(b, int(band_counts.get(b, 0))) for b in band_order if band_counts.get(b, 0) > 0]

if band_vals:
    fig_tl = go.Figure(
        go.Bar(
            x=[b for b, _ in band_vals],
            y=[v for _, v in band_vals],
            marker_color=[BAND_COLOR.get(b, "#94a3b8") for b, _ in band_vals],
            text=[v for _, v in band_vals],
            textposition="outside",
        )
    )
    fig_tl.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=280, margin=dict(l=10, r=10, t=30, b=10),
        title="各时段封板家数分布", yaxis_title="家数", xaxis_title="封板时段",
        showlegend=False,
    )
    st.plotly_chart(fig_tl, width="stretch")
    early = sum(v for b, v in band_vals if b == "早板")
    late = sum(v for b, v in band_vals if b == "尾板")
    if early >= late and early > 0:
        st.success(f"✅ 早板 {early} 只 ≥ 尾板 {late} 只 —— 资金**开盘即抢筹**，情绪偏强。")
    elif late > early:
        st.warning(f"⚠️ 尾板 {late} 只 > 早板 {early} 只 —— 资金**盘中犹豫、尾盘偷袭**，接力意愿偏弱。")
else:
    st.info("该日涨停池未提供封板时间字段，时间线不可用（不影响下方分类与评分）。")

st.markdown("---")

# ── ③ 连板梯队分布 + 断层提示 ─────────────────────────────────────────
section_header("连板梯队分布", "梯队厚＝赚钱效应扩散；断层（如 4 板 1 家、3 板 0 家）＝接力资金缺席", icon="🪜")
try:
    ladder = get_zt_ladder(src_date)
except Exception as e:  # noqa: BLE001
    logger.warning(f"[zt-review] 梯队获取失败: {e}")
    ladder = {}

dist = ladder.get("distribution") or []
if dist:
    fig_lad = go.Figure(
        go.Bar(
            x=[f"{b}板" for b, _ in dist],
            y=[c for _, c in dist],
            marker_color=UP_COLOR,
            text=[c for _, c in dist],
            textposition="outside",
        )
    )
    fig_lad.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=280, margin=dict(l=10, r=10, t=30, b=10),
        title="连板家数分布（含首板）", yaxis_title="家数", xaxis_title="连板高度",
        showlegend=False,
    )
    st.plotly_chart(fig_lad, width="stretch")

    # 断层检测：最高板与次高板之间（≥2 板区间）是否缺档
    gaps = []
    lv = {b: c for b, c in dist if b >= 2}
    if lv:
        top = max(lv)
        for b in range(top - 1, 1, -1):
            if lv.get(b, 0) == 0:
                gaps.append(b)
    if gaps:
        st.warning(f"⚠️ **梯队断层**：{'、'.join(f'{b}板' for b in sorted(gaps, reverse=True))} 无个股 —— "
                   "接力资金缺席，主线可能是「一只独苗」，追高需谨慎。")
    else:
        st.success("✅ 连板梯队连续无断层，接力链条完整。")
else:
    st.info("暂无梯队分布数据。")

st.markdown("---")

# ── ④ 龙头识别榜（多维可解释评分）─────────────────────────────────────
section_header(
    "龙头识别榜", "综合分 = 0.35×连板高度 + 0.25×封单强度 + 0.20×板块地位 + 0.20×成交额（启发式，非预测）",
    icon="👑",
)
ind_col_name = _col(df, "industry")
ind_count = df[ind_col_name].astype(str).value_counts().to_dict() if ind_col_name else {}
ld = _leader_breakdown(df, ind_count)
ld = ld.sort_values("_score", ascending=False)

name_c, code_c = _col(ld, "name"), _col(ld, "code")
top = ld.head(10)
if name_c and len(top) > 0:
    rows_html = ""
    for _, r in top.iterrows():
        nm = str(r.get(name_c, ""))
        cd = str(r.get(code_c, "")) if code_c else ""
        bd = int(r["_boards_i"])
        ind = str(r.get(ind_col_name, "")) if ind_col_name else ""
        sc = float(r["_score"])
        sc_color = UP_COLOR if sc >= 70 else ("#f59e0b" if sc >= 45 else "#94a3b8")
        bars = (
            _score_bar("连板高度", r["_s_height"], "#dc2626")
            + _score_bar("封单强度", r["_s_seal"], "#f97316")
            + _score_bar("板块地位", r["_s_ind"], "#8b5cf6")
            + _score_bar("成交额", r["_s_amt"], "#0ea5e9")
        )
        rows_html += (
            "<div style='border:1px solid rgba(148,163,184,.25);border-radius:12px;"
            "padding:10px 12px;margin:8px 0;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div><span style='font-weight:700;font-size:15px'>{nm}</span> "
            f"<span style='opacity:.6;font-size:12px'>{cd} · {ind}</span></div>"
            f"<div style='text-align:right'><span style='font-size:19px;font-weight:800;color:{sc_color}'>{sc:.1f}</span>"
            f"<div style='font-size:11px;opacity:.6'>{bd}板 · 同业涨停 {int(r['_ind_n'])} 家</div></div></div>"
            f"<div style='margin-top:6px'>{bars}</div></div>"
        )
    st.markdown(rows_html, unsafe_allow_html=True)
else:
    st.info("龙头榜不可用（缺少名称列）。")

st.markdown("---")

# ── ⑤ 分档明细（首板/二板/三板/高位板）────────────────────────────────
section_header("分档明细", "按连板高度分组；含封单资金、炸板次数、首封时间", icon="🗂️")


def _detail_table(sub):
    show = pd.DataFrame()
    if code_c:
        show["代码"] = sub[code_c]
    if name_c:
        show["名称"] = sub[name_c]
    if ind_col_name:
        show["行业"] = sub[ind_col_name]
    show["连板"] = sub["_boards_i"]
    seal_c = _col(sub, "seal")
    if seal_c:
        show["封板资金"] = pd.to_numeric(sub[seal_c], errors="coerce")
    amt_c = _col(sub, "amount")
    if amt_c:
        show["成交额"] = pd.to_numeric(sub[amt_c], errors="coerce")
    bro_c = _col(sub, "broken")
    if bro_c:
        show["炸板次数"] = pd.to_numeric(sub[bro_c], errors="coerce")
    show["首封时间"] = sub["_band"]
    return show


tab_first, tab_2, tab_3, tab_high = st.tabs(["首板", "二板", "三板", f"高位板（≥4板）"])
with tab_first:
    t = _detail_table(df[df["_boards_i"] <= 1])
    st.dataframe(t, width="stretch", hide_index=True) if len(t) else st.info("无首板。")
with tab_2:
    t = _detail_table(df[df["_boards_i"] == 2])
    st.dataframe(t, width="stretch", hide_index=True) if len(t) else st.info("无二板。")
with tab_3:
    t = _detail_table(df[df["_boards_i"] == 3])
    st.dataframe(t, width="stretch", hide_index=True) if len(t) else st.info("无三板。")
with tab_high:
    t = _detail_table(df[df["_boards_i"] >= 4])
    st.dataframe(t, width="stretch", hide_index=True) if len(t) else st.info("无高位板。")

st.markdown("---")

# ── ⑥ 题材分布 + 炸板追踪 ─────────────────────────────────────────────
cc1, cc2 = st.columns([3, 2])
with cc1:
    section_header("题材分布", "涨停家数 Top10 行业（板块效应强度）", icon="🎨")
    if ind_col_name:
        ic = df[ind_col_name].astype(str).value_counts().head(10)
        fig_ind = go.Figure(
            go.Bar(x=ic.values[::-1], y=ic.index[::-1], orientation="h",
                   marker_color=UP_COLOR, text=ic.values[::-1], textposition="outside")
        )
        fig_ind.update_layout(
            template="plotly_dark" if dark else "plotly_white",
            height=320, margin=dict(l=10, r=30, t=20, b=10),
            xaxis_title="涨停家数", showlegend=False,
        )
        st.plotly_chart(fig_ind, width="stretch")
    else:
        st.info("无行业字段。")

with cc2:
    section_header("炸板追踪", "当日曾开板（炸板次数>0）——烂板/反复板，接力风险高", icon="💥")
    if int(n_broken) > 0 and name_c:
        bad = df[broken_s > 0].sort_values("_boards_i", ascending=False).head(15)
        rows = ""
        for _, r in bad.iterrows():
            nm = str(r.get(name_c, ""))
            cd = str(r.get(code_c, "")) if code_c else ""
            bc = int(_num(pd.DataFrame([r]), "broken", 0.0).iloc[0])
            rows += (
                "<div style='display:flex;justify-content:space-between;padding:5px 0;"
                "border-bottom:1px solid rgba(148,163,184,.15);font-size:13px'>"
                f"<span>{nm} <span style='opacity:.55;font-size:11px'>{cd}</span></span>"
                f"<span style='color:{DOWN_COLOR};font-weight:700'>开板 {bc} 次 · {int(r['_boards_i'])}板</span></div>"
            )
        st.markdown(rows, unsafe_allow_html=True)
    else:
        st.success("✅ 池内无炸板标的（无曾开板），封板质量较好。")

st.markdown("---")

# ── ⑦ 情绪周期交叉验证（本页差异化）───────────────────────────────────
section_header("情绪周期交叉验证", "把涨停结构与市场状态机/温度对接——纯打板工具没有这一层", icon="🔄")
try:
    from modules import market_regime as mr
    regime = mr.regime_report(k=8)
    state = regime["latest"]["state"] if regime.get("available") else None
except Exception as e:  # noqa: BLE001
    logger.warning(f"[zt-review] 状态机不可用: {e}")
    regime, state = None, None

v1, v2, v3 = st.columns(3)
with v1:
    sf_metric("市场状态", state or "—",
              f"置信度 {regime['latest']['confidence']*100:.0f}%" if regime and regime.get("available") else "—")
with v2:
    sf_metric("情绪周期", cycle or "—", "来自每日决策快照")
with v3:
    sf_metric("市场温度", f"{temp:.1f}" if isinstance(temp, (int, float)) else "—", "0-100")

notes = []
if state and max_boards >= 4 and n_connect >= 10:
    notes.append(f"状态 **{state}** + 最高 **{max_boards}** 板 + 连板 **{n_connect}** 家 —— 高度与厚度同向，赚钱效应扩散中。")
if state in ("暴跌", "恐慌") and n_connect >= 8:
    notes.append(f"⚠️ 状态 **{state}** 却仍有 **{n_connect}** 家连板 —— 警惕「逆势强票」是诱多，或情绪正在修复的早期。")
if fail_ratio is not None and fail_ratio >= 40:
    notes.append(f"⚠️ 炸板率 **{fail_ratio:.1f}%** 偏高（≥40%）—— 封板不牢，次日溢价不确定。")
if fail_ratio is not None and fail_ratio <= 20:
    notes.append(f"✅ 炸板率 **{fail_ratio:.1f}%** 偏低（≤20%）—— 封板质量高，情绪偏强。")
if not notes:
    notes.append("当前无明显的结构—状态背离信号；结合《市场状态机》《市场温度计》综合判断。")
for n in notes:
    st.markdown(f"- {n}")

st.caption(
    "⚠️ 说明：龙头评分为启发式加权（非预测模型），不构成投资建议；涨停池数据经 10 分钟缓存，"
    "盘中读数可能有延迟。历史复盘请逐日切换上方日期。"
)
