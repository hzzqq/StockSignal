# -*- coding: utf-8 -*-
"""守卫：CI 必须真跑前端 v2 门禁，且守卫自身不得自我静音。

背景（2026-11-15）：.github/workflows/ci.yml 长期只有后端 Python 步骤，
前端 v2 的 tsc / vitest（含契约漂移、路由懒加载、导航守卫等 112 个测试文件）
只在本地手动跑。新增只读端点 / 路由 / Zod schema 漂移在 CI 上完全无人看守。

本守卫静态锁死前端 job 的必需步骤，并用反例自测防止「保留 job 名但掏空命令」
式静默退化；同时确认后端 pytest 门禁没被新 job 顶掉。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github/workflows/ci.yml"
FE = ROOT / "frontend-v2"

_JOB_MARKER = "  frontend-v2:"
_REQUIRED_COMMANDS = ("npm ci", "npm run typecheck", "npm test", "npm run build")
_REQUIRED_TOKENS = (
    "actions/setup-node@v4",
    'node-version: "22"',
    "cache-dependency-path: frontend-v2/package-lock.json",
    "working-directory: frontend-v2",
)
_BACKEND_GATES = (
    'python -m pytest tests/ -m "not live" -q',
    "python -m backend.tests.test_security",
)


def _gate_errors(ci_text: str, pkg_text: str, lock_exists: bool) -> list[str]:
    """纯函数：返回 CI 前端门禁的全部缺口（空列表 = 健康）。"""
    errors: list[str] = []
    head = ci_text.find(_JOB_MARKER)
    if head < 0:
        return ["CI 缺少 frontend-v2 job"]  # 找不到 job 必须报错，绝不静默通过
    block = ci_text[head:]

    for token in _REQUIRED_TOKENS:
        if token not in block:
            errors.append(f"前端 job 缺配置: {token}")
    for cmd in _REQUIRED_COMMANDS:
        if cmd not in block:
            errors.append(f"前端 job 缺门禁命令: {cmd}")
    for gate in _BACKEND_GATES:
        if gate not in ci_text:
            errors.append(f"后端门禁被顶掉: {gate}")
    for script in ("typecheck", "test", "build"):
        if f'"{script}"' not in pkg_text:
            errors.append(f"package.json 缺 script: {script}")
    if not lock_exists:
        errors.append("npm ci 需要 frontend-v2/package-lock.json")
    return errors


def _current() -> tuple[str, str, bool]:
    assert CI.exists(), "缺少 .github/workflows/ci.yml"
    return (
        CI.read_text(encoding="utf-8"),
        (FE / "package.json").read_text(encoding="utf-8"),
        (FE / "package-lock.json").exists(),
    )


def test_ci_frontend_gates_are_wired():
    errors = _gate_errors(*_current())
    assert not errors, "CI 前端门禁缺口:\n" + "\n".join(errors)


def test_ci_guard_is_not_self_silencing():
    ci, pkg, lock = _current()
    assert _gate_errors(ci, pkg, lock) == [], "当前 CI 必须通过门禁校验"

    # 1) 整段 job 被删：必须报错，不得因 find()==-1 而静默跳过
    assert _gate_errors(ci.replace(_JOB_MARKER, "  # removed"), pkg, lock)

    # 2) 保留 job 名但逐条掏空命令：每一条都必须被抓
    for cmd in _REQUIRED_COMMANDS:
        tampered = ci.replace(f"run: {cmd}", "run: echo skipped")
        assert any(cmd in e for e in _gate_errors(tampered, pkg, lock)), (
            f"掏空 {cmd} 竟未被守卫发现（守卫自我静音）"
        )

    # 3) 去掉 working-directory 会让命令在仓库根跑，vitest 会误报 cwd
    tampered = ci.replace("working-directory: frontend-v2", "")
    assert any("working-directory" in e for e in _gate_errors(tampered, pkg, lock))

    # 4) 后端 pytest 步骤被顶掉也不许通过
    tampered = ci.replace('python -m pytest tests/ -m "not live" -q', "python -m pytest -q")
    assert _gate_errors(tampered, pkg, lock)

    # 5) 空文本 / 缺 lock 都属守卫失效
    assert _gate_errors("", pkg, lock)
    assert _gate_errors(ci, pkg, False)
