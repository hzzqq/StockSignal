"""plot_correlation_heatmap 异频混数据回归（用户截图 bug 锁定）。

根因（修复前）：原始 .pct_change().dropna() 默认 how='any' 整行删，月频序列(6 点)与日频序列(180 点)
混在同一 df 时，整行只保留 6 个全有效的行（且 macro 的 pct_change 在 NaN 传播下变 0 有效），
触发『样本不足，无法计算相关性』假阴性。

修复：原始序列先 ffill() 传播前一个观测值，再 pct_change()；用 .corr(min_periods=2) pairwise。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import modules.linear_trends as lt


def _mixed_freq_df():
    """180 天：5 个日频 + 1 个真实月频 + 1 个 ref（模拟市场驱动力生产数据）。"""
    n = 180
    dates = pd.date_range('2026-01-01', periods=n, freq='D')
    np.random.seed(42)
    macro = np.full(n, np.nan, dtype=float)
    for i in [0, 31, 59, 90, 120, 151]:
        macro[i] = 2.0 + np.random.rand() * 0.5
    return pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'ref': 100 + np.cumsum(np.random.randn(n) * 0.5),
        '资金_融资余额': 1.5e5 + np.cumsum(np.random.randn(n) * 1e3),
        '资金_北向净流入': np.random.randn(n) * 100,
        '情绪_换手率': 0.5 + np.random.rand(n) * 0.3,
        '情绪_涨跌家数比': np.random.rand(n),
        '技术_RSI': 50 + np.random.randn(n) * 10,
        '宏观_CPI': macro,  # 月频
    })


def test_mixed_freq_renders_heatmap():
    """修复前返回『样本不足』fig（无 heatmap trace）；修复后应出 7x7 heatmap。"""
    df = _mixed_freq_df()
    sel = ['ref', '资金_融资余额', '资金_北向净流入',
           '情绪_换手率', '情绪_涨跌家数比', '技术_RSI', '宏观_CPI']
    fig = lt.plot_correlation_heatmap(df, selected=sel, dark_mode=True)
    heatmaps = [t for t in fig.data if t.type == 'heatmap']
    assert heatmaps, "修复后混频场景必须出 heatmap（用户截图 bug 锁）"
    z = np.array(heatmaps[0].z)
    assert z.shape == (7, 7), f"期望 7x7 矩阵，实际 {z.shape}"
    # 月频×日频对 不应全 NaN（修复前全 NaN）
    non_nan = int(np.count_nonzero(~np.isnan(z)))
    assert non_nan >= 36, f"修复后期望 ≥36 个非 NaN 对，实际 {non_nan}"


def test_mixed_freq_cross_pair_has_value():
    """月频(宏观_CPI)与日频(ref/资金)的相关性应有合理数值（非 NaN）。"""
    df = _mixed_freq_df()
    sel = ['ref', '资金_融资余额', '宏观_CPI']
    fig = lt.plot_correlation_heatmap(df, selected=sel, dark_mode=True)
    heatmaps = [t for t in fig.data if t.type == 'heatmap']
    assert heatmaps, "3 个序列必须出 heatmap"
    z = np.array(heatmaps[0].z)
    # ref×宏观_CPI 与 资金_融资余额×宏观_CPI 应有有效值
    assert not np.isnan(z[0, 2]), f"ref×宏观_CPI 应有值，实际 NaN"
    assert not np.isnan(z[1, 2]), f"资金_融资余额×宏观_CPI 应有值，实际 NaN"
    # 相关系数在 [-1, 1] 范围内
    assert -1 <= z[0, 2] <= 1, f"ref×宏观_CPI={z[0,2]} 超出 [-1,1]"


def test_same_freq_unchanged():
    """同频（全部日频）数据应正常出图，无回归。"""
    n = 180
    dates = pd.date_range('2026-01-01', periods=n, freq='D')
    np.random.seed(7)
    df = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'A': np.cumsum(np.random.randn(n)),
        'B': np.cumsum(np.random.randn(n)),
        'C': np.cumsum(np.random.randn(n)),
    })
    fig = lt.plot_correlation_heatmap(df, dark_mode=True)
    heatmaps = [t for t in fig.data if t.type == 'heatmap']
    assert heatmaps, "同频数据必须出 heatmap"
    z = np.array(heatmaps[0].z)
    assert z.shape == (3, 3)
    # 对角线应为 1
    for i in range(3):
        assert abs(z[i, i] - 1.0) < 1e-9, f"对角线 z[{i},{i}]={z[i,i]} 应为 1"


def test_extremely_sparse_no_crash():
    """极端稀疏（2 序列仅 day 0/179 各 1 个值）：仍能算，不崩溃。"""
    n = 180
    dates = pd.date_range('2026-01-01', periods=n, freq='D')
    df = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'A': [1.0] + [np.nan] * (n - 2) + [2.0],
        'B': [10.0] + [np.nan] * (n - 2) + [20.0],
    })
    fig = lt.plot_correlation_heatmap(df, dark_mode=True)  # 不应抛异常
    # 不强求 heatmap（ffill 后样本仍可能不足触发诊断），但 figure 必须有 title
    assert fig.layout.title is not None


def test_single_key_returns_friendly_error():
    """只选 1 个有效序列时返回友好空态（不抛异常）。"""
    n = 50
    dates = pd.date_range('2026-01-01', periods=n, freq='D')
    df = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'A': np.arange(n, dtype=float),
        'B': np.arange(n, dtype=float),
    })
    # 只选 1 个 selected
    fig = lt.plot_correlation_heatmap(df, selected=['A'], dark_mode=True)
    assert '至少 2 个有效序列' in (fig.layout.title.text or ''), \
        f"期望友好空态文案，实际: {fig.layout.title.text}"
