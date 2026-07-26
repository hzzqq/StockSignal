"""
tests/test_task_routes.py
--------------------------
离线、纯函数单元测试：直接验证 _validate_task_payload 的 payload 结构校验。

不依赖 Flask / 网络 / worker，仅校验畸形 payload 被拦截、合法 payload 被放行。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 backend 成为合法的包（task_routes 内部使用
# `from ..auth` 等相对导入，必须以 backend 为顶层包导入）。
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.api.task_routes import _validate_task_payload  # noqa: E402


def test_valid_dict_passes_through():
    d = {"ticker": "600000"}
    ok, result = _validate_task_payload("analysis", d)
    assert ok is True
    assert result is d


def test_none_payload_allowed():
    ok, result = _validate_task_payload("analysis", None)
    assert ok is True
    assert result is None


def test_list_payload_rejected():
    ok, result = _validate_task_payload("analysis", [1, 2, 3])
    assert ok is False
    assert isinstance(result, str)


def test_str_payload_rejected():
    ok, result = _validate_task_payload("compare", "not-an-object")
    assert ok is False
    assert isinstance(result, str)


def test_empty_dict_payload_allowed():
    ok, result = _validate_task_payload("quant_research", {})
    assert ok is True
    assert result == {}
