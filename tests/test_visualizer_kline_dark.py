"""
tests/test_visualizer_kline_dark.py
==================================
回归：暗夜模式下 K 线图（Visualizer.candlestick）不得出现「左上文字重合」。

背景（memory flagged 真实 UI 缺陷 + c46853e 修复）：
- 旧实现图例默认在左上角，与 plotly 默认左对齐主标题在暗色模板下文字叠在一起；
- show_volume=False 时 subplot_titles=(title,) 还会在左上角再叠加一份与主标题相同的
  文字，造成双标题重合。

本测试在强制暗色模式下渲染 K 线图，断言：
- 主标题居中(x=0.5, xanchor=center) 且文字颜色为暗色主题文字色；
- 图例移到右上角(yanchor=top, xanchor=right)，避开左上；
- 不存在与主标题文字相同的 subplot 标题注释（杜绝双标题重合）。
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import visualizer
from modules.visualizer import Visualizer, SF_TXT  # noqa: E402


def _sample_df(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=n, freq="D")
    base = np.linspace(100, 120, n)
    return pd.DataFrame({
        "date": idx,
        "open": base + np.random.uniform(-1, 1, n),
        "high": base + np.random.uniform(0.5, 2, n),
        "low": base - np.random.uniform(0.5, 2, n),
        "close": base + np.random.uniform(-1, 1, n),
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    })


@pytest.fixture
def dark(monkeypatch):
    monkeypatch.setattr(visualizer, "_is_dark", lambda: True)
    return True


def _has_duplicate_title_annotation(fig, title: str) -> bool:
    """subplot 标题会以 layout.annotations 形式存在；返回是否存在文字==title 的注释。"""
    anns = getattr(fig.layout, "annotations", None) or []
    return any(getattr(a, "text", None) == title for a in anns)


class TestKlineDarkLayout:
    def test_show_volume_true_no_overlap(self, dark):
        fig = Visualizer.candlestick(_sample_df(), title="测试K线", show_volume=True)
        assert fig.layout.title.text == "测试K线"
        assert fig.layout.title.x == 0.5
        assert fig.layout.title.xanchor == "center"
        assert fig.layout.title.font.color == SF_TXT
        assert fig.layout.legend.yanchor == "top"
        assert fig.layout.legend.xanchor == "right"
        assert not _has_duplicate_title_annotation(fig, "测试K线")

    def test_show_volume_false_no_duplicate_left_title(self, dark):
        fig = Visualizer.candlestick(_sample_df(), title="测试K线无量", show_volume=False)
        assert fig.layout.title.text == "测试K线无量"
        assert fig.layout.title.x == 0.5
        assert fig.layout.title.xanchor == "center"
        assert fig.layout.title.font.color == SF_TXT
        assert fig.layout.legend.yanchor == "top"
        assert fig.layout.legend.xanchor == "right"
        # 关键：不再因 subplot_titles=(title,) 在左上角产生第二份标题
        assert not _has_duplicate_title_annotation(fig, "测试K线无量")

    def test_light_mode_title_still_centered(self, monkeypatch):
        monkeypatch.setattr(visualizer, "_is_dark", lambda: False)
        fig = Visualizer.candlestick(_sample_df(), title="亮色K线", show_volume=True)
        assert fig.layout.title.x == 0.5
        assert fig.layout.title.xanchor == "center"
        assert not _has_duplicate_title_annotation(fig, "亮色K线")
