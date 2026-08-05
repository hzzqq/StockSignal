"""锁定 market_cache 的 sqlite 读写契约与损坏容错（防回归）。

聚焦：空输入守卫、save→load 往返一致性、单序列写入、缺失/损坏 DB 不崩降级。
此前无单测。
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

import modules.market_cache as mc


def _recent_dates(n: int = 3):
    """近 n 天（含今天），避免被 load 的 days cutoff 过滤掉。"""
    today = datetime.now().date()
    return pd.to_datetime([str(today - timedelta(days=n - 1 - i)) for i in range(n)])


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "test_market_cache.db"
    monkeypatch.setattr(mc, "_DB_PATH", str(db))
    monkeypatch.setattr(mc, "_DATA_DIR", str(tmp_path))
    return db


def _sample_df():
    return pd.DataFrame({
        "date": _recent_dates(3),
        "northbound": [1.2, 2.3, -0.5],
        "margin": [10.0, 11.0, 12.0],
    })


def test_save_empty_returns_zero(tmp_db):
    assert mc.save_drivers_to_cache(None) == 0
    assert mc.save_drivers_to_cache(pd.DataFrame()) == 0
    assert mc.save_drivers_to_cache(pd.DataFrame({"no_date": [1]})) == 0


def test_save_and_load_roundtrip(tmp_db):
    df = _sample_df()
    n = mc.save_drivers_to_cache(df)
    assert n == 6  # 2 指标 * 3 天

    out, meta = mc.load_drivers_from_cache(days=180)
    assert out is not None and not out.empty
    assert "northbound" in out.columns
    assert "margin" in out.columns
    # 值 round-trip 正确
    nb = out.set_index("date")["northbound"]
    assert abs(float(nb.iloc[0]) - 1.2) < 1e-6
    assert abs(float(nb.iloc[2]) - (-0.5)) < 1e-6


def test_save_single_series(tmp_db):
    s = pd.Series([1.0, 2.0, 3.0], index=_recent_dates(3))
    assert mc.save_single_series("test_key", s) == 3


def test_load_empty_db_returns_none(tmp_db):
    # 未写入任何数据，load 应安全返回 None（不崩）
    out, meta = mc.load_drivers_from_cache(days=180)
    assert out is None
    assert isinstance(meta, dict)


def test_corrupt_db_does_not_crash(tmp_db):
    # 写入损坏的非 sqlite 文件，load 必须捕获异常降级而非抛出
    tmp_db.write_bytes(b"this is not a sqlite database at all")
    out, meta = mc.load_drivers_from_cache(days=180)
    assert out is None  # 损坏 -> 安全降级
    assert isinstance(meta, dict)


def test_corrupt_db_write_paths_do_not_crash(tmp_db):
    """损坏 DB 下写入/状态/清理三条路径也必须优雅降级，不能抛。"""
    tmp_db.write_bytes(b"broken file, definitely not sqlite")
    assert mc.save_drivers_to_cache(_sample_df()) == 0
    assert mc.save_single_series("k", pd.Series([1.0], index=_recent_dates(1))) == 0
    assert "error" in mc.get_cache_status()
    assert mc.clear_stale_cache(days=1) == 0
