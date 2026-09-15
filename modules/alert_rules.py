"""告警规则引擎（G6）纯逻辑 + 规则持久化 + 通道可用性探测。

规则结构::

    {"id": "r1", "name": "炸板率过高", "logic": "AND"|"OR",
     "conditions": [{"metric": "zt_fail_ratio", "op": "gt", "value": 40}],
     "channel": "log"|"wecom"|"feishu"}

语义（诚实优先）：
- 条件的三值逻辑：True / False / **None(指标缺失=未知)**。
- ``AND``：任一未知即**无法确认为真**（返回 False）——不猜测；
- ``OR``：只要有已知条件为真即为真；全未知则为 False。
- 缺指标的规则绝不误报；评估结果附带 ``unknown`` 明细供页面展示。

通道：缺凭证的通道标为不可用，**绝不伪造发送**。
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

OPS = {
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}

DEFAULT_RULES = [
    {"id": "r1", "name": "炸板率过高（≥40%）", "logic": "AND",
     "conditions": [{"metric": "zt_fail_ratio", "op": "gt", "value": 40}], "channel": "log"},
    {"id": "r2", "name": "情绪冰点（温度<20）", "logic": "AND",
     "conditions": [{"metric": "temperature", "op": "lt", "value": 20}], "channel": "log"},
    {"id": "r3", "name": "涨停潮 或 情绪过热", "logic": "OR",
     "conditions": [{"metric": "limit_up", "op": "gt", "value": 80},
                    {"metric": "temperature", "op": "gt", "value": 85}], "channel": "log"},
]

_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "alert_rules.json"
)


def load_rules(path: str | None = None) -> list:
    p = path or _RULES_PATH
    try:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            rules = data.get("rules") if isinstance(data, dict) else data
            if isinstance(rules, list) and rules:
                return rules
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[alert] 读取规则失败: {e}")
    return [dict(r) for r in DEFAULT_RULES]


def save_rules(rules: list, path: str | None = None) -> bool:
    p = path or _RULES_PATH
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"rules": rules}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[alert] 保存规则失败: {e}")
        return False


def evaluate_condition(cond: dict, snapshot: dict):
    """返回 True/False/None(指标缺失或非法)。"""
    m = cond.get("metric")
    op = OPS.get(cond.get("op"))
    if m is None or op is None:
        return None
    if m not in snapshot or snapshot.get(m) is None:
        return None
    try:
        return bool(op(float(snapshot[m]), float(cond.get("value"))))
    except (TypeError, ValueError):
        return None


def evaluate_rule(rule: dict, snapshot: dict):
    """返回 (triggered: bool, detail: dict)。"""
    logic = str(rule.get("logic") or "AND").upper()
    conds = rule.get("conditions") or []
    results = [(c, evaluate_condition(c, snapshot)) for c in conds]
    known = [r for _, r in results if r is not None]
    unknown = [c for c, r in results if r is None]
    if logic == "OR":
        triggered = any(known) if known else False
    else:  # AND：有未知条件则无法确认为真（不猜测）
        triggered = bool(known) and all(known) and not unknown
    return triggered, {"logic": logic, "results": results, "unknown": unknown}


def evaluate_all(rules: list, snapshot: dict) -> list:
    out = []
    for r in rules:
        trig, detail = evaluate_rule(r, snapshot)
        out.append({**r, "triggered": trig, "detail": detail})
    return out


def channel_status() -> dict:
    """各通道可用性（缺凭证=不可用，不伪造）。"""
    return {
        "log": ("日志文件 data/alerts.log", True),
        "wecom": ("企业微信机器人", bool(os.environ.get("WECOM_WEBHOOK"))),
        "feishu": ("飞书机器人", bool(os.environ.get("FEISHU_WEBHOOK"))),
    }


def write_alert_log(lines: list, path: str | None = None) -> bool:
    """把触发的告警追加写入日志（唯一默认可用通道）。"""
    p = path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "alerts.log")
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[alert] 写日志失败: {e}")
        return False
