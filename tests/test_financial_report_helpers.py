"""个股财报片段纯函数测试（真实回归，非伪绿）。

覆盖 modules.financial_report_helpers 的格式化/过滤/着色逻辑，并用构造的
「与 get_earnings_report 真实返回列一致」的 DataFrame 验证按代码过滤链路。

关键回归护栏：fr_color_yoy 对正同比必须返回「红」(UP_COLOR=#ff4d4f)，
对负同比必须返回「绿」(DOWN_COLOR=#00d486)。此前 20页 误用「绿涨红跌」例外的
RED 变量（实为绿色 #009e60），导致业绩着色与 caption/16页 相反——本测试锁死该反转。
"""
import pandas as pd

from modules.colors import UP_COLOR, DOWN_COLOR, HOLD_COLOR
from modules.financial_report_helpers import (
    fr_fmt,
    fr_filter_by_code,
    fr_color_yoy,
    fr_format_financial_df,
)


# ───────────────────────── fr_fmt ─────────────────────────
def test_fr_fmt_big_to_yi():
    assert fr_fmt(92278072083.21) == "922.78亿"


def test_fr_fmt_medium_to_wan():
    # 明确落在万区间（5.47e6）
    assert fr_fmt(5470291.235) == "547.03万"
    assert fr_fmt(123456.0) == "12.35万"


def test_fr_fmt_small_as_is():
    assert fr_fmt(35.57) == "35.57"


def test_fr_fmt_none_and_nan():
    assert fr_fmt(None) == "—"
    assert fr_fmt(float("nan")) == "—"


# ───────────────────────── fr_filter_by_code ─────────────────────────
def _fake_earnings_df():
    """模拟 get_earnings_report 的真实返回（代码列名为「代码」，指标列齐全）。"""
    return pd.DataFrame([
        {"代码": "600519", "名称": "贵州茅台", "每股收益": 12.34, "营业总收入": 92278072083.21,
         "净利润": 46033330566.78, "ROE%": 18.2, "净利润同比%": 15.6, "营收同比%": 9.8, "披露时间": "2026-08-15"},
        {"代码": "000001", "名称": "平安银行", "每股收益": 1.2, "营业总收入": 1000000000.0,
         "净利润": 500000000.0, "ROE%": 10.0, "净利润同比%": -3.1, "营收同比%": 2.0, "披露时间": "2026-08-20"},
    ])


def test_fr_filter_by_code_hit():
    df = _fake_earnings_df()
    row = fr_filter_by_code(df, "600519")
    assert row is not None and not row.empty
    assert row.iloc[0]["名称"] == "贵州茅台"


def test_fr_filter_by_code_zfill():
    """ticker 可能不带前导零（如 1 → 000001）。"""
    df = _fake_earnings_df()
    row = fr_filter_by_code(df, "1")
    assert row is not None and not row.empty
    assert row.iloc[0]["代码"] == "000001"


def test_fr_filter_by_code_miss():
    df = _fake_earnings_df()
    assert fr_filter_by_code(df, "999999") is None or fr_filter_by_code(df, "999999").empty


def test_fr_filter_by_code_alt_column_name():
    """业绩预告原始 df 用「股票代码」列名，应自适应命中。"""
    df = pd.DataFrame([{"股票代码": "600519", "股票简称": "贵州茅台", "预告类型": "预增"}])
    row = fr_filter_by_code(df, "600519")
    assert row is not None and not row.empty
    assert row.iloc[0]["预告类型"] == "预增"


def test_fr_filter_by_code_none_df():
    assert fr_filter_by_code(None, "600519") is None


# ───────────────────────── fr_color_yoy（回归护栏核心） ─────────────────────────
def test_fr_color_yoy_positive_is_red():
    color, txt = fr_color_yoy(15.6)
    assert color == UP_COLOR, "正同比必须红(改善)，不得是绿涨例外的绿"
    assert color == "#ff4d4f", "A股默认红涨：改善=红 #ff4d4f"
    assert txt == "+15.60%"


def test_fr_color_yoy_negative_is_green():
    color, txt = fr_color_yoy(-3.1)
    assert color == DOWN_COLOR, "负同比必须绿(下滑)"
    assert color == "#00d486", "A股默认绿跌：下滑=绿 #00d486"
    assert txt == "-3.10%"


def test_fr_color_yoy_zero_is_amber():
    color, txt = fr_color_yoy(0.0)
    assert color == HOLD_COLOR
    assert txt == "0.00%"


def test_fr_color_yoy_invalid_is_amber():
    color, txt = fr_color_yoy("N/A")
    assert color == HOLD_COLOR
    assert txt == "—"


# ───────────────────────── fr_format_financial_df ─────────────────────────
def _fake_sina_income():
    """模拟新浪利润表宽表（行=报告期，列=科目）。"""
    return pd.DataFrame([
        {"报告日": 20260630, "营业总收入": 92278072083.21, "净利润": 46033330566.78,
         "基本每股收益": 35.57, "数据源": "新浪", "是否审计": "未审计", "公告日期": "2026-08-15",
         "币种": "CNY", "类型": "合并期末", "更新日期": "2026-08-14T20:50:10"},
        {"报告日": 20260331, "营业总收入": 54702912385.23, "净利润": 28153831489.89,
         "基本每股收益": 21.76, "数据源": "新浪", "是否审计": "未审计", "公告日期": "2026-04-25",
         "币种": "CNY", "类型": "合并期末", "更新日期": "2026-04-24T19:20:06"},
    ])


def test_fr_format_financial_df_amounts():
    out = fr_format_financial_df(_fake_sina_income())
    # 大数 → 亿
    assert out.iloc[0]["营业总收入"] == "922.78亿"
    assert out.iloc[0]["净利润"] == "460.33亿"
    # 小数科目保留原值
    assert out.iloc[0]["基本每股收益"] == "35.57"
    # 标识列原样保留
    assert out.iloc[0]["报告日"] == 20260630
    assert out.iloc[0]["数据源"] == "新浪"
    assert out.iloc[0]["是否审计"] == "未审计"


def test_fr_format_financial_df_returns_copy():
    src = _fake_sina_income()
    out = fr_format_financial_df(src)
    # 不修改入参
    assert src.iloc[0]["营业总收入"] == 92278072083.21
    assert out is not src


def test_fr_format_financial_df_empty():
    import pandas as pd
    assert fr_format_financial_df(pd.DataFrame()) is not None
    assert fr_format_financial_df(None) is None
