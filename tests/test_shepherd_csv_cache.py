"""回归守卫：_read_history_csv 的 CSV 解析缓存 + 副本安全性。

背景：此前 _read_history_csv 在每次 get_shepherd_indicators 调用时都重新 parse
全量 CSV（约 4771 行），市场情绪/状态机/全景等页在 st_autorefresh 下每 30~60s
触发一次，是广度页主要 CPU 浪费。改为按文件 mtime 缓存 1h，并返回副本避免调用方
改到缓存中的可变对象。
"""
import os
import tempfile

import pandas as pd

import modules.shepherd as shepherd


def _make_csv(path):
    df = pd.DataFrame(
        {
            "date": [
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
                "2026-01-04",
                "2026-01-05",
            ],
            "limit_up": [10, 12, 8, 15, 9],
            "limit_down": [2, 1, 3, 0, 4],
        }
    )
    df.to_csv(path, index=False)


def test_read_history_csv_cached_copy_safety():
    """_read_history_csv 必须返回独立副本：调用方改一版不应污染缓存/另一版。"""
    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, "shepherd_history.csv")
        _make_csv(csv_path)
        orig = shepherd._HISTORY_FILE
        shepherd._CACHE.clear()
        try:
            shepherd._HISTORY_FILE = csv_path
            full = shepherd._read_history_csv(None)
            assert full is not None and len(full) == 5
            tail = shepherd._read_history_csv(3)
            assert tail is not None and len(tail) == 3
            # 副本安全性：改动第一份不应出现在第二份
            full["__mut"] = 1
            again = shepherd._read_history_csv(None)
            assert again is not None and len(again) == 5
            assert "__mut" not in again.columns
        finally:
            shepherd._HISTORY_FILE = orig


def test_read_history_csv_missing_file_returns_none():
    """文件不存在时安全返回 None，不抛异常。"""
    with tempfile.TemporaryDirectory() as td:
        missing = os.path.join(td, "no_such.csv")
        orig = shepherd._HISTORY_FILE
        try:
            shepherd._HISTORY_FILE = missing
            assert shepherd._read_history_csv(None) is None
            assert shepherd._read_history_csv(60) is None
        finally:
            shepherd._HISTORY_FILE = orig
