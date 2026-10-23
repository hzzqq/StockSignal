"""
tests/test_worker_style_passthrough.py — T-308 后端 worker 对回应方式 style 的透传守卫

锁住两条任务链的 payload 契约（mutation 目标：删透传 → 必红）：
- ai_consult → ai_engine.ai_answer(question, context, style=payload["style"]，缺省 quick)；
- ai_research → research_agent.run_research(style=payload["style"]，缺省 report)，
  且 max_steps 缺省 6→8（T-308 研报扩大）、仍可被 payload 覆盖。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.tasks import worker  # noqa: E402


def test_ai_consult_passes_style(monkeypatch):
    captured = {}

    def _fake_ai_answer(question, context, style="quick"):
        captured["question"] = question
        captured["context"] = context
        captured["style"] = style
        return {"answer": "ok", "independent": True}

    monkeypatch.setattr("modules.ai_engine.ai_answer", _fake_ai_answer)

    out = worker._handle_ai_consult(
        {"question": "茅台怎么样", "context": {"k": 1}, "style": "report"}
    )
    assert out["answer"] == "ok"
    assert captured["style"] == "report"  # mutation：删透传 → 恒 quick → 红
    assert captured["question"] == "茅台怎么样"

    worker._handle_ai_consult({"question": "x"})
    assert captured["style"] == "quick"  # 缺省回落 quick（兼容既有调用方）


def test_ai_research_passes_style_and_default_steps(monkeypatch):
    captured = {}

    def _fake_run_research(question, max_steps=6, on_step=None, style="report", **extra):
        captured.update(question=question, max_steps=max_steps,
                        style=style, extra=extra)
        return {"steps": [], "citations": [], "answer": "r", "status": "ok"}

    monkeypatch.setattr("modules.research_agent.run_research", _fake_run_research)

    out = worker._handle_ai_research({"question": "深度研究茅台"})
    assert out["answer"] == "r"
    assert captured["style"] == "report"  # 缺省 report（研报结构合成）
    assert captured["max_steps"] == 8     # T-308：默认 6 → 8（mutation：还原 6 → 红）

    worker._handle_ai_research({"question": "x", "style": "quick"})
    assert captured["style"] == "quick"

    worker._handle_ai_research({"question": "x", "max_steps": "3"})
    assert captured["max_steps"] == 3     # payload 仍可覆盖

    worker._handle_ai_research({"question": "x", "max_steps": "垃圾"})
    assert captured["max_steps"] == 8     # 非法值回落默认
