"""
tests/test_config.py
===================
集中配置（backend.config）测试。

配置项在模块 import 时从环境变量读取（类属性），因此用例通过 monkeypatch 环境变量 +
importlib.reload 重新求值。重点守护：整型配置项（JWT_EXPIRES_SECONDS /
RATE_LIMIT_MAX / RATE_LIMIT_WINDOW）对非法/缺失值安全回退默认，不再让后端 import 时崩溃。
"""
import importlib

import pytest

import backend.config as cfg_mod

_ENV_KEYS = [
    "JWT_EXPIRES_SECONDS", "RATE_LIMIT_MAX", "RATE_LIMIT_WINDOW",
    "STOCKSIGNAL_RATE_LIMIT_ENABLED", "STOCKSIGNAL_SECRET", "CORS_ORIGINS",
]


@pytest.fixture
def fresh_config(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    mod = importlib.reload(cfg_mod)
    yield mod.Config
    importlib.reload(cfg_mod)  # 还原为真实环境


def _reload(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(cfg_mod).Config


def test_defaults(fresh_config):
    assert fresh_config.JWT_EXPIRES_SECONDS == 604800
    assert fresh_config.RATE_LIMIT_MAX == 5
    assert fresh_config.RATE_LIMIT_WINDOW == 60
    assert fresh_config.RATE_LIMIT_ENABLED is True
    assert fresh_config.SECRET_KEY == "dev-only-change-me-in-production"
    assert fresh_config.CORS_ORIGINS == "*"


def test_jwt_expires_override(fresh_config, monkeypatch):
    C = _reload(monkeypatch, JWT_EXPIRES_SECONDS="3600")
    assert C.JWT_EXPIRES_SECONDS == 3600


def test_rate_limit_override(fresh_config, monkeypatch):
    C = _reload(monkeypatch, RATE_LIMIT_MAX="20", RATE_LIMIT_WINDOW="120")
    assert C.RATE_LIMIT_MAX == 20
    assert C.RATE_LIMIT_WINDOW == 120


def test_malformed_jwt_expires_falls_back(fresh_config, monkeypatch):
    """回归：非法整型 env 不应让后端 import 时 int() 崩溃，应回退默认。"""
    C = _reload(monkeypatch, JWT_EXPIRES_SECONDS="abc")
    assert C.JWT_EXPIRES_SECONDS == 604800


def test_empty_jwt_expires_falls_back(fresh_config, monkeypatch):
    C = _reload(monkeypatch, JWT_EXPIRES_SECONDS="")
    assert C.JWT_EXPIRES_SECONDS == 604800


def test_malformed_rate_limit_max_falls_back(fresh_config, monkeypatch):
    C = _reload(monkeypatch, RATE_LIMIT_MAX="xyz")
    assert C.RATE_LIMIT_MAX == 5


def test_malformed_rate_limit_window_falls_back(fresh_config, monkeypatch):
    C = _reload(monkeypatch, RATE_LIMIT_WINDOW="oops")
    assert C.RATE_LIMIT_WINDOW == 60


def test_rate_limit_enabled_toggle(fresh_config, monkeypatch):
    assert _reload(monkeypatch, STOCKSIGNAL_RATE_LIMIT_ENABLED="0").RATE_LIMIT_ENABLED is False
    assert _reload(monkeypatch, STOCKSIGNAL_RATE_LIMIT_ENABLED="1").RATE_LIMIT_ENABLED is True
