"""T-250 接线端到端回归（离线、无网络、无 live 标记，默认门禁即收集）。

验证 get_daily 已真正接线 daily_full / daily_fullcov：
  1) 首次请求（无 daily_full）→ 走竞速取数，并写回 daily_full + 覆盖区间 cov；
  2) 二次请求落在 cov 真实区间内 → 命中 daily_full 快路径，**不再回源**（竞速调用数不增加）；
  3) 旧形态 daily 区间键仍被写入（向后兼容，既有 SQLite 缓存继续命中）；
  4) 诚实红线：cov 只记录 daily_full **真实包含**的日期区间；请求超出 cov 范围 → 重新回源。

全部纯本地 SQLite + 假取数，零网络。
"""
import os
import tempfile

import pandas as pd
import pytest

from modules.fetcher_core import _build_cache_key
from modules.fetcher import StockFetcher


@pytest.fixture
def fetcher(monkeypatch):
    # 跳过股票库预热（避免 BaoStock 网络），并注入假取数。
    StockFetcher._stocks_loaded = True

    calls = {"n": 0}

    def fake_fetch_level(self, level, symbol, start, end, adjust):
        calls["n"] += 1
        dates = pd.date_range(start, end, freq="D")
        return pd.DataFrame({
            "date": [d.strftime("%Y-%m-%d") for d in dates],
            "open": [10.0] * len(dates),
            "close": [10.5] * len(dates),
            "high": [11.0] * len(dates),
            "low": [9.8] * len(dates),
            "volume": [1000] * len(dates),
        }), None

    monkeypatch.setattr(StockFetcher, "_fetch_level", fake_fetch_level)

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "t250.db")
    f = StockFetcher()
    f.db_path = db
    f._calls = calls
    return f


def _cov(f, symbol, adjust):
    return f._read_cache(
        f._get_conn(), "daily_cache",
        _build_cache_key("daily_fullcov", symbol=symbol, adjust=adjust),
        as_dataframe=False, max_age_seconds=10 ** 9,
    )


def test_wiring_fast_path_and_legacy_key(fetcher):
    symbol, adjust = "600519", "qfq"
    s1, e1 = "2024-01-01", "2024-03-31"

    df1 = fetcher.get_daily(symbol, start=s1, end=e1, adjust=adjust)
    assert df1 is not None and not df1.empty
    n_after_first = fetcher._calls["n"]
    assert n_after_first > 0  # 首次必然回源

    # 旧形态 daily 区间键仍被写入（向后兼容）
    conn = fetcher._get_conn()
    legacy = fetcher._read_cache(conn, "daily_cache",
                                 _build_cache_key("daily", symbol=symbol, start=s1, end=e1, adjust=adjust))
    assert legacy is not None and not legacy.empty

    # 覆盖区间已写入 daily_fullcov
    cov = _cov(fetcher, symbol, adjust)
    assert isinstance(cov, dict) and cov.get("start") and cov.get("end")

    # 二次请求落在 cov 区间内 → 命中 daily_full 快路径，不再回源
    s2, e2 = "2024-02-01", "2024-03-20"
    meta = {}
    df2 = fetcher.get_daily(symbol, start=s2, end=e2, adjust=adjust, meta_out=meta)
    assert df2 is not None and not df2.empty
    assert fetcher._calls["n"] == n_after_first  # 竞速调用数未增加
    assert meta.get("source") == "cache"
    # 切片确实落在请求窗口内
    dts = pd.to_datetime(df2["date"])
    assert (dts >= pd.Timestamp(s2)).all() and (dts <= pd.Timestamp(e2)).all()


def test_wiring_honest_coverage_re_sources_beyond_cov(fetcher):
    """请求超出 cov 真实区间 → 必须重新回源（绝不拿残缺序列冒充完整区间）。"""
    symbol, adjust = "000001", "qfq"
    s1, e1 = "2024-01-01", "2024-01-31"
    fetcher.get_daily(symbol, start=s1, end=e1, adjust=adjust)
    n = fetcher._calls["n"]

    # cov 真实区间 == 假取数实际日期范围（2024-01-01..2024-01-31）
    cov = _cov(fetcher, symbol, adjust)
    assert cov["start"] == "2024-01-01" and cov["end"] == "2024-01-31"

    # 请求一个超出 cov 的窗口 → 应重新回源
    fetcher.get_daily(symbol, start="2024-02-01", end="2024-02-28", adjust=adjust)
    assert fetcher._calls["n"] > n
