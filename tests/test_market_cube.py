"""
市场魔方页面 · 回归测试

两层验证：
1. 集成（AppTest 真跑页面）：渲染不抛未捕获异常；三路数据源全空时降级不黑屏。
2. 合并逻辑（直接单测 _load_cube）：真实字段形状下三路合并正确，
   不产生 pandas 后缀 KeyError，综合强度把「半导体」(资金流+涨停) 排为最强。

注：safe_fragment 把页面主体作为 Streamlit fragment 运行，AppTest 的 at.markdown
不捕获 fragment 内部正文，故「内容穿透」不能用 at.markdown 断言，改由第 2 层直接验证。
"""
from __future__ import annotations

import importlib.util
import os

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import modules.fundflow as _ff_mod
import modules.shepherd as _shep_mod
from modules.fetcher import StockFetcher


_SECTOR = pd.DataFrame({"行业": ["半导体", "白酒", "银行", "新能源"], "涨跌幅": [3.2, -1.1, 0.4, 2.0]})
_FLOW = pd.DataFrame({"行业": ["半导体", "白酒", "银行"], "涨跌幅": [3.1, -1.0, 0.5],
    "流入资金": [8e8, 2e8, 5e8], "流出资金": [3e8, 4e8, 2e8], "净额": [5e8, -2e8, 3e8],
    "领涨股": ["中芯国际", "茅台", "工行"], "领涨股涨跌幅": [6.0, -0.5, 1.2]})
_ZT = pd.DataFrame({"行业": ["半导体", "新能源"], "涨停家数": [8, 3]})


@pytest.fixture
def _patch(monkeypatch):
    monkeypatch.setattr(_ff_mod, "get_industry_fund_flow", lambda: _FLOW.copy())
    monkeypatch.setattr(StockFetcher, "get_sector_list", lambda self, force_refresh=False: _SECTOR.copy())
    monkeypatch.setattr(_shep_mod, "get_zt_industry_distribution",
                        lambda top=10, date=None: _ZT.copy())


def test_cube_renders_without_exception(_patch):
    """集成：真跑页面，渲染不抛未捕获异常（三路样例数据已打通合并）。"""
    at = AppTest.from_file("pages/16_市场魔方.py", default_timeout=90)
    at.run()
    assert not at.exception, f"市场魔方渲染异常: {at.exception[:3]}"


def test_cube_degrades_when_sources_empty(_patch, monkeypatch):
    """集成：三路全空仍渲染（只降级，不黑屏）。"""
    monkeypatch.setattr(_ff_mod, "get_industry_fund_flow", lambda: pd.DataFrame())
    monkeypatch.setattr(StockFetcher, "get_sector_list", lambda self, force_refresh=False: pd.DataFrame())
    monkeypatch.setattr(_shep_mod, "get_zt_industry_distribution", lambda top=10, date=None: pd.DataFrame())
    at = AppTest.from_file("pages/16_市场魔方.py", default_timeout=90)
    at.run()
    assert not at.exception, f"空数据下市场魔方应降级而非崩溃: {at.exception[:3]}"


def test_cube_merge_logic(_patch, monkeypatch):
    """直接单测 _load_cube：三路合并字段正确，无 suffix KeyError，半导体综合最强。"""
    os.environ["OFFLINE_TEST"] = "1"

    # stub streamlit，让页面 import + 底部 fragment 运行无害
    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def _cols(n=1, *a, **k):
        cnt = int(n) if isinstance(n, int) else 1
        return tuple(_Ctx() for _ in range(cnt))
    for fn in ("plotly_chart", "metric", "markdown", "caption", "divider", "page_link",
               "switch_page", "radio", "selectbox", "slider", "text", "json",
               "error", "exception", "success", "warning", "info"):
        monkeypatch.setattr(st, fn, lambda *a, **k: None)
    monkeypatch.setattr(st, "columns", _cols)
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(st, "set_page_config", lambda *a, **k: None)

    import modules.page_utils as _pu
    import modules.page_guard as _pg
    import modules.session as _sess
    monkeypatch.setattr(_pu, "render_standard_page", lambda *a, **k: False)
    monkeypatch.setattr(_pg, "safe_fragment", lambda name: (lambda f: f))
    monkeypatch.setattr(_pg, "safe_section", lambda *a, **k: _Ctx())
    monkeypatch.setattr(_pg, "render_data_degradation_banner", lambda *a, **k: None)
    monkeypatch.setattr(_sess, "trading_autorefresh", lambda *a, **k: None)

    spec = importlib.util.spec_from_file_location("cube_page_test", "pages/16_市场魔方.py")
    cube = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cube)  # 底部 fragment 用样例数据跑，无异常即合并 OK

    try:
        cube._load_cube.clear()
    except Exception:
        pass
    m, health, src = cube._load_cube("行业板块")
    assert not m.empty, "合并后 merged 不应为空"
    assert health == {"sector": True, "flow": True, "zt": True}, health
    row = m[m["行业"] == "半导体"].iloc[0]
    assert row["涨跌幅"] == 3.1, row["涨跌幅"]
    assert row["净额"] == 5e8, row["净额"]
    assert row["领涨股"] == "中芯国际"
    assert row["涨停家数"] == 8, row["涨停家数"]
    # 新能源不在资金流里 → 涨跌幅回落 base，涨停来自 zt
    nv = m[m["行业"] == "新能源"].iloc[0]
    assert nv["涨跌幅"] == 2.0, nv["涨跌幅"]
    assert nv["涨停家数"] == 3, nv["涨停家数"]
    # 综合强度：半导体应排第一
    comp = cube._composite(m)
    assert comp.iloc[0] == comp.max(), f"半导体应综合最强: {comp.tolist()}"
