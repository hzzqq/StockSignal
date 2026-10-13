"""
tests/test_cache_eval_report.py
===============================
T-273A：缓存层实证报告 ↔ 毕设文档数字一致性守卫——文档引用的数字必须来自
reports/cache_layer_eval.json 实验产物（防手改数字/报告过期后文档失真）。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "cache_layer_eval.json"
DOC = ROOT / "docs" / "thesis-cache-eval.md"


def _report() -> dict:
    assert REPORT.exists(), "实验报告缺失——请运行 scripts/bench_cache_layers.py 重新生成"
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_meta_honesty():
    """报告必须带诚实边界（模拟负载非生产流量）。"""
    meta = _report()["meta"]
    assert "模拟负载" in meta.get("honesty_note", ""), "诚实边界说明被删"
    assert meta.get("seed"), "seed 缺失（不可复现）"


def test_doc_numbers_match_report():
    """文档关键数字与实验产物逐一对账（数字漂移即红）。"""
    rep = _report()["scenarios"]
    doc = DOC.read_text(encoding="utf-8")
    assert DOC.exists(), "毕设小节文档缺失"

    l0 = rep["l0_l1"]["results"]["layers"]["L0"]["hit_rate"]
    assert f"hit_rate={l0}" in doc or f"{l0}" in doc, f"L0 hit_rate {l0} 未进文档"
    assert "0.795" in doc, "文档 L0 数字与报告不符（预期 0.795）"

    rs = rep["l0_l1"]["results"]["restart_sim"]["layers"]["L1"]
    assert f"{rs['hits']}/25" in doc, f"重启模拟 L1 {rs['hits']}/25 未进文档"

    l5 = rep["l5_fallback"]["results"]
    assert l5["hit_count"] == 3 and l5["miss_count"] == 3, "L5 场景分布漂移（3/3）"
    assert "50% 救回" in doc or "3/3" in doc

    swr = rep["swr"]["results"]
    assert f"{swr['got_stale_immediately']}/{swr['users']}" in doc, "SWR 16/16 未进文档"
    assert f"{swr['singleflight_dedup_pct']}" in doc, "单飞去重比未进文档"


def test_doc_reproduction_command():
    """文档必须带复现命令（可复现性承诺不删）。"""
    doc = DOC.read_text(encoding="utf-8")
    assert "bench_cache_layers.py" in doc and "--seed" in doc, "复现命令缺失"
