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
    # 真实数据区间已写入静态表格
    assert "2009-11-02" in html and "2026-09-04" in html
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
