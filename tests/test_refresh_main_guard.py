"""守卫：触发 ProcessPoolExecutor 的刷新入口必须带 __main__ 守卫（Windows spawn 进程炸弹防线）。

背景（Backlog 第 3 项）：
  ``modules.market_cache.refresh_all_indicators`` 内部用 ``ProcessPoolExecutor``
  隔离 py_mini_racer(V8) 原生崩溃。Windows 以 **spawn** 启动子进程，子进程会重新
  导入 ``__main__``；入口若没有 ``if __name__ == "__main__":`` 守卫，就会递归重跑
  ``refresh_all_indicators`` → 无限 spawn → **进程炸弹**。

  历史隐患：``REFRESH_COMMANDS['market_temp']`` 曾用
  ``python -c "from modules.market_cache import refresh_all_indicators; ..."`` 内联调用，
  正是无守卫入口（``-c`` 的代码本身就是子进程的 ``__main__``）。已改为走
  ``python -m modules._refresh_runner --force``。

本测试锁死（防回退）：
  AC1 ``_refresh_runner.py`` 必须带 ``__main__`` 守卫；
  AC2 ``REFRESH_COMMANDS`` 中任何触发进程池的命令，禁止 ``python -c`` 内联写法；
  AC3 ``market_temp`` 必须指向受保护的 ``-m`` 入口；
  AC4 ``main()`` 正确把 ``--force`` 透传给 ``refresh_all_indicators``（真行为，非假绿）。
"""
from pathlib import Path

import pytest

from modules.data_health import REFRESH_COMMANDS

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "modules" / "_refresh_runner.py"


def test_ac1_runner_has_main_guard():
    """AC1：入口模块必须有 __main__ 守卫（spawn 递归的唯一防线）。"""
    assert RUNNER.exists(), f"缺少入口模块 {RUNNER}"
    src = RUNNER.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src, (
        "_refresh_runner.py 缺少 __main__ 守卫：Windows spawn 下会递归进程炸弹"
    )


def test_ac2_no_inline_python_c_for_processpool_commands():
    """AC2：任何触发进程池的刷新命令都禁止 `python -c` 内联（无守卫即炸弹）。"""
    offenders = []
    for key, item in REFRESH_COMMANDS.items():
        cmd = (item or {}).get("cmd", "") or ""
        if "refresh_all_indicators" in cmd and "python -c" in cmd:
            offenders.append((key, cmd))
    assert not offenders, (
        "以下命令用 `python -c` 内联触发 ProcessPoolExecutor，spawn 下会递归重跑："
        + "; ".join(f"{k} -> {c}" for k, c in offenders)
    )


def test_ac3_market_temp_uses_protected_entry():
    """AC3：market_temp 必须经由自带守卫的 -m 入口。"""
    cmd = REFRESH_COMMANDS["market_temp"]["cmd"]
    assert "modules._refresh_runner" in cmd, (
        f"market_temp 应走 -m modules._refresh_runner，实际为：{cmd}"
    )
    assert "python -c" not in cmd


def test_ac4_main_passes_force_flag(monkeypatch):
    """AC4：--force 必须真实透传（monkeypatch 替换刷新函数，验证参数而非仅源码）。"""
    import modules._refresh_runner as rr

    calls = {}

    def _fake(force=False):
        calls["force"] = force
        return {"status": "ok"}

    monkeypatch.setattr(rr, "refresh_all_indicators", _fake)

    assert rr.main(["--force"]) == 0
    assert calls.get("force") is True, "--force 未透传为 force=True"

    assert rr.main([]) == 0
    assert calls.get("force") is False, "缺省时应为 force=False"


def test_ac4_mutation_guard_main_is_callable():
    """AC4 配套：main() 必须是可测函数（禁止把逻辑塞回 __main__ 块导致无法注入）。"""
    import modules._refresh_runner as rr

    assert callable(getattr(rr, "main", None)), "main() 应定义为可调用的函数"
