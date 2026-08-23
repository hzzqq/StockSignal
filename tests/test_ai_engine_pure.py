"""
tests/test_ai_engine_pure.py — modules/ai_engine.py 纯函数单元测试

目标：锁住 AI 回答引擎的「安全/解析/快速通道」关键逻辑，防止后续改动悄悄破坏：
- _safe_eval 安全求值：正常四则、负数、括号；拒绝属性访问/调用/命名等沙箱逃逸
- _extract_codes_or_names：6 位代码、中文名、并列结构拆分
- _quick_answer：问候、自我介绍、简单算术命中
- _resolve_stock：mock fetcher 解析代码/名称

全程离线：_resolve_stock 用 monkeypatch 替换 StockFetcher 实例。
"""
import pytest

from modules import ai_engine


# ─────────────────────────────────────────────────────────────
#  _safe_eval 安全沙箱
# ─────────────────────────────────────────────────────────────
def test_safe_eval_basic_arithmetic():
    assert ai_engine._safe_eval("1 + 1") == 2.0
    assert ai_engine._safe_eval("2 * (3 + 4)") == 14.0
    assert ai_engine._safe_eval("10 / 4") == 2.5
    assert ai_engine._safe_eval("2**3") is None  # 幂运算不在白名单 → None
    assert ai_engine._safe_eval("1.5 + 2.5") == 4.0


def test_safe_eval_negative_and_unary():
    assert ai_engine._safe_eval("-5 + 3") == -2.0
    assert ai_engine._safe_eval("+(2 * 3)") == 6.0
    assert ai_engine._safe_eval("3 - -2") == 5.0  # 双负号


def test_safe_eval_rejects_sandbox_escape():
    # 经典属性访问逃逸 payload，必须被拒绝（返回 None 而非执行）
    assert ai_engine._safe_eval("(1).__class__.__subclasses__()") is None
    assert ai_engine._safe_eval("__import__('os')") is None
    # 函数调用 / 命名 / 下标等一切非白名单节点
    assert ai_engine._safe_eval("open('x')") is None
    assert ai_engine._safe_eval("a") is None
    assert ai_engine._safe_eval("x[0]") is None
    # 含字母（非数字/运算符）的非法字符
    assert ai_engine._safe_eval("1 + abc") is None


def test_safe_eval_rejects_bool_literal():
    # 布尔不是合法数字字面量
    assert ai_engine._safe_eval("True") is None


# ─────────────────────────────────────────────────────────────
#  _extract_codes_or_names
# ─────────────────────────────────────────────────────────────
def test_extract_codes():
    out = ai_engine._extract_codes_or_names("分析 600519 和 000001")
    assert "600519" in out
    assert "000001" in out


def test_extract_chinese_names():
    out = ai_engine._extract_codes_or_names("对比贵州茅台和五粮液")
    # 修复后：去前缀 + 收紧窗口，应能提取出精确名「贵州茅台」
    assert "贵州茅台" in out
    assert "五粮液" in out


def test_extract_parallel_sep():
    # 「A 和 B 哪个更好」并列结构应精确拆出两个名字
    out = ai_engine._extract_codes_or_names("贵州茅台和五粮液哪个更值得买")
    assert "贵州茅台" in out
    assert "五粮液" in out


def test_extract_strips_prefix():
    # 句首动词前缀应被剥离，避免贪婪误吞（「对比贵州茅台」→「贵州茅台」）
    out = ai_engine._extract_codes_or_names("对比贵州茅台怎么样")
    assert "贵州茅台" in out
    assert "对比贵州茅" not in out


def test_extract_dedup_preserves_order():
    out = ai_engine._extract_codes_or_names("600519 600519 茅台")
    # 去重后仍包含两者
    assert out.count("600519") == 1
    assert "茅台" in out


# ─────────────────────────────────────────────────────────────
#  _quick_answer 快速通道
# ─────────────────────────────────────────────────────────────
def test_quick_answer_greeting():
    assert "星辰" in (ai_engine._quick_answer("你好") or "")
    assert ai_engine._quick_answer("hello") is not None
    assert ai_engine._quick_answer("在吗") is not None


def test_quick_answer_self_intro():
    ans = ai_engine._quick_answer("你是谁")
    assert ans is not None and "星辰" in ans


def test_quick_answer_math_eq():
    ans = ai_engine._quick_answer("1 + 1 = ?")
    assert ans is not None and "2" in ans


def test_quick_answer_unknown_returns_none():
    assert ai_engine._quick_answer("请帮我预测明天涨停的股票") is None


# ─────────────────────────────────────────────────────────────
#  _resolve_stock（mock fetcher 离线）
# ─────────────────────────────────────────────────────────────
class _FakeFetcher:
    def get_stock_basic(self, code):
        return None, {"600519": "贵州茅台"}.get(code, code)

    def search_stocks(self, query, limit=5):
        if query == "茅台":
            return [{"code": "600519", "name": "贵州茅台"}]
        return []


def test_resolve_stock_by_code(monkeypatch):
    monkeypatch.setattr(ai_engine, "StockFetcher", lambda: _FakeFetcher())
    r = ai_engine._resolve_stock("600519")
    assert r == {"code": "600519", "name": "贵州茅台"}


def test_resolve_stock_by_name(monkeypatch):
    monkeypatch.setattr(ai_engine, "StockFetcher", lambda: _FakeFetcher())
    r = ai_engine._resolve_stock("茅台")
    assert r == {"code": "600519", "name": "贵州茅台"}


def test_resolve_stock_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(ai_engine, "StockFetcher", lambda: _FakeFetcher())
    # 既非代码也搜不到 → None
    assert ai_engine._resolve_stock("不存在的标的xyz") is None
