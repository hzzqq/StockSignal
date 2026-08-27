"""modules.perf.downsample 单元测试：降采样不破坏短序列、长序列收敛、首尾保留。"""
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.perf import downsample, downsample_series


def test_short_series_unchanged():
    df = pd.DataFrame({"x": range(100)})
    out = downsample(df, max_points=800)
    assert len(out) == 100
    assert list(out["x"]) == list(range(100))


def test_long_series_converges():
    df = pd.DataFrame({"x": range(5000)})
    out = downsample(df, max_points=800)
    assert len(out) <= 800
    assert len(out) >= 700  # 均匀采样不应过度丢点


def test_keep_first_last():
    df = pd.DataFrame({"x": range(5000)})
    out = downsample(df, max_points=500, keep_first=True, keep_last=True)
    assert out["x"].iloc[0] == 0
    assert out["x"].iloc[-1] == 4999


def test_drop_first_last():
    # keep_first/keep_last=False 时不应额外追加首尾行，结果长度等于均匀采样点数
    df = pd.DataFrame({"x": range(5000)})
    out = downsample(df, max_points=500, keep_first=False, keep_last=False)
    assert len(out) == 500
    # 保持首尾时长度不超过 max_points 且覆盖关键端点
    out2 = downsample(df, max_points=500, keep_first=True, keep_last=True)
    assert len(out2) <= 500
    assert out2["x"].iloc[0] == 0
    assert out2["x"].iloc[-1] == 4999


def test_no_index_leak():
    df = pd.DataFrame({"x": range(3000)})
    out = downsample(df, max_points=400)
    assert list(out.index) == list(range(len(out)))  # 索引已重置


def test_series_wrapper():
    s = pd.Series(range(2000))
    out = downsample_series(s, max_points=300)
    assert isinstance(out, pd.Series)
    assert len(out) <= 300
    assert out.iloc[0] == 0
    assert out.iloc[-1] == 1999


def test_empty():
    df = pd.DataFrame({"x": []})
    out = downsample(df)
    assert len(out) == 0
