"""tests/test_fundflow_health.py —— fundflow 数据层健康体检单测（fake provider 注入，零网络）。

覆盖：交易日折算 / 新鲜度三档 / 各接口结构体检 / summarize 汇总语义 / 报告渲染。
"""
from datetime import date

import pandas as pd
import pytest

import modules.fundflow_health as h

TODAY = date(2026, 11, 2)          # 周一
LAST_TRADING = date(2026, 10, 30)  # 周五（最近交易日；10-31 是周六）


# ───────────────────────── 交易日工具 ─────────────────────────
class TestTradingDay:
    @pytest.mark.parametrize("d,expect", [
        (date(2026, 11, 2), date(2026, 10, 30)),   # 周一 → 上周五
        (date(2026, 10, 30), date(2026, 10, 29)),  # 周五 → 周四（跳过自身）
        (date(2026, 11, 1), date(2026, 10, 30)),   # 周日 → 周五
        (date(2026, 10, 29), date(2026, 10, 28)),  # 周四 → 周三（跳过自身）
    ])
    def test_last_trading_day(self, d, expect):
        assert h.last_trading_day(d) == expect

    def test_age_in_days(self):
        assert h.age_in_days("2026-10-30", TODAY) == 0   # 最近交易日
        assert h.age_in_days("2026-10-29", TODAY) == 1   # 前一天
        assert h.age_in_days("2026-10-26", TODAY) == 4   # 断供 4 天
        assert h.age_in_days("bad-date", TODAY) is None
        assert h.age_in_days("", TODAY) is None


# ───────────────────────── 新鲜度判定 ─────────────────────────
class TestFreshness:
    def test_ok(self):
        r = h._freshness_status("2026-10-30", TODAY)
        assert r["status"] == "ok" and r["ok"] is True

    def test_yellow_edge(self):
        r = h._freshness_status("2026-10-26", TODAY)   # 差 4 天 > WARN(3) = 宽容带
        assert r["status"] == "yellow" and r["ok"] is True

    def test_red_stale(self):
        r = h._freshness_status("2026-10-23", TODAY)   # 差 7 天 > RED(6)
        assert r["status"] == "red" and r["ok"] is False

    def test_missing(self):
        r = h._freshness_status(None, TODAY)
        assert r["status"] == "red" and r["ok"] is False


# ───────────────────────── 单项体检 ─────────────────────────
class TestChecks:
    def test_industry_ok(self):
        df = pd.DataFrame({"行业": ["银行"], "涨跌幅": [1.0], "流入资金": [1],
                           "流出资金": [1], "净额": [1]})
        assert h.check_industry(df)["ok"] is True

    def test_industry_empty_red(self):
        assert h.check_industry(pd.DataFrame())["status"] == "red"

    def test_industry_missing_col_red(self):
        df = pd.DataFrame({"行业": ["银行"]})
        assert h.check_industry(df)["status"] == "red"

    def test_northbound_history_ok(self):
        d = {"last_net_buy": 1.0, "last_net_buy_date": "2024-08-15",
             "cumulative": 2.0, "cumulative_date": "2024-08-15"}
        r = h.check_northbound_history(d)
        assert r["ok"] is True and "豁免" in r["note"]

    def test_northbound_history_empty_red(self):
        assert h.check_northbound_history({})["status"] == "red"

    def test_northbound_fund_flow_ok(self):
        d = {"trade_date": "2026-10-30", "total_inflow": 1.0,
             "sh_inflow": 1.0, "sz_inflow": 1.0}
        assert h.check_northbound_fund_flow(d, today=TODAY)["ok"] is True

    def test_northbound_fund_flow_stale_red(self):
        d = {"trade_date": "2026-10-09", "total_inflow": 1.0,
             "sh_inflow": 1.0, "sz_inflow": 1.0}
        assert h.check_northbound_fund_flow(d, today=TODAY)["status"] == "red"

    def test_market_fund_flow_ok(self):
        df = pd.DataFrame({"日期": ["2026-10-30"], "主力净流入-净额": [1.0]})
        assert h.check_market_fund_flow(df, today=TODAY)["ok"] is True

    def test_market_fund_flow_stale_red(self):
        df = pd.DataFrame({"日期": ["2026-09-29"], "主力净流入-净额": [1.0]})
        assert h.check_market_fund_flow(df, today=TODAY)["status"] == "red"

    def test_market_fund_flow_gap_yellow(self):
        # 数据差 4 天（如周一盘前停在上周三）→ 黄灯登记不阻断
        df = pd.DataFrame({"日期": ["2026-10-26"], "主力净流入-净额": [1.0]})
        r = h.check_market_fund_flow(df, today=TODAY)
        assert r["status"] == "yellow" and r["ok"] is True

    def test_market_fund_flow_missing_col_red(self):
        df = pd.DataFrame({"日期": ["2026-10-31"]})
        assert h.check_market_fund_flow(df, today=TODAY)["status"] == "red"

    def test_earnings_report_ok(self):
        df = pd.DataFrame({"每股收益": [1.0], "净利润": [1.0],
                           "净利润同比%": [1.0], "营业总收入": [1.0]})
        assert h.check_earnings_report(df)["ok"] is True

    def test_earnings_report_empty_red(self):
        assert h.check_earnings_report(pd.DataFrame())["status"] == "red"

    def test_best_effort_empty_yellow(self):
        assert h.check_best_effort(pd.DataFrame(), "业绩预告")["status"] == "yellow"

    def test_best_effort_ok(self):
        df = pd.DataFrame({"a": [1]})
        assert h.check_best_effort(df, "披露日历")["ok"] is True


# ───────────────────────── 汇总语义 ─────────────────────────
class TestSummarize:
    def _ok_providers(self):
        return {
            "industry": lambda: pd.DataFrame({"行业": ["银行"], "涨跌幅": [0],
                                              "流入资金": [0], "流出资金": [0], "净额": [0]}),
            "northbound_history": lambda: {"last_net_buy": 1.0, "last_net_buy_date": "2024-08-15",
                                           "cumulative": 2.0, "cumulative_date": "2024-08-15"},
            "northbound_fund_flow": lambda: {"trade_date": "2026-10-30", "total_inflow": 1.0,
                                             "sh_inflow": 1.0, "sz_inflow": 1.0},
            "market_fund_flow": lambda: pd.DataFrame({"日期": ["2026-10-30"], "主力净流入-净额": [1.0]}),
            "earnings_report": lambda: pd.DataFrame({"每股收益": [1.0], "净利润": [1.0],
                                                     "净利润同比%": [1.0], "营业总收入": [1.0]}),
            "earnings_forecast": lambda: pd.DataFrame({"a": [1]}),
            "disclosure_calendar": lambda: pd.DataFrame({"b": [1]}),
        }

    def test_all_green(self):
        s = h.summarize(self._ok_providers(), today=TODAY)
        assert s["ok_all"] is True and not s["red"] and not s["yellow"]

    def test_one_red_blocks(self):
        p = self._ok_providers()
        p["market_fund_flow"] = lambda: pd.DataFrame({"日期": ["2026-09-29"], "主力净流入-净额": [1.0]})
        s = h.summarize(p, today=TODAY)
        assert s["ok_all"] is False and len(s["red"]) == 1 and s["red"][0]["model"] == "market_fund_flow"

    def test_exception_in_provider_red(self):
        p = self._ok_providers()
        p["earnings_report"] = lambda: (_ for _ in ()).throw(RuntimeError("net down"))
        s = h.summarize(p, today=TODAY)
        assert s["ok_all"] is False and "接口调用异常" in s["red"][0]["errors"][0]

    def test_best_effort_empty_yellow_not_blocks(self):
        p = self._ok_providers()
        p["earnings_forecast"] = lambda: pd.DataFrame()
        s = h.summarize(p, today=TODAY)
        assert s["ok_all"] is True and len(s["yellow"]) == 1

    def test_render_contains_conclusion(self):
        s = h.summarize(self._ok_providers(), today=TODAY)
        text = h.render_report(s)
        assert "✅" in text and "fundflow 数据层健康体检" in text
        p = self._ok_providers()
        p["industry"] = lambda: pd.DataFrame()
        text2 = h.render_report(h.summarize(p, today=TODAY))
        assert "红灯" in text2
