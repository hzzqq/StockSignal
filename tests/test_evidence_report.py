"""牧羊人实证证据报告生成器 回归测试（离线、真实数据驱动）。

锁死 R28+ 的论文级交付物：scripts/generate_evidence_report.py 必须能从真实
shepherd_history.csv 跑通、产出含真实区间/分布的 HTML，且服务端静态表格已注入
（断网打开也能看数）、无模板占位符残留。
真实数据被 .gitignore 忽略，缺失则跳过（与 test_decision_closure_realdata 一致）。
"""
from __future__ import annotations

import os
import re

import pytest

from modules.shepherd_reconstruct import _BREADTH_FILE


def _run():
    if not os.path.exists(_BREADTH_FILE):
        pytest.skip("真实 shepherd_history.csv 缺失，跳过报告生成测试")
    import scripts.generate_evidence_report as gen
    gen.main()
    return gen.OUT_PATH


def _first_last_dates() -> tuple[str, str]:
    """从真实广度 CSV 实算区间端点 —— 期望值不得写死。

    历史缺陷：本测试曾写死 ``"2009-11-02" / "2026-09-04"``；后来 CSV 被向前
    扩到 2007 年（现 4785 行 / 2007-01-05~2026-09-10），断言随即静默失败。
    测试必须钉在实算产物上，而非某一次快照的字面量。
    """
    import csv
    with open(_BREADTH_FILE, encoding="utf-8-sig", newline="") as f:
        ds = [r["date"] for r in csv.DictReader(f) if (r.get("date") or "").strip()]
    assert ds, "广度 CSV 无有效日期行"
    return min(ds), max(ds)


def test_evidence_report_generates_valid_html(tmp_path, monkeypatch):
    # 重定向输出到临时目录，避免覆盖已提交的交付物
    out = tmp_path / "shepherd_history_evidence.html"
    monkeypatch.setattr("scripts.generate_evidence_report.OUT_PATH", str(out))
    import scripts.generate_evidence_report as gen
    if not os.path.exists(_BREADTH_FILE):
        pytest.skip("真实 shepherd_history.csv 缺失，跳过报告生成测试")
    gen.main()

    html = out.read_text(encoding="utf-8")
    # 无模板占位符残留
    assert "__DATA__" not in html
    assert "__CYCLE_ROWS__" not in html
    assert "__BREADTH_ROWS__" not in html
    assert "__CONCL__" not in html
    # 真实数据区间已写入静态表格 —— 期望值从 CSV 实算（不再写死）
    first, last = _first_last_dates()
    assert first in html and last in html, f"静态表格未含真实区间 {first} ~ {last}（写死日期会随数据扩展静默过期）"
    # 内嵌 JSON 可解析
    m = re.search(r"const D = (\{.*?\});", html, re.S)
    assert m, "内嵌数据缺失"
    import json
    d = json.loads(m.group(1))
    assert d["n_days"] > 1000
    # 六阶段全命中（非空想分类）
    assert set(d["cycle_order"]) == {"冰点", "修复试探", "修复确认", "主升高潮", "高潮分化", "退潮"}
    # 退化如实披露
    assert "退化" in html or "修复试探" in html
