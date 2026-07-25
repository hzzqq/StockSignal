"""modules/cleaner 回归测试（无网依赖）。

覆盖：
- align_dates：取日期交集 + 各帧按日期升序一一对应（修复 row i 跨帧日期错位的隐性 bug）
- sort_by_date：date 列解析为 datetime 且按升序排序（新增能力）
"""
import pandas as pd

import modules.cleaner as C


def _mk(dates, vals):
    return pd.DataFrame({"date": dates, "v": vals})


def test_align_dates_intersection():
    a = _mk(["2026-01-01", "2026-01-02", "2026-01-03"], [1, 2, 3])
    b = _mk(["2026-01-01", "2026-01-04"], [10, 40])
    ra, rb = C.DataCleaner.align_dates(a, b)
    assert list(ra["date"]) == ["2026-01-01"]
    assert list(rb["date"]) == ["2026-01-01"]


def test_align_dates_row_alignment_preserved():
    # 两帧日期顺序不同，交集日期一致；修复后应按同一日期顺序排列
    a = _mk(["2026-01-03", "2026-01-01", "2026-01-02"], [3, 1, 2])
    b = _mk(["2026-01-01", "2026-01-02", "2026-01-03"], [10, 20, 30])
    ra, rb = C.DataCleaner.align_dates(a, b)
    assert list(ra["date"]) == list(rb["date"]), "对齐后两帧日期顺序必须一致"
    # 同一日期在两帧中对应的行索引一致（按日期键值对齐）
    ra_map = dict(zip(ra["date"], ra["v"]))
    rb_map = dict(zip(rb["date"], rb["v"]))
    assert set(ra_map.keys()) == set(rb_map.keys())


def test_align_dates_datetime_column():
    a = _mk(pd.to_datetime(["2026-01-03", "2026-01-01", "2026-01-02"]), [3, 1, 2])
    b = _mk(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]), [10, 20, 30])
    ra, rb = C.DataCleaner.align_dates(a, b)
    assert list(ra["date"]) == list(rb["date"])


def test_sort_by_date_ascending():
    df = _mk(["2026-01-03", "2026-01-01", "2026-01-02"], [3, 1, 2])
    out = C.DataCleaner.sort_by_date(df)
    assert list(out["date"]) == [
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-03"),
    ]
    assert list(out["v"]) == [1, 2, 3]


def test_sort_by_date_missing_col_returns_copy():
    df = pd.DataFrame({"x": [1, 2, 3]})
    out = C.DataCleaner.sort_by_date(df)
    assert list(out.columns) == ["x"]
