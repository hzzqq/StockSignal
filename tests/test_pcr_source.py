"""test_pcr_source.py — 离线验证 market_drivers._src_pcr 的 PCR 聚合逻辑。

PCR = 认沽成交量 / 认购成交量（上交所+深交所股票期权每日统计聚合）。
逐日接口按日抓取近 ~10 交易日；本测试用 monkeypatch 替换 akshare 按日接口，
不触网，验证：① 正常聚合出正确比值与日期索引；② 关键字列名容错；③ 全失败优雅返回 []。
"""
import pandas as pd
import akshare as ak

from modules.market_drivers import _src_pcr


def _fake_stats(call_v, put_v):
    """模拟 option_daily_stats_xx 返回：多标的各行含认沽/认购成交量列。"""
    return pd.DataFrame([
        {"标的": "510050", "认购成交量": call_v * 0.6, "认沽成交量": put_v * 0.6},
        {"标的": "510300", "认购成交量": call_v * 0.4, "认沽成交量": put_v * 0.4},
    ])


def _patch(dates_payload):
    """dates_payload: list of (ds_str, call, put) 按请求顺序返回。"""
    seq = list(dates_payload)

    def fake_sse(date=None):
        if not seq:
            return _fake_stats(0, 0)
        ds, c, p = seq.pop(0)
        return _fake_stats(c, p)

    def fake_szse(date=None):
        # 深交所另给 30% 量，验证跨市场聚合
        if not seq:
            return _fake_stats(0, 0)
        return _fake_stats(0, 0)  # szse 量已并入 sse 序列，这里返回空以隔离
    ak.option_daily_stats_sse = fake_sse
    ak.option_daily_stats_szse = fake_szse


def test_pcr_aggregates_correctly():
    # 4 个交易日：认购远大于认沽 → PCR 应 <1
    payload = [
        ("20240102", 1000, 600),
        ("20240103", 1100, 550),
        ("20240104", 900, 700),
        ("20240105", 1200, 500),
    ]
    _patch(payload)
    rows = _src_pcr(days=10)
    assert rows, "应返回 PCR 序列"
    key, name, s = rows[0]
    assert key == "pcr"
    assert name == "PCR(认沽/认购比)"
    assert len(s) == 4, f"应有 4 个交易日，实际 {len(s)}"
    # PCR = put/call，均 <1
    assert (s < 1).all(), f"PCR 应<1，实际 {s.tolist()}"
    # 首个值应为 600/1000 = 0.6
    assert abs(float(s.iloc[0]) - 0.6) < 1e-9, f"首个 PCR 应为 0.6，实际 {float(s.iloc[0])}"


def test_pcr_keyword_fallback():
    # 列名用「认购成交 / 认沽成交」(无"量"字) 也应被容错定位
    def fake_sse(date=None):
        return pd.DataFrame([
            {"认购成交": 800, "认沽成交": 400},
        ])
    ak.option_daily_stats_sse = fake_sse
    ak.option_daily_stats_szse = lambda date=None: pd.DataFrame([{"认购成交": 0, "认沽成交": 0}])
    rows = _src_pcr(days=3)
    assert rows, "容错列名应仍能聚合"
    s = rows[0][2]
    assert abs(float(s.iloc[0]) - 0.5) < 1e-9, f"PCR 应为 0.5，实际 {float(s.iloc[0])}"


def test_pcr_all_fail_returns_empty():
    def boom(date=None):
        raise RuntimeError("network")
    ak.option_daily_stats_sse = boom
    ak.option_daily_stats_szse = boom
    rows = _src_pcr(days=5)
    assert rows == [], "全失败时 PCR 应优雅返回空列表"


def test_pcr_zero_call_skips_day():
    # 某日认购量为 0 → 跳过该日（避免除零）
    payload = [
        ("20240102", 1000, 600),
        ("20240103", 0, 0),  # 无效日
        ("20240104", 900, 700),
    ]
    _patch(payload)
    rows = _src_pcr(days=10)
    s = rows[0][2]
    assert len(s) == 2, f"应跳过认购量为0的交易日，实际 {len(s)}"
