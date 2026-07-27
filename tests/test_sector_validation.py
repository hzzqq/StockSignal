"""fetcher._validate_sector_data 板块数据校验单元测试。

防护板块涨跌数据异常展示（用户曾反馈每日晨报 83 个板块全 +0.00%）。
"""
import pandas as pd
import pytest

from modules.fetcher import _validate_sector_data


def _df(vals):
    return pd.DataFrame({"change_pct": vals})


def test_none_returns_false():
    assert _validate_sector_data(None) is False


def test_empty_returns_false():
    assert _validate_sector_data(pd.DataFrame()) is False


def test_missing_col_returns_false():
    assert _validate_sector_data(pd.DataFrame({"foo": [1, 2]})) is False


def test_too_few_samples_returns_false():
    assert _validate_sector_data(_df([1.0, -0.5])) is False


def test_all_up_returns_false():
    """全涨视为数据源异常。"""
    assert _validate_sector_data(_df([1.0, 0.5, 2.0, 0.3, 1.2])) is False


def test_all_down_returns_false():
    """全跌视为数据源异常。"""
    assert _validate_sector_data(_df([-1.0, -0.5, -2.0, -0.3, -1.2])) is False


def test_all_zero_returns_false():
    """全 0（休市/空缓存）不应展示。"""
    assert _validate_sector_data(_df([0, 0, 0, 0, 0])) is False


def test_extreme_value_returns_false():
    """涨跌幅绝对值 > 20% 视为异常。"""
    assert _validate_sector_data(_df([1.0, -0.5, 25.0, -1.0, 0.3])) is False


def test_normal_mixed_returns_true():
    assert _validate_sector_data(_df([1.0, -0.5, 2.0, -1.0, 0.3])) is True


def test_nan_treated_as_missing_not_all_zero():
    """含 NaN 的混合数据（dropna 后仍有 >=5 个有效样本且涨跌混合）应通过。"""
    df = pd.DataFrame({"change_pct": [1.0, -0.5, None, 2.0, -1.0, 0.8]})  # 5 个有效
    assert _validate_sector_data(df) is True
