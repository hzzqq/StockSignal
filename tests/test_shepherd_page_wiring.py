"""牧羊人新能力「接线」回归测试（防回退 + 真数据渲染验证）。

背景（2026-08-29）：shepherd_forecast（次日走势预判）/ shepherd_note（情绪笔记）
/ shepherd.get_zt_ladder（连板梯队）三个能力层已就绪，但**页面没接线 = 老板看不到**。
本测试锁死两件事：

1. **AST 源码级**：P_市场情绪.py 必须 import 并调用这三个能力，且连板梯队必须渲染在
   「今日最高板」之后（老板原话：在今日最高板附近增加连板股票的相关信息）。
2. **功能级**：用构造数据跑真实页面（AppTest），断言「连板梯队 / 次日预判 / 情绪笔记」
   三个区块真的渲染出了内容，而不只是「不崩」（冒烟测试只验证不崩）。
"""
import ast
import os
import sys
import types

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "pages", "P_市场情绪.py")

# AppTest 需要在无浏览器 URL 上下文里中和这两个调用（同 test_pages_smoke）
import streamlit as st  # noqa: E402

st.page_link = lambda *a, **k: None  # noqa: E402
st.switch_page = lambda *a, **k: None  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402


# ══════════════════════════════════════════════════════════════
#  一、AST 源码级防回退
# ══════════════════════════════════════════════════════════════
def _tree():
    with open(PAGE, "r", encoding="utf-8") as f:
        return ast.parse(f.read())


def test_page_imports_shepherd_forecast_and_note():
    """页面必须 import 次日预判引擎、情绪笔记模块与连板梯队接口。"""
    src = open(PAGE, "r", encoding="utf-8").read()
    for token in ("get_zt_ladder", "shepherd_forecast", "shepherd_note"):
        assert token in src, f"P_市场情绪.py 缺少 {token} 的引用（能力没接线）"


def test_page_defines_and_calls_new_fragments():
    """必须定义 fragment_shepherd_forecast / fragment_shepherd_note 并在脚本末尾调用。"""
    tree = _tree()
    defined = {n.name for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name.startswith("fragment_")}
    assert {"fragment_shepherd_forecast", "fragment_shepherd_note"} <= defined

    # 顶层调用语句（不是 def 内部）
    called = set()
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name) and fn.id.startswith("fragment_"):
                called.add(fn.id)
    assert "fragment_shepherd_forecast" in called, "次日走势预判 fragment 未被调用"
    assert "fragment_shepherd_note" in called, "情绪笔记 fragment 未被调用"


def test_ladder_rendered_right_after_top_board():
    """连板梯队必须渲染在「今日最高板」之后（老板要求：最高板附近带上连板股票信息）。"""
    src = open(PAGE, "r", encoding="utf-8").read()
    i_top = src.find("get_zt_top_board()")
    i_lad = src.find("get_zt_ladder(")
    assert i_top > 0, "页面未渲染今日最高板"
    assert i_lad > i_top, "连板梯队(get_zt_ladder)必须出现在最高板(get_zt_top_board)之后"


# ══════════════════════════════════════════════════════════════
#  二、功能级：构造数据驱动真实页面渲染
# ══════════════════════════════════════════════════════════════
_IND_KEYS = ["limit_up", "limit_down", "zt_fail_ratio", "hb_wave10", "zt_prev_ret",
             "connect_hl", "connect_2b", "fc_ratio", "turnover_amt", "median_chg"]


def _fake_shepherd_df(n: int = 8) -> pd.DataFrame:
    """构造一段「主升确认」形态的牧羊人序列：
    炸板率低(<20) + 最高板 6 板(>=5) + 昨板溢价 3.5%(>3) + 梯队 18 家(>=12)。
    """
    rows = []
    for i in range(n):
        rows.append({
            "date": pd.Timestamp("2026-08-20") + pd.Timedelta(days=i),
            "limit_up": 55 + i,
            "limit_down": 5,
            "zt_fail_ratio": 12.0,          # 封板稳
            "hb_wave10": 10,
            "zt_prev_ret": 3.5,             # 赚钱效应炸裂
            "connect_hl": 6,                # 高度打开
            "connect_2b": 18,               # 梯队厚
            "fc_ratio": 1.5,
            "turnover_amt": 12000.0 + i * 100,
            "median_chg": 1.2,
        })
    return pd.DataFrame(rows)


_FAKE_LADDER = {
    "levels": [
        {"boards": 6, "count": 1,
         "stocks": [{"name": "龙头测试A", "code": "000001", "industry": "电子", "seal": 3.2e8, "amount": 1.1e9}]},
        {"boards": 3, "count": 4,
         "stocks": [{"name": "补涨测试B", "code": "000002", "industry": "汽车", "seal": 1.1e8, "amount": 8e8}]},
        {"boards": 2, "count": 13,
         "stocks": [{"name": "首板测试C", "code": "000003", "industry": "化工", "seal": 5e7, "amount": 4e8}]},
    ],
    "total_connect": 18,
    "max_boards": 6,
    "distribution": [(6, 1), (3, 4), (2, 13), (1, 45)],
    "top": {"name": "龙头测试A", "code": "000001", "boards": 6, "industry": "电子"},
}

_FAKE_TOP = {"name": "龙头测试A", "code": "000001", "boards": 6, "industry": "电子"}


@pytest.fixture
def patched_shepherd(monkeypatch):
    """把牧羊人取数口换成构造数据（页面 run 时执行 import，故必须在 AppTest 前 patch）。"""
    import modules.shepherd as shepherd_mod

    # 页面内 `_load_shepherd` 带 @st.cache_data，而 st 的缓存是**全局**的：
    # 若 test_pages_smoke 先跑过同一页面，缓存里已是「离线空结果」，
    # 本测试 patch 上游函数也不会重新取数。必须先清缓存。
    try:
        st.cache_data.clear()
    except Exception:  # noqa: BLE001
        pass

    df = _fake_shepherd_df()
    monkeypatch.setattr(shepherd_mod, "get_shepherd_indicators", lambda days=60: (df, {}), raising=True)
    monkeypatch.setattr(shepherd_mod, "get_shepherd_indicators_range",
                        lambda s, e, backfill=False: (df, {}), raising=True)
    monkeypatch.setattr(shepherd_mod, "get_zt_ladder", lambda date=None, top_per_level=3: dict(_FAKE_LADDER), raising=True)
    monkeypatch.setattr(shepherd_mod, "get_zt_top_board", lambda date=None: dict(_FAKE_TOP), raising=True)
    monkeypatch.setattr(shepherd_mod, "get_zt_industry_distribution", lambda n=8: None, raising=True)
    return df


def _markdown_text(at) -> str:
    return "\n".join(getattr(w, "value", "") for w in at.markdown)


def _button_labels(at) -> list:
    return [getattr(w, "label", "") for w in at.button]


def _login(at) -> None:
    """注入「已登录」态（同 test_pages_smoke），否则页面只渲染登录引导。"""
    import time

    import jwt

    from modules.site_config import TEST_SMOKE_SECRET

    at.session_state["auth_token"] = jwt.encode(
        {"sub": "demo", "username": "demo", "role": "admin", "exp": int(time.time()) + 999999},
        TEST_SMOKE_SECRET, algorithm="HS256",
    )
    at.session_state["auth_user"] = {"id": 1, "username": "demo", "role": "admin",
                                     "email": "demo@stocksignal.local"}


def test_page_renders_ladder_forecast_and_note(patched_shepherd):
    """真实渲染：最高板附近有梯队、有次日预判、有情绪笔记区块，且无未捕获异常。"""
    at = AppTest.from_file(PAGE, default_timeout=180)
    _login(at)
    at.run()

    assert not at.exception, f"页面渲染异常: {[str(e) for e in at.exception[:3]]}"
    text = _markdown_text(at)

    # ① 连板梯队（最高板附近）
    assert "今日最高板" in text, "未渲染今日最高板"
    assert "连板梯队全景" in text, "最高板附近未渲染连板梯队"
    assert "龙头测试A" in text, "梯队未列出代表股"
    assert "梯队厚" in text or "主升确认" in text, "梯队诊断文案缺失"

    # ② 次日走势预判（主升形态 → 应命中「主升确认」/「接力环境好」）
    assert "次日走势预判" in text, "未渲染次日走势预判区块"
    assert "主升确认" in text or "接力环境好" in text, (
        "主升形态数据下应命中主升确认/接力环境好联动规则")

    # ③ 情绪笔记（按钮 label 走 at.button，不在 markdown 里）
    assert "情绪笔记" in text, "未渲染情绪笔记区块"
    labels = _button_labels(at)
    for need in ("保存/更新今日笔记", "回填次日实际走势", "分析历史情绪"):
        assert any(need in lb for lb in labels), f"情绪笔记缺少按钮：{need}"
