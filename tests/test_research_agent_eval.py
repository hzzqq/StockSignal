"""
tests/test_research_agent_eval.py
=================================
T-273B：研究智能体评测守卫——与 scripts/agent_eval_suite.py **同源**
（逐 case 函数复用），pytest 绿 ⇔ reports/research_agent_eval.json 可复现。

评测范围：run_research 行为契约五维（序列/溯源/诚实降级/只读红线/有界执行）。
mutation 目标：删 run_research 的 error→limitations 回填 → E5 红；解除
conditional_orders 红线 → E6 红；解除 max_steps clamp → E8 红。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agent_eval_suite import CASES, run_eval  # noqa: E402

import pytest  # noqa: E402


def test_eval_all_cases_pass():
    """全量评测 9/9 通过（任一维度回潮即红）。"""
    result = run_eval()
    failed = [c for c in result["cases"] if not c["passed"]]
    assert not failed, (
        f"研究智能体评测失败 {len(failed)}/{result['total']}："
        + "; ".join(f"{c['id']}({c['dim']}) {c['detail']}" for c in failed)
    )
    assert result["pass_rate"] == 1.0


def test_eval_covers_five_dimensions():
    """五维缺一不可（防评测集被悄悄瘦身）。"""
    dims = {dim for _, dim, _ in CASES}
    assert dims == {"任务完成/序列", "引用溯源", "诚实降级", "只读红线", "有界执行"}, \
        f"评测维度漂移: {dims}"
    assert len(CASES) >= 9, "评测题数骤减——评测集被削弱"


def test_eval_report_matches_suite():
    """报告文件与套件当前结果一致（防报告陈旧/手改）。"""
    import json
    report = Path(__file__).resolve().parents[1] / "reports" / "research_agent_eval.json"
    assert report.exists(), "评测报告缺失——请运行 scripts/agent_eval_suite.py 重新生成"
    data = json.loads(report.read_text(encoding="utf-8"))
    fresh = run_eval()
    assert data.get("passed") == fresh["passed"] and data.get("total") == fresh["total"], \
        f"报告({data.get('passed')}/{data.get('total')})与套件当前结果({fresh['passed']}/{fresh['total']})不一致"
    assert data["meta"].get("honesty_note"), "报告必须带诚实边界说明（不评测 LLM 措辞）"
