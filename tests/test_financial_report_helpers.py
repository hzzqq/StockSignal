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
    fr_period_label,
    fr_build_history,
    fr_history_metrics,
    fr_expand_rows,
    fr_yoy_column,
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

# ══════════════════════════════════════════════════════════════════════════
# 横向历史对比（v3 · 2026-09-13）：fr_period_label / fr_build_history /
# fr_history_metrics / fr_expand_rows
# ══════════════════════════════════════════════════════════════════════════

def test_fr_period_label_quarter_suffixes():
    assert fr_period_label("20251231") == "2025年报"
    assert fr_period_label("20260331") == "2026一季报"
    assert fr_period_label("20260630") == "2026中报"
    assert fr_period_label("20260930") == "2026三季报"


def test_fr_period_label_passthrough_when_unparseable():
    assert fr_period_label("2025年报") == "2025年报"   # 非 8 位数字，原样
    assert fr_period_label("20269999") == "20269999"   # 非法 mmdd，原样
    assert fr_period_label("") == ""


def _one_row(code, eps, rev, rev_yoy, ni, ni_yoy, roe):
    """构造与 get_earnings_report 输出同构的「单行」结果。"""
    return pd.DataFrame([{
        "代码": code, "名称": "测试股", "每股收益": eps,
        "营业总收入": rev, "营收同比%": rev_yoy,
        "净利润": ni, "净利润同比%": ni_yoy, "ROE%": roe,
    }])


def test_fr_build_history_merges_and_sorts_ascending():
    rows = [
        ("20251231", _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0)),
        ("20231231", _one_row("600519", 50.0, 1.4e11, 10.0, 7.0e10, 9.0, 30.0)),
        ("20241231", _one_row("600519", 55.0, 1.5e11, 7.0, 7.5e10, 6.0, 31.0)),
    ]
    df = fr_build_history(rows)
    assert list(df["报告期"]) == ["20231231", "20241231", "20251231"], "必须按报告期升序（旧→新）"
    assert list(df["报告期标签"]) == ["2023年报", "2024年报", "2025年报"]
    assert df["净利润"].iloc[-1] == 8.2e10
    assert df["净利润同比%"].iloc[0] == 9.0


def test_fr_build_history_skips_missing_periods_without_fabricating():
    """缺失期必须跳过（不补零/不插空行），避免把「没披露」伪造成「0」。"""
    rows = [
        ("20231231", _one_row("600519", 50.0, 1.4e11, 10.0, 7.0e10, 9.0, 30.0)),
        ("20241231", None),                       # 未披露
        ("20241231", pd.DataFrame()),             # 空表
        ("20251231", _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0)),
    ]
    df = fr_build_history(rows)
    assert len(df) == 2, "缺失期不得占位"
    assert list(df["报告期"]) == ["20231231", "20251231"]
    assert not (df["净利润"] == 0).any(), "不得把缺失伪造成 0"


def test_fr_build_history_empty_when_no_valid_rows():
    df = fr_build_history([("20241231", None)])
    assert df.empty
    assert "报告期" in df.columns, "空表也应带完整列名（下游可直接渲染）"


def test_fr_build_history_does_not_mutate_input():
    r = _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0)
    before = r.copy(deep=True)
    fr_build_history([("20251231", r)])
    pd.testing.assert_frame_equal(r, before)


def test_fr_history_metrics_extracts_series():
    df = fr_build_history([
        ("20231231", _one_row("600519", 50.0, 1.4e11, 10.0, 7.0e10, 9.0, 30.0)),
        ("20241231", _one_row("600519", 55.0, 1.5e11, None, 7.5e10, -6.0, 31.0)),
        ("20251231", _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0)),
    ])
    x, y, yoy = fr_history_metrics(df, "净利润")
    assert x == ["2023年报", "2024年报", "2025年报"]
    assert y == [7.0e10, 7.5e10, 8.2e10]
    assert yoy == [9.0, -6.0, 12.0]

    # 营收同比缺失期必须是 None（断线），不得变 0
    _, _, rev_yoy = fr_history_metrics(df, "营业总收入")
    assert rev_yoy == [10.0, None, 8.0]


def test_fr_history_metrics_bad_input_returns_empty():
    assert fr_history_metrics(None, "净利润") == ([], [], [])
    assert fr_history_metrics(pd.DataFrame(), "净利润") == ([], [], [])
    df = fr_build_history([("20251231", _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0))])
    assert fr_history_metrics(df, "不存在的指标") == ([], [], [])


def test_fr_expand_rows_is_newest_first_and_same_source():
    """展开分析明细：与图同源但最新期在最前（用户视角）。"""
    df = fr_build_history([
        ("20231231", _one_row("600519", 50.0, 1.4e11, 10.0, 7.0e10, 9.0, 30.0)),
        ("20241231", _one_row("600519", 55.0, 1.5e11, 7.0, 7.5e10, 6.0, 31.0)),
        ("20251231", _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0)),
    ])
    rows = fr_expand_rows(df, "净利润")
    assert [r[0] for r in rows] == ["2025年报", "2024年报", "2023年报"]
    assert rows[0][1] == 8.2e10 and rows[0][2] == 12.0
    # 与图源完全一致（同一函数抽取，只是顺序反转）
    x, y, yoy = fr_history_metrics(df, "净利润")
    assert [r[0] for r in rows] == x[::-1]
    assert [r[1] for r in rows] == y[::-1]


def test_fr_expand_rows_empty_is_safe():
    assert fr_expand_rows(None) == []
    assert fr_expand_rows(pd.DataFrame()) == []

def test_fr_yoy_column_handles_dongcai_abbreviation():
    """回归：东财把「营业总收入」的同比列命名为「营收同比%」（缩写），
    不得用 f"{metric}同比%" 机械拼接——否则同比序列静默全 None。"""
    assert fr_yoy_column("营业总收入") == "营收同比%"
    assert fr_yoy_column("净利润") == "净利润同比%"
    assert fr_yoy_column("每股收益") is None, "东财未提供 EPS 同比，应显式无列"
    assert fr_yoy_column("ROE%") is None


def test_fr_history_metrics_revenue_yoy_uses_abbrev_column():
    """端到端：营收同比必须真的取到值（此前因列名拼接错误恒为 None）。"""
    df = fr_build_history([
        ("20231231", _one_row("600519", 50.0, 1.4e11, 10.0, 7.0e10, 9.0, 30.0)),
        ("20241231", _one_row("600519", 55.0, 1.5e11, 7.0, 7.5e10, -6.0, 31.0)),
    ])
    _, _, rev_yoy = fr_history_metrics(df, "营业总收入")
    assert rev_yoy == [10.0, 7.0], "营收同比不得因列名拼接而丢失"
    assert any(v is not None for v in rev_yoy), "不得全为空（静默丢数据）"


def test_fr_history_metrics_eps_has_no_yoy_series():
    """EPS 无同比列 → 应返回全 None（而非抛错/错列）。"""
    df = fr_build_history([("20251231", _one_row("600519", 60.0, 1.7e11, 8.0, 8.2e10, 12.0, 32.0))])
    x, y, yoy = fr_history_metrics(df, "每股收益")
    assert y == [60.0]
    assert yoy == [None]
