# -*- coding: utf-8 -*-
"""
页面 54：今日决策面板（StockSignal 差异化核心 —— 事件驱动 + 市场情绪闭环）

把牧羊人三块能力串成一条可直接用的决策链：
  情绪信号（市场温度 + 情绪周期六阶段 + 连板梯队晋级率）
        → 仓位建议（透明推导的仓位区间 + 一句话理由）
        → 复盘归档（保存今日决策快照 + 历史情绪回测验证准不准）

区别于 50_市场情绪（看「冷/热到什么程度」），本页只回答一个问题：
  「今天我该几成仓、为什么、盘后怎么验。」
数据层全部复用 modules.shepherd / shepherd_ladder / shepherd_forecast / shepherd_note，单源失败优雅降级。
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

from modules.page_utils import render_standard_page, import_autorefresh
from modules.ui_theme import sf_card
from modules.shepherd import (get_shepherd_indicators, shepherd_temperature, THRESHOLDS)
from modules import shepherd_ladder as _sl
from modules import shepherd_forecast as _sf
from modules import shepherd_note as _sn
# 仓位推导收敛到 modules.decision 单一实现：决策面板 / 每日快照脚本 / 首页 banner 三处共用，
# 避免各写一份漂移成互相矛盾的建议。改规则只需改 decision.derive_position 一处。
from modules.decision import derive_position, load_snapshot, is_stale, _event_position_adj, _event_long_symbols
from modules.decision_view import render_signal_cards, render_position_card, render_ladder_table
from modules import decision_track as _track
from modules import calibration as _cal
from modules.page_guard import safe_fragment
from modules.page_widgets import _section_title, _in_trading_hours, _empty_info
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box
from modules.p1_signal import P1SignalLoader  # P1 量化信号加载器（EV/GRU/融合）
from modules.event_factor import get_event_factor  # 事件因子适配器（真实信号，无合成）

st_autorefresh = import_autorefresh()

dark = render_standard_page(
    title="今日决策面板 · 情绪信号→仓位→复盘", icon="🎯",
    caption="把牧羊人三块能力串成一条可执行的决策链：市场温度 + 情绪周期六阶段 + 连板梯队晋级率 "
            "→ 透明推导的仓位建议 → 盘后保存快照、回测验证。事件驱动 + 市场情绪，是 StockSignal 的差异化主线。",
)
st.page_link("pages/50_市场情绪.py", label="🌡️ 看《市场情绪》广度与温度计（互补视角 / 指标明细）", icon="🔗")
sf_card(
    "今日决策面板 · 怎么用",
    "① 顶部「情绪信号总览」给你今天市场冷热的三个读数；② 「仓位建议」由温度/周期/评分/晋级率透明推导，"
    "可逐条核对理由；③ 盘后用「复盘归档」一键保存今日决策快照，并对历史情绪做回测，验证预判准不准。",
    icon="🎯",
)


# ───────────────────────── 本地辅助 ─────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _load_shepherd(days: int = 60):
    return get_shepherd_indicators(days=days)


def _row_to_indicators(df, i=-1):
    """牧羊人 DataFrame 第 i 行 → 指标 dict（供温度/预判/笔记用）。"""
    if df is None or getattr(df, "empty", True):
        return {}
    try:
        row = df.iloc[i]
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for k in df.columns:
        if k == "date":
            continue
        try:
            v = float(row[k])
            if v == v:
                out[k] = v
        except Exception:  # noqa: BLE901
            continue
    return out


def _last_data_date(df) -> str:
    """取牧羊人数据最后一行交易日；落盘类操作一律用它而非 now()，避免非交易日错位。"""
    try:
        return str(pd.to_datetime(df["date"].iloc[-1]).date())
    except Exception:  # noqa: BLEUE
        return pd.Timestamp.now().strftime("%Y-%m-%d")


def _signal_light(key, value):
    """按 THRESHOLDS 给单一牧羊人指标打信号灯（高=热 / 高=冷 / dir=0 观察项）。"""
    th = THRESHOLDS.get(key)
    if value is None or th is None:
        return ("—", "#888", "暂无数据")
    if th["dir"] == 0:
        return ("观察", "#888", f"{th['name']} {value:.2f}{th['unit']}（不参与温度计）")
    if th["dir"] > 0:
        if value >= th["hot"]:
            return (th["hot_label"], "#ee2a2a", f"{th['name']} {value:.0f}{th['unit']}，情绪亢奋")
        if value >= th["warm"]:
            return ("常温", "#f59e0b", f"{th['name']} {value:.0f}{th['unit']}，中性")
        return (th["cold_label"], "#3b82f6", f"{th['name']} {value:.0f}{th['unit']}，偏冷")
    else:
        if value <= th["hot"]:
            return (th["hot_label"], "#10b981", f"{th['name']} {value:.0f}{th['unit']}，安全")
        if value <= th["warm"]:
            return ("常温", "#f59e0b", f"{th['name']} {value:.0f}{th['unit']}，中性")
        return (th["cold_label"], "#ee2a2a", f"{th['name']} {value:.0f}{th['unit']}，风险")


# ───────────────────────── 顶部：情绪信号总览 + 仓位建议 ─────────────────────────
def _render_hero(df, today, prev, meta=None):
    # 数据来自 SQLite 缓存降级时，显示提示横幅（与 50_市场情绪 同口径）
    if meta and isinstance(meta, dict) and meta.get("_cache_fallback"):
        msg = meta.get("_cache_message", "当前展示为最近一次成功缓存的数据（网络暂时不可用）")
        st.markdown(
            f'<div style="background:#fff3cd;border:1px solid #ffc107;'
            f'border-radius:8px;padding:8px 14px;font-size:13px;color:#856404">'
            f'📦 <b>缓存模式</b>：{msg}</div>',
            unsafe_allow_html=True,
        )
    try:
        temp = shepherd_temperature(today)
    except Exception as e:  # noqa: BLE001
        xc_handle_error("市场温度计算失败", e)
        temp = 50.0
    try:
        fc = _sf.forecast_next_day(today, prev) if today else None
    except Exception as e:  # noqa: BLE001
        xc_handle_error("次日预判计算失败", e)
        fc = None
    try:
        promo = _sl.ladder_promotion_rates()
    except Exception:  # noqa: BLE001
        promo = dict(overall=None)

    cyc = (fc or {}).get("cycle") or {}
    bias = (fc or {}).get("bias", "中性")
    score = (fc or {}).get("score", 0)
    overall = promo.get("overall")

    # 环比 delta（较昨日）：温度直接算；晋级率用历史倒数第二日做基准
    prev_temp = None
    try:
        if prev:
            prev_temp = shepherd_temperature(prev)
    except Exception:  # noqa: BLE001
        prev_temp = None
    temp_delta = (temp - prev_temp) if (prev_temp is not None) else None
    prev_ov = None
    try:
        prev_ov = _sl.prev_overall()
    except Exception:  # noqa: BLE001
        prev_ov = None
    overall_delta = (overall - prev_ov) if (overall is not None and prev_ov is not None) else None

    # ① 情绪信号总览：四张读数卡（共享组件，与 50_市场情绪 同源，避免渲染漂移）
    render_signal_cards(temp, cyc.get("name", ""), cyc.get("emoji", "⚪"),
                        score, bias, overall, promo.get("latest_date", "—"),
                        temp_delta=temp_delta, overall_delta=overall_delta)

    # 数据新鲜度徽标：与「决策快照」快照片段同源（I2），避免实时面板假装最新（S2 自找缺口）
    # 事件因子滞后必须一并摊开：P1 信号的 latest_date 常远早于今天（实测滞后 21 天），
    # 只提示牧羊人滞后，会让「事件驱动催化 +2pt」看起来像当日结论。
    try:
        _dstr = _last_data_date(df)
        _age = (datetime.date.today() - datetime.date.fromisoformat(_dstr[:10])).days if _dstr else None
    except Exception:  # noqa: BLE001
        _age = None
    _ev_as_of = None
    try:
        _evd = _event_position_adj()
        if isinstance(_evd, dict):
            _ev_as_of = _evd.get("as_of")
    except Exception:  # noqa: BLE001
        _ev_as_of = None
    _ev_age = None
    if _ev_as_of:
        try:
            _ev_age = (datetime.date.today()
                       - datetime.date.fromisoformat(str(_ev_as_of)[:10])).days
        except Exception:  # noqa: BLE001
            _ev_age = None
    _lags = []
    if _age is not None:
        _lags.append(f"牧羊人 {_dstr}（滞后 {_age} 日）")
    if _ev_age is not None:
        _lags.append(f"事件因子 {_ev_as_of}（滞后 {_ev_age} 日）")
    if _lags:
        _max_age = max([a for a in (_age, _ev_age) if a is not None])
        if _max_age > 1:
            st.warning("⏰ 数据滞后：" + "、".join(_lags) + "——决策依据可能偏旧，谨慎参考")
        else:
            st.caption("数据截至：" + "、".join(_lags))

    # ② 仓位建议大卡（闭环的输出端）
    # 事件驱动催化：实时接通事件因子，消除「活/归档漂移」（S1 自找缺口）。
    # 与 build_snapshot 同源（都走 _event_position_adj），保证实时卡与归档快照一致；
    # 底层读 11MB 信号文件，靠模块级 300s 缓存避免每次刷新重读。失败则降级为 None（不臆造）。
    event_adj_val = None
    try:
        _ev = _event_position_adj()
        event_adj_val = _ev["adj"] if isinstance(_ev, dict) else None
    except Exception:  # noqa: BLE001
        event_adj_val = None
    # 暴露事件调节量到 session_state，供冒烟测试做「数据正确性」断言（不渲染、纯透传）
    try:
        st.session_state["decision_event_adj"] = event_adj_val
    except Exception:  # noqa: BLE001
        pass
    pos = derive_position(temp, score, bias, cyc.get("name", ""), overall,
                          event_adj=event_adj_val)
    # 暴露最终仓位到 session_state，供冒烟测试做「数据正确性」断言（不渲染、纯透传）
    try:
        st.session_state["decision_pos_pct"] = pos["pct"]
    except Exception:  # noqa: BLE001
        pass
    render_position_card(pos, bias=bias, confidence=(fc or {}).get("confidence", 0),
                         cyc_name=cyc.get("name", ""))

    # S4 事件驱动多头池下钻：实时卡可见具体标的，透明可解释（与事件催化同源）。
    # 信号可用（多头池非空）才展示；读不到/异常则静默降级，不拖崩卡片。
    try:
        ev_syms = _event_long_symbols(top_n=20)
    except Exception:  # noqa: BLE001
        ev_syms = None
    if ev_syms:
        _n = len(ev_syms)
        with st.expander(f"🔍 事件驱动多头池（前 {_n} 只，点开看标的）", expanded=False):
            _sym_df = pd.DataFrame(ev_syms).rename(
                columns={"symbol": "代码", "score": "模型百分位"})
            st.dataframe(_sym_df, width="stretch", hide_index=True, key="ev_long_expand")
            st.caption("事件驱动催化 +X% 即来源于此多头池广度（每满 10 只 +1pt）。"
                       "点开看具体标的，非买入建议；数据来自 P1 EV 事件因子。")


@safe_fragment("今日决策")
def fragment_decision():
    """情绪信号总览 + 仓位建议（交易时段自动刷新，隔离渲染失败）。"""
    if st_autorefresh is not None and _in_trading_hours():
        st_autorefresh(interval=180000, limit=80, key="dec_auto")
    try:
        with st.spinner("加载牧羊人指标…"):
            df, meta = _load_shepherd(60)
    except Exception as e:  # noqa: BLE401
        xc_handle_error("牧羊人指标加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
        return
    if df is None or df.empty:
        _empty_info("暂无牧羊人指标数据（网络/代理受限）。")
        return
    today = _row_to_indicators(df, -1)
    prev = _row_to_indicators(df, -2) if len(df) >= 2 else None
    try:
        today.update(_sl.current_promo_as_indicators())
    except Exception:  # noqa: BLE401
        pass
    _render_hero(df, today, prev, meta)


# ───────────────────────── 情绪信号明细（17 项温度计） ─────────────────────────
@safe_fragment("情绪信号明细")
def fragment_signals():
    _section_title("📡 情绪信号明细（牧羊人 17 项温度计）", accent="#7c5cff")
    try:
        df, _ = _load_shepherd(60)
    except Exception as e:  # noqa: BLE401
        xc_handle_error("牧羊人指标加载失败", e)
        return
    if df is None or df.empty:
        _empty_info("暂无数据。")
        return
    today = _row_to_indicators(df, -1)
    if not today:
        _empty_info("今日指标不足。")
        return

    cols = st.columns(3)
    idx = 0
    for key, th in THRESHOLDS.items():
        v = today.get(key)
        label, color, tip = _signal_light(key, v)
        with cols[idx % 3]:
            st.markdown(
                f"<div style='border-left:3px solid {color};padding:6px 10px;margin:5px 0;"
                f"background:rgba(255,255,255,.03);border-radius:0 8px 8px 0'>"
                f"<div style='display:flex;justify-content:space-between;font-size:13px'>"
                f"<span>{th.get('name', key)}</span>"
                f"<b style='color:{color}'>{label}</b></div>"
                f"<div style='font-size:12px;opacity:.7'>{tip}</div></div>",
                unsafe_allow_html=True,
            )
        idx += 1
    st.caption(f"数据日期：{_last_data_date(df)}　·　信号灯按《牧羊人·情绪温度计》阈值口径，红=热/风险，蓝=冷/安全，黄=中性。")


# ───────────────────────── 连板梯队晋级率 ─────────────────────────
@safe_fragment("连板梯队晋级率")
def fragment_ladder():
    _section_title("🪜 连板梯队晋级率（接力意愿温度计）", accent="#f59e0b")
    try:
        promo = _sl.ladder_promotion_rates()
    except Exception as e:  # noqa: BLE401
        xc_handle_error("晋级率计算失败", e)
        return
    if not promo.get("ready"):
        _empty_info("连板梯队历史不足 2 日，暂无晋级率（每日收盘后本页会自动落盘快照，积累后即可算）。")
        return
    overall = promo.get("overall")
    render_ladder_table(promo)


# ───────────────────────── P1 量化信号 · 多头侧灰度（事件驱动参考） ─────────────────────────
@safe_fragment("P1量化信号参考")
def fragment_p1_ev():
    """把 P1-QuantFactor 的 EV 看多榜接入决策面板，作为**多头侧灰度参考层**。

    ⚠️ 灰度定位：这是神经网络给出的「未来 N 日超额收益概率」排序，不是 StockSignal 的
    买入指令。它与本页牧羊人情绪信号相互独立、互为补充——情绪定仓位（该几成仓），
    P1 定个股（仓里买什么）。两者一致时增强信心，分歧时提示人工复核。
    """
    _section_title("🧠 P1 量化信号 · 多头侧灰度参考", accent="#5b6cff")
    if "p1_loader_54" not in st.session_state:
        st.session_state.p1_loader_54 = P1SignalLoader(ttl=300)
    ld: P1SignalLoader = st.session_state.p1_loader_54

    models = ld.available_models()
    if not models:
        _empty_info("未找到 P1 信号文件（data/p1_signals/ 或 P1 产出目录）。"
                    "详见 data/p1_signals/README.md。")
        return
    # 默认优先 EV（全量口径最优），否则取第一个可用模型
    model = "ev" if "ev" in models else models[0]

    col_ref, col_btn = st.columns([4, 1])
    with col_ref:
        st.caption(f"信号模型：**{ld.model_label(model)}**　·　数据日期：{ld.latest_date(model) or '未知'}"
                   f"　·　与牧羊人情绪信号独立互补（情绪定仓位 / P1 定个股）")
    with col_btn:
        if st.button("🔄 刷新", key="p1_ev_refresh", width="stretch",
                     help="P1 重新导出信号后点此立即生效"):
            ld.invalidate()
            st.rerun(scope="fragment")

    try:
        long_rows = ld.top_long(model, 15)
    except Exception as e:  # noqa: BLE401
        xc_handle_error("EV 看多榜加载失败", e)
        return

    # 灰度参考卡：明确标注 ML 参考、非买入指令；红=A股涨色
    body = (
        "P1 神经网络给出的多头候选（按预测得分排序）。**仅作参考，非买入指令**；"
        "A 股零售建议仅取多头侧，并与本页牧羊人仓位建议配合使用。"
    )
    sf_card("多头侧灰度 · EV 看多榜（前 15）", body, icon="🧠")

    if not long_rows:
        _empty_info("该信号无看多条目。")
        return
    rows_html = ""
    for i, r in enumerate(long_rows, 1):
        pred = float(r.get("pred", 0.0) or 0.0)
        sym = r.get("symbol", "")
        pcolor = "#ff5c5c" if pred >= 0 else "#19c37d"
        rows_html += (
            f"<tr><td style='color:#888'>{i}</td>"
            f"<td style='font-family:monospace'>{sym}</td>"
            f"<td style='color:{pcolor};font-weight:600'>{pred*100:+.2f}%</td></tr>"
        )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
        "<thead><tr style='color:#ff5c5c;text-align:left'>"
        "<th>#</th><th>代码</th><th>预测得分</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )

    # 稳定性附注：EV 与 GRU/融合看多榜重叠越低越互补；此处仅提示，不做重负载 A/B
    with st.expander("ℹ️ 这是什么 / 怎么用", expanded=False):
        st.markdown(
            "这是 P1-QuantFactor 用 1427 只 A 股训练的 GRU 神经网络、并入「牧羊人市场广度情绪」"
            "9 维事件因子后的**看多榜**。它是统计意义上的超额收益概率排序，**不是**涨跌预测；"
            "2026 单年仍为负，真实价值在 2022–2025。把它当「候选池」而非「指令」：\n"
            "- 与牧羊人仓位建议**一致**时（温度偏多 + P1 看多）→ 增强信心；\n"
            "- **分歧**时（温度退潮但 P1 仍看多某股）→ 提示人工复核，不盲目跟。\n"
            "完整三信号 A/B 对比见「🧠 P1 量化信号」专页。"
        )
    # A/B 重叠（轻量：仅与 gru 比，gru 已加载则快；未加载则跳过避免拉 55MB）
    if "gru" in models and model != "gru":
        try:
            jac, inter = ld.top_overlap(model, "gru", 15)
            st.caption(f"稳定性：与纯 GRU 看多榜重叠 {inter}/15（Jaccard={jac:.2f}）——"
                       f"同源 GRU 的高重叠属正常，差异主要在湍流期 regime 收缩。")
        except Exception:  # noqa: BLE401
            pass

    # ── 个股事件因子查询（事件因子适配器端到端可用）──
    st.divider()
    _q = st.text_input("🔍 查个股事件因子（P1 EV）",
                       placeholder="如 sh600000 / sz000001", key="p1_ev_symbol_q")
    if _q:
        try:
            ef = get_event_factor(_q.strip(), model=model, loader=ld)
        except Exception as e:  # noqa: BLE401
            ef = {"available": False, "reason": str(e)}
        if ef.get("available"):
            _sc = ef.get("score")
            if isinstance(_sc, (int, float)):
                _sc_txt = f"{_sc:+.2%}"
                _col = "#ff5c5c" if _sc >= 0 else "#19c37d"  # A股：涨红跌绿
            else:
                _sc_txt = "—"
                _col = "#888"
            st.markdown(
                f"**{ef['symbol']}**　事件因子得分："
                f"<span style='color:{_col};font-weight:600'>{_sc_txt}</span>"
                f"　信号：<b>{ef.get('signal')}</b>　来源：<code>{ef.get('source')}</code>",
                unsafe_allow_html=True)
    else:
        st.info(f"该标的无事件因子信号：{ef.get('reason', '未知')}")


@safe_fragment("事件驱动看多榜")
def fragment_event_driven_pool():
    """📈 事件驱动看多榜：把真实事件因子（P1 EV）直接落成「选股候选池」。

    与上方「🧠 P1 量化信号」的区别：那里是模型无关的「多头侧灰度参考」，
    这里是**事件因子维度的选股池**（ev 模型 = EV 事件因子，已并入牧羊人情绪
    9 维事件/regime 通道），明确标注真实信号来源，可直接喂给本页仓位决策。
    universe = P1 EV 池本身（模型已排序），免全市场 5000 股实时重排。
    """
    _section_title("📈 事件驱动看多榜（EV 事件因子 · 真实信号）", accent="#ff8a3d")
    try:
        from modules.event_factor import event_driven_long_list
        rows = event_driven_long_list(top_n=20, model="ev")
    except Exception as e:  # noqa: BLE401
        xc_handle_error("事件驱动看多榜加载失败", e)
        return

    if not rows:
        _empty_info("未找到 P1 EV 事件因子信号（data/p1_signals/ 或 P1 产出目录）。"
                    "接入真实信号后此处自动出现候选池；当前事件维度回退本地事件库。")
        return

    body = ("由 P1-QuantFactor 神经网络产出的**事件因子多头候选池**（EV 模型，已并入牧羊人情绪"
            "9 维事件/regime 通道）。这是统计意义上的超额收益概率排序，**非**买卖指令；"
            "建议仅取多头侧，并与本页牧羊人仓位建议配合使用。")
    sf_card("事件驱动 · EV 看多榜（前 20）", body, icon="📈")

    rows_html = ""
    for i, r in enumerate(rows, 1):
        sym = r.get("symbol", "")
        sc = r.get("score")
        sc_txt = f"{sc:.1f}" if isinstance(sc, (int, float)) else "—"
        # 百分位越高越红（A股涨色），但此处是「信号强度」而非涨跌，用橙红梯度更中性
        _col = "#ff8a3d"
        rows_html += (
            f"<tr><td style='color:#888'>{i}</td>"
            f"<td style='font-family:monospace'>{sym}</td>"
            f"<td style='color:{_col};font-weight:600'>{sc_txt}</td>"
            f"<td style='color:#888;font-size:12px'>{r.get('source','')}</td></tr>"
        )
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
        "<thead><tr style='color:#ff8a3d;text-align:left'>"
        "<th>#</th><th>代码</th><th>事件因子分</th><th>来源</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption("口径：事件因子分 = P1 模型百分位排名 × 100（越高越看多）。"
               "与牧羊人仓位建议**一致**时增强信心，分歧时提示人工复核。")


# ───────────────────────── 复盘归档（保存快照 + 历史回测） ─────────────────────────
@safe_fragment("复盘归档")
def fragment_review():
    _section_title("📔 复盘归档（保存今日决策快照 + 历史情绪回测）", accent="#7c5cff")
    try:
        df, _ = _load_shepherd(60)
    except Exception as e:  # noqa: BLE401
        xc_handle_error("牧羊人指标加载失败", e)
        return
    if df is None or df.empty:
        _empty_info("暂无数据。")
        return
    today = _row_to_indicators(df, -1)
    prev = _row_to_indicators(df, -2) if len(df) >= 2 else None
    try:
        today.update(_sl.current_promo_as_indicators())
    except Exception:  # noqa: BLE401
        pass
    dstr = _last_data_date(df)
    try:
        fc = _sf.forecast_next_day(today, prev) if today else None
    except Exception:  # noqa: BLE401
        fc = None

    with st.container(border=True):
        cyc = (fc or {}).get("cycle") or {}
        st.markdown(f"**📅 {dstr} 决策快照**　{cyc.get('emoji','')} {cyc.get('name','—')} ｜ "
                    f"评分 {(fc or {}).get('score',0):.0f} ｜ 次日 {(fc or {}).get('bias','—')}")
        # 数据新鲜度徽标：避免用陈旧指标却展示得「像最新的」（I2）
        try:
            from datetime import date as _d
            _age = (_d.today() - _d.fromisoformat(dstr[:10])).days if dstr else None
        except Exception:
            _age = None
        if _age is None:
            pass
        elif _age > 1:
            st.warning(f"⏰ 数据滞后 {_age} 日（最新指标截至 {dstr}）——决策依据可能偏旧，谨慎参考")
        elif _age >= 0:
            st.caption(f"数据截至 {dstr}（滞后 {_age} 日）")
        note_txt = st.text_area("今日决策手记（主线/计划/复盘感受，留空不改已存手记）", value="",
                                key="dec_note_text", height=80,
                                placeholder="例：温度 62 偏多，仓位 70%，盯连板晋级能否维持…")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 保存今日决策快照", key="dec_save", width="stretch"):
                ok = _sn.save_note(dstr, today, fc, note_txt or "")
                if ok:
                    xc_success_box("✅ 今日决策快照已保存（含指标 + 次日预判 + 手记）。")
                else:
                    xc_warn_box("⚠️ 保存失败，检查 data/ 写权限。")
        with b2:
            if st.button("🔄 回填次日实际", key="dec_backfill", width="stretch"):
                n = _sn.backfill_actuals(df)
                xc_success_box(f"✅ 已回填 {n} 条笔记的次日实际走势。") if n else st.caption("无需回填。")
        with b3:
            if st.button("🗑️ 删除今日快照", key="dec_del", width="stretch"):
                if _sn.delete_note(dstr):
                    xc_success_box("已删除今日快照。")
                else:
                    st.caption("今日尚无快照。")

    st.markdown("**🔬 历史情绪回测**（对过去每个交易日重跑情绪定位，统计「当时处某阶段→次日实际怎么走」）")
    rng = st.selectbox("回测区间", ["近 60 交易日", "近 250 交易日", "近 1250 交易日"],
                      index=0, key="dec_range")
    days_map = {"近 60 交易日": 60, "近 250 交易日": 250, "近 1250 交易日": 1250}
    if st.button("📊 分析历史情绪（真机回测）", key="dec_analyze", width="stretch"):
        try:
            with st.spinner("拉取真实区间数据并逐日重跑情绪定位…"):
                analysis, _meta = _sn.backtest_real(days_map[rng])
            if not analysis:
                st.caption("无回测结果（数据不足）。")
            else:
                st.info(_sn.summary_of(analysis))
        except Exception as e:  # noqa: BLE401
            xc_handle_error("历史回测失败", e)
    st.caption("📚 口径：杨哥复盘方法论（V反/延续）+ 实盘圈「盯四个数」。预判为概率结论，不构成投资建议。")


# ───────────────────────── 预测 vs 实际（准确率回测） ─────────────────────────
# ───────────────────────── 分情绪周期命中率（战术细分） ─────────────────────────
_GROUP_TIP = {
    "进攻期": "主升高潮 / 修复确认 —— 顺势期，看对了是应该的",
    "分化期": "高潮分化 —— 最容易骗人的阶段",
    "修复期": "修复试探 / 冰点 —— 分歧转一致，看对含金量高",
    "防守期": "退潮 —— 这时候看对才真正值钱",
}


def _acc_color(acc):
    """命中率配色（注意：这里是「可不可信」而非涨跌，不套红涨绿跌）。"""
    if acc is None:
        return "#888"
    if acc >= 60:
        return "#00d486"   # 可信
    if acc < 40:
        return "#ee2a2a"   # 不可信
    return "#f59e0b"       # 中性


def _render_cycle_breakdown(dark: bool):
    """按情绪周期拆解命中率 —— 回答「这套决策在哪些周期可信、哪些周期该打折」。"""
    st.markdown("#### 🎭 分情绪周期命中率（哪些周期该信、哪些该打折）")
    st.caption("总体命中率是个「平均数的谎言」—— 主升高潮期人人看对，退潮期看对才值钱。"
               "按周期拆开，才知道建议该打几折。")
    try:
        rows = _track.by_cycle()
        g_rows = _track.by_group(min_samples=2)
    except Exception as e:  # noqa: BLE001
        xc_handle_error("分周期统计失败", e)
        return
    if not rows:
        _empty_info("尚无分周期样本（需要已落盘且带情绪周期标注的预测记录）。")
        return

    # ① 四大战术分组（样本更集中，结论更稳）
    if g_rows:
        gcols = st.columns(len(g_rows) if len(g_rows) <= 4 else 4)
        for i, g in enumerate(g_rows[:4]):
            acc = g["accuracy"]
            with gcols[i % 4]:
                st.metric(
                    f"{g['group']}命中率",
                    f"{acc:.0f}%" if acc is not None else "—",
                    f"{g['hits']}/{g['n_call']} 次表态",
                    delta_color="off",
                )
                st.caption(_GROUP_TIP.get(g["group"], ""))
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[g["group"] for g in g_rows],
            y=[g["accuracy"] if g["accuracy"] is not None else 0 for g in g_rows],
            marker_color=[_acc_color(g["accuracy"]) for g in g_rows],
            text=[f"{g['accuracy']:.0f}%<br>({g['hits']}/{g['n_call']})"
                  if g["accuracy"] is not None else f"样本不足<br>({g['n_call']})"
                  for g in g_rows],
            textposition="outside",
            hovertemplate="%{x}<br>命中率 %{y:.1f}%<br>表态 %{text}<extra></extra>",
        ))
        fig.add_hline(y=50, line_dash="dash", line_color="#888",
                      annotation_text="抛硬币线 50%", annotation_position="bottom right")
        fig.update_layout(
            height=300, template="plotly_dark" if dark else "plotly_white",
            yaxis=dict(title="方向命中率(%)", range=[0, 100]),
            margin=dict(l=40, r=30, t=20, b=30), showlegend=False,
        )
        st.plotly_chart(fig, width="stretch", key="bt_cycle_bar")

    # ② 明细表：具体六阶段 + 平均建议仓位 vs 次日平均实际（看「敢不敢给」对不对）
    disp = pd.DataFrame([{
        "情绪周期": (r["cycle"] or "(未标注)"),
        "战术分组": r["group"],
        "记录": r["n"],
        "表态": r["n_call"],
        "命中": r["hits"],
        "命中率": "—" if r["accuracy"] is None else f"{r['accuracy']:.0f}%",
        "平均建议仓位": "—" if r["avg_pct"] is None else f"{r['avg_pct']:.0f}%",
        "次日平均实际": "—" if r["avg_realized"] is None else f"{r['avg_realized']:+.2f}%",
    } for r in rows])
    st.dataframe(disp, width="stretch", hide_index=True, key="bt_cycle_tbl")
    st.caption("📊 「平均建议仓位」= 该周期下系统平均给了几成仓；「次日平均实际」= 对应交易日上证平均涨跌。"
               "两者背离大说明该周期下的仓位刻度需要重新校准（如退潮期建议仓位偏高却持续下跌）。"
               "样本 <2 的分组不纳入上图统计。")


@safe_fragment("预测回测")
def fragment_backtest():
    _section_title("📈 预测 vs 实际 · 仓位预判准确率回测", accent="#7c5cff")
    st.caption("每天收盘后系统落盘一条「偏多/偏空 + 几成仓」预测；联网拉取次日上证指数真实涨跌，"
               "判定方向是否命中，积累出命中率与回测曲线。这是差异化主线「事件驱动 + 市场情绪」的能力验证。")
    try:
        s = _track.summary()
    except Exception as e:  # noqa: BLE401
        xc_handle_error("回测统计读取失败", e)
        return

    if s["n"] == 0:
        _empty_info("尚无预测记录。每日收盘后《daily_snapshot》脚本会自动落盘一条预测，积累几天后即可看回测曲线。")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("已记录预测", f"{s['n']} 天")
    c2.metric("已打分", f"{s['scored']} 天")
    c3.metric("方向命中率", f"{s['accuracy']:.0f}%" if s["accuracy"] is not None else "—")
    c4.metric("覆盖区间", f"{s['start']} ~ {s['end']}")

    if st.button("🔗 联网计算次日实际走势（打分）", key="bt_score", width="stretch"):
        try:
            with st.spinner("拉取上证指数次日涨跌并打分…"):
                res = _track.score_predictions()
            if res["scored"] == 0:
                st.info("本轮无新样本需要打分（可能已全部分数，或暂无法联网获取基准走势）。")
            else:
                acc = res["accuracy"]
                st.success(f"✅ 已对 {res['scored']} 条样本打分，累计方向命中率 "
                           f"{acc:.0f}%" if acc is not None else f"✅ 已对 {res['scored']} 条样本打分")
        except Exception as e:  # noqa: BLE401
            xc_handle_error("联网打分失败", e, hint="检查网络/代理；基准取不到时回测曲线仅显示预测侧")

    try:
        cd = _track.chart_data()
    except Exception as e:  # noqa: BLE401
        xc_handle_error("回测曲线生成失败", e)
        return
    if not cd or not cd["dates"]:
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cd["dates"], y=cd["predicted"], name="预测仓位(%)", mode="lines+markers",
        line=dict(color="#7c5cff", width=2), yaxis="y1",
    ))
    # 次日实际涨跌：有值才画（未打分样本为 None，plotly 自动跳过）
    if any(r is not None for r in cd["realized"]):
        fig.add_trace(go.Bar(
            x=cd["dates"], y=cd["realized"], name="次日上证涨跌(%)",
            marker_color=["#ee2a2a" if r and r > 0 else "#00d486" for r in cd["realized"]],
            yaxis="y2", opacity=0.45,
        ))
    fig.update_layout(
        height=360, template="plotly_dark" if dark else "plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(title="预测仓位(%)", range=[0, 100], side="left"),
        yaxis2=dict(title="次日涨跌(%)", overlaying="y", side="right", zeroline=True,
                    zerolinecolor="#888"),
        margin=dict(l=50, r=50, t=30, b=30),
    )
    st.plotly_chart(fig, width="stretch", key="bt_chart")
    st.caption("📈 紫线=当日预测仓位；红/绿柱=次日上证指数真实涨跌（红涨绿跌）。命中率=偏多/偏空预测中方向判断正确的比例。"
               "预判为概率结论，不构成投资建议。")

    # 分周期细分：总体命中率之上，再拆到「哪些周期可信」
    _render_cycle_breakdown(dark)


# ──────────────────────────────────────────────────────────────
# 刻度校准：用回测数据反推 CYCLE_ADJ 常数（只出建议，不自动改规则）
# ──────────────────────────────────────────────────────────────
@safe_fragment("刻度校准")
def fragment_calibration():
    _section_title("⚖️ 仓位刻度校准（用回测数据反推周期调节常数）", accent="#7c5cff")
    st.caption("decision.py 里的「情绪周期 → 仓位调节」常数（如退潮 −10、主升高潮 +5）当初是拍出来的。"
               "这里按四大战术分组对照「平均建议仓位 vs 次日真实涨跌」，算出**应该**调多少点。")
    try:
        v = _cal.verdict()
        sug = _cal.suggestions()
    except Exception as e:  # noqa: BLE401
        xc_handle_error("刻度校准计算失败", e)
        return

    if v["n_call"] == 0:
        _empty_info("尚无已打分的表态样本（中性预测不计入），无法校准刻度。"
                    "预测积累并打分后，本版块会自动给出各周期的建议调节量。")
        return

    if v["ready"]:
        xc_success_box(f"✅ {v['msg']}")
        # S3 闭环最后一英里：样本够后明确告诉老板如何落地（不自动改规则，人仍在回路）
        st.code("python scripts/apply_calibration.py --apply", language="bash")
        st.caption("⚠️ 默认 dry-run 仅预览将改哪些刻度；加 ``--apply`` 才写 "
                   "``decision.CYCLE_ADJ``（写前自动备份 + 审计日志）。人触发、人负责。")
    else:
        xc_warn_box(f"⏳ {v['msg']}。当前数值仅供观察趋势，**不要据此修改规则**——小样本算出的结论是噪音。")
    st.progress(min(v["n_call"] / float(v["strong_samples"]), 1.0),
                text=f"表态样本 {v['n_call']} / {v['strong_samples']} 条")
    # 样本新鲜度：评分自动化挂了，命中率会停在旧日期——必须如实暴露（I6）
    _lsd = v.get("last_scored_date")
    _stale = v.get("stale_days")
    if _lsd:
        if _stale is not None and _stale > 2:
            st.caption(f"🕓 最近一次打分：{_lsd}（{_stale} 天前）——若评分自动化未跑，命中率已过时")
        else:
            st.caption(f"🕓 最近一次打分：{_lsd}")

    if not sug:
        _empty_info("各分组表态样本均不足，暂不展示校准建议。")
        return

    rows = []
    for s in sug:
        rows.append({
            "战术分组": s["group"],
            "覆盖周期": "/".join(s["cycles"]) or "—",
            "表态数": s["n_call"],
            "平均建议仓位": f"{s['avg_pct']:.0f}%" if s["avg_pct"] is not None else "—",
            "次日平均实际": f"{s['avg_realized']:+.2f}%" if s["avg_realized"] is not None else "—",
            "暴露收益": f"{s['edge']:+.3f}%" if s["edge"] is not None else "—",
            "当前刻度": f"{s['cur_adj']:+.0f}" if s["cur_adj"] is not None else "—",
            "建议调节": f"{s['sug_delta']:+d} 点" if s["sug_delta"] else "0 点",
            "建议刻度": f"{s['sug_adj']:+.0f}" if s["sug_adj"] is not None else "—",
            "置信度": f"{s['confidence']:.0%}",
            "结论": s["verdict"],
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, key="cal_table")

    patch = _cal.as_patch()
    if patch:
        with st.expander("🛠️ 可直接抄进 decision.py 的 CYCLE_ADJ 补丁", expanded=False):
            st.code("CYCLE_ADJ = " + repr(patch), language="python")
            st.caption("⚠️ 本模块**不会自动修改规则**：过拟合比拍脑袋更危险。请人工判断后自行落地，"
                       "并同步更新 tests/test_decision.py 的期望值。")
    else:
        st.caption("🔒 暂无「值得采纳」的校准建议（需表态样本 ≥20 条且调节量 ≥2 点）。"
                   "此时 CYCLE_ADJ 保持原值不动。")

    # 事件驱动催化有效性：按「事件信号当日是否可用」拆命中率（I9）
    try:
        be = _track.by_event()
    except Exception:  # noqa: BLE401
        be = []
    if be:
        _ev_rows = [{
            "事件信号": r["group"], "样本": r["n"], "表态数": r["n_call"],
            "命中": r["hits"],
            "方向命中率": f"{r['accuracy']:.0f}%" if r["accuracy"] is not None else "样本不足",
        } for r in be]
        st.markdown("**🎯 事件驱动催化有效性**（按当日事件信号是否可用拆分命中率）")
        st.dataframe(pd.DataFrame(_ev_rows), width="stretch", hide_index=True, key="ev_eff")
        st.caption("事件开=当日有真实 P1 EV 事件因子多头池；事件关=无。两者命中率差即事件催化的边际贡献。")

    st.caption("⚖️ 口径：调节量 = clamp(2 × 次日平均涨跌, ±5 点)，即次日平均涨跌 1% → 刻度调 2 点，"
               "单次上限 5 点以防过拟合；中性预测不表态、不计入分母。本页结论不构成投资建议。")


fragment_decision()
fragment_signals()
fragment_ladder()
fragment_p1_ev()
fragment_event_driven_pool()
fragment_review()
fragment_backtest()
fragment_calibration()
