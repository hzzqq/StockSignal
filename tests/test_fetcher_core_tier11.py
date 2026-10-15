"""Tier1.1 fetcher.py 安全拆分第二批守卫（T-247 续）。

锁定范式：纯函数真身迁 modules.fetcher_core，fetcher.py 仅 re-export /
staticmethod 绑定同一对象：
- _df_last_date / _proc_cache_get / _proc_cache_set：fetcher 与 fetcher_core 同一对象；
- _safe_ident：StockFetcher._safe_ident 与 fetcher_core._safe_ident 同一对象；
- _SAFE_IDENT_RE：类属性与 fetcher_core.SAFE_IDENT_RE 同一 re 对象（L2328 与外部测试直接引用）；
- fetcher.py 不得再本地 def 这四个名字（防拆分回潮）。
"""
import ast
import pathlib
import time

import pandas as pd

import modules.fetcher as fetcher
from modules import fetcher_core
from modules.fetcher import StockFetcher

ROOT = pathlib.Path(__file__).resolve().parents[1]

MIGRATED = ("_df_last_date", "_proc_cache_get", "_proc_cache_set", "_safe_ident")


# ── 身份一致（零行为变化的根基）──
def test_df_last_date_identity():
    assert fetcher._df_last_date is fetcher_core._df_last_date


def test_proc_cache_identity():
    assert StockFetcher._proc_cache_get is fetcher_core._proc_cache_get
    assert StockFetcher._proc_cache_set is fetcher_core._proc_cache_set


def test_safe_ident_identity():
    assert StockFetcher._safe_ident is fetcher_core._safe_ident
    # 经实例/类的调用形态兼容（原 classmethod 调用点零变化）
    assert StockFetcher._safe_ident("stock_daily") == "stock_daily"
    assert StockFetcher()._safe_ident("t_1") == "t_1"


def test_safe_ident_re_identity():
    # 类属性保留同一 re 对象（fetcher L2328 与 tests/test_sql_identifier_safety 直接引用）
    assert StockFetcher._SAFE_IDENT_RE is fetcher_core.SAFE_IDENT_RE


# ── 行为等价 ──
def test_df_last_date_behaviour():
    df = pd.DataFrame({"date": ["2026-10-01", "2026-10-13"], "close": [1.0, 2.0]})
    assert fetcher_core._df_last_date(df) == "2026-10-13"
    assert fetcher_core._df_last_date(pd.DataFrame({"close": [1.0]})) is None
    assert fetcher_core._df_last_date(None) is None
    assert fetcher_core._df_last_date(pd.DataFrame()) is None
    empty = pd.DataFrame({"date": pd.Series([], dtype="object")})
    assert fetcher_core._df_last_date(empty) is None


def test_proc_cache_ttl_behaviour():
    cache = {}
    fetcher_core._proc_cache_set(cache, "k", "v")
    assert fetcher_core._proc_cache_get(cache, "k", ttl_seconds=10) == "v"
    # 人工回拨时间戳 → 过期清除
    cache["k"] = (time.monotonic() - 100, "old")
    assert fetcher_core._proc_cache_get(cache, "k", ttl_seconds=10) is None
    assert "k" not in cache  # 过期即清除
    assert fetcher_core._proc_cache_get({}, "nope", 10) is None


def test_safe_ident_rejects_injection():
    for bad in ("a;drop", "a b", 'a"b', "a--b", "a-b", "", "1abc", None, 123):
        try:
            fetcher_core._safe_ident(bad)
            raise AssertionError(f"应拒绝: {bad!r}")
        except ValueError:
            pass
    assert fetcher_core._safe_ident("stock_daily") == "stock_daily"


# ── AST 守卫：fetcher.py 不得再本地定义（防回潮）──
def test_fetcher_no_local_defs_of_migrated():
    tree = ast.parse((ROOT / "modules/fetcher.py").read_text(encoding="utf-8"))
    local = [n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name in MIGRATED]
    assert not local, f"fetcher.py 仍本地定义已迁函数: {local}，应只 re-export"


def test_fetcher_core_defines_all():
    src = (ROOT / "modules/fetcher_core/__init__.py").read_text(encoding="utf-8")
    for name in MIGRATED:
        assert f"def {name}" in src, f"fetcher_core 缺少 {name} 真身"
    assert "SAFE_IDENT_RE = re.compile" in src, "SAFE_IDENT_RE 真身缺失"
    fsrc = (ROOT / "modules/fetcher.py").read_text(encoding="utf-8")
    assert "from modules.fetcher_core import" in fsrc, "fetcher.py re-export 缺失"