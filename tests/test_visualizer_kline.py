"""test_visualizer_kline.py — K 线图增强（modebar 收拢 / 拖拽 / 区间高低 / 空异常兜底）白盒测试。

对应 5 次自主迭代中的 Iter2~Iter4：
- Iter2: dragmode 参数 + modebar 收拢（仅保留 toImage / resetScale2d）
- Iter3: show_range_levels 在可见窗口画「区间最高 / 区间最低」
- Iter4: 空 / 字段缺失 / 数据不足 / 非数值 优雅兜底
"""

import numpy as np
import pandas as pd
import pytest

from modules.visualizer import Visualizer, _empty_kline_figure


def _make_df(n=10, start=100.0):
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    np.random.seed(7)
    closes = start + np.cumsum(np.random.randn(n))
    opens = closes + np.random.randn(n) * 0.5
    highs = np.maximum(opens, closes) + np.abs(np.random.randn(n))
    lows = np.minimum(opens, closes) - np.abs(np.random.randn(n))
    vols = np.random.randint(1_000, 9_000, n)
    return pd.DataFrame({
        "date": dates, "open": opens, "high": highs,
        "low": lows, "close": closes, "volume": vols,
    })


# ── Iter2: dragmode 参数 ──────────────────────────────────────
def test_dragmode_default_pan():
    fig = Visualizer.candlestick(_make_df())
    assert fig.layout.dragmode == "pan"


def test_dragmode_zoom_passed():
    fig = Visualizer.candlestick(_make_df(), dragmode="zoom")
    assert fig.layout.dragmode == "zoom"


def test_modebar_collapsed():
    fig = Visualizer.candlestick(_make_df())
    removed = fig.layout.modebar.remove
    # 收拢后只保留 toImage + resetScale2d，平移/缩放/框选按钮移除
    assert "pan2d" in removed
    assert "zoom2d" in removed
    assert "select2d" in removed
    assert "lasso2d" in removed
    assert "autoScale2d" in removed


def test_dragmode_does_not_alter_structure():
    fig = Visualizer.candlestick(_make_df(), dragmode="zoom")
    # 仍保持首 trace 为 K 线实体（Bar），兼容既有白盒测试
    assert fig.data[0].type == "bar"


# ── Iter3: 区间最高 / 最低 ───────────────────────────────────
def test_range_levels_shown_by_default():
    fig = Visualizer.candlestick(_make_df())
    texts = " ".join(str(a.text) for a in (fig.layout.annotations or []))
    assert "区间最高" in texts
    assert "区间最低" in texts


def test_range_levels_hidden_when_disabled():
    fig = Visualizer.candlestick(_make_df(), show_range_levels=False)
    texts = " ".join(str(a.text) for a in (fig.layout.annotations or []))
    assert "区间最高" not in texts
    assert "区间最低" not in texts


# ── Iter4: 空 / 异常兜底 ─────────────────────────────────────
def test_empty_none():
    fig = Visualizer.candlestick(None)
    assert fig.layout.annotations[0].text == "暂无 K 线数据"


def test_empty_missing_columns():
    df = _make_df().drop(columns=["high"])
    fig = Visualizer.candlestick(df)
    assert "K 线字段缺失" in fig.layout.annotations[0].text


def test_empty_too_few_rows():
    fig = Visualizer.candlestick(_make_df(n=1))
    assert "数据不足" in fig.layout.annotations[0].text


def test_nonnumeric_coerced_and_dropped():
    df = _make_df(n=5)
    # 注入非数值（object 列才能容纳字符串），应被 to_numeric coerce 丢弃
    df["close"] = df["close"].astype(object)
    df.loc[0, "close"] = "NaN"
    df.loc[1, "close"] = "abc"
    fig = Visualizer.candlestick(df)
    # 非兜底图（不出现 "暂无"/"字段缺失"/"数据不足" 提示），且能正常产出 K 线
    texts = " ".join(str(a.text) for a in (fig.layout.annotations or []))
    assert "暂无" not in texts
    assert "字段缺失" not in texts
    assert "数据不足" not in texts
    assert fig.data[0].type == "bar"


def test_empty_helper_function():
    fig = _empty_kline_figure("测试图", "自定义提示")
    assert fig.layout.annotations[0].text == "自定义提示"
