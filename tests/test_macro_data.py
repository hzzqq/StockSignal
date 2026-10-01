"""tests/test_macro_data.py — 宏观指标模块守卫。

重点锁三条：
  ① 正常解析：能从 akshare 风格的宽表里按子串挑出「日期列 + 数值列」，
     并正确算出最新值 / 前值 / 变化 / 数据日期
  ② 失败降级：akshare 缺失或抛异常 → 返回 None，**不臆造任何数值**
  ③ 解读口径：PMI 荣枯线 50 的判断正确；无数据时不编解读
     （解读是规则生成的，必须在 UI 标注，不得冒充 AI 洞见）

测试用假的 akshare 模块注入 sys.modules，不触网。
"""
import sys

import pandas as pd
import pytest

from modules import macro_data as md


class _FakeAk:
    """假的 akshare：只提供本项目用到的几个宏观接口。"""

    def __init__(self, raise_on=None):
        self.raise_on = raise_on or set()

    def _maybe(self, key):
        if key in self.raise_on:
            raise RuntimeError("上游不可用")

    def macro_china_pmi(self):
        self._maybe("pmi")
        return pd.DataFrame({
            "月份": ["2026-01", "2026-02", "2026-03"],
            "制造业-指数": [49.2, 49.8, 50.4],
            "制造业-同比增长": [1.1, 1.2, 1.3],
        })

    def macro_china_cpi(self):
        self._maybe("cpi")
        return pd.DataFrame({
            "月份": ["2026-01", "2026-02"],
            "全国-当月": [100.2, 100.5],
            "全国-同比增长": [0.4, 0.9],
        })

    def macro_china_lpr(self):
        self._maybe("lpr")
        return pd.DataFrame({"日期": ["2026-02-20"], "LPR1Y": [3.10], "LPR5Y": [3.60]})

    # ----------------------------- 全球指标（对应新增的 12 个） -----------------------------
    def macro_usa_ism_pmi(self):
        self._maybe("us_ism_pmi")
        return pd.DataFrame({
            "日期": ["2026-01-01", "2026-02-01", "2026-03-01"],
            "今值": [47.5, 49.1, 50.3], "预测值": [48.0, 49.0, 50.0], "前值": [47.0, 47.5, 49.1],
        })

    def macro_usa_cpi_yoy(self):
        self._maybe("us_cpi")
        return pd.DataFrame({
            "日期": ["2026-01-01", "2026-02-01"],
            "今值": [3.1, 2.8], "预测值": [3.0, 2.9], "前值": [3.4, 3.1],
        })

    def macro_usa_ppi(self):
        self._maybe("us_ppi")
        return pd.DataFrame({
            "日期": ["2026-01-01", "2026-02-01"],
            "今值": [2.0, 1.6], "预测值": [2.1, 1.8], "前值": [2.5, 2.0],
        })

    def macro_usa_non_farm(self):
        self._maybe("us_nonfarm")
        return pd.DataFrame({
            "日期": ["2026-01-01", "2026-02-01"],
            "今值": [180.0, 120.0], "预测值": [170.0, 150.0], "前值": [200.0, 180.0],
        })

    def macro_usa_gdp_monthly(self):
        self._maybe("us_gdp")
        return pd.DataFrame({
            "日期": ["2026-01-01", "2026-02-01"],
            "今值": [2.3, 2.5], "预测值": [2.2, 2.4], "前值": [2.1, 2.3],
        })

    def macro_usa_unemployment_rate(self):
        self._maybe("us_unemployment")
        return pd.DataFrame({
            "日期": ["2026-01-01", "2026-02-01"],
            "今值": [4.1, 4.0], "预测值": [4.1, 4.0], "前值": [4.2, 4.1],
        })

    def bond_zh_us_rate(self):
        self._maybe("us_treasury_10y")
        return pd.DataFrame({
            "SOLAR_DATE": ["2026-03-01", "2026-03-02"],
            "中国国债收益率10年": [2.30, 2.31],
            "美国国债收益率10年": [4.20, 4.25],
            "美国国债收益率2年": [4.00, 4.02],
            "美国GDP年增率": [2.3, 2.3],
        })

    def fx_pair_quote(self):
        self._maybe("usd_cny")
        return pd.DataFrame({
            "货币对": ["USDCNY", "USDJPY", "EURUSD"],
            "买报价": [7.12, 150.3, 1.08],
            "卖报价": [7.13, 150.5, 1.09],
        })

    def index_global_hist_em(self, symbol="美元指数"):
        self._maybe("dxy")
        if symbol == "美元指数":
            vals = [102.5, 103.1]
        elif symbol == "标普500":
            vals = [5200.0, 5250.0]
        elif symbol == "纳斯达克":
            vals = [16000.0, 16200.0]
        elif symbol == "恒生指数":
            vals = [18000.0, 18200.0]
        else:
            vals = [100.0, 101.0]
        return pd.DataFrame({
            "日期": ["2026-03-01", "2026-03-02"],
            "代码": ["X", "X"], "名称": [symbol, symbol],
            "今开": [vals[0], vals[1]], "最新价": [vals[0], vals[1]],
            "最高": [vals[0] + 1, vals[1] + 1], "最低": [vals[0] - 1, vals[1] - 1],
            "振幅": [0.2, 0.2],
        })


@pytest.fixture()
def fake_ak(monkeypatch):
    def _install(raise_on=None):
        mod = _FakeAk(raise_on)
        monkeypatch.setitem(sys.modules, "akshare", mod)
        return mod
    return _install


def test_fetch_indicator_parses_latest_and_prev(fake_ak):
    """按 value_hint 挑中「制造业-指数」，而不是同表的同比增长列。"""
    fake_ak()
    got = md.fetch_indicator("pmi")
    assert got is not None
    assert got["value"] == 50.4, "应取最新一期，且选中 PMI 指数列而非同比增长列"
    assert got["prev"] == 49.8
    assert abs(got["change"] - 0.6) < 1e-6
    assert got["date"] == "2026-03"
    assert got["unit"] == "%"


def test_fetch_indicator_uses_hint_over_numeric_fallback(fake_ak):
    """CPI 表里有「全国-当月」和「全国-同比增长」，必须命中同比列。"""
    fake_ak()
    got = md.fetch_indicator("cpi")
    assert got is not None
    assert got["value"] == 0.9, "应按 hint 命中同比增长列，而不是当月值 100.5"
    assert got["prev"] == 0.4


def test_fetch_indicator_single_row_has_no_prev(fake_ak):
    """只有一行时 prev 应为 None，而不是拿自己当参照编一个变化量。"""
    fake_ak()
    got = md.fetch_indicator("lpr")
    assert got is not None
    assert got["value"] == 3.10
    assert got["prev"] is None
    assert got["change"] is None


def test_fetch_indicator_returns_none_on_error(fake_ak):
    """上游抛异常 → None，绝不臆造。"""
    fake_ak(raise_on={"pmi"})
    assert md.fetch_indicator("pmi") is None


def test_fetch_indicator_unknown_key_returns_none(fake_ak):
    fake_ak()
    assert md.fetch_indicator("not_a_macro_key") is None


def test_fetch_all_marks_failures_as_none(fake_ak):
    """fetch_all 里失败的指标对应 None，成功的照常返回，不能整体崩掉。"""
    fake_ak(raise_on={"cpi"})
    data = md.fetch_all()
    assert set(data) == {m["key"] for m in md.MACRO_INDICATORS}
    assert data["cpi"] is None
    assert data["pmi"] is not None


def test_interpret_pmi_below_and_above_threshold():
    below = md.interpret("pmi", 49.0, 49.5)
    above = md.interpret("pmi", 50.5, 49.5)
    assert "收缩" in below and "上方" not in below
    assert "扩张" in above


def test_interpret_cpi_tones():
    assert "通缩" in md.interpret("cpi", 0.2)
    assert "通胀压力" in md.interpret("cpi", 3.5)


def test_interpret_no_data_never_fabricates():
    red = md.interpret("pmi", None)
    assert "不臆造" in red


# ---------------------------------------------------------------------------
# 2026-09 新增：全球指标（美股/美债/美元/汇率/美国宏观）解析守卫
# ---------------------------------------------------------------------------
def test_fetch_indicator_global_us_cpi_parses_今值(fake_ak):
    """美国 CPI 必须命中「今值」列，而非预测值/前值。"""
    fake_ak()
    got = md.fetch_indicator("us_cpi")
    assert got is not None
    assert got["value"] == 2.8
    assert got["prev"] == 3.1
    assert got["region"] == "全球"
    assert got["unit"] == "%"


def test_fetch_indicator_global_us_ppi_and_ism(fake_ak):
    fake_ak()
    ppi = md.fetch_indicator("us_ppi")
    ism = md.fetch_indicator("us_ism_pmi")
    assert ppi and ppi["value"] == 1.6
    assert ism and ism["value"] == 50.3 and ism["prev"] == 49.1


def test_fetch_indicator_global_us_nonfarm_and_unemployment(fake_ak):
    fake_ak()
    nf = md.fetch_indicator("us_nonfarm")
    un = md.fetch_indicator("us_unemployment")
    assert nf and nf["value"] == 120.0 and nf["unit"] == "千人"
    assert un and un["value"] == 4.0


def test_fetch_indicator_global_dxy_uses_最新价(fake_ak):
    """美元指数必须命中「最新价」列，且能带上 symbol 参数。"""
    fake_ak()
    dxy = md.fetch_indicator("dxy")
    assert dxy is not None
    assert dxy["value"] == 103.1
    assert dxy["date"] == "2026-03-02"
    sp = md.fetch_indicator("us_sp500")
    assert sp and sp["value"] == 5250.0


def test_parse_us_treasury_10y_picks_us_column(fake_ak):
    """美债 10Y 必须从混合表里挑出「美国国债收益率10年」，而不是中国的。"""
    fake_ak()
    got = md.fetch_indicator("us_treasury_10y")
    assert got is not None
    assert got["value"] == 4.25
    assert got["prev"] == 4.20
    assert got["unit"] == "%"


def test_parse_usdcny_picks_usdcny_row(fake_ak):
    """汇率必须筛出 USDCNY 这一行，而不是 USDJPY/EURUSD。"""
    fake_ak()
    got = md.fetch_indicator("usd_cny")
    assert got is not None
    assert got["value"] == 7.12
    assert got["prev"] is None  # 实时报价无前期对照


def test_global_regime_score_computes(fake_ak):
    """四分项都在时，应给出 0-100 的评分与各分项。"""
    fake_ak()
    reg = md.global_regime_score()
    assert reg is not None
    assert 0 <= reg["score"] <= 100
    assert set(reg["sub"].keys()) == {"dxy", "us_treasury_10y", "us_cpi", "usd_cny"}
    # DXY=103.1 → 50+(100-103.1)*3 = 40.7；其余偏高也压低评分，整体 < 50
    assert reg["score"] < 50


def test_global_regime_score_none_when_all_fail(fake_ak):
    """四分项全取不到时返回 None，绝不臆造一个评分。"""
    fake_ak(raise_on={"dxy", "us_cpi", "us_treasury_10y", "usd_cny"})
    assert md.global_regime_score() is None


def test_fetch_all_includes_global_keys(fake_ak):
    """fetch_all 的 key 集合应覆盖全部 18 个指标（6 国内 + 12 全球）。"""
    fake_ak()
    data = md.fetch_all()
    global_keys = [m["key"] for m in md.MACRO_INDICATORS if m["region"] == "全球"]
    assert len(global_keys) == 12
    for k in global_keys:
        assert k in data
