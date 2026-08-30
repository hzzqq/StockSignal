"""
tests/test_sort_key_robust.py
=============================
回归：页面排序 key 不得对结果字典直接下标，避免任一条缺字段即 KeyError 崩整页。

背景（真实脆弱点）：
- pages/31_形态选股.py: results.sort(key=lambda r: r["技术评分"]) —— 形态扫描结果任一条
  缺 "技术评分" 字段（异常/部分输出）即 KeyError，整页崩溃。
- pages/34_体检扫描.py: _sort_key 用 r["priority"] / r["code"] 直接下标 —— 同样风险。

修复：统一改用 .get(字段, 默认值)，缺字段时按最低优先级/空 code 处理而非崩溃。
本测试为源码级防回退 + 行为级断言（复刻排序键逻辑验证缺字段不崩）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _extract_block(src: str, func_name: str) -> str:
    """粗略抽取 def func_name(...) 到下一个顶层 def/类 之前的源码块。"""
    m = re.search(rf"def {func_name}\(.*?\):", src)
    if not m:
        return ""
    start = m.start()
    # 找下一个顶层 def/类（同缩进 0）
    rest = src[m.end():]
    nxt = re.search(r"\n(?:def |class |@)", rest)
    end = m.end() + (nxt.start() if nxt else len(rest))
    return src[start:end]


class TestSortKeyUsesGetNotSubscript:
    def test_b_page_uses_get_for_score(self):
        src = (ROOT / "pages" / "31_形态选股.py").read_text(encoding="utf-8")
        assert 'r.get("技术评分", 0)' in src
        assert 'r["技术评分"]' not in src

    def test_i_page_sort_key_uses_get(self):
        src = (ROOT / "pages" / "34_体检扫描.py").read_text(encoding="utf-8")
        block = _extract_block(src, "_sort_key")
        assert block, "_sort_key 函数应存在"
        # 排序键函数体内必须用 .get 取 priority/code，不得裸下标
        assert "r.get(" in block
        assert 'r["priority"]' not in block
        assert 'r["code"]' not in block

    def test_i_sort_key_behavior_no_crash_on_missing_fields(self):
        # 复刻 I_体检扫描._sort_key 的修复后逻辑，验证缺字段不抛异常
        PRIORITY_RANK = {"高": 0, "中": 1, "低": 2}

        def sort_key(r):
            comp = r.get("composite")
            comp_rank = -comp if isinstance(comp, (int, float)) else 999
            return (PRIORITY_RANK.get(r.get("priority"), 9), comp_rank, r.get("code", ""))

        rows = [
            {"composite": 80},                       # 缺 priority / code
            {"priority": "高", "code": "600519", "composite": 90},
            {"priority": "低"},                       # 缺 composite / code
        ]
        # 不应抛 KeyError
        ranked = sorted(rows, key=sort_key)
        assert ranked[0]["code"] == "600519"        # 高优先级且含 code 排最前
        # 缺字段的行也能参与排序而不崩
        assert len(ranked) == 3
