"""Cycle 32 回归：_ensure_stock_db 在 BaoStock 可用时必须真正加载，而非静默空返回。

修复前：fetcher.py L1103 直接 `rs = bs.query_stock_basic()`，但 fetcher 模块从未导入
baostock，`bs` 未定义。_BS_OK=True 时走到此处必抛 NameError，被外层 except 吞掉，
导致全量股票库永远返回空 DataFrame（搜索/代码映射彻底失效）——典型的静默失效。

测试：构造 _BS_OK=True 且 baostock 可 import 的环境，注入会返回 2 条数据的 fake bs，
断言 _ensure_stock_db 真正取到数据（len==2）；修复前因 NameError 被吞，结果永远为 0 条。
"""
import os
import sys
import types
import sqlite3
import tempfile

import pandas as pd
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import fetcher


def test_ensure_stock_db_loads_from_baostock_when_available(monkeypatch):
    fake_bs = types.ModuleType("baostock")
    fake_bs.login = lambda: SimpleNamespace(error_code="0", error_msg="")
    fake_bs.logout = lambda: None

    class _RS:
        error_code = "0"

        def __init__(self):
            self._rows = [["sh.600519", "贵州茅台"], ["sz.000001", "平安银行"]]
            self._idx = 0

        def next(self):
            return self._idx < len(self._rows)

        def get_row_data(self):
            r = self._rows[self._idx]
            self._idx += 1
            return r

    fake_bs.query_stock_basic = lambda: _RS()
    monkeypatch.setitem(sys.modules, "baostock", fake_bs)
    monkeypatch.setattr(fetcher, "_BS_OK", True)
    monkeypatch.setattr(
        fetcher._BaoStockFetcher, "_ensure_login", classmethod(lambda cls: True)
    )

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "c.db")
    # 类级 monkeypatch：构造器与后续调用都走临时库，隔离真实缓存
    monkeypatch.setattr(
        fetcher.StockFetcher, "_get_conn", lambda self: sqlite3.connect(db)
    )

    inst = fetcher.StockFetcher()
    result = inst._ensure_stock_db()

    assert isinstance(result, pd.DataFrame)
    # 修复前 NameError 被吞 -> 永远 0 条；修复后真正从 bs 取到 2 条
    assert len(result) == 2
    assert set(result["code"]) == {"600519", "000001"}


def test_is_bs_available_reads_fetcher_switch_lazily(monkeypatch):
    """R75 锁定：_is_bs_available() 必须延迟读 fetcher._BS_OK，不缓存值拷贝。

    背景：_feed_io._is_bs_available 若在导入时 `from modules.fetcher import _BS_OK`
    值拷贝，monkeypatch.setattr(fetcher, "_BS_OK", ...) 将失效，测试无法模拟
    "BaoStock 未安装" 场景（曾出现过 re-export 值拷贝坑）。
    """
    import modules._feed_io as feed_io
    import modules.fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "_BS_OK", True)
    assert feed_io._is_bs_available() is True

    monkeypatch.setattr(fetcher_mod, "_BS_OK", False)
    assert feed_io._is_bs_available() is False
