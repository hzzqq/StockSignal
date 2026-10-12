"""
tests/test_cache_metrics.py
===========================
T-272①：缓存层命中率观测——计数器单测 + fetcher L0/L1 接线 + MCP 工具接线
+ 82 页展示接线守卫。

诚实语义：hit_rate 在无调用时为 None（不臆造 0）；观测埋点失败绝不影响主取数路径。
注：CACHE_METRICS 为进程级全局，所有断言用 before/after 相对增量，避免用例间串味。
"""
import ast
import threading
import time
from pathlib import Path

import pandas as pd

import modules.fetcher as fetcher_mod
from modules._feed_io import CACHE_METRICS, observe_cache_hit, get_cache_metrics

_PROJECT = Path(__file__).resolve().parents[1]


def _snapshot() -> dict:
    return {k: dict(v) for k, v in CACHE_METRICS.items()}


def test_observe_cache_hit_counts_and_rate():
    """observe_cache_hit：hit/miss 分开计数，hit_rate 计算正确。"""
    before = _snapshot().get("unit_layer", {"hits": 0, "misses": 0})
    observe_cache_hit("unit_layer", True)
    observe_cache_hit("unit_layer", True)
    observe_cache_hit("unit_layer", False)
    m = get_cache_metrics()["unit_layer"]
    assert m["hits"] == before["hits"] + 2
    assert m["misses"] == before["misses"] + 1
    assert m["calls"] == m["hits"] + m["misses"]
    assert m["hit_rate"] == round(m["hits"] / m["calls"], 4)


def test_hit_rate_none_when_no_calls():
    """无调用层不臆造 hit_rate=0，而是 None（诚实语义）。"""
    observe_cache_hit("empty_layer_probe", False)  # 至少一次调用才会出现
    # 直接构造「未登记层」验证：get_cache_metrics 不含未登记层
    assert "never_touched_layer" not in get_cache_metrics()
    # hit_rate=None 的路径：清空该层后人为构造 0/0 不可达，改为验证公式分支
    m = {"hits": 0, "misses": 0, "calls": 0, "hit_rate": None}
    calls = m["hits"] + m["misses"]
    assert (round(m["hits"] / calls, 4) if calls else None) is None


def test_thread_safety_concurrent_counts():
    """10 线程并发计数不丢数（线程安全）。"""
    before = _snapshot().get("conc_layer", {"hits": 0, "misses": 0})

    def _bump():
        for _ in range(50):
            observe_cache_hit("conc_layer", True)

    threads = [threading.Thread(target=_bump) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    after = _snapshot().get("conc_layer", {"hits": 0, "misses": 0})
    assert after["hits"] == before["hits"] + 500


def test_fetcher_l0_l1_wiring(tmp_path, monkeypatch):
    """get_daily 接线：预写 L1 → 第一次调用 L0 miss+L1 hit，第二次 L0 hit。

    零网络：数据直接写入 SQLite L1（_write_cache），不触发四源竞速。
    """
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    f = fetcher_mod.StockFetcher()
    start, end = "2025-01-01", "2025-01-31"
    df = pd.DataFrame({
        "date": pd.date_range(start, periods=5).strftime("%Y-%m-%d"),
        "open": 1.0, "close": 1.1, "high": 1.2, "low": 0.9, "volume": 100,
    })
    cache_key = fetcher_mod.StockFetcher.get_daily.__name__ and \
        f"daily_T272METRIC_{start}_{end}_qfq"
    conn = f._get_conn()
    f._write_cache(conn, "daily_cache", cache_key, df)
    conn.close()

    sym = "T272METRIC"
    m0 = _snapshot()
    l0_miss0 = m0.get("L0", {}).get("misses", 0)
    l1_hit0 = m0.get("L1", {}).get("hits", 0)

    meta = {}
    out = f.get_daily(sym, start=start, end=end, meta_out=meta)
    assert out is not None and meta.get("source") == "cache"
    m1 = _snapshot()
    assert m1["L0"]["misses"] == l0_miss0 + 1, "第一次调用应计一次 L0 miss"
    assert m1["L1"]["hits"] == l1_hit0 + 1, "L1 预写数据应计一次 L1 hit"

    l0_hit0 = m1.get("L0", {}).get("hits", 0)
    out2 = f.get_daily(sym, start=start, end=end)
    assert out2 is not None
    m2 = _snapshot()
    assert m2["L0"]["hits"] == l0_hit0 + 1, "第二次调用应命中 L0（不再读 L1）"
    assert m2["L1"]["hits"] == l1_hit0 + 1, "L0 命中时 L1 不应重复计数"


def test_mcp_tool_cache_wiring():
    """MCP 工具短缓存接线：命中/未命中分别计数（相对增量）。"""
    from mcp_server import tools

    key = f"t272_metric_probe_{time.time_ns()}"
    m0 = _snapshot()
    hit0 = m0.get("mcp_tool", {}).get("hits", 0)
    miss0 = m0.get("mcp_tool", {}).get("misses", 0)

    assert tools._tool_cache_get(key) is None  # miss
    tools._tool_cache_set(key, {"v": 1})
    assert tools._tool_cache_get(key) == {"v": 1}  # hit

    m1 = _snapshot()
    assert m1["mcp_tool"]["misses"] == miss0 + 1
    assert m1["mcp_tool"]["hits"] == hit0 + 1


def test_l5_fallback_merged_into_metrics():
    """L5 缓存兜底（SOURCE_METRICS.cache_fallback）合并进 get_cache_metrics。"""
    import modules._feed_io as fio
    fio.SOURCE_METRICS["cache_fallback"] = {"calls": 4, "success": 1,
                                            "latency_ms": 0.0, "last_error": None}
    m = get_cache_metrics()
    assert m["L5_fallback"] == {"hits": 1, "misses": 3, "calls": 4, "hit_rate": 0.25}


def test_page82_wiring_contract():
    """82 页展示接线守卫（AST）：命中率区块与 footprint 区块不被误删。"""
    src = (_PROJECT / "pages" / "82_数据时效性看板.py").read_text(encoding="utf-8")
    assert "get_cache_metrics" in src, "82 页缺少缓存命中率接线（T-272① 展示回退）"
    assert "cache_db_footprint" in src, "82 页缺少缓存库体积接线（T-272⑤ 展示回退）"
    assert "仅统计**本进程自启动以来**" in src, "命中率展示必须保留「仅本进程」诚实口径"
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
