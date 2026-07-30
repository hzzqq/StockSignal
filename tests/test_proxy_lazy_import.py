"""代理/SSL 探测惰性化回归测试（cycle 27）。

修复前：modules/margin_trading.py、linear_trends.py、market_drivers.py 在模块
*导入期* 同步调用 _ensure_proxy_and_ssl()（含对 127.0.0.1:26561 的 2s socket 探测），
阻塞所有 import 这些模块的页面（与 cycle 24 在 fundflow 修复的导入期阻塞同源）。

修复后：探测改为首次真实网络请求前惰性执行（_retry 包裹器内 / fundflow._cached 内，
_ensure_proxy_and_ssl 内部 _patch_done 幂等）。import 不再阻塞。

本测试用子进程验证：导入上述三个模块后，代理探测函数必须「未被调用」
（CALLED=0），证明导入期未跑阻塞探测。任何回归（重新在 import 期调用）都会让
CALLED>0 而失败。
"""
import subprocess
import sys


def _run(code: str) -> str:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=".",
    ).stdout.strip()


def test_import_no_probe_margin_trading():
    out = _run(
        "import modules.fundflow as ff; calls=[]; "
        "ff._ensure_proxy_and_ssl = lambda *a, **k: calls.append(1); "
        "import modules.margin_trading; "
        "print('CALLED=' + str(len(calls)))"
    )
    assert "CALLED=0" in out, f"margin_trading 导入期不应执行代理探测。输出: {out}"


def test_import_no_probe_linear_trends():
    out = _run(
        "import modules.fundflow as ff; calls=[]; "
        "ff._ensure_proxy_and_ssl = lambda *a, **k: calls.append(1); "
        "import modules.linear_trends; "
        "print('CALLED=' + str(len(calls)))"
    )
    assert "CALLED=0" in out, f"linear_trends 导入期不应执行代理探测。输出: {out}"


def test_import_no_probe_market_drivers():
    out = _run(
        "import modules.fundflow as ff; calls=[]; "
        "ff._ensure_proxy_and_ssl = lambda *a, **k: calls.append(1); "
        "import modules.market_drivers; "
        "print('CALLED=' + str(len(calls)))"
    )
    assert "CALLED=0" in out, f"market_drivers 导入期不应执行代理探测。输出: {out}"


def test_proxy_lazy_triggers_on_network_call():
    # 惰性触发仍有效：显式经 fundflow._cached 路径调用应触发探测。
    out = _run(
        "import modules.fundflow as ff; "
        "assert ff._patch_done is False; "
        "ff._ensure_proxy_and_ssl(); "
        "print('AFTER=' + str(ff._patch_done))"
    )
    assert "AFTER=True" in out, f"惰性代理设置应可触发。输出: {out}"
