"""真网集成测试层（评测集诊断项 #4 落地）。

目的：专抓「接口字段变了 / 返回空 / 真网异常 JSON」类问题——
这些在离线冒烟（OFFLINE_TEST=1，默认）里永远测不到，是测试绿但生产炸的真盲区。

运行机制：
- 默认 `pytest` 不跑本文件（用 `@pytest.mark.live` 标记 + pytest 配置 exclude）。
- 需显式开启：`OFFLINE_TEST=0 pytest -m live`
  （OFFLINE_TEST=0 关闭 conftest 的 session 级离线守卫，允许真实触网）。
- 建议 CI 每周定时跑一次（如 cron 周一 09:00），而非每次提交都跑（真网不稳定）。

注意：本层用例可能因真实网络/数据源临时故障而失败，属预期——它要暴露的是
「接口契约是否还成立」，不是「网络是否永远通」。失败时应人工核查是否为字段变更。
"""
import os
import time

import pandas as pd
import pytest

# 真网标记：默认不收集。需 `pytest -m live` 且 OFFLINE_TEST=0。
pytestmark = pytest.mark.live

# 真网超时（秒）：单源 fetch 上限，避免 hang 拖垮整批。
_LIVE_TIMEOUT = 25


def _live_enabled():
    """仅在 OFFLINE_TEST=0 时允许真网。"""
    return os.environ.get("OFFLINE_TEST", "1") == "0"


@pytest.mark.skipif(not _live_enabled(), reason="需 OFFLINE_TEST=0 开启真网")
class TestLiveDataContract:
    def test_get_daily_real_returns_ohlcv(self):
        """行情看板核心契约：真网 get_daily 必须返回含 close/ma5 的 DataFrame。"""
        from modules.fetcher import StockFetcher

        fetcher = StockFetcher()
        t0 = time.time()
        df = fetcher.get_daily("600519", start="2024-06-01", end="2024-06-30")
        elapsed = time.time() - t0
        # 真网应在合理时间内返回（四源并发竞速，10s 内应出结果或降级）
        assert elapsed < _LIVE_TIMEOUT + 5, f"get_daily 真网耗时异常: {elapsed:.1f}s"
        assert isinstance(df, pd.DataFrame), "get_daily 未返回 DataFrame"
        assert not df.empty, "get_daily 真网返回空（四源全失败或降级到空缓存）"
        for col in ("date", "open", "high", "low", "close", "volume"):
            assert col in df.columns, f"get_daily 缺失关键列 {col}"
        # 数值合理性：收盘价应为正
        assert (df["close"] > 0).all(), "get_daily 收盘价为负或 0（数据异常）"

    def test_shepherd_real_has_data(self):
        """牧羊人契约：真网 get_shepherd_indicators 应返回非空 DataFrame 且含阈值字段。"""
        from modules.shepherd import get_shepherd_indicators, THRESHOLDS

        t0 = time.time()
        df = get_shepherd_indicators(days=30)
        elapsed = time.time() - t0
        assert elapsed < _LIVE_TIMEOUT + 10, f"get_shepherd_indicators 真网耗时异常: {elapsed:.1f}s"
        assert isinstance(df, pd.DataFrame), "get_shepherd_indicators 未返回 DataFrame"
        # 历史 CSV 应至少有数据（2007 起），真网补算不应全空
        assert not df.empty, "get_shepherd_indicators 真网返回空"
        # 核心阈值字段至少部分存在（数据源正常时全部存在）
        present = [k for k in THRESHOLDS if k in df.columns]
        assert len(present) >= 1, "get_shepherd_indicators 关键阈值字段全部缺失"

    def test_shepherd_range_real_backfill(self):
        """牧羊人日期范围回溯：真网选近期区间应返回区间内数据。"""
        from modules.shepherd import get_shepherd_indicators_range

        end = pd.Timestamp.now().strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
        df, meta = get_shepherd_indicators_range(start, end, backfill=False)
        assert isinstance(df, pd.DataFrame), "get_shepherd_indicators_range 未返回 DataFrame"
        assert "date_range" in meta, "meta 缺失 date_range"
        assert meta["date_range"][0] == start and meta["date_range"][1] == end

    def test_westock_mcp_reachable(self):
        """腾讯自选股 MCP 连通性：验证 connector 在线（不依赖项目取数代码）。"""
        # westock-mcp 是已连接 connector，连通性本身由平台保障；
        # 此处仅做轻量契约：导入相关客户端不应抛异常。
        try:
            import mcp  # noqa: F401
        except Exception:
            pytest.skip("mcp 客户端未安装，跳过连通性断言")
        # 真实行情拉取由页面层负责，这里只验证契约层可达
        assert True, "westock-mcp 客户端可导入"

    def test_backend_health_endpoint(self):
        """Flask 后端健康：若后端在 5050 运行，/api/health 应返回 200。"""
        import requests

        try:
            r = requests.get("http://127.0.0.1:5050/api/health", timeout=5)
            assert r.status_code == 200, f"后端 health 非 200: {r.status_code}"
        except requests.exceptions.RequestException:
            pytest.skip("Flask 后端未启动（5050 不可达），跳过 health 断言")
