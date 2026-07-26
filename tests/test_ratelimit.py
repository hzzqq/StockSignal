"""
tests/test_ratelimit.py
=======================
进程内滑动窗口限流（backend.utils.ratelimit）测试。

用 Flask app context 提供 current_app.config，覆盖：窗口内放行/拒绝、
计数隔离、重置、关闭开关、退化配置保护（上限<=0 / 窗口<=0 不锁死登录）。
"""
import flask
import pytest

import backend.utils.ratelimit as rl


@pytest.fixture
def ctx(monkeypatch):
    app = flask.Flask(__name__)
    app.config["RATE_LIMIT_ENABLED"] = True
    app.config["RATE_LIMIT_MAX"] = 3
    app.config["RATE_LIMIT_WINDOW"] = 60
    with app.app_context():
        rl.reset_rate_limit()
        yield app
        rl.reset_rate_limit()


def test_allowed_within_limit(ctx):
    assert rl.is_allowed("a|u") is True
    assert rl.is_allowed("a|u") is True
    assert rl.is_allowed("a|u") is True
    # 第 4 次超过上限
    assert rl.is_allowed("a|u") is False


def test_reset_clears(ctx):
    for _ in range(3):
        rl.is_allowed("a|u")
    assert rl.is_allowed("a|u") is False
    rl.reset_rate_limit()
    assert rl.is_allowed("a|u") is True


def test_disabled_always_allows(ctx):
    flask.current_app.config["RATE_LIMIT_ENABLED"] = False
    for _ in range(10):
        assert rl.is_allowed("a|u") is True


def test_different_keys_independent(ctx):
    for _ in range(3):
        assert rl.is_allowed("a|u1") is True
    # 另一个用户独立计数
    assert rl.is_allowed("a|u2") is True


def test_get_hit_count(ctx):
    for _ in range(2):
        rl.is_allowed("a|u")
    assert rl.get_hit_count("a|u") == 2
    assert rl.get_hit_count("a|other") == 0


def test_make_key_format():
    assert rl.make_key("1.2.3.4", "alice") == "1.2.3.4|alice"


def test_max_zero_does_not_lock_out(ctx):
    """退化配置保护：上限<=0 不应拒绝一切登录。"""
    flask.current_app.config["RATE_LIMIT_MAX"] = 0
    for _ in range(5):
        assert rl.is_allowed("a|u") is True


def test_window_zero_does_not_crash(ctx):
    """窗口<=0 时退化为每次放行（清空式窗口），不崩溃也不死锁。"""
    flask.current_app.config["RATE_LIMIT_WINDOW"] = 0
    for _ in range(5):
        assert rl.is_allowed("a|u") is True


def test_negative_max_does_not_lock_out(ctx):
    flask.current_app.config["RATE_LIMIT_MAX"] = -1
    for _ in range(5):
        assert rl.is_allowed("a|u") is True
