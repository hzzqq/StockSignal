# -*- coding: utf-8 -*-
"""锐评 R3 守卫：批量/参数扫描回测把「已是百分比」的指标再 ×100（100 倍膨胀）。

根因：BacktestResult.total_return / max_drawdown / win_rate / annualized_return_pct
以及 run_batch summary 的 avg_total_return/avg_max_drawdown/avg_win_rate、
run_param_scan 的 total_return/annualized_return/max_drawdown/win_rate 返回值本身
已是百分比（构造时已 ×100），但 pages/30_策略回测.py 的批量/参数扫描展示路径又乘了 100，
导致 +25% 显示为 +2500%。同文件其他展示路径(581/797/839/840/946)均未 ×100，证明此处是 bug。
修复：pages/30_策略回测.py 移除这 11 处多余的 ×100（params 小数与 grid 比率标签的 ×100 保留）。
"""
import io
import os

import pandas as pd
import pytest

from modules.backtest import BacktestResult

PAGE = os.path.join(os.path.dirname(__file__), "..", "pages", "30_策略回测.py")

# 11 处被移除的膨胀模式（必须与 fix_r3 删除的完全一致）
BUGGY_PATTERNS = [
    "r['total_return']*100",
    "r['annualized_return']*100",
    "r['max_drawdown']*100",
    "r['win_rate']*100",
    "best['total_return']*100",
    "summary['avg_total_return']*100",
    "summary['avg_max_drawdown']*100",
    "res.total_return*100",
    "res.annualized_return_pct*100",
    "res.max_drawdown*100",
    "res.win_rate*100",
]


def _make_result(total_return_pct=25.0, max_drawdown_pct=-5.0, trades=None):
    """构造一个 BacktestResult，其累计收益/回撤已是百分比刻度。"""
    df = pd.DataFrame({
        "cumulative_return": [10.0, total_return_pct],
        "drawdown": [0.0, max_drawdown_pct],
        "daily_return": [1.0, 1.0],
        "total_asset": [100000.0, 125000.0],
        "position": [0, 0],
        "close": [10.0, 12.5],
        "ma20": [9.0, 9.0],
        "ma60": [8.0, 8.0],
        "rsi2": [50, 50],
        "rsi14": [50, 50],
    })
    return BacktestResult("600519", "multi_factor", df, 100000.0,
                          trades=trades or [{"profit_pct": 3.0}, {"profit_pct": 2.0}])


def test_backtestresult_is_percentage_scale():
    """属性返回值本身已是百分比（构造时已 ×100），页面绝不能再 ×100。"""
    r = _make_result(total_return_pct=25.0, max_drawdown_pct=-5.0)
    # 累计收益 +25% → 属性应为 25.0（而非 0.25）
    assert r.total_return == 25.0, f"total_return 应为百分比 25.0，实际 {r.total_return}"
    # 回撤 -5% → 属性应为 -5.0（而非 -0.05）
    assert r.max_drawdown == -5.0, f"max_drawdown 应为百分比 -5.0，实际 {r.max_drawdown}"
    # 2 笔全盈利 → 胜率 100.0（百分比）
    assert r.win_rate == 100.0, f"win_rate 应为百分比 100.0，实际 {r.win_rate}"
    # 年化收益率应为百分比刻度（有限浮点，非 None/NaN）
    ann = r.annualized_return_pct
    assert ann is not None and pd.notna(ann), "annualized_return_pct 不应为 None/NaN"
    assert isinstance(ann, float)


def test_old_bug_inflates_100x_negative_verification():
    """负向验证：复现 OLD 页面表达式产出 100× 膨胀；修复后表达式正确。"""
    total_return = 25.0  # BacktestResult.total_return 已是百分比
    old_disp = f"{total_return*100:+.2f}%"      # 复现修复前的页面代码
    new_disp = f"{total_return:+.2f}%"           # 修复后
    assert old_disp == "+2500.00%", f"旧代码把 +25% 膨胀成 {old_disp}（100× 膨胀 bug）"
    assert new_disp == "+25.00%", f"修复后应显示 {new_disp}"


def test_page_no_double_percent():
    """回归守卫：页面文件不得再出现「已是百分比的指标 ×100」膨胀模式。"""
    with io.open(PAGE, "r", encoding="utf-8") as f:
        src = f.read()
    for pat in BUGGY_PATTERNS:
        assert pat not in src, f"页面仍存在膨胀模式: {pat!r}"
    # params 小数 / grid 比率标签的 ×100 必须保留（未被误删）
    assert "take_profit_pct', 0)*100" in src or "take_profit_pct',0)*100" in src
    assert "g*100:.0f" in src


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
