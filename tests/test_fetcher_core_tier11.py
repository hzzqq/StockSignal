"""Tier1.1 fetcher.py 安全拆分第二批守卫（T-247 续）。

锁定范式：纯函数真身迁 modules.fetcher_core，fetcher.py 仅 re-export /
staticmethod 绑定同一对象：
- _df_last_date / _proc_cache_get / _proc_cache_set：fetcher 与 fetcher_core 同一对象；
- _safe_ident：StockFetcher._safe_ident 与 fetcher_core._safe_ident 同一对象；
- _SAFE_IDENT_RE：类属性与 fetcher_core.SAFE_IDENT_RE 同一 re 对象（L2328 与外部测试直接引用）；
- fetcher.py 不得再本地 def 这四个名字（防拆分回潮）。
"""
import ast
import os
import pathlib
import time

import pandas as pd

import modules.fetcher as fetcher
from modules import fetcher_core
from modules.fetcher import StockFetcher

ROOT = pathlib.Path(__file__).resolve().parents[1]

MIGRATED = ("_df_last_date", "_proc_cache_get", "_proc_cache_set", "_safe_ident")
# Tier2 第一批：真身迁 fetcher_core（staticmethod 绑定 / industry_map 参数注入）
MIGRATED_T2 = ("_safe_kline_df", "_resample_kline", "_get_stock_industry_keywords")


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


# ── 第三批（T-247 续）：_resolve_cache_db_path / _get_sina_prefix ──

def test_resolve_cache_path_identity():
    assert fetcher._resolve_cache_db_path is fetcher_core._resolve_cache_db_path


def test_resolve_cache_path_no_env_falls_back(monkeypatch):
    monkeypatch.delenv("SS_DATA_DIR", raising=False)
    assert fetcher_core._resolve_cache_db_path(None) == "data/cache.db"
    assert fetcher_core._resolve_cache_db_path("custom/db.sqlite") == "custom/db.sqlite"
    assert fetcher_core._resolve_cache_db_path("D:/abs/db.sqlite") == "D:/abs/db.sqlite"


def test_resolve_cache_path_redirects_real_data_dir(monkeypatch, tmp_path):
    """核心语义：SS_DATA_DIR 下「相对 data/cache.db」必须重定向到临时目录。

    同时钉住 __file__ 层级：fetcher_core/__init__.py 为 dirname×3 到项目根，
    若迁移时层级写错（如 ×2 指到 modules/），真实 data/ 判定将基于错误根，
    本测试必红（重定向失效）。
    """
    env_dir = str(tmp_path / "ss_data")
    monkeypatch.setenv("SS_DATA_DIR", env_dir)
    # 相对默认路径 → 落项目根 data/ → 必须重定向
    assert fetcher_core._resolve_cache_db_path(None) == os.path.join(env_dir, "cache.db")
    assert fetcher_core._resolve_cache_db_path("data/cache.db") == os.path.join(env_dir, "cache.db")
    # 项目根绝对路径 data/ → 同样重定向
    root_abs = os.path.join(ROOT, "data", "cache.db")
    assert fetcher_core._resolve_cache_db_path(root_abs) == os.path.join(env_dir, "cache.db")


def test_resolve_cache_path_keeps_explicit_non_data(monkeypatch, tmp_path):
    """SS_DATA_DIR 下显式指向其他位置（tmp_path/绝对盘符）一律保留，不破坏测试控制。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path / "ss_data"))
    keep = str(tmp_path / "my.db")
    assert fetcher_core._resolve_cache_db_path(keep) == keep
    assert fetcher_core._resolve_cache_db_path("other/sub.db") == "other/sub.db"


def test_sina_prefix_identity_and_behaviour():
    # 行为零变化：fetcher 薄壳与真身同参等价（表为参数注入，类常量留 fetcher）
    f = StockFetcher.__new__(StockFetcher)  # 免 __init__（不触库）
    for ticker in ("000001", "399001", "600000", "688001", "510300",
                   "000751", "002594", "300750", "abc", ""):
        assert f._get_sina_prefix(ticker) == fetcher_core._get_sina_prefix(
            ticker, StockFetcher._INDEX_SINA_PREFIX), ticker
    # 语义抽查：指数表命中 / 沪段 / 深段
    assert fetcher_core._get_sina_prefix("000001", StockFetcher._INDEX_SINA_PREFIX) == "sh"
    assert fetcher_core._get_sina_prefix("399001", StockFetcher._INDEX_SINA_PREFIX) == "sz"
    assert fetcher_core._get_sina_prefix("600000", StockFetcher._INDEX_SINA_PREFIX) == "sh"
    assert fetcher_core._get_sina_prefix("688001", StockFetcher._INDEX_SINA_PREFIX) == "sh"
    assert fetcher_core._get_sina_prefix("510300", StockFetcher._INDEX_SINA_PREFIX) == "sh"
    assert fetcher_core._get_sina_prefix("000751", StockFetcher._INDEX_SINA_PREFIX) == "sz"
    assert fetcher_core._get_sina_prefix("300750", StockFetcher._INDEX_SINA_PREFIX) == "sz"
    assert fetcher_core._get_sina_prefix("abc", StockFetcher._INDEX_SINA_PREFIX) == "sz"


def test_fetcher_no_local_defs_of_batch3():
    tree = ast.parse((ROOT / "modules/fetcher.py").read_text(encoding="utf-8"))
    local = [n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_resolve_cache_db_path"]
    assert not local, "fetcher.py 仍本地定义 _resolve_cache_db_path，应只 re-export"


# ── Tier2 第一批（T-247 续）：_safe_kline_df / _resample_kline / _get_stock_industry_keywords ──

def test_t2_identity():
    assert StockFetcher._safe_kline_df is fetcher_core._safe_kline_df
    assert StockFetcher._resample_kline is fetcher_core._resample_kline
    # 薄壳（industry_map 参数注入）行为零变化：与真身同参等价
    f = StockFetcher.__new__(StockFetcher)
    for name in ("贵州茅台", "宁德时代", "工商银行", ""):
        assert f._get_stock_industry_keywords(name) == fetcher_core._get_stock_industry_keywords(
            name, StockFetcher._INDUSTRY_KEYWORDS), name


def test_t2_safe_kline_df_behaviour():
    import numpy as np
    good = pd.DataFrame({"date": ["2026-10-01", "bad", "2026-10-13"],
                         "open": [1.0, 1.0, 1.0], "close": [2.0, 2.0, 3.0],
                         "high": [2.0, 2.0, 3.0], "low": [1.0, 1.0, 1.0],
                         "volume": [100, 100, 100], "amount": [200, 200, 300]})
    out = fetcher_core._safe_kline_df(good)
    assert out is not None and len(out) == 2  # "bad" 行 date coerce → NaT → 丢弃
    assert "amount" in out.columns  # 其余列原样保留
    assert fetcher_core._safe_kline_df(None) is None
    assert fetcher_core._safe_kline_df(pd.DataFrame()) is None
    assert fetcher_core._safe_kline_df(pd.DataFrame({"date": []})) is None  # 缺必备列
    broken = pd.DataFrame({"open": [np.inf]})  # 缺必备列 → None
    assert fetcher_core._safe_kline_df(broken) is None


def test_t2_resample_behaviour():
    import numpy as np
    daily = pd.DataFrame({
        "date": pd.date_range("2026-09-01", periods=10, freq="D").strftime("%Y-%m-%d"),
        "open": np.linspace(10, 15, 10), "high": np.linspace(11, 16, 10),
        "low": np.linspace(9, 14, 10), "close": np.linspace(10.5, 15.5, 10),
        "volume": [1000] * 10, "amount": [1e5] * 10,
    })
    wk = fetcher_core._resample_kline(daily, "weekly")
    assert len(wk) >= 2 and "change_pct" in wk.columns
    assert float(wk["volume"].sum()) == 10000
    mo = fetcher_core._resample_kline(daily, "monthly")
    assert len(mo) == 1  # 9 月单月
    assert mo.iloc[0]["open"] == daily["open"].iloc[0]  # first
    assert mo.iloc[0]["close"] == daily["close"].iloc[-1]  # last


def test_t2_industry_keywords_behaviour():
    imap = {frozenset(["银行", "金融"]): ["降息", "信贷"], frozenset(["白酒"]): ["消费", "提价"]}
    out = fetcher_core._get_stock_industry_keywords("招商银行", imap)
    assert out == ["信贷", "降息"]  # sorted
    assert fetcher_core._get_stock_industry_keywords("", imap) == []
    assert fetcher_core._get_stock_industry_keywords("无名股", imap) == []


def test_fetcher_no_local_defs_of_t2():
    tree = ast.parse((ROOT / "modules/fetcher.py").read_text(encoding="utf-8"))
    # 绑定型（staticmethod 同一对象）不得本地 def；薄壳型（参数注入）允许 def
    bound = [n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name in ("_safe_kline_df", "_resample_kline")]
    assert not bound, f"fetcher.py 仍本地定义绑定型已迁函数: {bound}"
    shells = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_get_stock_industry_keywords"]
    assert len(shells) == 1, "_get_stock_industry_keywords 薄壳缺失或多定义"
    body_src = ast.get_source_segment(
        (ROOT / "modules/fetcher.py").read_text(encoding="utf-8"), shells[0]) or ""
    assert "_get_stock_industry_keywords(stock_name, StockFetcher._INDUSTRY_KEYWORDS)" in body_src, \
        "薄壳必须委托 fetcher_core 真身并注入领域表"


def test_fetcher_core_defines_t2():
    src = (ROOT / "modules/fetcher_core/__init__.py").read_text(encoding="utf-8")
    for name in MIGRATED_T2:
        assert f"def {name}" in src, f"fetcher_core 缺少 {name} 真身"