"""
市场魔方页面（全球行情速览）· 回归测试（T-147 批6 重写）

两层验证：
1. 集成（AppTest 真跑页面）：渲染不抛未捕获异常——联网时跑真实数据，
   离线/接口失败时走 unavailable 诚实降级，两端都不崩。
2. 数据层（stub 5 个 _load_* 全部失败）：经济卡 8 张、产业卡 24 张全部
   unavailable 显性降级，涨跌统计条不崩——「数据缺失显性标注，绝不编造」。

注：旧立体魔方（_load_cube 三路合并/_composite）已随整页重写移除，
其专属单测 test_cube_merge_logic 一并退役（老板 2026-09-19：原来的就不用了）。
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


def test_cube_renders_without_exception():
    """集成：真跑页面，渲染不抛未捕获异常（联网=真实数据；离线=unavailable 降级）。"""
    at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", "pages", "17_市场魔方.py"),
                           default_timeout=120)
    at.run()
    assert not at.exception, f"市场魔方渲染异常: {at.exception[:3]}"


@pytest.fixture
def _stub_page_module(monkeypatch):
    """stub streamlit + 页面守卫层，加载页面模块用于函数级测试。"""
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    for fn in ("plotly_chart", "metric", "markdown", "caption", "divider", "page_link",
               "switch_page", "radio", "selectbox", "slider", "text", "json",
               "error", "exception", "success", "warning", "info"):
        monkeypatch.setattr(st, fn, lambda *a, **k: None)
    monkeypatch.setattr(st, "columns", lambda n=1, *a, **k: tuple(_Ctx() for _ in range(int(n))))
    monkeypatch.setattr(st, "tabs", lambda labels=None, *a, **k: tuple(_Ctx() for _ in (labels or [])))
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(st, "set_page_config", lambda *a, **k: None)

    import importlib.util
    import modules.page_utils as _pu
    import modules.page_guard as _pg
    import modules.session as _sess
    monkeypatch.setattr(_pu, "render_standard_page", lambda *a, **k: False)
    monkeypatch.setattr(_pg, "safe_fragment", lambda name: (lambda f: f))
    monkeypatch.setattr(_pg, "render_data_degradation_banner", lambda *a, **k: None)
    monkeypatch.setattr(_sess, "trading_autorefresh", lambda *a, **k: None)

    spec = importlib.util.spec_from_file_location(
        "cube_page_test", os.path.join(os.path.dirname(__file__), "..", "pages", "17_市场魔方.py"))
    cube = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cube)
    return cube


def test_cube_degrades_when_all_sources_fail(_stub_page_module, monkeypatch):
    """数据层：5 路数据源全挂 → 8 经济卡 + 24 产业卡全部 unavailable，不崩、不编造。"""
    cube = _stub_page_module
    for fn in ("_load_foreign_commodity", "_load_global_futures_backup",
               "_load_forex", "_load_us_bond", "_load_concept_board",
               "_load_industry_backup", "_load_vix"):
        monkeypatch.setattr(cube, fn, lambda *a, **k: (None, "mock: source down"))

    econ = cube._build_econ_cards()
    assert len(econ) == 8, f"经济卡应 8 张，实际 {len(econ)}"
    assert all(c["_status"] == "unavailable" for c in econ), "全源失败时经济卡应全部 unavailable"
    assert all("—" == c["value"] for c in econ), "unavailable 卡不得编造数值"

    ind = cube._build_industry_cards()
    assert len(ind) == 24, f"产业卡应 24 张，实际 {len(ind)}"
    assert all(c["_status"] == "unavailable" for c in ind), "全源失败时产业卡应全部 unavailable"

    # 涨跌统计条：全 unavailable 时不崩、计数为 0（不把缺失算成涨跌）
    cube._summary_strip(econ + ind)  # 无异常即通过


def test_cube_cards_use_real_data_when_sources_ok(_stub_page_module, monkeypatch):
    """数据层：数据源正常 → 卡片带真实数值与红涨绿跌语义（不污染下游 UI）。"""
    cube = _stub_page_module
    fx = pd.DataFrame({
        "名称": ["布伦特原油", "COMEX黄金", "COMEX白银", "COMEX铜", "NG天然气"],
        "最新价": [98.73, 4378.29, 66.25, 671.63, 3.04],
        "涨跌幅": [-1.20, 0.84, 1.61, 0.82, -0.13],
        "行情时间": ["15:02:00"] * 5,
    })
    forex = pd.DataFrame({"名称": ["美元指数"], "最新价": [100.22], "涨跌幅": [0.05]})
    bond = pd.DataFrame({"日期": ["2026-09-17", "2026-09-18"],
                         "美国国债收益率30年": [4.72, 4.70]})
    concept = pd.DataFrame({"板块名称": ["AI算力", "CPO概念", "稀土永磁"],
                            "涨跌幅": [0.32, -0.28, -1.83]})
    monkeypatch.setattr(cube, "_load_foreign_commodity", lambda *a, **k: (fx.copy(), None))
    monkeypatch.setattr(cube, "_load_global_futures_backup", lambda *a, **k: (fx.copy(), None))
    monkeypatch.setattr(cube, "_load_forex", lambda *a, **k: (forex.copy(), None))
    monkeypatch.setattr(cube, "_load_us_bond", lambda *a, **k: (bond.copy(), None))
    monkeypatch.setattr(cube, "_load_concept_board", lambda *a, **k: (concept.copy(), None))
    monkeypatch.setattr(cube, "_load_industry_backup", lambda *a, **k: (None, "mock: not needed"))
    monkeypatch.setattr(cube, "_load_vix", lambda *a, **k: (
        {"price": 21.67, "pct": -4.08, "name": "标普500波动率指数", "time": "09:30:00"}, None))

    econ = cube._build_econ_cards()
    by_label = {c["label"]: c for c in econ}
    assert by_label["布伦特原油"]["value"] == "98.73"
    assert by_label["布伦特原油"]["delta_dir"] == "down"  # -1.20% 绿跌
    assert by_label["黄金盎司"]["delta_dir"] == "up"      # +0.84% 红涨
    assert by_label["黄金盎司"]["_status"] == "ok"
    assert by_label["恐慌指数"]["_status"] == "ok"           # 腾讯行情 VIX 已接入
    assert by_label["恐慌指数"]["value"] == "21.67"
    assert by_label["恐慌指数"]["delta_dir"] == "down"       # -4.08% 绿
    assert by_label["美债长债"]["_status"] == "ok"          # 收益率口径

    ind = cube._build_industry_cards()
    by_label_i = {c["label"]: c for c in ind}
    assert by_label_i["🧠 AI算力"]["_status"] == "ok"
    assert by_label_i["🧠 AI算力"]["tone"] == "up"          # +0.32% 红
    assert by_label_i["🧲 稀土"]["tone"] == "down"          # -1.83% 绿
    ok_count = sum(1 for c in ind if c["_status"] == "ok")
    assert ok_count == 3, f"样例概念表只有 3 个命中，其余应 unavailable：{ok_count}"
