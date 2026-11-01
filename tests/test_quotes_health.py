"""tests/test_quotes_health.py —— 行情取数层体检单测（fake provider 零网络）。

覆盖：三接口结构契约（空/缺列/正常）、日频新鲜度（正常/边缘/断供）、
汇总三档语义与 skipped 状态、渲染输出。
"""
from datetime import date

import pandas as pd
import pytest

from modules import quotes_health as h

TODAY = date(2026, 11, 2)          # 周一
PREV_TD = date(2026, 10, 30)       # 上周五


def _df(latest: str, data_cols=None) -> pd.DataFrame:
    """构造行情宽表：date 列 + 数据列（默认 3 个指数列）。"""
    cols = data_cols or ["date", "sh000001", "sz399001", "sz399006"]
    row = {c: 1.0 for c in cols}
    row["date"] = latest
    return pd.DataFrame([row])


class TestCheckIndex:
    def test_ok_fresh(self):
        r = h.check_index(_df("2026-10-30"), TODAY)
        assert r["status"] == "ok" and r["age_days"] == 0

    def test_empty_red(self):
        r = h.check_index(pd.DataFrame(), TODAY)
        assert r["status"] == "red" and not r["ok"]

    def test_missing_col_red(self):
        r = h.check_index(_df("2026-10-30", data_cols=["date", "sh000001", "sz399001"]), TODAY)
        assert r["status"] == "red"
        assert "缺列" in r["errors"][0]

    def test_stale_red(self):
        r = h.check_index(_df("2026-10-20"), TODAY)   # 距上周五 10 天
        assert r["status"] == "red"
        assert "断供" in r["errors"][0]

    def test_warn_yellow(self):
        r = h.check_index(_df("2026-10-26"), TODAY)   # 距上周五 4 天（宽容带内）
        assert r["status"] == "yellow"


class TestCheckIndustryBoard:
    def test_ok_fresh(self):
        r = h.check_industry_board(_df("2026-10-30", data_cols=["date", "半导体"]), TODAY)
        assert r["status"] == "ok"

    def test_empty_red(self):
        r = h.check_industry_board(pd.DataFrame(), TODAY)
        assert r["status"] == "red"

    def test_no_data_col_red(self):
        r = h.check_industry_board(pd.DataFrame([{"date": "2026-10-30"}]), TODAY)
        assert r["status"] == "red"
        assert "无数据列" in r["errors"][0]


class TestCheckEtf:
    def test_ok_fresh(self):
        r = h.check_etf(_df("2026-10-30", data_cols=["date", "510300"]), TODAY)
        assert r["status"] == "ok"

    def test_empty_red(self):
        r = h.check_etf(pd.DataFrame(), TODAY)
        assert r["status"] == "red"

    def test_bad_date_red(self):
        r = h.check_etf(_df("not-a-date", data_cols=["date", "510300"]), TODAY)
        assert r["status"] == "red"
        assert "不可解析" in r["errors"][0]


class TestSummarize:
    def _providers(self, ok=True):
        return {
            "index": lambda: _df("2026-10-30") if ok else pd.DataFrame(),
            "industry_board": lambda: _df("2026-10-30", data_cols=["date", "半导体"]),
            "etf": lambda: _df("2026-10-30", data_cols=["date", "510300"]),
        }

    def test_all_green(self):
        s = h.summarize(self._providers(), TODAY)
        assert s["ok_all"] is True and s["red"] == [] and s["yellow"] == []

    def test_one_red_blocks(self):
        s = h.summarize(self._providers(ok=False), TODAY)
        assert s["ok_all"] is False
        assert [r["model"] for r in s["red"]] == ["index"]

    def test_provider_exception_red(self):
        p = self._providers()
        p["etf"] = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        s = h.summarize(p, TODAY)
        assert s["ok_all"] is False
        assert any(r["model"] == "etf" and r["status"] == "red" for r in s["rows"])

    def test_skipped(self):
        p = self._providers()
        del p["industry_board"]
        s = h.summarize(p, TODAY)
        assert any(r["model"] == "industry_board" and r["status"] == "skipped" for r in s["rows"])


class TestRender:
    def test_render_contains_rows(self):
        s = h.summarize({
            "index": lambda: _df("2026-10-30"),
            "industry_board": lambda: _df("2026-10-30", data_cols=["date", "半导体"]),
            "etf": lambda: _df("2026-10-30", data_cols=["date", "510300"]),
        }, TODAY)
        out = h.render_report(s)
        assert "行情取数层健康体检" in out and "index" in out and "✅" in out
