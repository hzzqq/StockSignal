"""
tests/test_cache_db_footprint.py
================================
T-272⑤：缓存库体积体检——cache_db_footprint 单测（missing/ok/over 三态 +
SS_DATA_DIR 隔离）+ 82 页展示接线守卫。

诚实语义：体积超限只软告警不判数据错误（库可再生，删除后自动重建）；
config 自定义库路径时按默认位置「估算」并在 UI 口径说明中如实标注。
"""
from pathlib import Path

from modules import data_health as dh

_PROJECT = Path(__file__).resolve().parents[1]


def test_missing_dbs_reported_honestly(tmp_path, monkeypatch):
    """目录无库文件 → status=missing，不臆造体积。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    rows = dh.cache_db_footprint()
    assert [r["name"] for r in rows] == ["cache.db", "market_cache.db"]
    assert all(r["status"] == "missing" and r["size_mb"] is None for r in rows)


def test_ok_when_below_limit(tmp_path, monkeypatch):
    """小文件 + 高阈值 → status=ok。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    (tmp_path / "cache.db").write_bytes(b"x" * 4096)
    rows = dh.cache_db_footprint(limit_mb=1.0)
    by_name = {r["name"]: r for r in rows}
    assert by_name["cache.db"]["status"] == "ok"
    assert by_name["cache.db"]["size_mb"] is not None and by_name["cache.db"]["size_mb"] < 1
    assert by_name["market_cache.db"]["status"] == "missing"


def test_over_limit_flags_and_suggests_clean(tmp_path, monkeypatch):
    """超软阈值 → status=over，且 note 指向 clean_cache.py --dry-run（可执行建议）。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    (tmp_path / "market_cache.db").write_bytes(b"x" * (1100 * 1024))  # ≈1.1MB
    rows = dh.cache_db_footprint(limit_mb=1.0)
    by_name = {r["name"]: r for r in rows}
    assert by_name["market_cache.db"]["status"] == "over"
    assert "clean_cache.py --dry-run" in by_name["market_cache.db"]["note"]
    assert by_name["cache.db"]["status"] == "missing"


def test_does_not_follow_config_custom_path_estimates_only():
    """默认（无 SS_DATA_DIR）走项目 data/ 目录口径——纯只读不触网不建文件。"""
    rows = dh.cache_db_footprint()
    assert len(rows) == 2
    for r in rows:
        assert r["status"] in ("ok", "over", "missing", "unknown")
        if r["status"] != "missing":
            assert isinstance(r["size_mb"], (int, float))


def test_page82_footprint_and_metrics_sections():
    """82 页两个缓存区块存在（AST 守卫：展示接线不回退）。"""
    src = (_PROJECT / "pages" / "82_数据时效性看板.py").read_text(encoding="utf-8")
    assert "### 🧱 缓存层命中率" in src
    assert "### 💾 缓存库体积" in src
