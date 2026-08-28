"""tests/test_updown_color_semantics.py

锁死 A股「红涨绿跌」配色语义。

项目铁律：A 股与欧美相反——**涨用红、跌用绿**。
``modules/colors.py`` 中 ``UP_COLOR``（红 #ff4d4f）代表涨/非负，
``DOWN_COLOR``（绿 #00d486）代表跌/负。

这类 bug 不会崩溃、不会报错，只会让**K线/柱状图颜色整体反过来**，
在有大量条件表达式的代码里极难靠 review 肉眼发现，因此用 AST 静态锁定：

对任何涉及 UP_COLOR / DOWN_COLOR 的三元表达式：
- ``UP_COLOR if v >= 0 else DOWN_COLOR``   ✅（非负 → 涨色）
- ``DOWN_COLOR if v < 0 else UP_COLOR``    ✅（负 → 跌色）
- ``UP_COLOR if v < 0 else DOWN_COLOR``    ❌ 语义反了
- ``DOWN_COLOR if v > 0 else UP_COLOR``    ❌ 语义反了

判定规则：三元表达式的**真值分支**若包含 UP_COLOR，其条件必须是
``>`` / ``>=``（正向比较）；真值分支若包含 DOWN_COLOR，条件必须是
``<`` / ``<=``（负向比较）。无法静态判定的条件（如函数调用）跳过，
避免误报。

2026-08-28 新增（Cycle 68）。
"""
import ast
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UP = "UP_COLOR"
DOWN = "DOWN_COLOR"
POS_OPS = ("Gt", "GtE")   # >  >=
NEG_OPS = ("Lt", "LtE")   # <  <=


def _subtree_names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _compare_op(test):
    if isinstance(test, ast.Compare) and test.ops:
        return type(test.ops[0]).__name__
    return None


def _iter_py():
    for path in sorted(glob.glob(os.path.join(ROOT, "pages", "**", "*.py"), recursive=True)
                       + glob.glob(os.path.join(ROOT, "modules", "**", "*.py"), recursive=True)):
        yield path


def test_updown_ternary_semantics():
    bad = []
    checked = 0
    for path in _iter_py():
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.IfExp):
                continue
            body_names = _subtree_names(node.body)
            orelse_names = _subtree_names(node.orelse)
            if not ({UP, DOWN} & (body_names | orelse_names)):
                continue
            op = _compare_op(node.test)
            # 只在能明确判定正负号方向时校验。Eq / NotEq / Is / In 以及函数调用等
            # 条件（如 `UP_COLOR if et == "利好" else DOWN_COLOR`）语义上完全正确，
            # 但无法静态判断正负，一律跳过，避免误报。
            if op not in POS_OPS and op not in NEG_OPS:
                continue
            checked += 1
            # 明确矛盾：涨色配了负向比较，或跌色配了正向比较
            if UP in body_names and op in NEG_OPS:
                bad.append((rel, node.lineno,
                            f"真值分支是 {UP}（涨/红）但条件是 {op}（负向）—— 语义反了"))
            if DOWN in body_names and op in POS_OPS:
                bad.append((rel, node.lineno,
                            f"真值分支是 {DOWN}（跌/绿）但条件是 {op}（正向）—— 语义反了"))

    assert checked >= 1, "未扫描到任何 UP/DOWN 三元表达式，疑似路径或解析有误"
    assert not bad, (
        "发现「红涨绿跌」语义反了的配色表达式:\n"
        + "\n".join(f"  {r}:{ln} {why}" for r, ln, why in bad)
    )
