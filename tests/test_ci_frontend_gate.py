# -*- coding: utf-8 -*-
"""守卫：CI 必须真跑前端 v2 门禁与实时契约校验，且守卫自身不得自我静音。

背景（2026-11-15）：.github/workflows/ci.yml 长期只有后端 Python 步骤，
前端 v2 的 tsc / vitest（含契约漂移、路由懒加载、导航守卫等 112 个测试文件）
只在本地手动跑。同日补了 frontend-v2 job；但 contract-drift B 段（实时后端
JSON ↔ Zod）仍因缺 SS_BACKEND_URL 默认跳过，等于跨语言契约无人看守。

本守卫锁死两个 job 的必需步骤 + B 段的防自我静音断言与超时口径、CI 真实归档
样本夹具的完整性（字节数 / sha256 / 诚实声明），并用反例自测防止
「保留 job 名但掏空命令」「加 continue-on-error」「删 okCount / 删覆盖门禁」
「把夹具换成编造数据」式退化。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github/workflows/ci.yml"
FE = ROOT / "frontend-v2"
CD = FE / "tests/unit/contract-drift.test.ts"
FIX = ROOT / "tests/fixtures/ci_data"

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
    "cp tests/fixtures/ci_data/*.json data/",
    "cp tests/fixtures/ci_data/snapshots/*.json data/snapshots/",
    "rm -f data/manifest.json",
)
_CD_TOKENS = (
    "okCount",
    "toBeGreaterThanOrEqual(2)",
    "setTimeout(() => ac.abort(), 12000)",
    "checkedCount",
    "DegradedEnvelope",
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
        "cp tests/fixtures/ci_data/*.json data/",
        "rm -f data/manifest.json",
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

    # 6b) 删掉 80% 覆盖门禁 / 降级信封校验，也必须被抓（否则「扩覆盖」可被静默撤回）
    assert _all_errors(ci, pkg, cd.replace("checkedCount", ""), lock)
    assert _all_errors(ci, pkg, cd.replace("DegradedEnvelope", ""), lock)

    # 7) 后端 pytest 被顶掉 / 去 working-directory / 空文本 / 缺 lock
    assert _all_errors(ci.replace('python -m pytest tests/ -m "not live" -q', "python -m pytest -q"), pkg, cd, lock)
    assert _all_errors(ci.replace("working-directory: frontend-v2", ""), pkg, cd, lock)
    assert _all_errors("", pkg, cd, lock)
    assert _all_errors(ci, pkg, cd, False)


def _fixture_errors(readme: str, manifest: dict, blobs: dict[str, bytes]) -> list[str]:
    """纯函数：CI 样本夹具的完整性缺口（空列表 = 健康）。"""
    errors: list[str] = []
    for phrase in ("真实归档", "非合成", "字节级", "不代表当前行情"):
        if phrase not in readme:
            errors.append(f"夹具 README 缺诚实声明: {phrase}")
    entries = manifest.get("files", [])
    if len(entries) < 8:
        errors.append(f"真实样本数量异常（{len(entries)}），夹具疑似被掏空")
    for e in entries:
        name = e.get("name", "")
        raw = blobs.get(name)
        if raw is None:
            errors.append(f"缺样本文件: {name}")
            continue
        norm = raw.replace(b"\r\n", b"\n")
        # Git 会把 CRLF 规范化成 LF：本机工作副本是 CRLF，CI Ubuntu checkout 是 LF。
        # 完整性一律按「LF 归一化后」的内容断言；manifest.bytes 只记录原始归档
        # 字节数供溯源，跨平台不参与断言（否则 CI 会因换行差异假红）。
        if not isinstance(e.get("bytes"), int) or e["bytes"] <= 0:
            errors.append(f"{name}: manifest 缺原始归档字节数（溯源信息）")
        if e.get("bytes_lf") != len(norm):
            errors.append(f"{name}: LF 归一化字节数与 manifest 不符（夹具被改动）")
        if e.get("sha256_lf") != hashlib.sha256(norm).hexdigest():
            errors.append(f"{name}: sha256 与 manifest 不符（夹具被改动）")
        try:
            json.loads(norm.decode("utf-8"))
        except Exception as exc:
            errors.append(f"{name}: 不是合法 JSON（{exc}）")
    return errors


def test_ci_fixture_samples_are_real_and_intact():
    """真实归档样本必须完整、可解析、带诚实声明；反例必须被抓。"""
    readme = (FIX / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((FIX / "manifest.json").read_text(encoding="utf-8"))
    blobs = {
        e["name"]: (FIX / e["name"]).read_bytes()
        for e in manifest["files"]
        if (FIX / e["name"]).exists()
    }
    errors = _fixture_errors(readme, manifest, blobs)
    assert not errors, "CI 样本夹具异常:\n" + "\n".join(errors)

    # 反例：删诚实声明 / 删文件 / 改 1 字节 / 掏空清单，都必须报错
    assert _fixture_errors(readme.replace("非合成", ""), manifest, blobs)
    assert _fixture_errors(readme, manifest, {})
    first = manifest["files"][0]["name"]
    tampered = dict(blobs)
    tampered[first] = blobs[first] + b" "
    assert _fixture_errors(readme, manifest, tampered)
    assert _fixture_errors(readme, {**manifest, "files": []}, blobs)

    # 跨平台（2026-11-15 真缺陷）：Git 把 CRLF 规范化为 LF，CI Ubuntu checkout
    # 的工作副本就是 LF；完整性校验必须仍然全绿，不能因换行口径假红。
    lf_blobs = {k: v.replace(b"\r\n", b"\n") for k, v in blobs.items()}
    assert not _fixture_errors(readme, manifest, lf_blobs), (
        "LF 版夹具被判异常：CI 会因换行规范化假红（守卫跨平台失效）"
    )
    # 删 bytes_lf / 抹掉 sha256_lf 都必须被抓，防止完整性门禁被静默掏空
    stripped = json.loads(json.dumps(manifest))
    for f in stripped["files"]:
        f.pop("bytes_lf", None)
    assert _fixture_errors(readme, stripped, blobs)
    broken_hash = json.loads(json.dumps(manifest))
    broken_hash["files"][0]["sha256_lf"] = "0" * 64
    assert _fixture_errors(readme, broken_hash, blobs)
