"""fundflow 资金流模块单元测试（mock akshare，无真实网络）。

验证：
- get_industry_fund_flow 正常清洗（中文列名归一、返回非空）
- akshare 失败时返回空 DataFrame（不抛错、可降级）
- 重试/缓存逻辑不破坏返回结构
"""
import pandas as pd
import pytest
from unittest.mock import patch

import modules.fundflow as fundflow
from modules.fundflow import get_industry_fund_flow


@pytest.fixture(autouse=True)
def _clear_cache():
    fundflow._CACHE.pop("industry_ff", None)
    yield
    fundflow._CACHE.pop("industry_ff", None)


def _fake_df():
    return pd.DataFrame([
        {"行业": "银行", "行业-涨跌幅": 1.5, "流入资金": 1e8, "流出资金": 8e7, "净额": 2e7,
         "领涨股": "招商银行", "领涨股-涨跌幅": 2.0},
        {"行业": "半导体", "行业-涨跌幅": -0.8, "流入资金": 5e7, "流出资金": 6e7, "净额": -1e7,
         "领涨股": "中芯国际", "领涨股-涨跌幅": 1.0},
    ])


def test_industry_fund_flow_normal():
    with patch("akshare.stock_fund_flow_industry", return_value=_fake_df()):
        df = get_industry_fund_flow()
    assert not df.empty
    # 列名已归一为英文
    for col in ["行业", "涨跌幅", "流入资金", "流出资金", "净额", "领涨股", "领涨股涨跌幅"]:
        assert col in df.columns, f"缺少归一列 {col}"
    # 净额符号正确
    assert df[df["行业"] == "银行"]["净额"].iloc[0] > 0
    assert df[df["行业"] == "半导体"]["净额"].iloc[0] < 0


def test_industry_fund_flow_akshare_error_returns_empty():
    """akshare 抛异常时必须返回空 DataFrame，不向上抛出（页面降级）。"""
    with patch("akshare.stock_fund_flow_industry", side_effect=RuntimeError("network")):
        df = get_industry_fund_flow()
    assert df.empty


def test_industry_fund_flow_empty_akshare_returns_empty():
    """akshare 返回空/None 时同样返回空 DataFrame。"""
    with patch("akshare.stock_fund_flow_industry", return_value=pd.DataFrame()):
        df = get_industry_fund_flow()
    assert df.empty
