# -*- coding: utf-8 -*-
"""tests/test_cache_key_normalization.py — T-250 daily 缓存键归一守卫（AST + 行为）。

锁四条硬性红线（改造验收基线，防回潮）：
  (a) 新键 ``daily_full_{symbol}_{adjust}`` 形态**不含日期区间**——换任何 start/end
      都是同一把键（本次治本的目的：区间变化不再必然 miss）；
  (b) 旧 ``daily`` 区间键形态**逐字节不变**——既有 SQLite 缓存必须继续命中；
  (c) 新键→旧键**兼容反查函数**存在且能构造旧键（双读兼容的根基）；
  (d) **调用点迁移**：modules/fetcher_kline.py 与 modules/stock_research.py 均不再
      直接调 ``_build_cache_key("daily", ...)``——fetcher_kline 走兼容反查
      ``_legacy_daily_cache_key``，stock_research 强制刷新清新全量键。

行为层（全离线、零网络、stub 四源竞速）：
  - 切片命中：cov 覆盖请求窗口 → daily_full 切片直返，不回源；
  - 旧键无残留误命中：旧区间键只能被**精确反查**命中，换窗口绝不串旧数据；
  - 增量合并不丢行：_write_daily_full 并集合并，重叠日期取新值、区间外旧行保留；
  - 跨复权不串：qfq 全量行对 hfq 请求不可见（键含 adjust，绝不混价格口径）。
"""
import ast
import os
import re
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]

import modules.fetcher as fetcher_mod  # noqa: E402
from modules.fetcher import StockFetcher  # noqa: E402
from modules.fetcher_core import (  # noqa: E402
    _build_cache_key,
    _legacy_daily_cache_key,
)


# ── 造数 ─────────────────────────────────────────────────────────────────
def _dates(d1, d2):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(d1, d2, freq="D")]


def _df(dates, close):
    n = len(dates)
    return pd.DataFrame({"date": pd.to_datetime(dates),
                         "open": close, "high": [c * 1.02 for c in close],
                         "low": [c * 0.98 for c in close], "close": close,
                         "volume": [1e6] * n, "amount": [2e7] * n})


def _instance(db, levels=None):
    """最小 StockFetcher 实例（同 test_fetcher_speedups 范式，全离线零网络）。"""
    f = StockFetcher.__new__(StockFetcher)
    f._code_to_name = {}
    f.cache_days = 7
    f._get_conn = lambda: sqlite3.connect(db)  # type: ignore[method-assign]
    calls = {"n": 0}

    if levels is None:
        def _levels(self, level, symbol, start, end, adjust):
            calls["n"] += 1
            return None, f"{level}: offline"
    else:
        def _levels(self, level, symbol, start, end, adjust):
            calls["n"] += 1
            return levels(start, end), None

    f._fetch_level = _levels.__get__(f, StockFetcher)  # type: ignore[method-assign]
    f._calls = calls
    return f


@pytest.fixture(autouse=True)
def _clean_l0():
    fetcher_mod._L0_CACHE.clear()
    yield
    fetcher_mod._L0_CACHE.clear()


# ── (a) 新键形态：不含日期区间 ───────────────────────────────────────────
def test_daily_full_key_shape_has_no_date_range():
    key = _build_cache_key("daily_full", symbol="600519", adjust="qfq")
    assert key == "daily_full_600519_qfq"
    assert not re.search(r"\d{4}-\d{2}-\d{2}", key), "新键内嵌日期区间即回潮"
    assert not re.search(r"\d{8}", key), "新键内嵌 YYYYMMDD 即回潮"


def test_daily_full_key_ignores_caller_date_range():
    """核心目的：前端换日期区间不得换键。"""
    a = _build_cache_key("daily_full", symbol="600519", adjust="qfq")
    b = _build_cache_key("daily_full", symbol="600519", adjust="qfq",
                         start="2026-01-01", end="2026-03-31")
    c = _build_cache_key("daily_full", symbol="600519", adjust="qfq",
                         start="2025-07-01", end="2025-09-30")
    assert a == b == c


# ── (b) 旧键逐字节不变 + (c) 兼容反查函数 ────────────────────────────────
def test_legacy_daily_key_byte_identical():
    assert _build_cache_key("daily", symbol="600519", start="2024-01-01",
                            end="2024-12-31", adjust="qfq") == \
        "daily_600519_2024-01-01_2024-12-31_qfq"


def test_compat_reverse_lookup_exists_and_builds_old_key():
    """新键→旧键兼容反查：函数存在、可导入、输出与单一真源逐字节一致。"""
    from modules import fetcher_core as fc
    assert hasattr(fc, "_legacy_daily_cache_key")
    for symbol, start, end, adjust in (
        ("600519", "2024-01-01", "2024-12-31", "qfq"),
        ("000001", "2025-12-01", "2026-01-05", "hfq"),
    ):
        assert _legacy_daily_cache_key(symbol, start, end, adjust) == \
            _build_cache_key("daily", symbol=symbol, start=start,
                             end=end, adjust=adjust)


# ── (d) 调用点迁移（AST 守卫）────────────────────────────────────────────
def _daily_keytype_call_sites(fname):
    """AST 扫描：文件内 _build_cache_key 调用中 key_type 恰为 "daily" 的位置。"""
    src = (_ROOT / "modules" / fname).read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (
            f.attr if isinstance(f, ast.Attribute) else None)
        if name != "_build_cache_key":
            continue
        kinds = []
        if node.args and isinstance(node.args[0], ast.Constant):
            kinds.append(node.args[0].value)
        for kw in node.keywords:
            if kw.arg == "key_type" and isinstance(kw.value, ast.Constant):
                kinds.append(kw.value.value)
        if "daily" in kinds:  # 精确匹配："daily_prefix"/"daily_full" 不算
            offenders.append(f"{fname}:L{node.lineno}")
    return offenders


def test_call_sites_no_longer_build_legacy_daily_key():
    """fetcher_kline 与 stock_research 均不得再直接调 _build_cache_key("daily", ...)。"""
    offenders = []
    for fname in ("fetcher_kline.py", "stock_research.py"):
        offenders.extend(_daily_keytype_call_sites(fname))
    assert not offenders, (
        "调用点迁移回潮（应走 _legacy_daily_cache_key 反查 / daily_full 新键）：\n  "
        + "\n  ".join(offenders)
    )


def test_fetcher_kline_wires_compat_reverse_lookup():
    """AST：fetcher_kline 从 fetcher_core 导入并在 get_daily 内调用兼容反查。"""
    src = (_ROOT / "modules" / "fetcher_kline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "modules.fetcher_core":
            if any(a.name == "_legacy_daily_cache_key" for a in node.names):
                imported = True
    assert imported, "fetcher_kline 必须从 fetcher_core 导入 _legacy_daily_cache_key"
    assert src.count("_legacy_daily_cache_key(") >= 1, \
        "get_daily 的旧形态区间键必须经兼容反查构造（读/写共用 cache_key 变量）"


def test_stock_research_force_refresh_clears_full_keys():
    """AST：个股研究页「强制刷新」必须齐清新全量行/覆盖行，否则快路径假刷新。"""
    src = (_ROOT / "modules" / "stock_research.py").read_text(encoding="utf-8")
    assert '_build_cache_key("daily_full"' in src, \
        "强刷精确键应改为 daily_full（全量行）"
    assert "daily_fullcov_{ticker}_%" in src and "daily_full_{ticker}_%" in src, \
        "强刷前缀批清必须覆盖 daily_full_ / daily_fullcov_ 两类新键"


# ── 行为：切片命中（cov 覆盖 → 直返，不回源）────────────────────────────
def test_slice_hit_served_from_full_row(tmp_path):
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance(db)
    conn = f._get_conn()
    f._write_daily_full(conn, "600519", "qfq", _df(_dates("2026-01-01", "2026-06-30"), [10.0] * 181))
    conn.close()

    meta = {}
    out = f.get_daily("600519", start="2026-03-01", end="2026-03-31",
                      adjust="qfq", meta_out=meta)
    assert out is not None and not out.empty
    assert meta["source"] == "cache" and meta["is_stale"] is False
    assert meta["as_of"] == "2026-03-31", "as_of 必须是切片内容日期而非 now()"
    dts = pd.to_datetime(out["date"])
    assert (dts >= pd.Timestamp("2026-03-01")).all() and (dts <= pd.Timestamp("2026-03-31")).all()
    assert f._calls["n"] == 0, "cov 覆盖请求窗口时不得回源（这正是本次治本要消灭的）"


def test_slice_outside_coverage_refetches(tmp_path):
    """诚实红线：cov 未覆盖请求窗口 → 必须回源（绝不拿残缺序列冒充完整区间）。"""
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance(db)
    conn = f._get_conn()
    f._write_daily_full(conn, "600519", "qfq", _df(_dates("2026-01-01", "2026-01-31"), [10.0] * 31))
    conn.close()
    n0 = f._calls["n"]

    try:
        f.get_daily("600519", start="2026-03-01", end="2026-03-31", adjust="qfq")
    except RuntimeError:
        pass  # 四源离线 + 旧键无行 → 诚实抛错（预期）
    assert f._calls["n"] > n0, "未覆盖窗口必须回源补拉"


# ── 行为：旧键无残留误命中 ──────────────────────────────────────────────
def test_legacy_key_only_hits_on_exact_reverse_lookup(tmp_path):
    """旧区间键只能被精确反查命中：换窗口绝不串旧数据（prefix 式误命中即红）。"""
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance(db)
    conn = f._get_conn()
    legacy_key = _legacy_daily_cache_key("600519", "2026-01-01", "2026-01-31", "qfq")
    f._write_cache(conn, "daily_cache", legacy_key,
                   _df(_dates("2026-01-01", "2026-01-31"), [111.0] * 31))
    conn.close()

    # ① 精确反查窗口 → 命中（双读兼容）
    meta = {}
    out = f.get_daily("600519", start="2026-01-01", end="2026-01-31",
                      adjust="qfq", meta_out=meta)
    assert out is not None and (out["close"] == 111.0).all()
    assert meta["source"] == "cache"

    # ② 不同窗口（旧键形态不同、无全量行）→ 绝不得误命中 ① 的行
    with pytest.raises(RuntimeError):
        f.get_daily("600519", start="2026-03-01", end="2026-03-31", adjust="qfq")


# ── 行为：增量合并不丢行 ────────────────────────────────────────────────
def test_merge_full_keeps_rows_outside_new_fetch(tmp_path):
    """增量合并：新抓窗口外的旧行必须保留（绝不整段覆盖丢旧行）。"""
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance(db)
    conn = f._get_conn()
    f._write_daily_full(conn, "600519", "qfq", _df(_dates("2026-01-01", "2026-01-31"), [10.0] * 31))
    f._write_daily_full(conn, "600519", "qfq", _df(_dates("2026-03-01", "2026-03-31"), [12.0] * 31))
    full = f._read_cache(conn, "daily_cache",
                         _build_cache_key("daily_full", symbol="600519", adjust="qfq"),
                         max_age_seconds=10 ** 9)
    cov = f._read_cache(conn, "daily_cache",
                        _build_cache_key("daily_fullcov", symbol="600519", adjust="qfq"),
                        as_dataframe=False, max_age_seconds=10 ** 9)
    conn.close()

    assert full is not None and len(full) == 62, "1 月 + 3 月共 62 行，丢行即红"
    cov_dates = pd.to_datetime(full["date"])
    assert cov_dates.min() == pd.Timestamp("2026-01-01")
    assert cov_dates.max() == pd.Timestamp("2026-03-31")
    assert cov == {"start": "2026-01-01", "end": "2026-03-31"}, \
        "cov 只记**实际包含**区间（诚实红线）"


def test_merge_full_overlapping_date_takes_new_value(tmp_path):
    """重叠日期去重取新值（keep=last）：刷新后同日价格以最新抓取为准。"""
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance(db)
    conn = f._get_conn()
    old = _df(_dates("2026-02-01", "2026-02-05"), [100.0] * 5)
    new = _df(_dates("2026-02-03", "2026-02-07"), [200.0] * 5)
    f._write_daily_full(conn, "600519", "qfq", old)
    f._write_daily_full(conn, "600519", "qfq", new)
    full = f._read_cache(conn, "daily_cache",
                         _build_cache_key("daily_full", symbol="600519", adjust="qfq"),
                         max_age_seconds=10 ** 9)
    conn.close()

    assert len(full) == 7, "02-01..02-07 共 7 行（重叠日去重）"
    row = full[pd.to_datetime(full["date"]) == pd.Timestamp("2026-02-03")]
    assert float(row["close"].iloc[0]) == 200.0, "重叠日期必须取新值"
    row_old = full[pd.to_datetime(full["date"]) == pd.Timestamp("2026-02-01")]
    assert float(row_old["close"].iloc[0]) == 100.0, "窗口外旧行不得丢"


# ── 行为：跨复权不串 ────────────────────────────────────────────────────
def test_full_row_not_served_across_adjust(tmp_path):
    """qfq 全量行对 hfq 请求不可见：键含 adjust，绝不混价格口径。"""
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance(db)
    conn = f._get_conn()
    f._write_daily_full(conn, "600519", "qfq", _df(_dates("2026-01-01", "2026-06-30"), [10.0] * 181))
    conn.close()

    with pytest.raises(RuntimeError):
        f.get_daily("600519", start="2026-03-01", end="2026-03-31", adjust="hfq")
