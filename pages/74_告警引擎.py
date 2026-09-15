"""页面 74：消息/告警引擎（G6）

补本项目「仅有简单价格预警」的短板：**多条件 AND/OR 规则引擎** + 多通道通知。

现状与诚实边界：
- 规则以 JSON 编辑、持久化到 ``data/alert_rules.json``；
- 指标来自既有本地数据源（牧羊人情绪指标 + 决策快照 + 市场状态机）；
- 通道：日志文件**默认可用**；企业微信 / 飞书机器人需配 ``WECOM_WEBHOOK`` /
  ``FEISHU_WEBHOOK`` 环境变量，**未配置即标「不可用」，绝不伪造发送**；
- 条件三值逻辑：指标缺失=未知，AND 规则遇未知**不报**（宁可漏报不误报）。

⚠️ 规则为启发式阈值，非预测；告警只是提示「值得看一眼」，不构成投资建议。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import streamlit as st

from modules.alert_rules import (
    channel_status, evaluate_all, load_rules, save_rules, write_alert_log,
)
from modules.page_utils import render_standard_page
from modules.ui_theme import section_header, sf_metric

logger = logging.getLogger(__name__)


def _build_snapshot() -> dict:
    snap: dict = {}
    try:
        from modules.shepherd import get_shepherd_indicators, load_latest_snapshot
        df, _meta = get_shepherd_indicators(days=5)
        if df is not None and not df.empty:
            row = df.iloc[-1]
            for k in ("zt_fail_ratio", "limit_up", "limit_down", "median_chg"):
                v = row.get(k)
                if v is not None and v == v:
                    snap[k] = float(v)
        s = load_latest_snapshot() or {}
        if isinstance(s.get("temperature"), (int, float)):
            snap["temperature"] = float(s["temperature"])
        if s.get("cycle"):
            snap["cycle"] = s["cycle"]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[alert] 快照构建失败: {e}")
    try:
        from modules import market_regime as mr
        rep = mr.regime_report(k=8)
        if rep and rep.get("available"):
            snap["state"] = rep["latest"].get("state")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[alert] 状态机不可用: {e}")
    return snap


dark = render_standard_page(
    title="告警引擎", icon="🛎️",
    caption="多条件 AND/OR 规则引擎 + 多通道通知。指标取自本地情绪/快照/状态机；"
            "通道未配置即明示不可用，绝不伪造发送。启发式阈值，非预测。",
)

snapshot = _build_snapshot()

# ── ① 当前指标快照 ────────────────────────────────────────────────────
section_header("当前指标快照", "规则据此求值；缺失指标会让 AND 规则不触发（宁漏勿误）", icon="📸")
if snapshot:
    keys = [k for k in ("limit_up", "zt_fail_ratio", "temperature", "limit_down", "median_chg") if k in snapshot]
    cols = st.columns(max(len(keys), 1))
    for c, k in zip(cols, keys):
        with c:
            sf_metric(k, f"{snapshot[k]:.1f}", "")
    if snapshot.get("state") or snapshot.get("cycle"):
        st.caption(f"市场状态 **{snapshot.get('state', '—')}** · 情绪周期 **{snapshot.get('cycle', '—')}**")
else:
    st.warning("⚠️ 当前指标快照为空（数据源不可用），规则无法求值。")

st.markdown("---")

# ── ② 规则配置 ────────────────────────────────────────────────────────
section_header("规则配置（JSON）", "每条：{id,name,logic:'AND'|'OR',conditions:[{metric,op,value}],channel}", icon="📝")
_rules = load_rules()
rules_txt = st.text_area("规则 JSON", value=json.dumps(_rules, ensure_ascii=False, indent=2),
                         height=240, key="alert_rules_txt")

parsed, parse_err = None, None
try:
    parsed = json.loads(rules_txt)
    if isinstance(parsed, dict) and "rules" in parsed:
        parsed = parsed["rules"]
    if not isinstance(parsed, list):
        parse_err = "规则必须是 JSON 数组"
except Exception as e:  # noqa: BLE001
    parse_err = f"JSON 解析失败：{e}"

_btn1, _btn2, _sp = st.columns([1, 1, 3])
with _btn1:
    if st.button("💾 保存规则", key="alert_save", width="stretch"):
        if parse_err:
            st.error(f"⚠️ 规则无效，未保存：{parse_err}")
        else:
            st.success("✅ 已保存。") if save_rules(parsed) else st.warning("⚠️ 保存失败（磁盘异常）。")

# ── ③ 评估 ────────────────────────────────────────────────────────────
st.markdown("---")
section_header("评估结果", "AND：全部已知条件为真才触发；OR：任一已知条件为真即触发", icon="🔎")
if parse_err:
    st.error(f"⚠️ 规则无效，无法评估：{parse_err}")
elif not snapshot:
    st.info("📭 快照为空，暂不评估。")
else:
    results = evaluate_all(parsed, snapshot)
    triggered = [r for r in results if r["triggered"]]
    if triggered:
        st.error(f"🔔 **{len(triggered)} 条规则触发**：")
        for r in triggered:
            unk = r["detail"].get("unknown") or []
            extra = f"（另有 {len(unk)} 个条件指标缺失）" if unk else ""
            st.markdown(f"- **{r.get('name', r.get('id'))}** · 逻辑 {r['detail']['logic']} · 通道 `{r.get('channel', 'log')}`{extra}")
    else:
        st.success("✅ 当前无规则触发。")

    with st.expander("查看全部规则求值明细"):
        for r in results:
            marks = []
            for cond, res in r["detail"]["results"]:
                marks.append(f"{cond.get('metric')}{cond.get('op')}{cond.get('value')}="
                             + ("✅" if res is True else ("❌" if res is False else "❓未知")))
            st.markdown(f"- **{r.get('name', r.get('id'))}** [{r['detail']['logic']}] "
                        + ("**触发**" if r["triggered"] else "未触发") + " — " + "；".join(marks))

    _btn3, _sp2 = st.columns([1, 4])
    with _btn3:
        if st.button("📝 写入告警日志", key="alert_log", width="stretch"):
            if not triggered:
                st.info("本次无触发，未写入。")
            else:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                lines = [f"[{ts}] {r.get('name', r.get('id'))} (logic={r['detail']['logic']})" for r in triggered]
                st.success("✅ 已写入 data/alerts.log") if write_alert_log(lines) \
                    else st.warning("⚠️ 日志写入失败（磁盘异常）。")

# ── ④ 通道状态 ────────────────────────────────────────────────────────
st.markdown("---")
section_header("通知通道状态", "未配置凭证的通道标为不可用；不伪造发送", icon="📡")
for key, (label, ok) in channel_status().items():
    if ok:
        st.markdown(f"- ✅ **{label}** —— 可用")
    else:
        st.markdown(f"- ⛔ **{label}** —— 未配置（设环境变量后可用）")

st.caption("⚠️ 说明：告警为启发式阈值触发，非预测模型，不构成投资建议；"
           "「触发」只代表值得关注，不代表必然发生。")
