"""
tests/test_prefs_persist.py
=======================
锁定 modules/prefs_persist.py 的浏览器端偏好持久化行为。

该模块是项目内「零测试覆盖」核心模块（81 行，无对应 tests）。
它依赖 streamlit.components.v1.html 注入 JS 把偏好写入 localStorage，
本测试用 monkeypatch 捕获注入脚本字符串，验证：
  - save_prefs 生成的 JS 含 localStorage.setItem 且 JSON 双重转义正确（含中文不破坏）
  - restore_prefs_from_local_storage 生成的 JS 读取 localStorage 并补回 URL prefs 参数
  - load_prefs_from_local_storage 安全返回 {}
  - 任意输入都不抛异常（隐私模式/配额满被 try/except 吞掉，不影响页面）
"""

from __future__ import annotations

import json
import re

import streamlit.components.v1 as components
import modules.prefs_persist as pp


def _capture_html(monkeypatch):
    """monkeypatch components.html，捕获注入脚本字符串。"""
    captured = {}

    def fake_html(script, height=0, **kw):
        captured["script"] = script
        captured["height"] = height
        return None

    monkeypatch.setattr(components, "html", fake_html)
    return captured


def _extract_setitem_value(script: str) -> str:
    """提取 localStorage.setItem("ss_prefs", "<json>") 中的 JSON 字面量字符串。"""
    m = re.search(r'setItem\("ss_prefs",\s*("(?:[^"\\]|\\.)*")\)', script)
    assert m, "未找到 setItem 的 JSON 字面量"
    return m.group(1)


def test_save_prefs_injects_localstorage_setitem(monkeypatch):
    cap = _capture_html(monkeypatch)
    pp.save_prefs({"theme_mode": "dark", "font_size": 14})
    s = cap["script"]
    assert "localStorage.setItem" in s
    assert '"ss_prefs"' in s
    # 双重 json：外层是 JS 字符串字面量，内层是偏好 JSON；两层解回应还原为原 dict
    outer = json.loads(_extract_setitem_value(s))  # JS 字符串 -> Python str
    inner = json.loads(outer)  # 内部 JSON -> dict
    assert inner == {"theme_mode": "dark", "font_size": 14}
    assert cap["height"] == 0


def test_save_prefs_keeps_chinese_with_ensure_ascii_false(monkeypatch):
    cap = _capture_html(monkeypatch)
    pp.save_prefs({"theme_mode": "暗色"})
    s = cap["script"]
    # ensure_ascii=False：中文保留在注入脚本内，而非 \\uXXXX 转义
    assert "暗色" in s
    inner = json.loads(json.loads(_extract_setitem_value(s)))
    assert inner == {"theme_mode": "暗色"}


def test_save_prefs_never_raises_on_edge_inputs(monkeypatch):
    """空 dict / 嵌套结构 / 特殊字符都不应抛异常（隐私模式被 try/except 吞掉）。"""
    cap = _capture_html(monkeypatch)
    pp.save_prefs({})
    pp.save_prefs({"a": {"b": [1, 2, 3]}, "quote": '"backslash\\slash"'})
    assert cap["script"]  # 至少注入了一次脚本（最后一次）


def test_restore_prefs_reads_localstorage_and_sets_url(monkeypatch):
    cap = _capture_html(monkeypatch)
    pp.restore_prefs_from_local_storage()
    s = cap["script"]
    assert 'localStorage.getItem("ss_prefs")' in s
    assert "URLSearchParams" in s
    # QP_PREFS 常量 "prefs" 被写回 URL
    assert 'params.set("prefs"' in s
    # 已有 prefs 时不打扰（避免死循环）
    assert "if (params.get" in s


def test_load_prefs_from_local_storage_returns_empty_dict():
    assert pp.load_prefs_from_local_storage() == {}
