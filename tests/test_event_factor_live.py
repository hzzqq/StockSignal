"""事件因子适配器 · 真实信号集成测试（LIVE 层）。

与 tests/test_event_factor.py（离线合成夹具）互补：那层证「逻辑对」，
本层证「**真实落盘的 P1 信号文件**也能跑通」——即对接的是真事件数据而非演示。

运行机制（同 tests/test_live_integration.py 约定）：
- 默认 `pytest` 不收集（@pytest.mark.live + 配置排除）。
- 显式开启：`OFFLINE_TEST=0 pytest -m live tests/test_event_factor_live.py`
- 本机无真实 P1 信号目录时整层 skip（不误报）。

数据契约（来自 modules/p1_signal.py 解析的 signal_*_h10.json）：
  top_long/top_short: [{"symbol": "sh600869", "pred": 0.0297, "rank": 1.0}, ...]
  daily: [{"date": "2026-05-18", "symbol": "sh600000", "score": -0.014, "signal": "中性"}, ...]
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    """仅在 OFFLINE_TEST=0 时运行（同 test_live_integration 约定）。"""
    return os.environ.get("OFFLINE_TEST", "1") == "0"


def _real_signal_dir() -> str | None:
    """找到本机真实存在的 P1 信号目录；没有则返回 None（整层 skip）。"""
    from modules.p1_signal import discover_source_dirs

    for d in discover_source_dirs():
        try:
            if any(f.startswith("signal_") for f in os.listdir(d)):
                return d
        except OSError:
            continue
    return None


# 模块级缓存：真实目录只探测一次
_real_dir_cache: str | None = None


def _real_dir_once() -> str:
    """探测真实目录（模块内复用）；无则 pytest.skip。"""
    global _real_dir_cache
    if _real_dir_cache is None:
        d = _real_signal_dir()
        if d is None:
            pytest.skip("本机无真实 P1 信号目录")
        _real_dir_cache = d
    return _real_dir_cache


@pytest.fixture(scope="module")
def real_loader():
    """指向真实信号目录的 loader（只读，ttl 足够长避免重复扫盘）。"""
    if not _live_enabled():
        pytest.skip("需 OFFLINE_TEST=0 开启 LIVE 层")
    from modules.p1_signal import P1SignalLoader

    d = _real_dir_once()
    return P1SignalLoader(source_dirs=[d], ttl=10_000)


class TestRealEventFactor:
    def test_real_models_discovered(self, real_loader):
        """真实目录必须能发现至少一个模型，且 ev 在列（适配器默认模型）。"""
        models = real_loader.available_models()
        assert models, f"真实目录未发现任何模型信号: {real_loader.source_dirs}"
        assert "ev" in models, f"ev 模型缺失，现有: {models}"

    def test_real_top_long_hit(self, real_loader):
        """真实榜单里的标的必须命中「看多」，分数/排名为真实 float（绝不合成）。"""
        longs = real_loader.top_long("ev")
        assert longs, "真实 ev top_long 为空，请核查 P1 信号产出链路"
        target = longs[0]["symbol"]
        from modules.event_factor import get_event_factor

        r = get_event_factor(target, model="ev", loader=real_loader)
        assert r["available"] is True, f"真实榜单标的 {target} 未命中: {r}"
        assert r["signal"] == "看多"
        assert isinstance(r["score"], float)
        assert r["source"] == "P1-ev-top_long"
        # 分数必须等于文件里的真实 pred，而非兜底 0.0 伪造
        assert r["score"] == pytest.approx(float(longs[0]["pred"]))

    def test_real_top_short_hit(self, real_loader):
        shorts = real_loader.top_short("ev")
        if not shorts:
            pytest.skip("真实 ev top_short 为空（可能当日无空头信号）")
        target = shorts[0]["symbol"]
        from modules.event_factor import get_event_factor

        r = get_event_factor(target, model="ev", loader=real_loader)
        assert r["available"] is True
        assert r["signal"] == "看空"
        assert r["score"] == pytest.approx(float(shorts[0]["pred"]))
        assert r["score"] < 0, f"空头信号得分应为负: {r}"

    def test_real_daily_precise_fallback(self, real_loader):
        """不在榜内但在 daily 里的标的，走精确路径返回最新日期得分。"""
        df = real_loader.daily_df("ev")
        assert df is not None and not df.empty, "真实 ev daily 为空"
        # 找一个不在 top_long/top_short 榜内的标的（若全在榜内则跳过）
        longs = {r["symbol"] for r in real_loader.top_long("ev")}
        shorts = {r["symbol"] for r in real_loader.top_short("ev")}
        offboard = df[~df["symbol"].isin(longs | shorts)]
        if offboard.empty:
            pytest.skip("daily 标的全在榜内，无精确路径样本")
        row = offboard.sort_values("date").iloc[-1]
        from modules.event_factor import get_event_factor

        r = get_event_factor(row["symbol"], model="ev", loader=real_loader)
        assert r["available"] is True
        assert r["source"] == "P1-ev-daily"
        assert r["date"] == str(row["date"])
        assert r["score"] == pytest.approx(float(row["score"]))

    def test_real_absent_symbol_never_synthesized(self, real_loader):
        """核心契约：真实环境下取不到的标的必须 available=False，绝不编数。"""
        from modules.event_factor import get_event_factor

        r = get_event_factor("sh999999", model="ev", loader=real_loader)
        assert r["available"] is False
        assert "reason" in r
        assert "score" not in r, "不可用时不得携带任何分数（防合成泄漏）"
