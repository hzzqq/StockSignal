"""fundflow 模块导入期性能回归测试。

修复前：modules/fundflow.py 在模块导入时即同步执行 _proxy_reachable 的 socket 探测
（默认本地代理 127.0.0.1:26561，timeout 2s）。这导致每个 import fundflow 的页面
（16+ 个）在加载时都要先等这次最多 2 秒的网络探测——"几乎所有模块加载极慢"的
隐藏根因之一。

修复后：该探测改为在首次真实网络请求前惰性执行（_cached 包裹器内、_patch_done 幂等）。
import 不再阻塞。

本测试用子进程验证：导入 fundflow 后 _patch_done 必须为 False（证明导入期未跑探测），
且惰性函数仍可正常触发（_patch_done 变 True）。
"""
import subprocess
import sys


def _run(code: str) -> str:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=".",
    ).stdout.strip()


def test_import_does_not_run_proxy_probe():
    # 全新子进程导入 fundflow，导入后 _patch_done 必须为 False
    out = _run(
        "import modules.fundflow as f; "
        "print('PATCH_DONE=' + str(f._patch_done))"
    )
    assert "PATCH_DONE=False" in out, f"导入期不应执行代理探测，但 _patch_done=True。输出: {out}"


def test_lazy_proxy_setup_triggers_on_call():
    # 显式调用 _ensure_proxy_and_ssl 后 _patch_done 应变为 True（惰性触发仍有效）
    out = _run(
        "import modules.fundflow as f; "
        "assert f._patch_done is False; "
        "f._ensure_proxy_and_ssl(); "
        "print('AFTER=' + str(f._patch_done))"
    )
    assert "AFTER=True" in out, f"惰性代理设置应可触发，但 _patch_done 仍为 False。输出: {out}"
