"""stock_screener 纯逻辑单元测试。

不触发网络/IO（不实例化 StockScreener，不调用 StockFetcher）：
- 数据清洗 _norm_price / _norm_col 的中文列名归一正确性
- 策略元信息一致性（STRATEGY_NAMES_CN 与 DEFAULT_PARAMS 键必须一一对应，
  否则运行时新增策略漏配参数会 KeyError）
- 行业 PE 基准表完整性
"""
import pandas as pd
import pytest

from modules.stock_screener import (
    DEFAULT_PARAMS,
    STRATEGY_NAMES_CN,
    _INDUSTRY_PE_BENCHMARK,
    _norm_col,
    _norm_price,
)


# ───────────────────────── 价格列名归一 ─────────────────────────
def test_norm_price_vol_alias():
    df = pd.DataFrame({"close": [1], "vol": [100]})
    out = _norm_price(df)
    assert "volume" in out.columns
    assert out["volume"].iloc[0] == 100


def test_norm_price_volume_alias():
    df = pd.DataFrame({"close": [1], "volume": [200]})
    out = _norm_price(df)
    assert "vol" in out.columns
    assert out["vol"].iloc[0] == 200


def test_norm_price_pct_alias():
    df = pd.DataFrame({"close": [1], "pct_chg": [3.0]})
    out = _norm_price(df)
    assert "change_pct" in out.columns
    assert out["change_pct"].iloc[0] == 3.0


def test_norm_price_none_passthrough():
    assert _norm_price(None) is None


def test_norm_price_empty_passthrough():
    df = pd.DataFrame()
    assert _norm_price(df).empty


def test_norm_price_preserves_original():
    df = pd.DataFrame({"close": [10], "volume": [5], "change_pct": [1.5]})
    out = _norm_price(df)
    # 原列仍在，补齐的别名也加上
    assert "close" in out.columns and "volume" in out.columns
    assert "vol" in out.columns and "pct_chg" in out.columns


# ───────────────────────── 中文列名归一 ─────────────────────────
def test_norm_col_chinese_to_english():
    df = pd.DataFrame({"净资产收益率": [0.15], "资产负债率": [0.5]})
    mapping = {"roe": ["净资产收益率"], "debt_ratio": ["资产负债率"]}
    out = _norm_col(df, mapping)
    assert "roe" in out.columns
    assert "debt_ratio" in out.columns
    assert out["roe"].iloc[0] == 0.15


def test_norm_col_no_match_leaves_untouched():
    df = pd.DataFrame({"随机列": [1]})
    out = _norm_col(df, {"roe": ["净资产收益率"]})
    assert "随机列" in out.columns
    assert "roe" not in out.columns


# ───────────────────────── 策略元信息一致性 ─────────────────────────
def test_strategy_meta_consistency():
    """STRATEGY_NAMES_CN 与 DEFAULT_PARAMS 的键必须一一对应。"""
    assert set(STRATEGY_NAMES_CN.keys()) == set(DEFAULT_PARAMS.keys()), (
        "策略名与默认参数键不一致，新增策略漏配参数会在运行时 KeyError"
    )


def test_all_strategies_have_top_n_param():
    """每个策略默认参数都应含 top_n（排序/截断需要）。"""
    for name, params in DEFAULT_PARAMS.items():
        assert "top_n" in params, f"{name} 缺少 top_n 参数"


def test_industry_pe_benchmark_sane():
    assert len(_INDUSTRY_PE_BENCHMARK) > 0
    for k, v in _INDUSTRY_PE_BENCHMARK.items():
        assert isinstance(v, (int, float)) and v > 0, f"行业 {k} 的 PE 基准 {v} 非法"
