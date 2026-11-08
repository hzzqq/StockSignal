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

反自静音（2026-11-09）：第 3 项检查曾是对全文做 `in s` 子串包含，
把修复代码删掉、只在 rem/echo 注释里留同样文字就能喂饱守卫。现在只检查可执行行，
并新增反例测试证明「纯注释样本必然被判缺失」。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP = ('node_modules', '.venv', 'site-packages', '__pycache__')


def _bats():
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        if any(s in dirpath.replace('\\', '/') for s in _SKIP):
            continue
        for fn in filenames:
            if fn.lower().endswith('.bat'):
                yield os.path.join(dirpath, fn)


def _executable_lines(b: bytes) -> str:
    """只保留可执行行：剥离 rem / :: / 纯输出 echo。

    ⚠️ `echo %PID%|findstr /R "[^0-9]"` 这类**带管道**的 echo 是真实校验逻辑，
    不能当注释剥掉，否则守卫会自己把防回退修复藏起来。
    """
    out = []
    for line in b.decode('ascii').splitlines():
        t = line.strip()
        low = t.lower()
        if low.startswith(('rem ', 'rem\t', '::', '@echo')):
            continue
        if low.startswith(('echo ', 'echo.', 'echo\t')) and '|' not in t and '&' not in t:
            continue
        out.append(t)
    return '\n'.join(out)


# (可执行行里必须出现的片段, 缺失说明)
_GUARDS = (
    ('if "%PID%"=="0" exit /b 0', 'PID 0 守卫（回归会再输出 Killing PID 0）'),
    ('findstr /R "[^0-9]"', '非数字 PID 守卫'),
    ('set "SEEN=%SEEN%%PID%,"', 'PID 去重写入'),
    ('findstr /C:",%PID%,"', 'PID 去重查找'),
    ('taskkill /f /t /pid %PID%', '按端口定位到的 PID 精确 kill'),
)


def _missing_guards(code: str) -> list[str]:
    return [label for token, label in _GUARDS if token not in code]


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
    """_stop_services.bat：纯 ASCII + 可执行行里真实保留三项防回退修复。"""
    p = os.path.join(ROOT, '_stop_services.bat')
    assert os.path.exists(p), "缺少 _stop_services.bat"
    with open(p, 'rb') as f:
        b = f.read()
    b.decode('ascii')                                    # 断言纯 ASCII
    code = _executable_lines(b)
    assert len(code.splitlines()) >= 10, "可执行行过少，过滤逻辑疑似把真实逻辑也剥掉了"
    assert not _missing_guards(code), (
        "可执行行里缺少防回退修复（注释里写了不算）：\n  " + "\n  ".join(_missing_guards(code))
    )
    assert 'taskkill /f /im python' not in code, "不得无差别杀 python.exe（会误杀量化软件）"
    # 运维红线：8899 是老板保留端口，从来不是 StockSignal 监听端口
    # （真实启动器一律选空闲端口并记录到 active_ports*.json）。停止脚本不得
    # 有任何硬编码的 8899 杀端口目标，且必须保留 8899 红线守卫（跳过而非误杀）。
    raw = b.decode('ascii')
    assert 'set "FRONTEND_PORT=8899"' not in raw, "不得把 8899 当默认杀端口（会误杀老板的服务）"
    assert 'call :kill_port 8899' not in code, "不得直接杀 8899"
    assert 'call :maybe_kill 8899' not in code, "不得直接杀 8899"
    assert '"8899"' in code, "必须保留 8899 红线守卫（跳过而非误杀）"
    # 杀端口目标必须全部来自状态文件（变量），不得出现任何写死的数字端口
    for line in code.splitlines():
        if re.match(r'\s*call :(?:kill_port|maybe_kill)\b', line):
            assert re.search(r'%\w+%', line), \
                f"杀端口调用必须传状态文件变量而非写死端口: {line}"
            assert not re.search(r'call :(?:kill_port|maybe_kill)\s+\d{2,5}', line), \
                f"不得写死数字端口: {line}"
            assert not re.search(r'"\d{2,5}"', line), \
                f"不得用引号写死数字端口: {line}"


def test_guards_cannot_be_fed_by_comments():
    """反例：只在 rem/::/echo 注释里写修复片段，守卫必须全部判缺失。"""
    fake = b'\r\n'.join([
        b'@echo off',
        b'rem if "%PID%"=="0" exit /b 0',
        b'echo findstr /R "[^0-9]"',
        b':: set "SEEN=%SEEN%%PID%,"',
        b'echo findstr /C:",%PID%,"',
        b'echo taskkill /f /t /pid %PID%',
    ])
    code = _executable_lines(fake)
    assert len(_missing_guards(code)) == len(_GUARDS), (
        "纯注释就能喂饱守卫，说明可执行行过滤失效"
    )


def test_echo_pipeline_lines_are_real_logic():
    """带管道的 echo 不是注释：防「过滤一刀切」把真实校验逻辑藏起来。"""
    sample = (
        b'echo     Killing PID %PID%\r\n'
        b'echo %PID%|findstr /R "[^0-9]" >nul 2>&1\r\n'
        b'echo %SEEN%|findstr /C:",%PID%," >nul 2>&1\r\n'
    )
    code = _executable_lines(sample)
    assert 'Killing PID %PID%' not in code, "纯输出 echo 应被剥离"
    assert 'findstr /R "[^0-9]"' in code, "带管道的校验逻辑不得被剥离"
    assert 'findstr /C:",%PID%,"' in code, "带管道的去重逻辑不得被剥离"
