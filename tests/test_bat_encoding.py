# -*- coding: utf-8 -*-
"""Windows .bat 脚本编码 / 换行不变量守卫。

背景（真实故障，2026-09-14）：`_stop_services.bat` 存为 **UTF-8(无 BOM)** 却内含中文，
脚本里又 `chcp 936` 让 cmd 按 GBK 解析字节 → 中文乱码；更致命的是 UTF-8 多字节序列
在 GBK 下会产生 DBCS 前导字节、**吞掉后一个 ASCII 字符**，导致命令解析错位 ——
一行 `echo` 被当成命令去执行，报「不是内部或外部命令，也不是可运行的程序或批处理文件」。

不变量：
1. 含非 ASCII 字节的 .bat 不得是 UTF-8（cmd 按本地代码页读整份文件）。
   允许：纯 ASCII（任何代码页都安全）；或 GBK/ANSI（配 chcp 936，同 启动StockSignal.bat）。
2. .bat 必须 CRLF 换行（LF-only 在 cmd 下行为不稳）。
3. `_stop_services.bat` 保持纯 ASCII，并保留三项防回退修复（PID 0 / 非数字 / 去重）。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP = ('node_modules', '.venv', 'site-packages', '__pycache__')


def _bats():
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        if any(s in dirpath.replace('\\', '/') for s in _SKIP):
            continue
        for fn in filenames:
            if fn.lower().endswith('.bat'):
                yield os.path.join(dirpath, fn)


def test_no_bat_is_utf8_with_nonascii():
    """含非 ASCII 的 .bat 不得是 UTF-8 编码（否则 cmd 按代码页解析必乱码/错位执行）。"""
    bad = []
    for p in _bats():
        with open(p, 'rb') as f:
            b = f.read()
        try:
            b.decode('ascii')
            continue           # 纯 ASCII：任何代码页都安全
        except UnicodeDecodeError:
            pass
        try:
            b.decode('utf-8')
        except UnicodeDecodeError:
            continue           # 非 UTF-8（GBK/ANSI）：与脚本内 chcp 936 匹配，可用
        bad.append(os.path.relpath(p, ROOT))
    assert not bad, (
        "以下 .bat 是 UTF-8 且含非 ASCII：cmd 按本地代码页解析会乱码并可能错位执行。"
        "请改为纯 ASCII 或存为 GBK/ANSI：\n  " + "\n  ".join(bad)
    )


def test_bats_use_crlf():
    """.bat 必须 CRLF；裸 LF 在 cmd 下解析行为不稳。"""
    bad = []
    for p in _bats():
        with open(p, 'rb') as f:
            b = f.read()
        if b'\n' in b.replace(b'\r\n', b''):
            bad.append(os.path.relpath(p, ROOT))
    assert not bad, "以下 .bat 含裸 LF（应统一 CRLF）：\n  " + "\n  ".join(bad)


def test_stop_services_bat_ascii_and_antifootgun_guards():
    """_stop_services.bat：纯 ASCII + 精确按端口 kill + 三项防回退修复。"""
    p = os.path.join(ROOT, '_stop_services.bat')
    assert os.path.exists(p), "缺少 _stop_services.bat"
    with open(p, 'rb') as f:
        b = f.read()
    b.decode('ascii')                                    # 断言纯 ASCII
    s = b.decode('ascii')
    assert 'if "%PID%"=="0" exit /b 0' in s, "缺少 PID 0 守卫（回归会再输出 Killing PID 0）"
    assert 'findstr /R "[^0-9]"' in s, "缺少非数字 PID 守卫"
    assert 'set "SEEN=%SEEN%%PID%,"' in s and 'findstr /C:",%PID%,"' in s, \
        "缺少 PID 去重（netstat 的 IPv4+IPv6 两行指向同一 PID，会重复 kill）"
    assert 'taskkill /f /t /pid %PID%' in s, "应按端口定位到的 PID 精确 kill"
    assert 'taskkill /f /im python' not in s, "不得无差别杀 python.exe（会误杀量化软件）"
