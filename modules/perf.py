"""前端性能工具：大时间序列降采样，降低 Plotly 图表 JSON 体积与渲染开销。

适用于：资金流向历史序列、板块轮动时序、回测权益曲线、基本面长周期图表等
可能返回上千点的 DataFrame。Streamlit 会将整段序列序列化为 JSON 下发前端，
点数越多网络/解析/渲染越慢；在视觉无损的前提下均匀降采样可显著减负。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def downsample(
    df: pd.DataFrame,
    max_points: int = 800,
    keep_first: bool = True,
    keep_last: bool = True,
) -> pd.DataFrame:
    """对 DataFrame 按行做均匀降采样，返回 ≤ max_points 行的副本。

    - 行数不超过 max_points 时原样返回（不破坏短序列精度）。
    - 超过时按等间距取点，并可选保留首/尾行（时间序列首尾通常是关键拐点）。
    - 采样后重置索引（drop=True），避免原索引被当作类别轴造成 Plotly 抖动。

    Args:
        df: 待降采样的 DataFrame（按时间升序最佳，但本函数不依赖索引语义）。
        max_points: 目标最大点数。
        keep_first: 是否强制保留第 0 行。
        keep_last: 是否强制保留最后一行。

    Returns:
        降采样后的新 DataFrame（副本，不修改入参）。
    """
    n = len(df)
    if n == 0 or n <= max_points:
        return df.copy()

    if max_points <= 1:
        # 退化情况：最多 1 个点
        if keep_last and not keep_first:
            return df.iloc[[-1]].reset_index(drop=True)
        return df.iloc[[0]].reset_index(drop=True)

    # 先为强制保留的首/尾预留名额，均匀采样剩余点数，保证总数 ≤ max_points
    forced = (1 if keep_first else 0) + (1 if keep_last else 0)
    uniform_count = max(0, max_points - forced)
    if uniform_count == 0:
        # 仅保留首/尾
        idx = []
        if keep_first:
            idx.append(0)
        if keep_last:
            idx.append(n - 1)
        return df.iloc[idx].reset_index(drop=True)

    step = n / uniform_count
    indices = [int(round(i * step)) for i in range(uniform_count)]
    seen: set[int] = set()
    unique_idx: list[int] = []
    for i in indices:
        i = max(0, min(n - 1, i))
        if i not in seen:
            seen.add(i)
            unique_idx.append(i)
    unique_idx.sort()

    if keep_first and 0 not in seen:
        unique_idx = [0] + unique_idx
    if keep_last and (n - 1) not in seen:
        unique_idx.append(n - 1)

    return df.iloc[unique_idx].reset_index(drop=True)


def downsample_series(
    series: pd.Series,
    max_points: int = 800,
    keep_first: bool = True,
    keep_last: bool = True,
) -> pd.Series:
    """对 Series 做均匀降采样（便捷封装，见 :func:`downsample`）。"""
    df = series.to_frame("__v__")
    out = downsample(df, max_points=max_points, keep_first=keep_first, keep_last=keep_last)
    return out["__v__"].reset_index(drop=True)
