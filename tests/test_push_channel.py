# -*- coding: utf-8 -*-
"""tests/test_push_channel.py — H7 推送通道测试。

全程离线：桥接用假 config.json + 假脚本模块注入；webhook 用假的 ``urlopen``。
重点覆盖诚实红线——**未配置/发送失败都必须 sent=False 且带真实原因**。
"""
import json
import os
import sys
import types

import pytest

from modules import push_channel as pc


@pytest.fixture
def no_config(tmp_path, monkeypatch):
    """桥接配置与 webhook 环境变量都不存在。"""
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(tmp_path / "config.json"))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(tmp_path / "wechat_bridge.py"))
    monkeypatch.delenv("WECOM_WEBHOOK", raising=False)
    monkeypatch.delenv("FEISHU_WEBHOOK", raising=False)
    return tmp_path


# ─────────────────────────── channel_status ───────────────────────────
def test_status_all_unavailable_when_nothing_configured(no_config):
    st = pc.channel_status()
    assert st["wechat_bridge"]["available"] is False
    assert st["wecom_webhook"]["available"] is False
    assert st["feishu_webhook"]["available"] is False
    # 每条都必须给原因，不能只给一个 False
    for k, v in st.items():
        assert v["detail"], f"{k} 缺原因说明"


def test_status_bridge_available_with_serverchan(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"channel": "serverchan", "serverchan_sendkey": "SCT123"}),
                   encoding="utf-8")
    script = tmp_path / "wechat_bridge.py"
    script.write_text("def push(text, cfg=None, touser=None):\n    return True\n", encoding="utf-8")
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(cfg))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(script))
    st = pc.channel_status()
    assert st["wechat_bridge"]["available"] is True
    assert "serverchan" in st["wechat_bridge"]["detail"]


def test_status_bridge_missing_key_names_the_missing_key(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"channel": "serverchan"}), encoding="utf-8")
    script = tmp_path / "wechat_bridge.py"
    script.write_text("def push(text, cfg=None, touser=None):\n    return True\n", encoding="utf-8")
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(cfg))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(script))
    st = pc.channel_status()
    assert st["wechat_bridge"]["available"] is False
    assert "serverchan_sendkey" in st["wechat_bridge"]["detail"]


def test_status_env_webhooks(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(tmp_path / "nope.json"))
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/wecom")
    monkeypatch.setenv("FEISHU_WEBHOOK", "https://example.com/feishu")
    st = pc.channel_status()
    assert st["wecom_webhook"]["available"] is True
    assert st["feishu_webhook"]["available"] is True


# ─────────────────────────── push_text ───────────────────────────
def test_push_empty_text_refuses(no_config):
    r = pc.push_text("   ")
    assert r["sent"] is False and "空" in r["reason"]


def test_push_without_any_channel_is_honest_failure(no_config):
    r = pc.push_text("hello")
    assert r["sent"] is False
    assert r["channel"] == "none"
    assert "未配置" in r["reason"]


def test_push_via_bridge_success(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"channel": "serverchan", "serverchan_sendkey": "SCT123"}),
                   encoding="utf-8")
    script = tmp_path / "wechat_bridge.py"
    script.write_text("def push(text, cfg=None, touser=None):\n    return True\n", encoding="utf-8")
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(cfg))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(script))
    r = pc.push_text("测试消息")
    assert r["sent"] is True and r["channel"] == "wechat_bridge"


def test_push_bridge_false_reports_reason(tmp_path, monkeypatch):
    """桥接返回 False（如额度用尽）必须如实上报，不能吞成成功、也不能换通道重发。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"channel": "serverchan", "serverchan_sendkey": "SCT123"}),
                   encoding="utf-8")
    script = tmp_path / "wechat_bridge.py"
    script.write_text("def push(text, cfg=None, touser=None):\n    return False\n", encoding="utf-8")
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(cfg))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(script))
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/wecom")  # 即便还有备用通道
    r = pc.push_text("测试消息")
    assert r["sent"] is False
    assert r["channel"] == "wechat_bridge"      # 不静默换通道
    assert "额度" in r["reason"] or "失败" in r["reason"]


def test_push_bridge_exception_is_caught(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"channel": "serverchan", "serverchan_sendkey": "SCT123"}),
                   encoding="utf-8")
    script = tmp_path / "wechat_bridge.py"
    script.write_text("def push(text, cfg=None, touser=None):\n    raise RuntimeError('boom')\n",
                      encoding="utf-8")
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(cfg))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(script))
    r = pc.push_text("测试消息")
    assert r["sent"] is False and "boom" in r["reason"]


def _fake_urlopen(payload, captured):
    class _Resp:
        def __init__(self, p):
            self._p = p

        def read(self):
            return json.dumps(self._p).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _open(req, timeout=10):
        captured.append(req)
        return _Resp(payload)

    return _open


def test_push_wecom_webhook_success(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(tmp_path / "nope.json"))
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/wecom")
    monkeypatch.delenv("FEISHU_WEBHOOK", raising=False)
    captured = []
    monkeypatch.setattr(pc.urllib.request, "urlopen", _fake_urlopen({"errcode": 0}, captured))
    r = pc.push_text("测试消息")
    assert r["sent"] is True and r["channel"] == "wecom_webhook"
    assert len(captured) == 1 and b"msgtype" in captured[0].data


def test_push_wecom_webhook_err_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(tmp_path / "nope.json"))
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/wecom")
    monkeypatch.setattr(pc.urllib.request, "urlopen",
                        _fake_urlopen({"errcode": 93000, "errmsg": "invalid webhook url"}, []))
    r = pc.push_text("测试消息")
    assert r["sent"] is False and "93000" in r["reason"]


def test_push_feishu_webhook(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(tmp_path / "nope.json"))
    monkeypatch.delenv("WECOM_WEBHOOK", raising=False)
    monkeypatch.setenv("FEISHU_WEBHOOK", "https://example.com/feishu")
    monkeypatch.setattr(pc.urllib.request, "urlopen", _fake_urlopen({"code": 0}, []))
    r = pc.push_text("测试消息")
    assert r["sent"] is True and r["channel"] == "feishu_webhook"


def test_push_prefer_unknown_channel():
    r = pc.push_text("x", prefer="nope")
    assert r["sent"] is False and "未知通道" in r["reason"]


# ─────────────────────────── 消息构造 ───────────────────────────
def test_build_message_contains_names_and_disclaimer():
    trig = [{"name": "炸板率过高", "detail": {"logic": "AND"}},
            {"id": "r2", "detail": {"logic": "OR"}}]
    msg = pc.build_alert_message(trig, {"limit_up": 88.0, "temperature": 91.2, "state": "过热"},
                                 ts="2026-09-17 21:40:00")
    assert "2026-09-17 21:40:00" in msg
    assert "2 条规则触发" in msg
    assert "炸板率过高" in msg and "r2" in msg
    assert "涨停 88.0" in msg and "温度 91.2" in msg
    assert "非预测" in msg          # 免责声明必须在


def test_build_message_no_trigger():
    msg = pc.build_alert_message([], ts="2026-09-17 21:40:00")
    assert "无规则触发" in msg and "非预测" in msg


def test_no_secret_leaked_in_reason(tmp_path, monkeypatch):
    """原因文本里不得出现 secret 本身。"""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"channel": "serverchan", "serverchan_sendkey": "SCT_SECRET_XYZ"}),
                   encoding="utf-8")
    script = tmp_path / "wechat_bridge.py"
    script.write_text("def push(text, cfg=None, touser=None):\n    return False\n", encoding="utf-8")
    monkeypatch.setattr(pc, "BRIDGE_CFG", str(cfg))
    monkeypatch.setattr(pc, "BRIDGE_SCRIPT", str(script))
    r = pc.push_text("x")
    assert "SCT_SECRET_XYZ" not in json.dumps(r, ensure_ascii=False)
    assert "SCT_SECRET_XYZ" not in json.dumps(pc.channel_status(), ensure_ascii=False)
