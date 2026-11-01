# -*- coding: utf-8 -*-
"""事件因子链路「无合成/假数据」不变量护栏。

锁死差异化主线「去除 P4 合成演示依赖」：modules.event_factor（适配器入口）与
modules.signal.event_score（事件得分：P1 EV 优先 → 本地事件库/实时新闻回退）不得
出现任何合成/随机数据生成——取不到真实信号就可用 available=False / 空池 / 真实新闻回退，
绝不 np.random / randint / fake 造数。

只扫描 AST **代码节点**（Name/Attribute/Call），**不**扫 docstring / 字符串常量，
避免「而非合成演示数据」这类文档文字误伤。回归脚本若有人在事件链路里重新引入
random/synthetic 造数，本测试会红。
"""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 事件因子主链路的两个文件（含「P4 合成演示」历史的那条）
TARGETS = [
    os.path.join(ROOT, "modules", "event_factor.py"),
    os.path.join(ROOT, "modules", "signal.py"),
]

# 事件因子链路相关的另外两个文件：信号×广度对照（modules/event_compare.py）
# 与离线快照刷新脚本（scripts/refresh_event_pool.py）。它们同样不得引入合成/
# 随机造数——前者直接复用 shepherd_ladder.load_event_pool 渲染事件池，后者负责
# 把 P1 实时因子刷新进离线快照，任一环节重新引入 random/synthetic 都会污染事件真值。
# 纳入同一不变量护栏（复用同一个 _scan 扫描辅助函数，不再造逻辑）。
EXTENDED_TARGETS = [
    os.path.join(ROOT, "modules", "event_compare.py"),
    os.path.join(ROOT, "scripts", "refresh_event_pool.py"),
    os.path.join(ROOT, "modules", "event_announcements.py"),
]

# 禁止在事件链路代码里出现的「造数」调用名（仅代码节点，非文档）
FORBIDDEN_CALLS = {
    "randint", "random", "uniform", "rand", "gen_event", "fake_event",
    "synthetic", "make_fake", "gen_synthetic", "mock_event",
}
# 禁止的属性链末端（如 np.random）
FORBIDDEN_ATTR = {"random"}


def _dotted(node):
    """把 Call/Attribute 还原成 dotted 名（用于匹配 np.random 之类）。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _scan(path):
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = _dotted(n.func) if isinstance(n.func, (ast.Attribute, ast.Name)) else ""
            last = fn.split(".")[-1]
            if last in FORBIDDEN_CALLS:
                bad.append(f"Call {fn} @line {n.lineno}")
            # np.random / xxx.random 这类属性调用
            if isinstance(n.func, ast.Attribute) and n.func.attr in FORBIDDEN_ATTR:
                bad.append(f"Call .{n.func.attr} @line {n.lineno}")
        elif isinstance(n, ast.Attribute):
            if n.attr in FORBIDDEN_ATTR:
                bad.append(f"Attr .{n.attr} @line {n.lineno}")
    return bad


@pytest.mark.parametrize("path", TARGETS, ids=lambda p: os.path.basename(p))
def test_no_synthetic_generation(path):
    bad = _scan(path)
    assert not bad, (
        f"{os.path.basename(path)} 发现疑似合成/随机造数调用"
        f"（违反「事件链路无合成演示依赖」不变量）：\n" + "\n".join(bad)
    )


@pytest.mark.parametrize("path", EXTENDED_TARGETS, ids=lambda p: os.path.basename(p))
def test_no_synthetic_generation_extended(path):
    """事件因子链路外延文件（对照 / 刷新脚本）同样禁止合成造数。

    复用同一个 _scan 扫描辅助函数，仅扩展扫描目标，不重复造逻辑。
    """
    bad = _scan(path)
    assert not bad, (
        f"{os.path.basename(path)} 发现疑似合成/随机造数调用"
        f"（违反「事件链路无合成演示依赖」不变量）：\n" + "\n".join(bad)
    )
