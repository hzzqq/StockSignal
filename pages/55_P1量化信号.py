"""
页面：P1 量化信号（EV / GRU / regime 融合）

把 P1-QuantFactor 训练好的「未来 N 日超额收益概率」信号接入 StockSignal：
- 看多 / 看空榜单（按模型切换，默认 EV 事件因子——全量口径最优）
- 三信号 A/B 对比（top_long 重叠度，验证 EV 是否真优于 GRU / 融合）
- 个股信号查询（近 40 日每日预测得分走势）

信号来源：P1 导出的 signal_*.json（见 modules/p1_signal 的自动发现逻辑）。

⚠️ 口径铁律（页面内已明示用户）：
- 这是「统计意义上的超额收益概率」，**不是**「明天必涨/必跌」。
- 2026 单年口径订正：此前「仍为负」系 rf=15 错配桶（信号 10 日窗口在 15 日持有中衰减）所致；阶段 18/19 改用 rf=10（=horizon，非重叠桶）后 2026 已转正——GRU +8.67%、EV(fusion) +11.56%，多年度（2022–2026）复合正期望不变。
- 信号为市场中性多空（看多/看空各 N 只）；A 股零售场景通常**仅取多头侧**或降权空头。
"""
import pandas as pd
import streamlit as st

from modules.page_utils import render_standard_page, import_autorefresh
from modules.ui_theme import sf_card, sf_metric
from modules.ui_kit import xc_warn_box, xc_success_box
from modules.p1_signal import P1SignalLoader

dark = render_standard_page(
    title="P1 量化信号",
    icon="🧠",
    caption="接入 P1-QuantFactor 的神经网络预测信号（EV 事件因子 / GRU / regime 融合），"
            "提供看多·看空榜单与三信号 A/B 对比。结果仅供参考，非投资建议。",
)

# 自动刷新：P1 重新导出信号（文件 mtime 变化）或超 5min ttl 即重载；未变化则不重读大文件。
st_autorefresh = import_autorefresh()
if st_autorefresh is not None:
    st_autorefresh(interval=300000, limit=200, key="p1_auto")

# ───────────────────────── 加载器（会话级缓存 + 实时刷新） ─────────────────────────
if "p1_loader" not in st.session_state:
    st.session_state.p1_loader = P1SignalLoader(ttl=300)
loader: P1SignalLoader = st.session_state.p1_loader

models = loader.available_models()
if not models:
    xc_warn_box(
        "未找到 P1 信号文件",
        hint="请把 P1 导出的 signal_*.json 放到 StockSignal 的 data/p1_signals/ 目录，"
             "或设置环境变量 P1_SIGNAL_DIR 指向其所在目录。",
    )
    st.stop()

label_to_key = {loader.model_label(m): m for m in models}
ev_label = loader.model_label("ev")
default_idx = list(label_to_key.keys()).index(ev_label) if ev_label in label_to_key else 0

# ───────────────────────── 侧边栏控制 ─────────────────────────
with st.sidebar:
    sel_label = st.selectbox("信号模型", list(label_to_key.keys()), index=default_idx)
    model = label_to_key[sel_label]
    n = st.slider("榜单只数", 5, 30, 20, 5)
    if st.button("🔄 刷新信号", key="p1_refresh", width="stretch",
                 help="清除缓存并重新读取信号文件（P1 重新导出后点此立即生效）"):
        loader.invalidate()
        st.rerun()
    st.caption(f"数据日期：{loader.latest_date(model) or '未知'}　·　每 5 分钟自动刷新")

# ───────────────────────── 头部说明 + 口径警告 ─────────────────────────
sf_card(
    "P1 量化信号 · 接入说明",
    "信号由 P1-QuantFactor 用 1427 只 A 股训练的 GRU 神经网络产出，EV 模型在 38 维量价特征上"
    "额外并入「牧羊人市场广度情绪」9 维作为事件/regime 通道（共 47 维）。EV 为全量 1427 严格"
    "hold-out 口径下的最优候选。",
    icon="🧠",
)
xc_warn_box(
    "⚠️ 阅读前必读（口径）",
    hint="这是「统计意义上的超额收益概率」，**不是**「明天必涨/必跌」的预测。2026 单年口径订正："
         "此前「仍为负」系 rf=15 错配桶（信号 10 日窗口在 15 日持有中衰减）所致；阶段 18/19 改用 rf=10（=horizon，非重叠桶）后"
         "2026 已转正（GRU +8.67%、EV(fusion) +11.56%），多年度（2022–2026）复合正期望。信号为市场中性多空，"
         "A 股零售场景通常仅取多头侧。",
)

# ───────────────────────── 选中模型概览 ─────────────────────────
s = loader.summary().get(model, {})
c1, c2, c3, c4 = st.columns(4)
with c1:
    sf_metric("数据日期", s.get("latest_date", "—"))
with c2:
    sf_metric("预测周期", f"h{s.get('horizon', '?')}")
with c3:
    sf_metric("看多/看空", f"{s.get('n_top_long', 0)}/{s.get('n_top_short', 0)}")
with c4:
    sf_metric("逐日样本", f"{s.get('n_daily', 0):,}")


# ───────────────────────── 榜单渲染 ─────────────────────────
def _board_html(rows, head_color, empty="无数据"):
    if not rows:
        return f"<div style='color:#888;padding:8px'>{empty}</div>"
    body = ""
    for i, r in enumerate(rows, 1):
        pred = float(r.get("pred", 0.0) or 0.0)
        sym = r.get("symbol", "")
        rank = float(r.get("rank", 0.0) or 0.0)
        pcolor = "#ff5c5c" if pred >= 0 else "#19c37d"  # A股：涨红跌绿
        body += (
            f"<tr><td style='color:#888'>{i}</td>"
            f"<td style='font-family:monospace'>{sym}</td>"
            f"<td style='color:{pcolor};font-weight:600'>{pred*100:+.2f}%</td>"
            f"<td style='color:#888'>{rank*100:.0f}%</td></tr>"
        )
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
        f"<thead><tr style='color:{head_color};text-align:left'>"
        "<th>#</th><th>代码</th><th>预测得分</th><th>排名</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


long_rows = loader.top_long(model, n)
short_rows = loader.top_short(model, n)

st.markdown("### 📈 看多榜（前 {n} 只，红=A股涨色）".format(n=n))
st.markdown(_board_html(long_rows, "#ff5c5c"), unsafe_allow_html=True)

st.markdown("### 📉 看空榜（前 {n} 只，绿=A股跌色）".format(n=n))
st.markdown(_board_html(short_rows, "#19c37d"), unsafe_allow_html=True)

# ───────────────────────── 三信号 A/B 对比 ─────────────────────────
if len(models) >= 2:
    st.markdown("### 🔬 三信号 A/B 对比（看多榜重叠度）")
    st.caption("Jaccard = 两模型看多榜交集 / 并集；重叠越低说明信号越互补。"
               "EV 与 GRU/融合高重叠属正常（同源 GRU），差异主要体现在湍流期的 regime 收缩。")

    body = ""
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            a, b = models[i], models[j]
            try:
                jac, inter = loader.top_overlap(a, b, n)
            except Exception:
                jac, inter = 0.0, 0
            body += (
                f"<tr><td>{loader.model_label(a)}</td><td>{loader.model_label(b)}</td>"
                f"<td style='text-align:center'>{inter}/{n}</td>"
                f"<td style='text-align:center;color:#9ec5fe'>{jac:.2f}</td></tr>"
            )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
        "<thead><tr style='color:#9ec5fe;text-align:left'>"
        "<th>信号 A</th><th>信号 B</th><th style='text-align:center'>看多榜重叠(前{n})</th>"
        "<th style='text-align:center'>Jaccard</th></tr></thead>"
        f"<tbody>{body}</tbody></table>".format(n=n),
        unsafe_allow_html=True,
    )
    xc_success_box(
        "如何解读",
        hint="EV 在 2026 全量严格 hold-out 下把亏损从纯 GRU 的 −4.11% 收窄到 −1.87%（+2.24pp），"
             "且 IC 最高（0.0842）——全量候选最优。重叠高说明三者同源，EV 是同一 GRU 的"
             "事件因子增强版，而非独立新信号。",
    )

# ───────────────────────── 个股信号查询 ─────────────────────────
st.markdown("### 🔍 个股信号查询")
sym = st.text_input("输入 P1 代码（如 sh600000 / sz000001）", "")
if sym:
    df = loader.daily_df(model)
    if df is not None and not df.empty:
        sub = df[df["symbol"] == sym].copy()
        if sub.empty:
            st.info(f"信号文件中无 `{sym}` 的逐日记录（可能不在 1427 只池内或近期无预测）。")
        else:
            sub["date"] = pd.to_datetime(sub["date"])
            sub = sub.sort_values("date").tail(40)
            st.line_chart(sub.set_index("date")[["score"]], height=220,
                          width="stretch")
            st.dataframe(sub[["date", "symbol", "score", "signal"]].rename(
                columns={"score": "预测得分", "signal": "信号"}), width="stretch")
    else:
        st.info("无法加载 daily 明细（pandas 不可用或文件解析失败）。")

st.markdown("---")
st.caption("数据：P1-QuantFactor（1427 只 A 股，严格 2026 hold-out）。"
           "本页仅做信号可视化与对比，不构成任何投资建议。")
