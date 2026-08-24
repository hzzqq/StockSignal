"""
tests/test_shepherd_range.py — 牧羊人指标自定义日期范围回溯

目标：
- 锁定 get_shepherd_history_range / get_shepherd_indicators_range 对 CSV 的过滤行为
- 验证 backfill=True 时对近期缺失日调用 fetch_zt_data_for_dates
- 验证未覆盖/缺失列在 meta 中正确标记，前端 caption 可用

全程离线：monkeypatch _read_history_csv / _trading_days_range / fetch_zt_data_for_dates。
"""
import pandas as pd
import pytest

from modules import shepherd


def _make_csv_df(start, periods):
    """构造模拟长历史 CSV 数据。"""
    dates = pd.date_range(start=start, periods=periods, freq="D")
    return pd.DataFrame({
        "date": dates,
        "up_count": [2000 + i for i in range(periods)],
        "down_count": [1500 + i for i in range(periods)],
        "limit_up": [40 + i for i in range(periods)],
        "limit_down": [5 + i for i in range(periods)],
        "zt_prev_ret": [1.0 + i * 0.1 for i in range(periods)],
        "red_ratio": [55.0 + i for i in range(periods)],
    })


def test_get_shepherd_history_range_filters_csv(monkeypatch):
    """按 start/end 正确过滤 CSV 行。"""
    full = _make_csv_df("2024-01-01", 20)
    monkeypatch.setattr(shepherd, "_read_history_csv", lambda days=None: full, raising=False)

    df = shepherd.get_shepherd_history_range("2024-01-05", "2024-01-10")
    assert len(df) == 6
    assert df["date"].min().strftime("%Y-%m-%d") == "2024-01-05"
    assert df["date"].max().strftime("%Y-%m-%d") == "2024-01-10"
    assert "up_count" in df.columns


def test_get_shepherd_history_range_backfill_recent_missing(monkeypatch):
    """backfill=True 且缺失日在最近 15 天内时，合并 zt 补算数据。"""
    today = pd.Timestamp.now().normalize()
    # CSV 只有 3 天，且不含 zt 类字段
    dates = [today - pd.Timedelta(days=i) for i in range(3, 0, -1)]
    full = pd.DataFrame({
        "date": dates,
        "up_count": [2000, 2100, 2200],
        "down_count": [1500, 1400, 1300],
        "red_ratio": [55.0, 58.0, 60.0],
    })
    monkeypatch.setattr(shepherd, "_read_history_csv", lambda days=None: full, raising=False)

    # 缺失昨天和今天
    missing = [today - pd.Timedelta(days=1), today]
    monkeypatch.setattr(shepherd, "_trading_days_range",
                        lambda start, end: [d for d in pd.date_range(start, end, freq="D") if d in missing],
                        raising=False)

    def _fake_fetch_zt(ds):
        rows = []
        for d in ds:
            rows.append({
                "date": pd.to_datetime(d),
                "limit_up": 99,
                "connect_hl": 8,
                "zt_fail_ratio": 20.0,
                "zt_prev_ret": 5.0,
            })
        return pd.DataFrame(rows)

    monkeypatch.setattr("modules.shepherd_reconstruct.fetch_zt_data_for_dates",
                        _fake_fetch_zt, raising=False)

    df = shepherd.get_shepherd_history_range(today - pd.Timedelta(days=4), today, backfill=True)
    assert not df.empty
    # 补上的「今天」limit_up == 99；昨天仍缺失（CSV 没 limit_up）
    today_mask = df["date"] == today
    assert df.loc[today_mask, "limit_up"].iloc[0] == 99
    # CSV 原有日期 red_ratio 仍在
    assert df["red_ratio"].notna().any()


def test_get_shepherd_history_range_empty_csv_returns_empty(monkeypatch):
    """CSV 不存在且 backfill=False 时返回空 DataFrame。"""
    monkeypatch.setattr(shepherd, "_read_history_csv", lambda days=None: None, raising=False)
    df = shepherd.get_shepherd_history_range("2020-01-01", "2020-01-31", backfill=False)
    assert df.empty


def test_get_shepherd_indicators_range_missing_columns_meta(monkeypatch):
    """所选时段内某列全为 NaN 时，meta.missing_columns 标注。"""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "up_count": [2000] * 5,
        "connect_hl": [float("nan")] * 5,
    })
    monkeypatch.setattr(shepherd, "get_shepherd_history_range",
                        lambda start, end, backfill=False: df, raising=False)

    _, meta = shepherd.get_shepherd_indicators_range("2024-01-01", "2024-01-05")
    assert "connect_hl" in meta["missing_columns"]
    assert "up_count" not in meta["missing_columns"]


def test_get_shepherd_indicators_range_unavailable_when_empty(monkeypatch):
    """日期范围无数据时，unavailable 包含全部 8 项指标。"""
    monkeypatch.setattr(shepherd, "get_shepherd_history_range",
                        lambda start, end, backfill=False: pd.DataFrame(columns=["date"]),
                        raising=False)
    df, meta = shepherd.get_shepherd_indicators_range("2010-01-01", "2010-01-31")
    assert df.empty
    assert set(k for k, _ in meta["unavailable"]) == set(shepherd.THRESHOLDS.keys())


def test_get_shepherd_indicators_range_date_range_meta(monkeypatch):
    """meta 正确带回 date_range。"""
    dates = pd.date_range("2024-06-01", periods=3, freq="D")
    df = pd.DataFrame({"date": dates, "up_count": [1, 2, 3]})
    monkeypatch.setattr(shepherd, "get_shepherd_history_range",
                        lambda start, end, backfill=False: df, raising=False)
    _, meta = shepherd.get_shepherd_indicators_range("2024-06-01", "2024-06-03")
    assert meta["date_range"] == ("2024-06-01", "2024-06-03")
