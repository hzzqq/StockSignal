"""
market_alert_engine._evaluate 的纯离线健壮性测试
================================================
仅构造小型规则 dict + 行情样本 dict，绝不触网 / 不碰数据库 / 不依赖 Flask 应用上下文。
覆盖：
- 正常规则正确触发；
- 缺失阈值字段 -> 安全跳过（不抛异常）；
- quote 值为 None -> 安全跳过；
- 未知 kind / 畸形结构 -> 安全跳过（不抛异常）；
- NaN / inf / 非数字字符串 -> 安全跳过；
并校验合法输入行为未被破坏。
"""
import math
import os
import sys

# 保证 backend 包可被导入（无论 pytest 的 rootdir / 导入模式如何）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.market_alert_engine import _evaluate  # noqa: E402


def _warn_hi_rule():
    """一个形状良好、应当触发的规则。"""
    return dict(key="vix", name="VIX恐慌指数", warn_hi=20, danger_hi=30,
                hi_msg="恐慌指数走高（避险情绪升温）")


def test_normal_rule_fires():
    rule = _warn_hi_rule()
    res = _evaluate(rule, 25.0, None)
    assert res is not None
    sev, msg, thr = res
    assert sev == "warning"
    assert thr == 20
    # 命中规则自带 hi_msg 文案
    assert "恐慌指数走高" in msg


def test_normal_rule_danger_fires():
    rule = _warn_hi_rule()
    res = _evaluate(rule, 35.0, None)
    assert res is not None
    sev, *_ = res
    assert sev == "danger"


def test_rule_no_fire_below_threshold():
    rule = _warn_hi_rule()
    assert _evaluate(rule, 15.0, None) is None


def test_missing_threshold_field_safe():
    # 规则有 key，但完全没有阈值字段 -> 安全跳过，不抛异常。
    rule = dict(key="mystery", name="神秘指标")
    assert _evaluate(rule, 999.0, None) is None
    # 阈值字段为 None -> 同样安全跳过
    rule2 = dict(key="mystery", name="神秘指标", warn_hi=None, danger_hi=None)
    assert _evaluate(rule2, 999.0, None) is None


def test_none_quote_value_safe():
    rule = _warn_hi_rule()
    assert _evaluate(rule, None, None) is None


def test_nan_quote_value_safe():
    rule = _warn_hi_rule()
    assert _evaluate(rule, float("nan"), None) is None
    assert _evaluate(rule, math.inf, None) is None
    assert _evaluate(rule, -math.inf, None) is None


def test_non_numeric_quote_safe():
    rule = _warn_hi_rule()
    assert _evaluate(rule, "oops", None) is None


def test_unknown_kind_safe():
    # 带有无法识别的 kind / 字段结构的规则 -> 不应抛异常，安全跳过。
    rule = dict(key="macd", name="MACD", kind="cross", fast=12, slow=26)
    assert _evaluate(rule, 100.0, None) is None


def test_missing_key_safe():
    # 规则缺少 key 字段 -> 安全跳过，不抛 KeyError。
    rule = dict(name="无key指标", warn_hi=10)
    assert _evaluate(rule, 50.0, None) is None


def test_non_numeric_threshold_safe():
    # 阈值字段为非数字字符串 -> 安全跳过（不抛 / 不误触发）。
    rule = dict(key="bad", name="坏阈值", warn_hi="not-a-number", danger_hi="x")
    assert _evaluate(rule, 50.0, None) is None


def test_positive_hi_downgraded_to_info():
    # north_net 属于「利好高位」指标，severity 应为 info。
    rule = dict(key="north_net", name="北向资金净流入", warn_hi=100, danger_hi=200,
                hi_msg="北向资金大幅净流入")
    res = _evaluate(rule, 150.0, None)
    assert res is not None
    sev, *_ = res
    assert sev == "info"
