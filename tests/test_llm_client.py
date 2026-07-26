"""
tests/test_llm_client.py
========================
校验 modules.llm_client 的纯逻辑（不触网）：

- _extract_json：三级兜底抽取（整段 / ```围栏``` / 首尾括号子串）；
- chat_completion_json：契约收紧——只放行 dict/list，裸标量一律回退 default；
- _model_chain / fallback_models / _extra_headers / is_configured / config：
  环境变量解析与模型回退链去重；
- answer_with_llm：历史仅保留最近 6 轮 + system/user 组装；
- last_error 可观测性。

全部离线：涉及网络的 chat_completion 用 monkeypatch 替身。
"""
from __future__ import annotations

import importlib

import pytest

from modules import llm_client as lc


# ── _extract_json：三级兜底 ─────────────────────────────
def test_extract_json_plain():
    assert lc._extract_json('{"a": 1, "b": [2,3]}') == {"a": 1, "b": [2, 3]}


def test_extract_json_fenced():
    text = "解读如下：\n```json\n{\"score\": 88}\n```\n以上。"
    assert lc._extract_json(text) == {"score": 88}


def test_extract_json_fenced_no_lang():
    text = "```\n[1, 2, 3]\n```"
    assert lc._extract_json(text) == [1, 2, 3]


def test_extract_json_substring():
    text = 'prefix noise {"k": "v"} trailing words'
    assert lc._extract_json(text) == {"k": "v"}


def test_extract_json_nested_brackets():
    text = 'result: {"a": [1, 2], "b": {"c": 3}} done'
    assert lc._extract_json(text) == {"a": [1, 2], "b": {"c": 3}}


def test_extract_json_empty_or_garbage():
    assert lc._extract_json("") is None
    assert lc._extract_json(None) is None          # type: ignore[arg-type]
    assert lc._extract_json("完全没有 JSON 的文本") is None


# ── chat_completion_json：只放行 dict/list ────────────────
@pytest.mark.parametrize("raw, expected", [
    ('{"ok": true}', {"ok": True}),
    ('[1, 2, 3]', [1, 2, 3]),
    ('false', "DEFAULT"),      # 裸 bool → default
    ('123', "DEFAULT"),        # 裸 int → default
    ('"just a string"', "DEFAULT"),  # 裸 str → default
    ('null', "DEFAULT"),       # null → default
    ('这不是 json', "DEFAULT"),
])
def test_chat_completion_json_only_containers(monkeypatch, raw, expected):
    monkeypatch.setattr(lc, "chat_completion", lambda *a, **k: raw)
    sentinel = "DEFAULT"
    got = lc.chat_completion_json([{"role": "user", "content": "x"}], default=sentinel)
    if expected == "DEFAULT":
        assert got is sentinel
    else:
        assert got == expected


def test_chat_completion_json_none_returns_default(monkeypatch):
    monkeypatch.setattr(lc, "chat_completion", lambda *a, **k: None)
    sentinel = object()
    assert lc.chat_completion_json([{"role": "user", "content": "x"}], default=sentinel) is sentinel


# ── 环境变量解析与模型回退链 ─────────────────────────────
def test_fallback_models_from_env(monkeypatch):
    monkeypatch.setattr(lc, "_env", lambda k, d="": "m1, m2 ,, m3" if k == "STARFIELD_LLM_FALLBACK_MODELS" else d)
    assert lc.fallback_models() == ["m1", "m2", "m3"]


def test_fallback_models_default(monkeypatch):
    monkeypatch.setattr(lc, "_env", lambda k, d="": d)
    assert lc.fallback_models() == lc._DEFAULT_FALLBACK_MODELS


def test_model_chain_dedup(monkeypatch):
    def fake_env(k, d=""):
        if k == "STARFIELD_LLM_MODEL":
            return "primary"
        if k == "STARFIELD_LLM_FALLBACK_MODELS":
            return "primary, backup, backup2"
        return d
    monkeypatch.setattr(lc, "_env", fake_env)
    chain = lc._model_chain()
    assert chain[0] == "primary"
    assert chain.count("primary") == 1          # 主模型不重复
    assert "backup" in chain and "backup2" in chain


def test_extra_headers_openrouter():
    h = lc._extra_headers("https://openrouter.ai/api/v1")
    assert h.get("X-Title") == "StockSignal"
    assert lc._extra_headers("https://api.openai.com/v1") == {}


def test_is_configured(monkeypatch):
    monkeypatch.setattr(lc, "_env", lambda k, d="": "sk-xxx" if k == "STARFIELD_LLM_API_KEY" else d)
    assert lc.is_configured() is True
    monkeypatch.setattr(lc, "_env", lambda k, d="": d)
    assert lc.is_configured() is False


# ── answer_with_llm：历史裁剪 + 组装 ──────────────────────
def test_answer_with_llm_trims_history(monkeypatch):
    captured = {}

    def fake_cc(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(lc, "chat_completion", fake_cc)
    history = [{"role": "user", "content": str(i)} for i in range(20)]
    lc.answer_with_llm("SYS", "问题", history=history)
    msgs = captured["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[-1] == {"role": "user", "content": "问题"}
    # system(1) + 最近6轮 + 当前user(1) = 8
    assert len(msgs) == 8


def test_answer_with_llm_no_history(monkeypatch):
    captured = {}
    monkeypatch.setattr(lc, "chat_completion", lambda messages, **k: captured.setdefault("m", messages) or "r")
    lc.answer_with_llm("SYS", "Q")
    assert captured["m"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "Q"},
    ]


# ── last_error 可观测性 ──────────────────────────────────
def test_last_error_roundtrip():
    lc._set_last_err("boom")
    assert lc.last_error() == "boom"
    lc._set_last_err("")
    assert lc.last_error() == ""
