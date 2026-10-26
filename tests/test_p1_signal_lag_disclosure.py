# -*- coding: utf-8 -*-
"""
tests/test_p1_signal_lag_disclosure.py
======================================
T-331 P1 深度学习信号「滞后天数」诚实披露守卫。

背景（T-331 勘测实证 2026-10-26）：P1 现役 4 模型信号 latest_date=2026-09-17
（滞后 39 个自然日）、fusion 停 2026-08-14（滞后 72 天）。T-324 已建推送侧告警
（data_refresh_engine lag≥8 → MarketAlert），但页面侧只显示「数据日期」原始值，
用户不易感知滞后程度。

契约：
- modules/p1_signal.age_days_from_latest(latest_date, today=None) 纯函数：
  正常 "YYYY-MM-DD"（或带时间的 ISO 串取前 10 位）→ 自然日差 int；
  latest_date 为 None/空/解析失败 → None（unavailable，绝不编造 0）；
  today 缺省取当天（date.today()）。
- P1SignalLoader.signal_age_days(model)：复用上式，latest 缺失 → None。
- pages/55_P1量化信号.py 与 pages/54_今日决策面板.py：数据日期旁追加滞后警示
  （age≥15 自然日 → "⚠️ 信号滞后 N 自然日…仅供参考"）；additive-only，不动原展示。

mutation：警示分支被移除 / None 被编造成 0 → 对应用例变红。
"""
import inspect
from datetime import date

from modules import p1_signal as ps


class TestAgeDaysPure:
    def test_normal_iso_date(self):
        assert ps.age_days_from_latest("2026-09-17", today=date(2026, 10, 26)) == 39

    def test_iso_with_time_takes_date_part(self):
        assert ps.age_days_from_latest("2026-09-17 01:45:10", today=date(2026, 10, 26)) == 39

    def test_none_or_empty_or_bad_returns_none(self):
        for bad in (None, "", "unknown", "2026/09/17", 123):
            assert ps.age_days_from_latest(bad, today=date(2026, 10, 26)) is None, \
                f"输入 {bad!r} 应返回 None（不可编造）"

    def test_negative_age_clamped_to_zero(self):
        """latest 在未来（时钟偏差）→ 钳 0，不返负数。"""
        assert ps.age_days_from_latest("2026-10-27", today=date(2026, 10, 26)) == 0


class TestLoaderMethod:
    def test_signal_age_days_exists_and_delegates(self):
        assert hasattr(ps.P1SignalLoader, "signal_age_days")
        src = inspect.getsource(ps.P1SignalLoader.signal_age_days)
        assert "age_days_from_latest" in src and "latest_date" in src


class TestPageWiring:
    def test_page55_has_lag_warning(self):
        src = _read("pages", "55_P1量化信号.py")
        assert "signal_age_days" in src, "55 页未接滞后天数"
        assert "信号滞后" in src, "55 页缺滞后警示文案"
        assert ">= 15" in src, "55 页缺滞后阈值门控（≥15 自然日）"

    def test_page54_has_lag_warning(self):
        src = _read("pages", "54_今日决策面板.py")
        assert "signal_age_days" in src, "54 页未接滞后天数"
        assert "信号滞后" in src, "54 页缺滞后警示文案"
        assert ">= 15" in src, "54 页缺滞后阈值门控（≥15 自然日）"


def _read(*parts):
    import io
    import os
    path = os.path.join(os.path.dirname(__file__), "..", *parts)
    with io.open(path, encoding="utf-8") as f:
        return f.read()
