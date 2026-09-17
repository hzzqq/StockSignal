"""modules/push_channel.py — 推送通道（H7 闭环）。

告警引擎（``pages/74_告警引擎.py``）此前只能把触发结果写进本地 ``data/alerts.log``；
``alert_rules.channel_status()`` 里声明的「企业微信 / 飞书机器人」通道**只有可用性探测、
没有任何发送实现**——「声称可用但发不出去」本身就是一类静默失败。

本模块把这条链路补成闭环：

- ``channel_status()``   真实探测各通道可用性（微信桥接 / 企业微信机器人 / 飞书机器人）；
- ``push_text()``        实际发送，返回 ``{"sent","channel","reason"}``；
- ``build_alert_message()`` 把告警结果格式化成一条可直接推的文本。

通道优先级（``auto``）：**微信桥接**（老板已配的 Server酱/PushPlus/企微应用，含每日额度保护）
→ 企业微信机器人 webhook → 飞书机器人 webhook。

━━━━━━━━━━━━━━━━━━━━━━━━━━━ 诚实红线 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 未配置任何通道 → ``sent=False`` + 明确原因，**绝不假装发出去**；
- 通道返回 False（额度用尽 / 凭证失效 / 网络异常）→ 原样上报原因，不吞成「成功」；
- 本模块**不打印/不回传任何 secret**。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

__all__ = [
    "BRIDGE_HOME", "BRIDGE_CFG", "BRIDGE_SCRIPT",
    "channel_status", "push_text", "build_alert_message",
]

BRIDGE_HOME = os.path.expanduser("~/.workbuddy/wechat_bridge")
BRIDGE_CFG = os.path.join(BRIDGE_HOME, "config.json")
BRIDGE_SCRIPT = os.path.expanduser("~/.workbuddy/skills/wechat-bridge/scripts/wechat_bridge.py")

_TIMEOUT = 10
_CHANNEL_LABEL = {
    "wechat_bridge": "微信桥接（Server酱 / PushPlus / 企微应用）",
    "wecom_webhook": "企业微信机器人 Webhook",
    "feishu_webhook": "飞书机器人 Webhook",
}


def _load_bridge_cfg():
    """读微信桥接配置；文件缺失/损坏返回 ``None``（不抛）。"""
    try:
        if not os.path.exists(BRIDGE_CFG):
            return None
        with open(BRIDGE_CFG, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else None
    except Exception as e:  # noqa: BLE001
        logger.info("[push] 读取桥接配置失败: %s", e)
        return None


def _bridge_state() -> tuple[bool, str]:
    """微信桥接是否真的能发 → ``(available, detail)``。"""
    cfg = _load_bridge_cfg()
    if cfg is None:
        return False, f"未找到桥接配置 {BRIDGE_CFG}"
    if not os.path.exists(BRIDGE_SCRIPT):
        return False, f"桥接脚本缺失 {BRIDGE_SCRIPT}"
    ch = str(cfg.get("channel") or "wecom_app")
    if ch == "serverchan":
        if not cfg.get("serverchan_sendkey"):
            return False, "channel=serverchan 但缺少 serverchan_sendkey"
        return True, "通道 serverchan（Server酱 → 个人微信）"
    if ch == "pushplus":
        if not cfg.get("pushplus_token"):
            return False, "channel=pushplus 但缺少 pushplus_token"
        return True, "通道 pushplus（PushPlus → 个人微信）"
    if not (cfg.get("corpid") and cfg.get("corpsecret") and cfg.get("agentid")):
        return False, "channel=wecom_app 但缺少 corpid/corpsecret/agentid"
    return True, "通道 wecom_app（企业微信应用消息）"


def channel_status() -> dict:
    """各推送通道的真实可用性。缺凭证一律 ``available=False``，并给出原因。"""
    ok_bridge, bridge_detail = _bridge_state()
    wecom_url = os.environ.get("WECOM_WEBHOOK")
    feishu_url = os.environ.get("FEISHU_WEBHOOK")
    return {
        "wechat_bridge": {
            "label": _CHANNEL_LABEL["wechat_bridge"],
            "available": ok_bridge,
            "detail": bridge_detail,
        },
        "wecom_webhook": {
            "label": _CHANNEL_LABEL["wecom_webhook"],
            "available": bool(wecom_url),
            "detail": "已配置 WECOM_WEBHOOK" if wecom_url else "未配置环境变量 WECOM_WEBHOOK",
        },
        "feishu_webhook": {
            "label": _CHANNEL_LABEL["feishu_webhook"],
            "available": bool(feishu_url),
            "detail": "已配置 FEISHU_WEBHOOK" if feishu_url else "未配置环境变量 FEISHU_WEBHOOK",
        },
    }


def _post(url: str, data: bytes, headers: dict):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def _push_bridge(text: str) -> tuple[bool, str]:
    """调用微信桥接脚本的 ``push()``（复用它的通道切换与每日额度保护）。"""
    if not os.path.exists(BRIDGE_SCRIPT):
        return False, f"桥接脚本不存在：{BRIDGE_SCRIPT}"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_wb_skill", BRIDGE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ok = bool(mod.push(text))
    except Exception as e:  # noqa: BLE001
        return False, f"桥接调用异常：{type(e).__name__}: {e}"
    if ok:
        return True, "已通过微信桥接发送"
    return False, "桥接返回失败（可能触及 Server酱 每日额度、凭证失效或网络异常；详见服务端日志）"


def _push_wecom_webhook(text: str, url: str) -> tuple[bool, str]:
    payload = json.dumps({"msgtype": "text", "text": {"content": text}}).encode("utf-8")
    try:
        r = _post(url, payload, {"Content-Type": "application/json; charset=utf-8"})
    except Exception as e:  # noqa: BLE001
        return False, f"企业微信机器人请求异常：{type(e).__name__}: {e}"
    if r.get("errcode", 0) != 0:
        return False, f"企业微信机器人返回错误：errcode={r.get('errcode')} {r.get('errmsg', '')}".strip()
    return True, "已通过企业微信机器人发送"


def _push_feishu_webhook(text: str, url: str) -> tuple[bool, str]:
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    try:
        r = _post(url, payload, {"Content-Type": "application/json; charset=utf-8"})
    except Exception as e:  # noqa: BLE001
        return False, f"飞书机器人请求异常：{type(e).__name__}: {e}"
    if r.get("code", 0) != 0:
        return False, f"飞书机器人返回错误：code={r.get('code')} {r.get('msg', '')}".strip()
    return True, "已通过飞书机器人发送"


def push_text(text: str, prefer: str = "auto") -> dict:
    """把 ``text`` 推到可用通道。

    ``prefer``：``auto``（默认，按优先级挑第一个可用通道）或指定
    ``wechat_bridge`` / ``wecom_webhook`` / ``feishu_webhook``。

    返回 ``{"sent": bool, "channel": str, "reason": str}``——**失败必须带真实原因**。
    """
    body = (text or "").strip()
    if not body:
        return {"sent": False, "channel": "none", "reason": "推送内容为空，未发送"}

    status = channel_status()
    order = [prefer] if prefer and prefer != "auto" else \
        ["wechat_bridge", "wecom_webhook", "feishu_webhook"]

    tried = []
    for key in order:
        st = status.get(key)
        if not st:
            return {"sent": False, "channel": key, "reason": f"未知通道 {key}"}
        if not st["available"]:
            tried.append(f"{_CHANNEL_LABEL.get(key, key)}：{st['detail']}")
            continue
        if key == "wechat_bridge":
            ok, reason = _push_bridge(body)
        elif key == "wecom_webhook":
            ok, reason = _push_wecom_webhook(body, os.environ.get("WECOM_WEBHOOK", ""))
        else:
            ok, reason = _push_feishu_webhook(body, os.environ.get("FEISHU_WEBHOOK", ""))
        if ok:
            return {"sent": True, "channel": key, "reason": reason}
        # 该通道可用但发送失败：不静默换下一个通道，如实上报（避免重复推送）
        return {"sent": False, "channel": key, "reason": reason}

    reason = ("未配置任何可用推送通道 —— " + "；".join(tried)) if tried else "未配置任何推送通道"
    return {"sent": False, "channel": "none", "reason": reason}


def build_alert_message(triggered: list, snapshot: dict | None = None,
                        ts: str | None = None) -> str:
    """把触发的告警格式化成一条推送文本（含免责声明，不夸大）。"""
    ts = ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"🛎️ StockSignal 告警 · {ts}"]
    names = []
    for r in (triggered or []):
        if isinstance(r, dict):
            nm = r.get("name") or r.get("id") or "未命名规则"
            logic = (r.get("detail") or {}).get("logic", r.get("logic", ""))
            names.append(f"{nm}（{logic}）" if logic else str(nm))
        elif r:
            names.append(str(r))
    if not names:
        lines.append("✅ 本次无规则触发。")
    else:
        lines.append(f"🔔 {len(names)} 条规则触发：")
        lines += [f"· {n}" for n in names]

    if isinstance(snapshot, dict) and snapshot:
        disp = {"limit_up": "涨停", "limit_down": "跌停", "zt_fail_ratio": "炸板率",
                "temperature": "温度", "median_chg": "涨跌中位数"}
        parts = []
        for k, label in disp.items():
            v = snapshot.get(k)
            if isinstance(v, (int, float)):
                parts.append(f"{label} {v:.1f}")
        if parts:
            lines.append("指标快照：" + " · ".join(parts))
        if snapshot.get("state") or snapshot.get("cycle"):
            lines.append(f"市场状态 {snapshot.get('state', '—')} · 情绪周期 {snapshot.get('cycle', '—')}")

    lines.append("（启发式阈值触发，非预测，不构成投资建议）")
    return "\n".join(lines)
