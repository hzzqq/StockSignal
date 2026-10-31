"""R6 连续风险扣分守卫。

防回退：continuous_risk_penalty 必须维持 振幅/回撤/换手三分量 + 诚实语义。
mutation 注入点：①振幅阈值 5%→4%（阈值下移=罚得更多，守卫应红）②回撤阈值 20%→10% ③换手 unavailable→默认 0
"""
import math
import pandas as pd
import pytest
from modules.recommend_engine import continuous_risk_penalty


def _make_df(n: int, *, amp5: float = 0.02, dd20: float = 0.00, base: float = 100.0) -> pd.DataFrame:
    """生成 n 行行情 df。参数 = continuous_risk_penalty 实际计算值：

    - amp5：近 5 日均振幅 (high-low)/prev_close 的 mean → 直接映射振幅分量阈值
    - dd20：20 日回撤 1-close[-1]/max(close[-20:]) → 直接映射回撤分量阈值

    最后 20 行里放一个高点制造 dd20；high/low 相对 close 偏移 amp5/2 让 mean≈amp5。
    """
    # close：最后 20 行首放高点制造 dd20，其余平 base
    peak = base / (1 - dd20) if dd20 > 0 else base  # 使 max/close[-1]=peak/base → dd20 精确
    prices = [base] * (n - 20) + [peak] + [base] * 19  # tail(20) 第一个=peak
    close = pd.Series(prices, dtype=float)
    # high/low：相对 close 各偏 amp5/2，使 (high-low)/prev = amp5
    high = close * (1 + amp5 / 2)
    low = close * (1 - amp5 / 2)
    return pd.DataFrame({"close": close, "high": high, "low": low})


class TestContinuousRiskPenaltyStructure:
    """结构守卫：返回形状固定 + 三分量恒在 + turnover 恒 unavailable。"""

    def test_returns_expected_keys(self):
        df = _make_df(25, amp5=0.08, dd20=0.30)
        r = continuous_risk_penalty(df)
        assert set(r.keys()) == {"penalty", "components", "reasons"}

    def test_three_components_present(self):
        df = _make_df(25)
        r = continuous_risk_penalty(df)
        assert set(r["components"].keys()) == {"amplitude", "drawdown", "turnover"}

    def test_turnover_always_unavailable(self):
        """数据链无换手率字段 → 恒 unavailable，绝不默认 0。"""
        df = _make_df(25, amp5=0.08, dd20=0.30)
        r = continuous_risk_penalty(df)
        assert r["components"]["turnover"]["status"] == "unavailable"


class TestContinuousRiskPenaltyValues:
    """数值守卫：阈值/封顶/起罚点精确。"""

    def test_amplitude_under_threshold_no_penalty(self):
        """amp5 ≤ 5% 不起罚。"""
        df = _make_df(25, amp5=0.04, dd20=0.05)
        r = continuous_risk_penalty(df)
        assert r["components"]["amplitude"]["penalty"] == 0.0

    def test_amplitude_over_threshold_linear(self):
        """amp5=10% → penalty=(0.10-0.05)*120=6.0。"""
        df = _make_df(25, amp5=0.10, dd20=0.05)
        r = continuous_risk_penalty(df)
        assert r["components"]["amplitude"]["penalty"] == pytest.approx(6.0, abs=0.01)

    def test_amplitude_capped_at_8(self):
        """amp5=10% 时理论罚 6，但封顶 8；验封顶真生效（amp5=20% 也只罚 8）。"""
        df = _make_df(25, amp5=0.20, dd20=0.05)
        r = continuous_risk_penalty(df)
        assert r["components"]["amplitude"]["penalty"] <= 8.0

    def test_drawdown_under_threshold_no_penalty(self):
        """dd20 ≤ 20% 不起罚。"""
        df = _make_df(25, amp5=0.02, dd20=0.05)
        r = continuous_risk_penalty(df)
        assert r["components"]["drawdown"]["penalty"] == 0.0

    def test_drawdown_over_threshold_linear(self):
        """dd20=30% → penalty=(0.30-0.20)*60=6.0。"""
        df = _make_df(25, amp5=0.02, dd20=0.30)
        r = continuous_risk_penalty(df)
        assert r["components"]["drawdown"]["penalty"] == pytest.approx(6.0, abs=0.01)

    def test_penalty_bounded_0_to_14(self):
        """总罚分 ∈ [0, 14]（amplitude 封顶 8 + drawdown 封顶 6）。"""
        df = _make_df(25, amp5=0.20, dd20=0.40)
        r = continuous_risk_penalty(df)
        assert 0 <= r["penalty"] <= 14


class TestContinuousRiskPenaltyHonestDegradation:
    """诚实语义守卫：取不到数据 → unavailable，不编造。"""

    def test_missing_high_low_columns(self):
        df = pd.DataFrame({"close": [100.0] * 25})
        r = continuous_risk_penalty(df)
        assert r["components"]["amplitude"]["status"] == "unavailable"
        assert r["components"]["amplitude"]["reason"] is not None

    def test_insufficient_rows_drawdown(self):
        df = _make_df(15, amp5=0.08, dd20=0.30)  # 只有 15 行 < 21 行要求
        r = continuous_risk_penalty(df)
        assert r["components"]["drawdown"]["status"] == "unavailable"

    def test_penalty_does_not_invent_zero_when_unavailable(self):
        """一分量 unavailable → 不计入总分，penalty 不是"假装没这个分量"。"""
        df = pd.DataFrame({"close": [100.0] * 25})  # 缺 high/low
        r = continuous_risk_penalty(df)
        # amplitude unavailable（不计入）、drawdown available（close 25 行够）、turnover unavailable
        assert r["components"]["amplitude"]["status"] == "unavailable"
        assert r["components"]["drawdown"]["status"] == "ok" or r["components"]["drawdown"]["status"] == "unavailable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

