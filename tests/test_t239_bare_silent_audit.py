# -*- coding: utf-8 -*-
"""tests/test_t239_bare_silent_audit.py

T-239 静默异常治理收口守卫（R3）：裸静默吞异常（except 体仅 pass/continue/break/
裸 return）必须显式审计——在 except 体内部或紧邻 except 的上一行携带 `ui_audit_exempt`
标注（与 T-239R2 既定范式一致），否则视为未审计缺口。

锁死不变量：
1. 裸静默 handler 必须携带显式抑制标注——`ui_audit_exempt`（T-239 审计标注）或
   `noqa`（lint 级「已知 broad-except  intentionally」标注），位于 except 体内部
   或紧邻 except 的上一行；
2. 测试目录 / thesis/ 不约束（测试允许静默吞）；
3. 带 logger/logging/raise / 返回带 reason 的降级不在此列（由 test_exception_logging
   等行为守卫覆盖，本守卫只锁「纯静默无留痕、也无任何抑制标注」这一档）。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDED_DIRS = ["modules", "backend", "pages", "scripts"]


def _is_bare_silent(node):
    body = node.body
    if not body or len(body) != 1:
        return False
    b = body[0]
    if not isinstance(b, (ast.Pass, ast.Continue, ast.Break, ast.Return)):
        return False
    if isinstance(b, ast.Return) and b.value is not None:
        return False  # 带返回值的诚实降级（如 return {"status":"unavailable","reason":...}）不在此列
    return True


def test_bare_silent_handlers_are_audited():
    offenders = []
    for d in GUARDED_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "tests" in p.parts or p.name.startswith("test_"):
                continue
            try:
                src = p.read_text(encoding="utf-8")
                tree = ast.parse(src)
            except Exception:
                continue
            lines = src.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if not _is_bare_silent(node):
                    continue
                seg = "\n".join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
                # 显式抑制标注（审计标注或 lint 级 known-broad-except 标注）即视为已审计
                if "ui_audit_exempt" in seg or "noqa" in seg:
                    continue
                prev = lines[node.lineno - 2] if node.lineno >= 2 else ""
                if "ui_audit_exempt" in prev or "noqa" in prev:
                    continue
                offenders.append(f"{p.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, \
        "存在未审计的裸静默吞异常（须加 ui_audit_exempt 标注）：\n  " + "\n  ".join(offenders)
