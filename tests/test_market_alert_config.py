"""
tests/test_market_alert_config.py
==================================
市场异动扫描策略配置（backend.market_alert_config）纯逻辑测试。

覆盖：环境变量默认值覆盖、运行时覆盖校验、resolve_rules 过滤与阈值应用，
以及新增的数值阈值容错（非法字符串/None 不污染数值字段）。
"""
import importlib

import pytest

import backend.market_alert_config as cfg_mod


@pytest.fixture(autouse=True)
def _reset_overrides(monkeypatch):
    """每个用例前清空运行时覆盖，避免跨用例污染全局状态。"""
    monkeypatch.setattr(cfg_mod, "_RUNTIME_OVERRIDES", {})
    yield
    monkeypatch.setattr(cfg_mod, "_RUNTIME_OVERRIDES", {})


def test_defaults():
    cfg = cfg_mod.get_alert_config()
    assert cfg["scan_interval_minutes"] == 15
    assert cfg["cooldown_hours"] == 6
    assert cfg["thresholds"] == {}


def test_env_int_override(monkeypatch):
    monkeypatch.setenv("MARKET_ALERT_SCAN_INTERVAL_MINUTES", "30")
    cfg = cfg_mod.get_alert_config()
    assert cfg["scan_interval_minutes"] == 30


def test_env_int_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("MARKET_ALERT_SCAN_INTERVAL_MINUTES", "abc")
    cfg = cfg_mod.get_alert_config()
    assert cfg["scan_interval_minutes"] == 15


def test_env_thresholds_json(monkeypatch):
    monkeypatch.setenv("MARKET_ALERT_THRESHOLDS", '{"zdf": {"warn_hi": 5}}')
    cfg = cfg_mod.get_alert_config()
    assert cfg["thresholds"].get("zdf", {}).get("warn_hi") == 5


def test_env_thresholds_malformed_ignored(monkeypatch):
    monkeypatch.setenv("MARKET_ALERT_THRESHOLDS", "not-json")
    cfg = cfg_mod.get_alert_config()
    assert cfg["thresholds"] == {}


def test_set_runtime_overrides_rejects_wrong_type():
    res = cfg_mod.set_runtime_overrides({"scan_interval_minutes": "oops"})
    # 字符串非数字 → 被忽略，保持默认
    assert res["scan_interval_minutes"] == 15


def test_set_runtime_overrides_accepts_int_string():
    res = cfg_mod.set_runtime_overrides({"scan_interval_minutes": "45"})
    assert res["scan_interval_minutes"] == 45


def test_set_runtime_overrides_enabled_rules_list():
    res = cfg_mod.set_runtime_overrides({"enabled_rules": ["zdf", "cje"]})
    assert res["enabled_rules"] == ["zdf", "cje"]


def test_set_runtime_overrides_persists():
    cfg_mod.set_runtime_overrides({"cooldown_hours": 12})
    again = cfg_mod.get_alert_config()
    assert again["cooldown_hours"] == 12


_BASE = [
    {"key": "zdf", "warn_hi": 7.0, "danger_hi": 9.0, "warn_lo": -7.0,
     "danger_lo": -9.0, "hi_msg": "涨", "lo_msg": "跌"},
    {"key": "cje", "warn_hi": 5.0, "danger_hi": 8.0, "warn_lo": -5.0,
     "danger_lo": -8.0, "hi_msg": "主力流入", "lo_msg": "主力流出"},
]


def test_resolve_rules_enabled_filter():
    cfg_mod.set_runtime_overrides({"enabled_rules": ["zdf"]})
    out = cfg_mod.resolve_rules(_BASE)
    assert [r["key"] for r in out] == ["zdf"]


def test_resolve_rules_applies_numeric_thresholds():
    cfg_mod.set_runtime_overrides(
        {"thresholds": {"zdf": {"warn_hi": 6.0, "danger_hi": 10.0}}}
    )
    out = cfg_mod.resolve_rules(_BASE)
    zdf = out[0]
    assert zdf["warn_hi"] == 6.0
    assert zdf["danger_hi"] == 10.0
    # 未覆盖字段保持原值
    assert zdf["warn_lo"] == -7.0


def test_resolve_rules_coerces_string_numeric_threshold():
    cfg_mod.set_runtime_overrides(
        {"thresholds": {"zdf": {"warn_hi": "8.5"}}}
    )
    out = cfg_mod.resolve_rules(_BASE)
    assert out[0]["warn_hi"] == 8.5  # 字符串数字被转为 float


def test_resolve_rules_skips_invalid_numeric_threshold():
    cfg_mod.set_runtime_overrides(
        {"thresholds": {"zdf": {"warn_hi": "abc", "danger_hi": None}}}
    )
    out = cfg_mod.resolve_rules(_BASE)
    zdf = out[0]
    # 非法字符串 / None 被跳过，保留原始数值
    assert zdf["warn_hi"] == 7.0
    assert zdf["danger_hi"] == 9.0


def test_resolve_rules_applies_message_overrides():
    cfg_mod.set_runtime_overrides(
        {"thresholds": {"zdf": {"hi_msg": "放量大涨"}}}
    )
    out = cfg_mod.resolve_rules(_BASE)
    assert out[0]["hi_msg"] == "放量大涨"
