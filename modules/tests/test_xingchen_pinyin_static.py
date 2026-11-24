"""守卫测试：星辰 AI 股票名解析链路的拼音方法必须是 @staticmethod。

缺陷背景：
- ``modules/fetcher_base.py::ReferenceMixin`` 里的 ``_pinyin_full`` /
  ``_pinyin_initials``（以及同族的 ``_pinyin_static`` /
  ``_pinyin_initials_variants`` / ``_name_tokens``）签名只有 ``name``，没有 ``self``；
- 但 ``modules/fetcher_search.py`` 全部走实例调用 ``self._xxx(name)``，
  Python 会把实例绑定成第一个参数 → 稳定 TypeError
  ``ReferenceMixin._xxx() takes 1 positional argument but 2 were given``；
- 该异常被 ``modules/ai_engine.py::_resolve_stock`` 的 try/except 吞掉并返回 None，
  导致「通富微电」等中文股票名在星辰 AI 后端解析不出代码，答非所问。

守卫内容：
1. AST 断言上述方法都带 @staticmethod（类调用与实例调用同时兼容）；
2. 实例调用 / 类调用两条路径都能正常得到拼音；
3. 端到端：``search_stocks('通富微电', limit=5)`` 与 ``_resolve_stock('通富微电')``
   解析出真实代码 002156。

测试数据说明（诚实红线）：
根 conftest 会把 SS_DATA_DIR 指向 session 临时目录，pytest 内股票池为空且网络被屏蔽，
故用最小 DataFrame 注入真实股票池中的真实行（002156/通富微电，已在真实本地股票池
5191 行中核实存在），只替换数据源、不替换任何解析逻辑；不编造通过、不伪造解析结果。
"""
import ast
import os

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FETCHER_BASE = os.path.join(REPO_ROOT, "modules", "fetcher_base.py")

#: 签名只收 name、没有 self 的全部方法（漏一个，search_stocks 仍会在后续层级抛 TypeError）
NO_SELF_METHODS = (
    "_pinyin_static",
    "_pinyin_initials_variants",
    "_pinyin_full",
    "_pinyin_initials",
    "_name_tokens",
)

REAL_CODE = "002156"
REAL_NAME = "通富微电"

#: 来自真实股票池的行（+两只在池内的真实票，确保 search_stocks 会遍历到非命中分支）
REAL_POOL_ROWS = [
    (REAL_CODE, REAL_NAME),
    ("600519", "贵州茅台"),
    ("000001", "平安银行"),
]


def _reference_mixin_nodes():
    with open(FETCHER_BASE, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ReferenceMixin":
            return node
    raise AssertionError("modules/fetcher_base.py 中未找到 ReferenceMixin")


@pytest.fixture
def real_pool(monkeypatch):
    """注入真实股票池的 3 行，绕开 pytest 的 SS_DATA_DIR 隔离与网络屏蔽。"""
    from modules.fetcher import StockFetcher

    tiny = pd.DataFrame(REAL_POOL_ROWS, columns=["code", "name"])
    monkeypatch.setattr(StockFetcher, "_ensure_stock_db", lambda self: tiny)
    return tiny


@pytest.mark.parametrize("method_name", NO_SELF_METHODS)
def test_no_self_methods_are_staticmethod(method_name):
    """AST 守卫：没有 self 形参的方法必须显式加 @staticmethod。"""
    cls = _reference_mixin_nodes()
    node = next(
        (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name),
        None,
    )
    assert node is not None, f"ReferenceMixin 缺少 {method_name} 定义"
    decorators = [
        d.id if isinstance(d, ast.Name) else getattr(d, "attr", None)
        for d in node.decorator_list
    ]
    assert "staticmethod" in decorators, (
        f"ReferenceMixin.{method_name} 缺少 @staticmethod：实例调用 self.{method_name}(name) "
        "会把实例绑定成第一个参数，抛 'takes 1 positional argument but 2 were given'"
    )


def test_pinyin_methods_callable_both_ways():
    """实例调用与类调用都必须正常（staticmethod 不绑定 self）。"""
    from modules.fetcher import StockFetcher

    inst = StockFetcher()
    for method_name in ("_pinyin_full", "_pinyin_initials"):
        via_instance = getattr(inst, method_name)(REAL_NAME)
        via_class = getattr(StockFetcher, method_name)(REAL_NAME)
        assert via_instance == via_class, f"{method_name}: 实例调用与类调用结果应一致"


def test_search_stocks_resolves_tongfuweidian(real_pool):
    """search_stocks('通富微电', limit=5) 必须解析出真实代码 002156。"""
    from modules.fetcher import StockFetcher

    results = StockFetcher().search_stocks(REAL_NAME, limit=5)
    assert isinstance(results, list) and results, "股票池含通富微电，搜索不应为空"
    assert any(str(r.get("code")) == REAL_CODE for r in results), (
        f"search_stocks('{REAL_NAME}') 未解析出 {REAL_CODE}：实际 {results}"
    )


def test_ai_engine_resolve_stock_resolves_tongfuweidian(real_pool):
    """星辰 AI 的 _resolve_stock 必须拿到 002156（此前 TypeError 被吞成 None）。"""
    from modules.ai_engine import _resolve_stock

    resolved = _resolve_stock(REAL_NAME)
    assert resolved is not None, (
        f"_resolve_stock('{REAL_NAME}') 返回 None：解析异常很可能被 try/except 吞掉"
    )
    assert resolved.get("code") == REAL_CODE, (
        f"_resolve_stock('{REAL_NAME}') 代码错误：{resolved}"
    )
