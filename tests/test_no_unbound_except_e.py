"""回归护栏：禁止 as-e 转换器陷阱（except X:  # ... as e: 注释掉导致 e 未绑定）。

2026-08-27 曾出现 10 处 ``except Exception:  # noqa: BLE001 as e:`` 把 ``as e:`` 写进注释，
真实异常触发时抛 ``NameError``（且被 fetch_parallel 外层误判为整批超时）。

本测试扫描全仓源码，发现同类「except 后注释里残留 `as e:`」模式即失败，
防止该 bug 类复发。与此配套的运行时修复见 commit ee74521 + tests/test_fetch_parallel.py。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

# 仅匹配真正的 except 语句（行首，忽略前导空白），避免误伤文档字符串/注释中的示例文本。
# 命中意味着 `as e:` 落在注释内（未真正绑定 name）。
PATTERN = re.compile(r"^\s*except\s+\w+\s*:\s*#.*\bas\s+\w+\s*:")

EXCLUDE_DIRS = {"__pycache__", ".git", "venv", "node_modules", ".workbuddy"}


def _iter_py():
    for p in ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


def test_no_commented_as_e_in_except():
    violations = []
    for p in _iter_py():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                violations.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not violations, (
        "发现 as-e 转换器陷阱（except 注释内残留 `as e:`，e 未绑定）：\n"
        + "\n".join(violations)
    )
