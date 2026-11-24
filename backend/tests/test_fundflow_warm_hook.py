"""
backend/tests/test_fundflow_warm_hook.py
----------------------------------------
守卫「Flask 后端冷启动预热行业资金流缓存」这处性能修复：

  1. create_app 必须调用 warm_fundflow_caches()，且调用被 try/except 包裹，
     禁止改成阻塞式直接取数（get_market_wide_snapshot / get_industry_fund_flow）。
  2. warm_fundflow_caches 保持幂等：连续调用两次只触发一次底层快照。
  3. 后台 job 抛异常时不把异常抛给调用方（失败静默降级）。

全程 monkeypatch 掉 get_market_wide_snapshot，绝不发真实网络请求。
"""
from __future__ import annotations

import ast
import sys
import threading
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import modules.fundflow as fundflow  # noqa: E402

_APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _create_app_node() -> ast.FunctionDef:
    tree = ast.parse(_APP_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "create_app":
            return node  # type: ignore[return-value]
    raise AssertionError(f"{_APP_PATH} 中未找到 create_app 函数定义")


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_create_app_calls_warm_hook_inside_try_except() -> None:
    """源码结构守卫：预热调用存在、被 try/except 包裹、且是后台幂等入口而非阻塞取数。"""
    create_app = _create_app_node()

    warm_calls = [
        node
        for node in ast.walk(create_app)
        if isinstance(node, ast.Call) and _call_name(node) == "warm_fundflow_caches"
    ]
    assert len(warm_calls) == 1, (
        "create_app 函数体内必须且只能有一处 warm_fundflow_caches() 调用"
        f"（实际 {len(warm_calls)} 处）"
    )
    call = warm_calls[0]

    # 调用点必须落在带 except 的 try 块内，防止预热异常导致 app 起不来。
    protected = any(
        isinstance(node, ast.Try)
        and node.handlers
        and any(child is call for child in ast.walk(node))
        for node in ast.walk(create_app)
    )
    assert protected, "warm_fundflow_caches() 必须被 try/except 包裹（预热失败不能阻断服务启动）"

    # 必须 import 自 modules.fundflow，避免被同名本地桩函数蒙混过关。
    imported_from_fundflow = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "modules.fundflow"
        and any(alias.name == "warm_fundflow_caches" for alias in node.names)
        for node in ast.walk(create_app)
    )
    assert imported_from_fundflow, "必须从 modules.fundflow import warm_fundflow_caches"

    # 非阻塞红线：create_app 里绝不能同步直调底层取数。
    blocking = {"get_market_wide_snapshot", "get_industry_fund_flow", "get_northbound_fund_flow"}
    direct = [
        node
        for node in ast.walk(create_app)
        if isinstance(node, ast.Call) and _call_name(node) in blocking
    ]
    assert not direct, (
        "create_app 内禁止同步直调底层资金流取数，必须走 warm_fundflow_caches 的 daemon 线程"
    )


def test_warm_fundflow_caches_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """幂等守卫：连续两次调用只触发一次底层快照，绝不发真网。"""
    calls: list[int] = []
    done = threading.Event()

    def fake_snapshot():
        calls.append(1)
        done.set()
        return {"industry": None, "northbound": None, "market": None}

    monkeypatch.setattr(fundflow, "get_market_wide_snapshot", fake_snapshot)
    monkeypatch.setattr(fundflow, "_warm_started", False)

    fundflow.warm_fundflow_caches()
    assert fundflow._warm_started is True, "首次调用应把 _warm_started 置 True"
    assert done.wait(timeout=10), "后台预热线程未在 10s 内执行"
    assert len(calls) == 1, f"首次调用应恰好触发一次快照，实际 {len(calls)} 次"

    fundflow.warm_fundflow_caches()
    assert len(calls) == 1, f"第二次调用必须幂等，不得再次取数（实际 {len(calls)} 次）"
    assert fundflow._warm_started is True


def test_warm_fundflow_caches_swallows_background_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """失败静默降级：后台 job 抛异常时，异常被 daemon 线程内 except 吞掉，不抛给调用方。"""
    done = threading.Event()

    def boom():
        done.set()
        raise RuntimeError("模拟东财超时降级")

    monkeypatch.setattr(fundflow, "get_market_wide_snapshot", boom)
    monkeypatch.setattr(fundflow, "_warm_started", False)

    # 调用方不应收到后台 job 的异常。
    fundflow.warm_fundflow_caches()
    assert fundflow._warm_started is True
    assert done.wait(timeout=10), "后台预热 job 未执行"
