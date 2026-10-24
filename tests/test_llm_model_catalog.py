"""
tests/test_llm_model_catalog.py — T-314 真实 AI 模型接入守卫（离线可跑）

缺陷背景（2026-10-24 实测）：
- DeepSeek 侧可用模型已变为 deepseek-flash / deepseek-v4-pro（旧 deepseek-chat 仍可用但
  随时下线），三者均带 reasoning_content（推理模型）。
- 推理模型的推理过程与正文共享 max_tokens 预算：实测 max_tokens=400 时推理吃光预算，
  content 返回空串；现有「空内容即终止回退链」策略会把这类失败静默降级为规则引擎。
- 旧代码只有单一 env 主模型，无法按回应方式分层，也无法让用户在前端选择。

钉住契约（mutation 目标）：
1. 模型目录单一真理源 MODEL_CATALOG + 回应方式默认路由 STYLE_MODEL_DEFAULTS；
2. 推理模型 token 预算下限（effective_max_tokens 抬升，普通模型不动）；
3. resolve_model 只在 provider 目录匹配时返回，跨 provider 不写死模型名；
4. ai_engine.STYLE_PRESETS 每项声明 model，且 ai_answer 把 model 透传到 LLM 层；
5. 后端 worker 透传 model（payload → ai_answer）；
6. 前端提供模型选择器且提交 payload 带 model。
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from modules import llm_client  # noqa: E402


# ── 1. 目录与默认路由 ────────────────────────────────────────────
def test_catalog_contains_active_models():
    cat = llm_client.MODEL_CATALOG
    assert isinstance(cat, dict) and cat, "MODEL_CATALOG 不能为空"
    for m in ("deepseek-flash", "deepseek-v4-pro"):
        assert m in cat, f"目录缺少实测可用模型 {m}"
    for m, spec in cat.items():
        assert isinstance(spec, dict), f"{m} 规格必须是 dict"
        assert spec.get("label"), f"{m} 缺少 label"
        assert "reasoning" in spec, f"{m} 必须声明 reasoning（决定 token 预算策略）"
        if spec["reasoning"]:
            assert int(spec.get("min_tokens") or 0) >= 1000, (
                f"{m} 是推理模型，min_tokens 必须给推理留足预算（实测 400 会导致正文为空）"
            )


def test_style_defaults_cover_all_styles():
    styles = llm_client.STYLE_MODEL_DEFAULTS
    assert set(styles) >= {"quick", "report", "debate", "teach"}, "四种回应方式都要有默认模型"
    for s, m in styles.items():
        assert m in llm_client.MODEL_CATALOG, f"{s} 默认模型 {m} 不在目录内"


# ── 2. 推理预算下限 ─────────────────────────────────────────────
def test_reasoning_budget_floor():
    got = llm_client.effective_max_tokens("deepseek-flash", 400)
    assert got >= 1500, f"推理模型 400 tokens 会被推理吃光正文，必须抬升（得到 {got}）"
    # 已足够大时不压缩
    assert llm_client.effective_max_tokens("deepseek-flash", 3000) == 3000


def test_non_reasoning_model_untouched():
    assert llm_client.effective_max_tokens("some-plain-model", 400) == 400
    assert llm_client.effective_max_tokens(None, 400) == 400


# ── 3. provider 感知的模型解析 ──────────────────────────────────
def test_resolve_model_on_deepseek(monkeypatch):
    monkeypatch.setenv("STARFIELD_LLM_BASE_URL", "https://api.deepseek.com/v1")
    assert llm_client.resolve_model("deepseek-v4-pro", "quick") == "deepseek-v4-pro", \
        "显式选择必须优先于 style 默认"
    assert llm_client.resolve_model(None, "report") == "deepseek-v4-pro"
    assert llm_client.resolve_model(None, "quick") == "deepseek-flash"


def test_resolve_model_skips_foreign_provider(monkeypatch):
    monkeypatch.setenv("STARFIELD_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    assert llm_client.resolve_model("deepseek-v4-pro", "report") is None, (
        "非 DeepSeek provider 下不得写死 deepseek 模型名（否则所有调用必失败）"
    )


def test_resolve_model_rejects_unknown_choice(monkeypatch):
    monkeypatch.setenv("STARFIELD_LLM_BASE_URL", "https://api.deepseek.com/v1")
    assert llm_client.resolve_model("gpt-9-imaginary", "quick") == "deepseek-flash", \
        "未知选择应回落 style 默认，而不是原样下发"


# ── 4. ai_engine 接线 ──────────────────────────────────────────
def test_ai_engine_style_presets_declare_model():
    src = (ROOT / "modules" / "ai_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    presets = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "STYLE_PRESETS" for t in node.targets
        ):
            presets = node.value
            break
    assert isinstance(presets, ast.Dict), "未找到 STYLE_PRESETS 字典字面量"
    for k, v in zip(presets.keys, presets.values):
        style = getattr(k, "value", None)
        assert isinstance(v, ast.Dict), f"{style} 预设必须是 dict"
        keys = {kk.value for kk in v.keys if isinstance(kk, ast.Constant)}
        assert "model" in keys, f"{style} 预设缺少 model（分层路由未落地）"


def test_ai_answer_forwards_model():
    src = (ROOT / "modules" / "ai_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ai_answer"), None)
    assert fn is not None, "未找到 ai_answer"
    args = [a.arg for a in fn.args.kwonlyargs]
    assert "model" in args, "ai_answer 必须接受 model（keyword-only），否则前端选择无法生效"
    seg = ast.get_source_segment(src, fn) or ""
    assert "resolve_model" in seg, "ai_answer 必须经 resolve_model 解析（provider 感知），不得直接下发"
    assert "model=" in seg, "ai_answer 未把解析后的模型传给 LLM 层"


# ── 5. 后端透传 ────────────────────────────────────────────────
def test_worker_forwards_model():
    src = (ROOT / "backend" / "tasks" / "worker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_handle_ai_consult"), None)
    assert fn is not None
    seg = ast.get_source_segment(src, fn) or ""
    assert 'payload.get("model")' in seg, "_handle_ai_consult 未从 payload 取 model"
    assert "model=model" in seg or "model=_model" in seg, "_handle_ai_consult 未把 model 传给 ai_answer"


# ── 6. 前端选择器与 payload ────────────────────────────────────
def test_page_has_model_selector_and_payload():
    src = (ROOT / "pages" / "53_星辰AI.py").read_text(encoding="utf-8")
    assert "xc_model_choice" in src, "缺少模型选择器 state key"
    assert ("provider_catalog" in src) or ("MODEL_CATALOG" in src), (
        "选择器选项必须来自 llm_client 的模型目录（单一真理源），不得页面内自抄清单"
    )
    # 反向断言：页面不得硬编码模型名（否则加/换模型要改两处，易漂移）
    for hardcoded in ('"deepseek-flash"', '"deepseek-v4-pro"', "'deepseek-flash'"):
        assert hardcoded not in src, f"页面硬编码了模型名 {hardcoded}（应走目录映射）"
    assert '"model":' in src, "提交 payload 未携带 model"
