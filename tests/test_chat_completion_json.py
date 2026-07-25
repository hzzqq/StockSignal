"""R12：llm_client 结构化 JSON 输出 + 失败可观测性测试（无网、全 mock）。"""
from unittest import mock

import modules.llm_client as lc


def _fake_client(content):
    """构造一个 openai.OpenAI 客户端替身，其 chat.completions.create 返回给定 content。"""
    client = mock.MagicMock()
    msg = mock.MagicMock()
    msg.content = content
    choice = mock.MagicMock()
    choice.message = msg
    resp = mock.MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp
    return client


def _patch_config(monkeypatch):
    """让 llm_client 认为已配置、且只有主模型（无回退链），便于单模型断言。"""
    monkeypatch.setattr(lc, "is_configured", lambda: True)
    monkeypatch.setattr(lc, "config", lambda: ("https://api.openai.com/v1", "gpt-4o-mini", "k"))
    monkeypatch.setattr(lc, "fallback_models", lambda: [])
    monkeypatch.setattr(lc, "_extra_headers", lambda base_url: {})


def test_extract_json_plain():
    assert lc._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "好的，结果如下：\n```json\n{\"score\": 88}\n```\n以上。"
    assert lc._extract_json(text) == {"score": 88}


def test_extract_json_with_prose():
    text = "分析完成：{\"verdict\": \"buy\", \"target\": 12.5} 仅供参考"
    assert lc._extract_json(text) == {"verdict": "buy", "target": 12.5}


def test_extract_json_invalid_returns_none():
    assert lc._extract_json("这不是 JSON") is None
    assert lc._extract_json("") is None


def test_extract_json_list():
    assert lc._extract_json("[1, 2, 3]") == [1, 2, 3]


def test_chat_completion_json_valid(monkeypatch):
    _patch_config(monkeypatch)
    client = _fake_client('{"ok": true}')
    with mock.patch("openai.OpenAI", return_value=client):
        out = lc.chat_completion_json([{"role": "user", "content": "x"}])
    assert out == {"ok": True}


def test_chat_completion_json_fenced(monkeypatch):
    _patch_config(monkeypatch)
    client = _fake_client("```json\n{\"score\": 70}\n```")
    with mock.patch("openai.OpenAI", return_value=client):
        out = lc.chat_completion_json([{"role": "user", "content": "x"}])
    assert out == {"score": 70}


def test_chat_completion_json_default_on_unparseable(monkeypatch):
    _patch_config(monkeypatch)
    client = _fake_client("模型拒绝回答")
    with mock.patch("openai.OpenAI", return_value=client):
        out = lc.chat_completion_json([{"role": "user", "content": "x"}, ], default=[])
    assert out == []


def test_chat_completion_json_default_when_unconfigured(monkeypatch):
    monkeypatch.setattr(lc, "is_configured", lambda: False)
    out = lc.chat_completion_json([{"role": "user", "content": "x"}], default={})
    assert out == {}


def test_last_error_observability_on_unconfigured(monkeypatch):
    monkeypatch.setattr(lc, "is_configured", lambda: False)
    lc._set_last_err("")
    out = lc.chat_completion([{"role": "user", "content": "x"}])
    assert out is None
    assert "未配置" in lc.last_error()


def test_last_error_captures_model_failure(monkeypatch):
    _patch_config(monkeypatch)
    client = mock.MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("rate limit")
    lc._set_last_err("")
    with mock.patch("openai.OpenAI", return_value=client):
        out = lc.chat_completion([{"role": "user", "content": "x"}])
    assert out is None
    assert "rate limit" in lc.last_error()
