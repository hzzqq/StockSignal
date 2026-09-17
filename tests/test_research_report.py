# -*- coding: utf-8 -*-
"""tests/test_research_report.py — H8 一键研报测试（纯渲染，离线）。"""
import json
import re

from modules import research_report as rr


def _full_data():
    return {
        "quote": {"price": 15.32, "change_pct": 2.15},
        "fundamentals": {"market_cap": 320.5, "pe_ttm": 18.6, "pb": 2.1,
                         "dividend_yield": 1.2, "industry": "电力设备"},
        "technical": {"trend": {"trend_score": 72.0},
                      "momentum": {"momentum_score": 61.5},
                      "volume": {"volume_price_score": 55.0},
                      "patterns": [{"name": "金叉", "bias": "看涨"}]},
        "fundflow": {"main_net": 1.2e8, "super_net": 8e7, "big_net": 4e7},
        "risk_report": {
            "overall_level": "medium", "coverage_pct": 83.3, "reliable": True,
            "components": {
                "goodwill": {"level": "low", "note": "未见商誉"},
                "pledge": {"level": "low", "note": "未见未解押股份"},
                "unlock": {"level": "medium", "note": "未来 90 日 12% 解禁"},
                "reduction": {"level": "low", "note": "无变动"},
                "litigation": {"level": "low", "note": "未见"},
                "st": {"level": "low", "note": "正常"},
            },
        },
        "announcements": ["2026年半年度报告", "关于董事会换届的公告"],
    }


# ─────────────────────────── 装配 ───────────────────────────
def test_full_report_covers_everything():
    rep = rr.build_report("600000", "浦发银行", _full_data(), ts="2026-09-17 22:00:00")
    assert rep["coverage_pct"] == 100.0
    assert rep["warnings"] == []
    for key, _cn in rr.SECTION_KEYS:
        assert rep["sections"][key]["available"] is True, key
    assert rep["sections"]["risk"]["summary"] == "整体风险：中"


def test_empty_data_reports_zero_coverage_and_never_fabricates():
    rep = rr.build_report("600000", "浦发银行", {})
    assert rep["coverage_pct"] == 0.0
    assert len(rep["warnings"]) >= 5
    assert rep["sections"]["conclusion"]["available"] is False
    html = rr.render_html(rep)
    assert "无有效数据板块" in html
    # 不得凭空出现任何数字型指标
    assert "总市值" not in html and "市盈率TTM" not in html


def test_partial_data_lists_missing_sections_in_conclusion():
    data = _full_data()
    data["fundflow"] = None
    data["announcements"] = None
    rep = rr.build_report("600000", "X", data)
    assert rep["coverage_pct"] == 60.0
    concl = rep["sections"]["conclusion"]["summary"]
    assert "60%" in concl
    body = json.dumps(rep["sections"]["conclusion"]["rows"], ensure_ascii=False)
    assert "资金面" in body and "公告与事件" in body


def test_low_coverage_flag_from_risk_report():
    """风险报告自身覆盖率不足时，研报必须把这句提示带出来。"""
    data = _full_data()
    data["risk_report"]["reliable"] = False
    data["risk_report"]["coverage_pct"] = 40.0
    rep = rr.build_report("600000", "X", data)
    assert "覆盖率不足" in rep["sections"]["risk"]["note"]


def test_decimal_like_strings_are_parsed():
    data = _full_data()
    data["fundamentals"]["market_cap"] = "320.5"
    rep = rr.build_report("600000", "X", data)
    rows = dict((r[0], r[1]) for r in rep["sections"]["basic"]["rows"])
    assert rows["总市值"] == "320.50 亿"


# ─────────────────────────── HTML 渲染 ───────────────────────────
def test_html_is_self_contained():
    html = rr.render_html(rr.build_report("600000", "X", _full_data()))
    assert html.startswith("<!DOCTYPE html>")
    assert not re.search(r'(?:src|href)\s*=\s*"https?://', html), "不得引用任何外部资源"
    assert "<script" not in html.lower(), "研报不应含脚本"


def test_html_has_disclaimer_always():
    for data in (_full_data(), {}):
        html = rr.render_html(rr.build_report("600000", "X", data))
        assert "不构成任何投资建议" in html


def test_html_escapes_injected_text():
    data = _full_data()
    data["announcements"] = ["<script>alert(1)</script>", "正常公告"]
    html = rr.render_html(rr.build_report("600000", "<img src=x onerror=1>", data))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x" not in html


def test_ashare_color_convention_up_red_down_green():
    """A 股口径：涨=红、跌=绿（只断言数值单元格，CSS 里的告警色不算）。"""
    data = _full_data()
    data["quote"] = {"price": 15.32, "change_pct": 2.15}
    html_up = rr.render_html(rr.build_report("600000", "X", data))
    assert f'<td style="color:{rr.UP_COLOR}">15.32</td>' in html_up
    assert f'<td style="color:{rr.DOWN_COLOR}">' not in html_up

    data["quote"] = {"price": 15.32, "change_pct": -2.15}
    html_dn = rr.render_html(rr.build_report("600000", "X", data))
    assert f'<td style="color:{rr.DOWN_COLOR}">15.32</td>' in html_dn
    # 同一个价格数值绝不能仍用红色
    assert f'<td style="color:{rr.UP_COLOR}">15.32</td>' not in html_dn


def test_html_unavailable_section_badged():
    data = _full_data()
    data["technical"] = None
    html = rr.render_html(rr.build_report("600000", "X", data))
    assert "数据不可用" in html
    assert "未取到技术面数据" in html


# ─────────────────────────── Markdown 渲染 ───────────────────────────
def test_markdown_contains_sections_and_disclaimer():
    md = rr.render_markdown(rr.build_report("600000", "浦发银行", _full_data()))
    assert "# 📄 600000 浦发银行 · 个股研报" in md
    assert "## 风险排雷" in md and "## 技术面" in md
    assert "| 项 | 值 |" in md
    assert "不构成任何投资建议" in md


def test_markdown_zero_coverage_warns():
    md = rr.render_markdown(rr.build_report("600000", "X", {}))
    assert "覆盖率 0%" in md
    assert "无有效数据板块" in md
