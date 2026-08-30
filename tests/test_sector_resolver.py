"""
tests/test_sector_resolver.py
===========================
回归：resolve_sector_df 必须**永远返回 pandas.DataFrame**（失败/两源皆空时返回空 DataFrame，
绝不返回 None），否则上层 `if not sector_df.empty` 会在 None 上抛 AttributeError 崩页。

复现历史 bug：get_sector_list() -> None 且 get_industry_fund_flow() -> None 时，
旧内联逻辑把 sector_df 残留为 None，导致 E_基本面分析 整页崩溃。
"""
from __future__ import annotations

import pandas as pd
import pytest

from modules.fundamental_helpers import resolve_sector_df


def _sector_df():
    return pd.DataFrame({"sector": ["白酒", "银行"], "change_pct": ["1.2%", "-0.5%"]})


def _ff_df_ok():
    return pd.DataFrame({"行业": ["白酒", "银行"], "涨跌幅": ["1.2%", "-0.5%"]})


def _ff_df_bad_cols():
    return pd.DataFrame({"foo": [1, 2], "bar": [3, 4]})


def test_primary_source_valid_returns_normalized_df():
    out = resolve_sector_df(lambda: _sector_df(), lambda: _ff_df_ok())
    assert isinstance(out, pd.DataFrame)
    assert not out.empty
    assert "change_pct" in out.columns
    # 涨跌幅已规整为数值
    assert pd.api.types.is_numeric_dtype(out["change_pct"])


def test_primary_none_fallback_valid_returns_renamed_df():
    out = resolve_sector_df(lambda: None, lambda: _ff_df_ok())
    assert isinstance(out, pd.DataFrame)
    assert not out.empty
    assert list(out.columns) == ["sector", "change_pct"]
    assert pd.api.types.is_numeric_dtype(out["change_pct"])


def test_both_sources_none_returns_empty_dataframe_not_none():
    # 历史崩溃路径：两源皆 None 时旧逻辑残留 None -> 上层 .empty 抛 AttributeError
    out = resolve_sector_df(lambda: None, lambda: None)
    assert isinstance(out, pd.DataFrame)
    assert out.empty  # 关键：是空 DataFrame，不是 None


def test_primary_none_fallback_bad_columns_returns_empty_dataframe():
    # fallback 缺必需列 -> 不能返回 None，必须收敛为空 DataFrame
    out = resolve_sector_df(lambda: None, lambda: _ff_df_bad_cols())
    assert isinstance(out, pd.DataFrame)
    assert out.empty


def test_primary_empty_fallback_valid():
    out = resolve_sector_df(lambda: pd.DataFrame(), lambda: _ff_df_ok())
    assert isinstance(out, pd.DataFrame)
    assert not out.empty


def test_primary_raises_fallback_valid():
    def _boom():
        raise RuntimeError("network down")
    out = resolve_sector_df(_boom, lambda: _ff_df_ok())
    assert isinstance(out, pd.DataFrame)
    assert not out.empty


def test_both_raise_returns_empty_dataframe():
    def _boom():
        raise RuntimeError("down")
    out = resolve_sector_df(_boom, _boom)
    assert isinstance(out, pd.DataFrame)
    assert out.empty


def test_source_level_no_residual_none_pattern():
    """源码级防回退：22_基本面分析.py 的 sector 解析已委托给 resolve_sector_df
    （含 'ff.get_industry_fund_flow' 作为第二入参），不再内联残留 None 的风险路径。"""
    import pathlib
    src = pathlib.Path("pages/22_基本面分析.py").read_text(encoding="utf-8")
    assert "resolve_sector_df(fetcher.get_sector_list, ff.get_industry_fund_flow)" in src
