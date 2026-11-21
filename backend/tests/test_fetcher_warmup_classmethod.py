"""守卫测试：StockFetcher._warmup_stock_db 必须是 @classmethod 且失败不得永久标记成功。

缺陷背景：
- modules/fetcher_base.py 原 ``def _warmup_stock_db(cls):`` 缺 @classmethod 装饰器，
  被实例调用（fetcher_base.py __init__ / fetcher_search.py get_all_codes 等）时
  ``cls`` 实为实例，``cls.__new__(cls)`` 抛 TypeError；
- 异常在 except 分支被吞且 ``_stocks_loaded=True`` 永久标记 → get_all_codes() 恒返 []。

守卫内容：
1. AST 断言 _warmup_stock_db 带 @classmethod 装饰器；
2. monkeypatch 样例：实例调用路径（get_all_codes）不再因 TypeError 返空；
3. 失败语义：预热失败后 _stocks_loaded 不立即置 True（允许下次重试），
   连续失败达上限才停止重试。
"""
import ast
import os

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FETCHER_BASE = os.path.join(REPO_ROOT, "modules", "fetcher_base.py")


def _load_warmup_node():
    with open(FETCHER_BASE, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_warmup_stock_db":
            return node
    raise AssertionError("modules/fetcher_base.py 中未找到 _warmup_stock_db 定义")


def test_warmup_stock_db_is_classmethod():
    node = _load_warmup_node()
    decorators = [
        d.id if isinstance(d, ast.Name) else getattr(d, "attr", None)
        for d in node.decorator_list
    ]
    assert "classmethod" in decorators, (
        "_warmup_stock_db 缺少 @classmethod 装饰器：实例调用时 cls 为实例，"
        "cls.__new__(cls) 会抛 TypeError 并被吞，get_all_codes() 恒返 []"
    )


@pytest.fixture
def restore_warmup_state():
    """保存/恢复类级预热状态，避免用例间与既有测试串扰。"""
    from modules.fetcher import StockFetcher

    saved = (
        StockFetcher._stocks_loaded,
        StockFetcher._warmup_failures,
        StockFetcher._stock_df,
        dict(StockFetcher._name_to_code),
        dict(StockFetcher._code_to_name),
    )
    StockFetcher._stocks_loaded = False
    StockFetcher._warmup_failures = 0
    yield StockFetcher
    (
        StockFetcher._stocks_loaded,
        StockFetcher._warmup_failures,
        StockFetcher._stock_df,
        StockFetcher._name_to_code,
        StockFetcher._code_to_name,
    ) = saved


def test_get_all_codes_not_empty_after_instance_warmup(monkeypatch, tmp_path, restore_warmup_state):
    """实例调用路径：__init__ 内 self._warmup_stock_db() 预热成功后 get_all_codes 非空。

    修复前：cls 为实例 → cls.__new__(cls) TypeError → 被吞且永久标记 → 恒返 []。
    """
    sf = restore_warmup_state
    monkeypatch.setattr("modules.fetcher_base.load_config", lambda *a, **k: {"database": {"path": str(tmp_path / "t.db")}})
    monkeypatch.setattr("modules.fetcher_base._resolve_cache_db_path", lambda p: p)

    tiny = pd.DataFrame({"code": ["600000", "000001"], "name": ["浦发银行", "平安银行"]})
    monkeypatch.setattr(sf, "_ensure_stock_db", lambda self: tiny)
    # 拼音缓存纯函数替换，避免依赖 pypinyin 词库
    monkeypatch.setattr(sf, "_pinyin_static", staticmethod(lambda name: "A"))
    monkeypatch.setattr(sf, "_pinyin_initials_variants", staticmethod(lambda name: {"A"}))

    from modules.fetcher import StockFetcher as SF

    inst = object.__new__(SF)  # 绕过 __init__，直接模拟实例方法调用路径
    inst._warmup_stock_db()
    assert SF._stock_df is not None and not SF._stock_df.empty

    # get_all_codes（SearchMixin，实例调用 self._warmup_stock_db()）不应返 []
    codes = inst.get_all_codes()
    assert codes == ["600000", "000001"]


def test_warmup_failure_does_not_permanently_mark_loaded(monkeypatch, tmp_path, restore_warmup_state):
    """预热失败：首次失败不置 _stocks_loaded=True（允许下次重试）；
    连续失败达 _MAX_WARMUP_FAILURES 上限才停止重试。"""
    sf = restore_warmup_state
    monkeypatch.setattr("modules.fetcher_base.load_config", lambda *a, **k: {"database": {"path": str(tmp_path / "t.db")}})
    monkeypatch.setattr("modules.fetcher_base._resolve_cache_db_path", lambda p: p)

    def _boom(self):
        raise RuntimeError("预热失败样例")

    monkeypatch.setattr(sf, "_ensure_stock_db", _boom)

    from modules.fetcher import StockFetcher as SF

    inst = object.__new__(SF)
    for i in range(1, SF._MAX_WARMUP_FAILURES):
        inst._warmup_stock_db()
        assert SF._stocks_loaded is False, f"第 {i} 次失败后不应永久标记成功（应允许下次重试）"

    inst._warmup_stock_db()
    assert SF._stocks_loaded is True, "连续失败达上限后应停止重试（避免每次实例化都打网络）"
