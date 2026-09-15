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
