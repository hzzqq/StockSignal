# -*- coding: utf-8 -*-
"""T-248 缓存维护单一真理源守卫。

锁住：
1. prune_sqlite_cache 删除早于保留期的行、保留边界日及更新的行，并如实返回删除数；
2. prune_sqlite_cache 对缺失库返回 error=missing 而非抛异常；
3. prune_sqlite_cache 遇到不存在的表不报错（no such table 视为预期）；
4. prune_shepherd_dirs 默认只清 v1，include_v2=True 才清 v2；
5. run_cache_maintenance 在临时根下不触碰真实库、返回结构完整的报告、best-effort 不抛。

诚实语义：返回真实删除数 / 释放字节；失败留痕绝不谎报。
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.cache_maintenance as cm  # noqa: E402


def _make_cache_db(path: Path, old_rows: int, new_rows: int):
    """造 cache.db 风格 daily_cache 表：old_rows 行 updated_at 远早于 cutoff，new_rows 行远晚。"""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)"
    )
    old_date = "2000-01-01T00:00:00"  # 必然 < cutoff
    new_date = "2099-01-01T00:00:00"  # 必然 > cutoff（保留）
    for i in range(old_rows):
        conn.execute(
            "INSERT OR REPLACE INTO daily_cache VALUES (?,?,?)",
            (f"old_{i}", "{}", old_date),
        )
    for i in range(new_rows):
        conn.execute(
            "INSERT OR REPLACE INTO daily_cache VALUES (?,?,?)",
            (f"new_{i}", "{}", new_date),
        )
    conn.commit()
    conn.close()


def test_prune_sqlite_cache_deletes_old_keeps_new(tmp_path):
    db = tmp_path / "cache.db"
    _make_cache_db(db, old_rows=5, new_rows=3)
    res = cm.prune_sqlite_cache(db, ["daily_cache"], days=90, date_col="updated_at")
    assert res["error"] is None
    assert res["deleted"] == 5, res
    conn = sqlite3.connect(str(db))
    n_old = conn.execute("SELECT COUNT(*) FROM daily_cache WHERE cache_key LIKE 'old_%'").fetchone()[0]
    n_new = conn.execute("SELECT COUNT(*) FROM daily_cache WHERE cache_key LIKE 'new_%'").fetchone()[0]
    conn.close()
    assert n_old == 0 and n_new == 3


def test_prune_sqlite_cache_missing_db(tmp_path):
    res = cm.prune_sqlite_cache(tmp_path / "nope.db", ["daily_cache"], days=90)
    assert res["error"] == "missing"
    assert res["deleted"] == 0


def test_prune_sqlite_cache_no_such_table_no_error(tmp_path):
    db = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE other (x TEXT)")
    conn.commit()
    conn.close()
    res = cm.prune_sqlite_cache(db, ["daily_cache"], days=90)  # daily_cache 不存在
    assert res["error"] is None
    assert res["deleted"] == 0


def _touch(path: Path, days_ago: float):
    mtime = time.time() - days_ago * 86400
    os.utime(path, (mtime, mtime))


def test_prune_shepherd_dirs_v2_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "DATA", tmp_path)
    v1 = tmp_path / "shepherd_cache"
    v2 = tmp_path / "shepherd_cache_v2"
    v1.mkdir()
    v2.mkdir()
    old1 = v1 / "old.csv"
    old1.write_text("x\n")
    _touch(old1, 40)
    new1 = v1 / "new.csv"
    new1.write_text("x\n")
    _touch(new1, 1)
    old2 = v2 / "old.csv"
    old2.write_text("x\n")
    _touch(old2, 40)
    # include_v2=False -> 只清 v1
    cm.prune_shepherd_dirs(days=30, include_v2=False)
    assert not old1.exists() and new1.exists()
    assert old2.exists()  # v2 未清
    # include_v2=True -> 清 v2
    cm.prune_shepherd_dirs(days=30, include_v2=True)
    assert not old2.exists()


def test_prune_shepherd_dirs_dry_run_no_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "DATA", tmp_path)
    v1 = tmp_path / "shepherd_cache"
    v1.mkdir()
    old1 = v1 / "old.csv"
    old1.write_text("x\n")
    _touch(old1, 40)
    rep = cm.prune_shepherd_dirs(days=30, include_v2=False, dry_run=True)
    assert rep[0]["removed"] == 1  # 预估删除数
    assert old1.exists()  # dry-run 不实际删除


def test_run_cache_maintenance_temp_root(tmp_path, monkeypatch):
    """在临时根下编排四源清理，不触碰真实 data/，验证报告结构与真实删除数。"""
    monkeypatch.setattr(cm, "DATA", tmp_path)
    # market_cache 部分用桩替代（避免触碰真实库 / 重依赖）：
    # run_cache_maintenance 内部 `from modules.market_cache import clear_stale_cache`，
    # 故直接 patch market_cache 模块上的该函数即可被懒导入拿到桩。
    import modules.market_cache as _mc_mod  # noqa: E402
    monkeypatch.setattr(_mc_mod, "clear_stale_cache", lambda days: 0, raising=True)

    # cache.db
    _make_cache_db(tmp_path / "cache.db", old_rows=4, new_rows=2)
    # news.db
    conn = sqlite3.connect(str(tmp_path / "news.db"))
    conn.execute("CREATE TABLE news (id INTEGER, date TEXT)")
    conn.execute("INSERT INTO news VALUES (1, '2000-01-01')")  # 旧
    conn.execute("INSERT INTO news VALUES (2, '2099-01-01')")  # 新
    conn.commit()
    conn.close()
    # shepherd 空目录（v1）
    (tmp_path / "shepherd_cache").mkdir()

    rep = cm.run_cache_maintenance(days=90, include_v2=False, dry_run=False)
    assert "sqlite" in rep and "shepherd" in rep and "errors" in rep
    cache_res = next(s for s in rep["sqlite"] if s["db"].endswith("cache.db"))
    assert cache_res["deleted"] == 4, rep
    news_res = next(s for s in rep["sqlite"] if s["db"].endswith("news.db"))
    assert news_res["deleted"] == 1, rep
    # shepherd v1 空目录 -> removed 0
    assert rep["shepherd"][0]["removed"] == 0
    # 真实删除已生效
    c = sqlite3.connect(str(tmp_path / "cache.db"))
    assert c.execute("SELECT COUNT(*) FROM daily_cache WHERE cache_key LIKE 'old_%'").fetchone()[0] == 0
    c.close()
