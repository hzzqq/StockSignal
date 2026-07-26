"""
tests/test_research_state.py
=============================
多智能体投研共享状态（modules.quantagent.state）测试。

覆盖：DataFrame 注册表存/取、resolve_df 优先级、trace/error 追加与回调容错、
to_dict 剔除不可序列化字段（df/reporter）、以及 _json_safe 对 pandas Timestamp /
numpy 标量 / datetime 的净化保证（确保交付字典可严格 JSON 序列化）。
"""
import json

import pytest

import modules.quantagent.state as st


@pytest.fixture(autouse=True)
def _clear_df_registry():
    """_DF_REGISTRY 是模块级全局可变状态，用例间必须隔离。"""
    st._DF_REGISTRY.clear()
    yield
    st._DF_REGISTRY.clear()


def test_store_fetch_df_roundtrip():
    st.store_df("600519", {"k": "v"})
    assert st.fetch_df("600519") == {"k": "v"}
    assert st.fetch_df("nonexist") is None


def test_resolve_df_prefers_state_df():
    state = st.ResearchState(ticker="600519", df="STATE_DF")
    st.store_df("600519", "REGISTRY_DF")
    # state.df 优先
    assert st.resolve_df(state) == "STATE_DF"


def test_resolve_df_falls_back_to_registry():
    state = st.ResearchState(ticker="600519")
    st.store_df("600519", "REGISTRY_DF")
    assert st.resolve_df(state) == "REGISTRY_DF"


def test_resolve_df_no_df_returns_none():
    state = st.ResearchState(ticker="600519")
    # 既无 state.df 也无注册表
    assert st.resolve_df(state) is None


def test_add_trace_appends_and_invokes_reporter():
    calls = []
    state = st.ResearchState(ticker="x")
    state.reporter = lambda n, m: calls.append((n, m))
    state.add_trace("data_agent", "done")
    assert state.trace == [{"node": "data_agent", "log": "done"}]
    assert calls == [("data_agent", "done")]


def test_add_trace_reporter_failure_does_not_raise():
    def boom(n, m):
        raise RuntimeError("callback dead")

    state = st.ResearchState(ticker="x")
    state.reporter = boom
    # 回调异常不能影响主流程
    state.add_trace("node", "log")
    assert state.trace[-1] == {"node": "node", "log": "log"}


def test_add_error_appends():
    state = st.ResearchState(ticker="x")
    state.add_error("boom")
    assert state.errors == ["boom"]


def test_to_dict_excludes_df_and_reporter():
    state = st.ResearchState(ticker="600519", df=object())
    state.reporter = lambda n, m: None
    d = state.to_dict()
    assert "df" not in d
    assert "reporter" not in d
    assert d["ticker"] == "600519"


def test_to_dict_json_safe_with_pandas_timestamp():
    pd = pytest.importorskip("pandas")
    ts = pd.Timestamp("2024-01-02 09:30:00")
    state = st.ResearchState(ticker="x", market_brief={"last": ts})
    d = state.to_dict()
    assert d["market_brief"]["last"] == "2024-01-02T09:30:00"
    # 严格可 JSON 序列化
    json.dumps(d)


def test_to_dict_json_safe_with_numpy():
    np = pytest.importorskip("numpy")
    state = st.ResearchState(
        ticker="x",
        data_report={"count": np.int64(3), "ratio": np.float64(0.25)},
    )
    d = state.to_dict()
    assert d["data_report"]["count"] == 3
    assert d["data_report"]["ratio"] == 0.25
    json.dumps(d)


def test_to_dict_serialize_nested_datetime():
    import datetime as dt
    state = st.ResearchState(ticker="x", memory={"updated": dt.datetime(2024, 5, 1, 12, 0, 0)})
    d = state.to_dict()
    assert d["memory"]["updated"] == "2024-05-01T12:00:00"
    json.dumps(d)
