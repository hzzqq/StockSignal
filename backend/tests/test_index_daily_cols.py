"""守卫测试：index-quotes 指数日线列名口径兼容（缺陷2 回归守卫）。

缺陷背景：
- backend/api/_index_daily_worker.py 原 _COLS 只认中文列（日期/开盘/...），
  但 akshare 1.19.1 stock_zh_index_daily 返回英文列 date/open/high/low/close/volume，
  _rows_for 按中文筛选返空 → 父层 read_routes.py 二次校验「收盘 in columns」再次丢弃
  → /api/v2/read/index-quotes 全部指数 current/date 恒为 null。

守卫内容（全离线纯函数）：
1. worker._rows_for：英文列 DataFrame 经映射后产出中文列 records；
2. worker._rows_for：中文列 DataFrame 行为不变（向后兼容）；
3. 父层 read_routes._w4x_rows_to_df：英文列 rows 映射成功、无收盘列诚实返 None。
"""
import os
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from backend.api._index_daily_worker import _rows_for  # noqa: E402


def test_rows_for_maps_english_columns():
    df = pd.DataFrame({
        "date": ["2026-11-20", "2026-11-21"],
        "open": [3900.0, 3910.0],
        "high": [3960.0, 3970.0],
        "low": [3890.0, 3905.0],
        "close": [3955.9, 3966.1],
        "volume": [123456.0, 234567.0],
    })
    rows = _rows_for(df)
    assert rows, "英文列应被映射为中文列后产出 records（修复前按中文筛选返空）"
    assert set(rows[0].keys()) == {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
    assert rows[-1]["收盘"] == 3966.1
    assert rows[-1]["日期"] == "2026-11-21"


def test_rows_for_chinese_columns_unchanged():
    df = pd.DataFrame({
        "日期": ["2026-11-20", "2026-11-21"],
        "开盘": [3900.0, 3910.0],
        "收盘": [3955.9, 3966.1],
        "最高": [3960.0, 3970.0],
        "最低": [3890.0, 3905.0],
        "成交量": [123456.0, 234567.0],
    })
    rows = _rows_for(df)
    assert rows and rows[-1]["收盘"] == 3966.1


def test_rows_for_empty_and_none():
    assert _rows_for(None) == []
    assert _rows_for(pd.DataFrame()) == []


def test_parent_rows_to_df_english_columns():
    from backend.api.read_routes import _w4x_rows_to_df

    rows = [
        {"date": "2026-11-20", "open": 3900.0, "close": 3955.9,
         "high": 3960.0, "low": 3890.0, "volume": 123456.0},
        {"date": "2026-11-21", "open": 3910.0, "close": 3966.1,
         "high": 3970.0, "low": 3905.0, "volume": 234567.0},
    ]
    df = _w4x_rows_to_df(rows)
    assert df is not None, "父层应接受英文列 rows（修复前二次丢弃）"
    assert "收盘" in df.columns and "日期" in df.columns
    assert float(df.iloc[-1]["收盘"]) == 3966.1


def test_parent_rows_to_df_without_close_is_none():
    from backend.api.read_routes import _w4x_rows_to_df

    assert _w4x_rows_to_df([{"date": "2026-11-20", "open": 1.0}]) is None
    assert _w4x_rows_to_df([]) is None
    assert _w4x_rows_to_df(None) is None
