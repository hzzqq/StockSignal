"""tests/test_voice_event.py — 语音转写事件因子模块守卫。

覆盖：transcribe_audio 的 未配置/空音频/成功/失败 四态 + extract_event_factors 的
空文本/硬逻辑/题材炒作/中性。ASR 真实调用需网络+key，本套用 sys.modules 注入 fake
openai 隔离，不触网；extract_event_factors 复用 event_factor 透明规则真实执行。
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest

_ROOT = __file__ if False else None  # noqa
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mod():
    return importlib.import_module("modules.voice_event")


def _patch_openai(monkeypatch, client_factory):
    """把全局 openai 模块替换成 fake（transcribe_audio 内 import openai 会命中）。"""
    fake = types.SimpleNamespace(OpenAI=client_factory)
    monkeypatch.setitem(sys.modules, "openai", fake)


# ── transcribe_audio：诚实降级四态 ──
def test_transcribe_empty_audio_returns_none():
    ve = _mod()
    assert ve.transcribe_audio(b"") is None
    assert ve.transcribe_audio(None) is None


def test_transcribe_no_key_returns_none(monkeypatch):
    ve = _mod()
    monkeypatch.setattr(ve, "is_configured", lambda: False)
    assert ve.transcribe_audio(b"fake-audio-bytes") is None


def test_transcribe_success(monkeypatch):
    ve = _mod()

    class _Resp:
        text = " 公司中标大合同，产能扩张  "

    class _Audio:
        class transcriptions:
            @staticmethod
            def create(*a, **k):
                return _Resp()

    class _Client:
        audio = _Audio()

    _patch_openai(monkeypatch, lambda *a, **k: _Client())
    monkeypatch.setattr(ve, "is_configured", lambda: True)
    monkeypatch.setattr(ve, "config", lambda: ("https://api.openai.com/v1", "gpt-4o-mini", "sk-x"))
    out = ve.transcribe_audio(b"fake", filename="a.webm")
    assert out == "公司中标大合同，产能扩张"


def test_transcribe_failure_returns_none(monkeypatch):
    ve = _mod()

    def _boom(*a, **k):
        raise RuntimeError("endpoint does not support audio / network down")

    class _Audio:
        class transcriptions:
            create = staticmethod(_boom)

    class _Client:
        audio = _Audio()

    _patch_openai(monkeypatch, lambda *a, **k: _Client())
    monkeypatch.setattr(ve, "is_configured", lambda: True)
    monkeypatch.setattr(ve, "config", lambda: ("https://api.openai.com/v1", "gpt-4o-mini", "sk-x"))
    assert ve.transcribe_audio(b"fake") is None


# ── extract_event_factors：复用 event_factor 透明规则 ──
def test_extract_empty_text_unavailable():
    ve = _mod()
    r = ve.extract_event_factors("")
    assert r["available"] is False
    assert "空" in r["reason"]


def test_extract_hard_logic():
    ve = _mod()
    r = ve.extract_event_factors("公司中标大合同，业绩预增，产能扩张")
    assert r["available"] is True
    assert r["hard_logic"]["hard_logic"] == "硬逻辑"
    assert "中标" in r["hard_logic"]["evidence"]


def test_extract_speculation():
    ve = _mod()
    r = ve.extract_event_factors("市场消息传闻概念股炒作，小作文称将蹭风口")
    assert r["available"] is True
    assert r["hard_logic"]["hard_logic"] == "题材炒作"


def test_extract_neutral_unavailable():
    ve = _mod()
    r = ve.extract_event_factors("今天天气不错")
    assert r["available"] is True
    assert r["hard_logic"]["status"] == "unavailable"
