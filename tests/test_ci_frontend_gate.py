# -*- coding: utf-8 -*-
"""守卫：CI 必须真跑前端 v2 门禁与实时契约校验，且守卫自身不得自我静音。

背景（2026-11-15）：.github/workflows/ci.yml 长期只有后端 Python 步骤，
前端 v2 的 tsc / vitest（含契约漂移、路由懒加载、导航守卫等 112 个测试文件）
只在本地手动跑。同日补了 frontend-v2 job；但 contract-drift B 段（实时后端
JSON ↔ Zod）仍因缺 SS_BACKEND_URL 默认跳过，等于跨语言契约无人看守。

本守卫锁死两个 job 的必需步骤 + B 段的防自我静音断言与超时口径，并用反例
自测防止「保留 job 名但掏空命令」「加 continue-on-error」「删 okCount」式退化。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github/workflows/ci.yml"
FE = ROOT / "frontend-v2"
CD = FE / "tests/unit/contract-drift.test.ts"

_FE_JOB = "  frontend-v2:"
_LIVE_JOB = "  contract-drift-live:"

_FE_COMMANDS = ("npm ci", "npm run typecheck", "npm test", "npm run build")
_FE_TOKENS = (
    "actions/setup-node@v4",
    'node-version: "22"',
    "cache-dependency-path: frontend-v2/package-lock.json",
    "working-directory: frontend-v2",
)
_BACKEND_GATES = (
    'python -m pytest tests/ -m "not live" -q',
    "python -m backend.tests.test_security",
)
_LIVE_TOKENS = (
    "SS_BACKEND_URL: http://127.0.0.1:5050",
    "python -m backend.scripts.init_db",
    "python -m flask --app backend.app:app run",
    "/api/health",
    "npm test -- tests/unit/contract-drift.test.ts",
    "STOCKSIGNAL_ENABLE_ALERT_SCHEDULER: \"0\"",
    "STOCKSIGNAL_ENABLE_COND_SCHEDULER: \"0\"",
    "STOCKSIGNAL_ENABLE_RESEARCH_WATCH: \"0\"",
    "STOCKSIGNAL_ENABLE_RECOMMEND_SCHEDULER: \"0\"",
    "STOCKSIGNAL_ENABLE_DATA_REFRESH: \"0\"",
    "STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER: \"0\"",
    "trap 'kill",
)
_CD_TOKENS = (
    "okCount",
    "toBeGreaterThanOrEqual(2)",
    "setTimeout(() => ac.abort(), 12000)",
)


def _job_block(ci_text: str, marker: str) -> str | None:
    """按 2 空格缩进的 job key 精确切块。

    历史缺陷（本轮修复）：旧守卫用 ``ci_text[head:]`` 一直取到文件末尾，
    追加 contract-drift-live job 后，被掏空的 frontend-v2 命令会「借」后续
    job 的同名命令蒙混过关 —— 守卫自我静音。
    """
    head = ci_text.find(marker)
    if head < 0:
        return None
    rest = ci_text[head + len(marker):]
    nxt = re.search(r"\n  [A-Za-z0-9_-]+:", rest)
    return rest[:nxt.start()] if nxt else rest


def _all_errors(ci_text: str, pkg_text: str, cd_text: str, lock_exists: bool) -> list[str]:
    """纯函数：返回 CI 门禁的全部缺口（空列表 = 健康）。"""
    errors: list[str] = []

    fe = _job_block(ci_text, _FE_JOB)
    if fe is None:
        errors.append("CI 缺少 frontend-v2 job")
    else:
        for token in _FE_TOKENS:
            if token not in fe:
                errors.append(f"前端 job 缺配置: {token}")
        for cmd in _FE_COMMANDS:
            if cmd not in fe:
                errors.append(f"前端 job 缺门禁命令: {cmd}")

    live = _job_block(ci_text, _LIVE_JOB)
    if live is None:
        errors.append("CI 缺少 contract-drift-live job（B 段又变回默认不跑）")
    else:
        for token in _LIVE_TOKENS:
            if token not in live:
                errors.append(f"实时契约 job 缺: {token}")
        if "continue-on-error" in live:
            errors.append("实时契约门禁不得 continue-on-error（等于门禁空转）")

    for gate in _BACKEND_GATES:
        if gate not in ci_text:
            errors.append(f"后端门禁被顶掉: {gate}")
    for script in ("typecheck", "test", "build"):
        if f'"{script}"' not in pkg_text:
            errors.append(f"package.json 缺 script: {script}")
    for token in _CD_TOKENS:
        if token not in cd_text:
            errors.append(f"contract-drift B 段缺 {token}（防自我静音 / 超时口径）")
    if not lock_exists:
        errors.append("npm ci 需要 frontend-v2/package-lock.json")
    return errors


def _current() -> tuple[str, str, str, bool]:
    assert CI.exists(), "缺少 .github/workflows/ci.yml"
    return (
        CI.read_text(encoding="utf-8"),
        (FE / "package.json").read_text(encoding="utf-8"),
        CD.read_text(encoding="utf-8"),
        (FE / "package-lock.json").exists(),
    )


def test_ci_gates_are_wired():
    errors = _all_errors(*_current())
    assert not errors, "CI 门禁缺口:\n" + "\n".join(errors)


def test_ci_guard_is_not_self_silencing():
    ci, pkg, cd, lock = _current()
    assert _all_errors(ci, pkg, cd, lock) == [], "当前 CI 必须通过门禁校验"

    # 1) 任一整段 job 被删：必须报错，不得因 find()==-1 静默跳过
    assert _all_errors(ci.replace(_FE_JOB, "  # removed"), pkg, cd, lock)
    assert _all_errors(ci.replace(_LIVE_JOB, "  # removed"), pkg, cd, lock)

    # 2) 保留 job 名但逐条掏空前端命令：每一条都必须被抓（精确切块后不能借 live job）
    for cmd in _FE_COMMANDS:
        tampered = ci.replace(f"run: {cmd}", "run: echo skipped")
        assert any(cmd in e for e in _all_errors(tampered, pkg, cd, lock)), (
            f"掏空 {cmd} 竟未被守卫发现（守卫自我静音）"
        )

    # 3) 掏空实时契约测试命令
    tampered = ci.replace(
        "npm test -- tests/unit/contract-drift.test.ts",
        "npm test -- tests/unit/probe-kind.test.ts",
    )
    assert _all_errors(tampered, pkg, cd, lock)

    # 4) 删 SS_BACKEND_URL / health 等待 / 调度器关闭开关，都必须被抓
    for token in (
        "SS_BACKEND_URL: http://127.0.0.1:5050",
        "curl -fsS http://127.0.0.1:5050/api/health",
        'STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER: "0"',
    ):
        assert _all_errors(ci.replace(token, ""), pkg, cd, lock)

    # 5) 给实时门禁加 continue-on-error 也不许过
    tampered = ci.replace(_LIVE_JOB, _LIVE_JOB + "\n    continue-on-error: true")
    assert any("continue-on-error" in e for e in _all_errors(tampered, pkg, cd, lock))

    # 6) B 段去掉防自我静音断言 / 把超时改回 30s，都必须被抓
    assert _all_errors(ci, pkg, cd.replace("toBeGreaterThanOrEqual(2)", ""), lock)
    assert _all_errors(
        ci, pkg,
        cd.replace("setTimeout(() => ac.abort(), 12000)", "setTimeout(() => ac.abort(), 30000)"),
        lock,
    )

    # 7) 后端 pytest 被顶掉 / 去 working-directory / 空文本 / 缺 lock
    assert _all_errors(ci.replace('python -m pytest tests/ -m "not live" -q', "python -m pytest -q"), pkg, cd, lock)
    assert _all_errors(ci.replace("working-directory: frontend-v2", ""), pkg, cd, lock)
    assert _all_errors("", pkg, cd, lock)
    assert _all_errors(ci, pkg, cd, False)
