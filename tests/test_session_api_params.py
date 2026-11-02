"""R17：session.api_kline / api_quote 参数约定单测（无网依赖）。

R-05 拆分（2026-11-02）：业务封装 api_quote/api_kline 位于 modules.session_api，
其内部按模块全局查找 api_get —— 故补丁必须打在 session_api 上（打主入口无效，
且会静默走真实网络造成假绿）。对外调用仍走 modules.session 的 re-export。

锁定工作记忆中的易错点：
- GET /api/kline 用 symbol=（6 位数字，非 ticker）；
- GET /api/quote 用 ticker=（非 symbol）。

通过 monkeypatch api_get 捕获最终拼接的 URL，断言参数键名正确，
且不串用。同时验证空入参短路（不发起请求）、信封解析 (status=="ok")。
"""

import modules.session as sess
import modules.session_api as sess_api


def test_api_quote_uses_ticker(monkeypatch):
    captured = {}

    def fake_api_get(path, timeout=5, **kwargs):
        captured["path"] = path
        return 200, {"status": "ok", "data": {"price": 12.34}}

    monkeypatch.setattr(sess_api, "api_get", fake_api_get)
    result = sess.api_quote("600519")
    assert result is not None
    assert result["price"] == 12.34
    # 关键：quote 用 ticker=，绝不用 symbol=
    assert "ticker=600519" in captured["path"]
    assert "symbol=" not in captured["path"]


def test_api_quote_empty_returns_none(monkeypatch):
    called = []
    monkeypatch.setattr(sess_api, "api_get", lambda *a, **k: called.append(1) or (200, {"status": "ok", "data": {}}))
    assert sess.api_quote("") is None
    # 空 ticker 不发起请求
    assert called == []


def test_api_quote_non_ok_returns_none(monkeypatch):
    monkeypatch.setattr(sess_api, "api_get", lambda *a, **k: (200, {"status": "fail", "data": {"price": 1}}))
    assert sess.api_quote("600519") is None


def test_api_kline_uses_symbol(monkeypatch):
    captured = {}

    def fake_api_get(path, timeout=5, **kwargs):
        captured["path"] = path
        return 200, {"status": "ok", "data": [{"close": 1}]}

    monkeypatch.setattr(sess_api, "api_get", fake_api_get)
    result = sess.api_kline("600519")
    assert result == [{"close": 1}]
    # 关键：kline 用 symbol=，绝不用 ticker=
    assert "symbol=600519" in captured["path"]
    assert "ticker=" not in captured["path"]
    # 默认参数
    assert "period=daily" in captured["path"]
    assert "adjust=qfq" in captured["path"]
    assert "start=" in captured["path"]


def test_api_kline_custom_params(monkeypatch):
    captured = {}

    def fake_api_get(path, timeout=5, **kwargs):
        captured["path"] = path
        return 200, {"status": "ok", "data": []}

    monkeypatch.setattr(sess_api, "api_get", fake_api_get)
    sess.api_kline("000001", start="2023-01-01", end="2023-12-31", period="weekly", adjust="hfq")
    assert "symbol=000001" in captured["path"]
    assert "start=2023-01-01" in captured["path"]
    assert "end=2023-12-31" in captured["path"]
    assert "period=weekly" in captured["path"]
    assert "adjust=hfq" in captured["path"]


def test_api_kline_empty_symbol_no_request(monkeypatch):
    called = []
    monkeypatch.setattr(sess_api, "api_get", lambda *a, **k: called.append(1) or (200, {"status": "ok", "data": []}))
    assert sess.api_kline("") is None
    assert called == []


def test_api_kline_non_ok_returns_none(monkeypatch):
    monkeypatch.setattr(sess_api, "api_get", lambda *a, **k: (200, {"status": "fail", "data": []}))
    assert sess.api_kline("600519") is None
