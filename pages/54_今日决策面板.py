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
from modules.decision import derive_position, load_snapshot, is_stale
from modules.decision_view import render_signal_cards, render_position_card, render_ladder_table
from modules import decision_track as _track
from modules.page_guard import safe_fragment
from modules.page_widgets import _section_title, _in_trading_hours, _empty_info
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box

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

    # ② 仓位建议大卡（闭环的输出端）
    pos = derive_position(temp, score, bias, cyc.get("name", ""), overall)
    # 暴露最终仓位到 session_state，供冒烟测试做「数据正确性」断言（不渲染、纯透传）
    try:
        st.session_state["decision_pos_pct"] = pos["pct"]
    except Exception:  # noqa: BLE001
        pass
    render_position_card(pos, bias=bias, confidence=(fc or {}).get("confidence", 0),
                         cyc_name=cyc.get("name", ""))


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
        note_txt = st.text_area("今日决策手记（主线/计划/复盘感受，留空不改已存手记）", value="",
                                key="dec_note_text", height=80,
                                placeholder="例：温度 62 偏多，仓位 70%，盯连板晋级能否维持…")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 保存今日决策快照", key="dec_save", use_container_width=True):
                ok = _sn.save_note(dstr, today, fc, note_txt or "")
                if ok:
                    xc_success_box("✅ 今日决策快照已保存（含指标 + 次日预判 + 手记）。")
                else:
                    xc_warn_box("⚠️ 保存失败，检查 data/ 写权限。")
        with b2:
            if st.button("🔄 回填次日实际", key="dec_backfill", use_container_width=True):
                n = _sn.backfill_actuals(df)
                xc_success_box(f"✅ 已回填 {n} 条笔记的次日实际走势。") if n else st.caption("无需回填。")
        with b3:
            if st.button("🗑️ 删除今日快照", key="dec_del", use_container_width=True):
                if _sn.delete_note(dstr):
                    xc_success_box("已删除今日快照。")
                else:
                    st.caption("今日尚无快照。")

    st.markdown("**🔬 历史情绪回测**（对过去每个交易日重跑情绪定位，统计「当时处某阶段→次日实际怎么走」）")
    rng = st.selectbox("回测区间", ["近 60 交易日", "近 250 交易日", "近 1250 交易日"],
                      index=0, key="dec_range")
    days_map = {"近 60 交易日": 60, "近 250 交易日": 250, "近 1250 交易日": 1250}
    if st.button("📊 分析历史情绪（真机回测）", key="dec_analyze", use_container_width=True):
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

    if st.button("🔗 联网计算次日实际走势（打分）", key="bt_score", use_container_width=True):
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
    st.plotly_chart(fig, use_container_width=True, key="bt_chart")
    st.caption("📈 紫线=当日预测仓位；红/绿柱=次日上证指数真实涨跌（红涨绿跌）。命中率=偏多/偏空预测中方向判断正确的比例。"
               "预判为概率结论，不构成投资建议。")


fragment_decision()
fragment_signals()
fragment_ladder()
fragment_review()
fragment_backtest()
