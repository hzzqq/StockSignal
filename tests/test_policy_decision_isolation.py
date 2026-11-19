# -*- coding: utf-8 -*-
"""tests/test_policy_decision_isolation.py — 政策上下文隔离守卫（决策闭环真理源）。

最关键的守卫：证明 policy_context() 的返回值**只**落在快照展示字段
snap["event_factor"]["policy"]，即便它返回了伪造的 score/direction/利好
等脏字段，也绝不改变仓位（pct/contributions/sensitivity）与数据新鲜度。

全部离线确定性：monkeypatch 钉死 decision.py 的所有外部取数入口，零真实库/网络。
"""
import ast
import os
import sys

from modules.decision import build_snapshot
import modules.decision as decision  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _patch_deps(monkeypatch, policy_value):
    """钉死 build_snapshot 的全部外部依赖；policy_context 用 fake 注入。

    decision.py 里 policy_context 是函数内 `from modules.policy_store import ...`
    局部导入，patch 模块属性即可让局部 import 拿到 fake。
    """
    monkeypatch.setattr(
        "modules.decision.event_position_adj",
        lambda top_n=50: {"adj": 3, "long_count": 30, "as_of": "2026-08-20"},
    )
    monkeypatch.setattr(
        "modules.event_factor.macro_event_context",
        lambda: {"available": False, "reason": "test stub"},
    )
    monkeypatch.setattr("modules.policy_store.policy_context", lambda: policy_value)
    monkeypatch.setattr("modules.decision.compute_dual_factor_inputs", lambda: {})
    monkeypatch.setattr(
        "modules.decision._thesis_model_adj",
        lambda: {"adj": 0.0, "lines": [], "live": False},
    )


_INPUTS = ("2026-08-21", {}, 50.0, {"bias": "偏多", "score": 0.5}, None, None)


def test_policy_field_present_in_snapshot(monkeypatch):
    """build_snapshot 后 policy 展示字段存在且忠实透传 policy_context 返回。"""
    value = {"available": True, "total_documents": 3, "as_of": "2026-11-01", "derived": True}
    _patch_deps(monkeypatch, value)
    snap = build_snapshot(*_INPUTS)
    assert "policy" in snap["event_factor"]
    assert snap["event_factor"]["policy"] == value


def test_dirty_policy_fields_are_isolated_from_position(monkeypatch):
    """隔离证明：policy 返回伪造多空脏字段，仓位链路与新鲜度仍逐字节一致。"""
    clean = {"available": True, "total_documents": 3, "derived": True}
    dirty = {
        "available": True,
        "score": 999,
        "direction": "利好",
        "bullish": True,
        "sentiment": "强利好",
        "impact": "利好",
    }
    _patch_deps(monkeypatch, clean)
    a = build_snapshot(*_INPUTS)
    _patch_deps(monkeypatch, dirty)
    b = build_snapshot(*_INPUTS)

    # 先证明脏值确实进了展示层（排除 patch 未生效导致的假绿）
    assert b["event_factor"]["policy"] == dirty
    # 再证明仓位链路逐字节一致。contributions/sensitivity 仅 explain=True 才产出，
    # 当前 build_snapshot 未启用 explain，用 .get() 比较（两侧同为 None 亦属一致）。
    assert a["position"]["pct"] == b["position"]["pct"]
    assert a["position"].get("contributions") == b["position"].get("contributions")
    assert a["position"].get("sensitivity") == b["position"].get("sensitivity")
    assert a["data_freshness"] == b["data_freshness"]


def test_policy_not_in_freshness_sources_and_ast_isolation(monkeypatch):
    """policy 不进新鲜度守卫；AST 证明 policy_context() 只流入 ev_info['policy']。"""
    _patch_deps(monkeypatch, {"available": True, "derived": True})
    snap = build_snapshot(*_INPUTS)
    assert "policy" not in snap["data_freshness"]["sources"]

    with open(decision.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    def is_policy_call(node):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "policy_context")

    calls = [n for n in ast.walk(tree) if is_policy_call(n)]
    assert len(calls) == 1, "policy_context() 在 decision.py 中应只调用一次"

    # policy_context() 的结果先赋给临时变量（try/except 降级写法），
    # 该临时变量的唯一下游赋值必须是 ev_info["policy"]。
    assigns = [n for n in ast.walk(tree)
               if isinstance(n, ast.Assign) and is_policy_call(n.value)]
    assert len(assigns) == 1
    tmp = ast.unparse(assigns[0].targets[0])
    assert tmp == "_policy_ctx"

    ev_assigns = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name)
                  and n.value.id == tmp]
    assert len(ev_assigns) == 1
    assert ast.unparse(ev_assigns[0].targets[0]) in ("ev_info['policy']", 'ev_info["policy"]')

    # policy_context 调用与临时变量都不得出现在 derive_position 实参 / _fresh_sources 子树
    def uses_policy(node):
        return any(is_policy_call(sub) or (isinstance(sub, ast.Name) and sub.id == tmp)
                   for sub in ast.walk(node))

    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "derive_position"):
            assert not uses_policy(n)
        if (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_fresh_sources"
                        for t in n.targets)):
            assert not uses_policy(n.value)
