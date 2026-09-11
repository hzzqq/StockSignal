"""#90 守卫：modules.linear_trends 的共享纯函数 figure builder 已被 cached_fig 装饰。

这些函数被 11_/13_/15_/35_ 等多个 st_autorefresh 页复用，装饰后可在每次
脚本重跑（含交易时段每 30~60s 的自动刷新）时避免重复 rebuild 图形，降低 CPU。

守卫点：
1. 两个 builder 确为 cached_fig 包装（存在 __wrapped__）；
2. 在函数外部（无 Streamlit runtime）调用仍能正确返回 go.Figure（见
   cache_test 实证：st.cache_data 在外部仅告警不抛异常）；
3. 相同入参两次调用返回结构一致的 figure（纯函数语义未被缓存破坏）；
4. 装饰后函数名被改写为 xxx__cached，避免跨 builder 缓存键碰撞。
"""
import pandas as pd
import plotly.graph_objects as go

from modules import linear_trends as lt


def _sample_df():
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=5).astype(str),
        "A": [10, 11, 12, 11, 13],
        "B": [20, 19, 21, 22, 20],
    })


def test_plot_normalized_multi_is_cached_fig():
    assert hasattr(lt.plot_normalized_multi, "__wrapped__"), \
        "plot_normalized_multi 应被 @cached_fig 装饰（保留 __wrapped__）"
    assert lt.plot_normalized_multi.__name__.endswith("__cached")


def test_plot_correlation_heatmap_is_cached_fig():
    assert hasattr(lt.plot_correlation_heatmap, "__wrapped__"), \
        "plot_correlation_heatmap 应被 @cached_fig 装饰（保留 __wrapped__）"
    assert lt.plot_correlation_heatmap.__name__.endswith("__cached")


def test_plot_normalized_multi_pure_output():
    df = _sample_df()
    f1 = lt.plot_normalized_multi(df, dark_mode=True)
    f2 = lt.plot_normalized_multi(df, dark_mode=True)
    assert isinstance(f1, go.Figure)
    assert isinstance(f2, go.Figure)
    # 相同入参 → 相同 trace 数（纯函数语义）
    assert len(f1.data) == len(f2.data)
    assert len(f1.data) >= 1


def test_plot_correlation_heatmap_pure_output():
    df = _sample_df()
    f = lt.plot_correlation_heatmap(df, dark_mode=False)
    assert isinstance(f, go.Figure)
    assert len(f.data) == 1  # 单 Heatmap trace


def test_dark_mode_branches_independent_keys():
    """dark=True 与 dark=False 应视为不同缓存键（返回各自独立构建的 figure）。"""
    df = _sample_df()
    fd = lt.plot_normalized_multi(df, dark_mode=True)
    fl = lt.plot_normalized_multi(df, dark_mode=False)
    assert isinstance(fd, go.Figure)
    assert isinstance(fl, go.Figure)
    # 暗/浅色为不同入参 → 不同缓存键 → 不同 figure 对象（非同一引用）
    assert fd is not fl
    # 两者都应包含数据 trace（纯函数语义未被缓存破坏）
    assert len(fd.data) >= 1
    assert len(fl.data) >= 1
