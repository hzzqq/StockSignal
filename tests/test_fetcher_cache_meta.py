"""T-248 缓存加固 A：L5 旧缓存兜底一致性 + get_daily meta_out 诚实元数据（全离线）。

验收基线（docs/data_cache_hardening.md 第1步）：
  - 复现：qfq 请求命中 none 复权旧行 → 修复前返回不可比价格序列；修复后拒绝该行；
  - L5 兜底补窗口裁剪 + 行数下限（裁剪后碎片宁可诚实失败不喂调用方）；
  - get_daily 加 meta_out 出口（source/is_stale/as_of，内容日期而非 mtime），不动签名；
  - observe_cache_fallback 死埋点接通：L5 命中/未命中均上报。

mutation 基线：
  - 去掉 adjust 后缀过滤 → test_stale_rejects_adjust_mismatch 变红；
  - 去掉 observe_cache_fallback 接线 → test_l5_hit_emits_observe / miss 用例变红；
  - meta_out 在 L5 命中谎报 is_stale=False → test_get_daily_meta_out_on_l5_hit 变红。
"""
from __future__ import annotations

import inspect
import os
import sqlite3
import sys
from datetime import timedelta

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.time_utils import now_cst_naive  # noqa: E402
from modules.fetcher import StockFetcher  # noqa: E402


# ── 造数 ──
def _df(dates, close):
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": close, "high": [c * 1.02 for c in close],
        "low": [c * 0.98 for c in close], "close": close,
        "volume": [1e6] * len(dates), "amount": [2e7] * len(dates),
    })


def _dates(d1, d2):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(d1, d2, freq="D")]


def _make_db(tmp_path, rows):
    """rows: [(cache_key, df, updated_at_datetime)] → 落盘 SQLite（同 clear_cache 测试范式）。"""
    db = os.path.join(str(tmp_path), "cache.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)")
    for key, df, updated_at in rows:
        conn.execute("INSERT INTO daily_cache VALUES (?,?,?)",
                     (key, df.to_json(orient="records", date_format="iso"),
                      updated_at.isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    return db


def _instance_for(db_path):
    f = StockFetcher.__new__(StockFetcher)
    f._get_conn = lambda: sqlite3.connect(db_path)  # type: ignore[method-assign]
    f._code_to_name = {}
    f.cache_days = 7
    return f


DATES = _dates("2026-01-01", "2026-04-10")   # 100 行
RECENT = now_cst_naive() - timedelta(hours=1)


def _seed(tmp_path):
    """复现场景：同一 symbol 两行缓存——none 复权（价 100）+ qfq（价 90），qfq 更旧。"""
    return _make_db(tmp_path, [
        ("daily_600519_2024-01-01_2026-10-11_none", _df(DATES, [100.0] * 100), RECENT),
        ("daily_600519_2024-01-01_2026-10-10_qfq", _df(DATES, [90.0] * 100),
         RECENT - timedelta(hours=2)),
    ])


# ── _read_stale_cache 一致性 ──
def test_stale_rejects_adjust_mismatch(tmp_path):
    """复现用例：库里只有 none 行（更新）时，qfq 请求必须拒绝（修复前会拿到价 100 的不可比序列）。"""
    db = os.path.join(str(tmp_path), "cache.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO daily_cache VALUES (?,?,?)",
                 ("daily_600519_2024-01-01_2026-10-11_none",
                  _df(DATES, [100.0] * 100).to_json(orient="records", date_format="iso"),
                  RECENT.isoformat(timespec="seconds")))
    conn.commit()
    f = _instance_for(db)
    out = f._read_stale_cache(conn, "daily_cache", "daily_600519",
                              adjust="qfq", start="2026-01-01", end="2026-10-11",
                              min_rows=60)
    conn.close()
    assert out is None, "qfq 请求不得命中 none 复权旧行"


def test_stale_accepts_adjust_match_and_clips_window(tmp_path):
    db = _seed(tmp_path)
    f = _instance_for(db)
    conn = f._get_conn()
    out = f._read_stale_cache(conn, "daily_cache", "daily_600519",
                              adjust="qfq", start="2026-03-01", end="2026-10-11",
                              min_rows=10)
    conn.close()
    assert out is not None
    assert (out["close"] == 90.0).all(), "必须拿到 qfq 行（价 90）而非 none 行（价 100）"
    assert out["date"].min() >= pd.Timestamp("2026-03-01"), "必须裁剪到请求窗口"


def test_stale_min_rows_rejects_fragment(tmp_path):
    db = _seed(tmp_path)
    f = _instance_for(db)
    conn = f._get_conn()
    out = f._read_stale_cache(conn, "daily_cache", "daily_600519",
                              adjust="qfq", start="2026-04-08", end="2026-10-11",
                              min_rows=60)
    conn.close()
    assert out is None, "窗口裁剪后碎片（3 行）不得当兜底返回"


def test_stale_no_adjust_keeps_legacy_semantics(tmp_path):
    """不传 adjust → 维持旧行为（取最新一行），兼容既有调用方。"""
    db = _seed(tmp_path)
    f = _instance_for(db)
    conn = f._get_conn()
    out = f._read_stale_cache(conn, "daily_cache", "daily_600519")
    conn.close()
    assert out is not None and (out["close"] == 100.0).all(), "无 adjust 过滤时取最新行（none）"


# ── get_daily meta_out ──
def _fail_levels(self, level, symbol, start, end, adjust):
    return None, f"{level}: offline"


def test_get_daily_meta_out_on_l5_hit(tmp_path, monkeypatch):
    db = _seed(tmp_path)
    f = _instance_for(db)
    monkeypatch.setattr(f, "_fetch_level", _fail_levels.__get__(f, StockFetcher))
    meta = {}
    out = f.get_daily("600519", start="2026-01-01", end="2026-10-11",
                      adjust="qfq", meta_out=meta)
    assert out is not None and (out["close"] == 90.0).all()
    assert meta.get("source") == "cache_fallback"
    assert meta.get("is_stale") is True, "L5 兜底必须如实标注 stale"
    assert meta.get("as_of") == "2026-04-10", "as_of 必须是内容日期而非缓存写入时间"


def test_get_daily_meta_out_on_live(tmp_path, monkeypatch):
    db = os.path.join(str(tmp_path), "cache.db")
    f = _instance_for(db)
    live = _df(_dates("2026-04-01", "2026-04-10"), [88.0] * 10)

    def _ok_levels(self, level, symbol, start, end, adjust):
        return live.copy(), None

    monkeypatch.setattr(f, "_fetch_level", _ok_levels.__get__(f, StockFetcher))
    meta = {}
    out = f.get_daily("600519", start="2026-04-01", end="2026-10-11",
                      adjust="qfq", meta_out=meta)
    assert out is not None
    assert meta.get("source") == "live" and meta.get("is_stale") is False
    assert meta.get("as_of") == "2026-04-10"


def test_l5_hit_emits_observe(tmp_path, monkeypatch):
    """observe_cache_fallback 死埋点必须接通：命中 hit=True，未命中 hit=False。"""
    db = _seed(tmp_path)
    f = _instance_for(db)
    monkeypatch.setattr(f, "_fetch_level", _fail_levels.__get__(f, StockFetcher))
    calls = []
    monkeypatch.setattr("modules.fetcher.observe_cache_fallback",
                        lambda level, hit, detail="": calls.append((level, hit)))
    f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    assert ("L5", True) in calls, "L5 命中必须上报埋点"

    calls.clear()
    f2 = _instance_for(os.path.join(str(tmp_path), "empty.db"))
    monkeypatch.setattr(f2, "_fetch_level", _fail_levels.__get__(f2, StockFetcher))
    try:
        f2.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    except RuntimeError:
        pass  # 全源失败 + 无兜底 → 诚实抛错（预期）
    assert ("L5", False) in calls, "L5 未命中也必须上报埋点"


def test_get_daily_meta_out_absent_no_break(tmp_path, monkeypatch):
    """不传 meta_out（34 处既有调用方形态）→ 行为与返回值零变化。"""
    db = _seed(tmp_path)
    f = _instance_for(db)
    monkeypatch.setattr(f, "_fetch_level", _fail_levels.__get__(f, StockFetcher))
    out = f.get_daily("600519", start="2026-01-01", end="2026-10-11", adjust="qfq")
    assert out is not None and (out["close"] == 90.0).all()


# ── 荐股 stale_count 接线 ──
def test_recommend_stale_count_wired():
    """引擎必须落盘 stale_count（接线源码守卫，防脱落）。"""
    from modules import recommend_engine as re_mod

    src = inspect.getsource(re_mod.generate_daily_recommendation)
    assert "stale_count" in src and "meta_out" in src
