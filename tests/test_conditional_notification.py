"""
tests/test_conditional_notification.py
======================================
校验 backend.conditional_engine.build_trigger_notification 纯函数：
- 买/卖方向文案正确（买入▲ / 卖出▼）；
- 标题含代码与名称、名称缺失时不留多余空格；
- 正文包含触发原因与下单结果；
- info 为 None 时安全降级。
"""
from __future__ import annotations

from backend.conditional_engine import build_trigger_notification


def test_buy_direction():
    title, msg = build_trigger_notification(
        "600519", "贵州茅台", "buy", 100, "现价上穿MA5", "已成交")
    assert "600519" in title and "贵州茅台" in title
    assert "买入▲ 100 股" in msg
    assert "现价上穿MA5" in msg
    assert "已成交" in msg


def test_sell_direction():
    _, msg = build_trigger_notification(
        "000858", "五粮液", "sell", 200, "跌破MA5", "下单失败：余额不足")
    assert "卖出▼ 200 股" in msg
    assert "下单失败：余额不足" in msg


def test_missing_name_no_trailing_space():
    title, _ = build_trigger_notification(
        "600519", None, "buy", 100, "x", "y")
    assert not title.endswith(" ")
    assert "600519" in title


def test_none_info_safe():
    _, msg = build_trigger_notification(
        "600519", "贵州茅台", "buy", 100, None, "（未下单）")
    assert "触发：\n" in msg  # info=None -> 空串，不报错
    assert "（未下单）" in msg


def test_unknown_action_passthrough():
    _, msg = build_trigger_notification(
        "600519", "贵州茅台", "hold", 100, "x", "y")
    assert "hold 100 股" in msg  # 未知方向按原样显示，不误判
