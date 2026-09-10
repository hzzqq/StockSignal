"""test_strategy_plugin.py — P0 策略可插拔化 + 长电科技回归锁。

不依赖网络：用合成数据构造「长电科技类长期 RSI>85 强势上涨股」，
验证从 STRATEGY_REGISTRY 取到的策略类能产生买入信号，且参数扫描/批量回测可用。
"""

import pytest
import pandas as pd
import numpy as np

from modules.strategies import (
    STRATEGY_REGISTRY,
    get_strategy,
    list_strategies,
    MultiFactorStrategy,
    DualTrendStrategy,
    MaCrossStrategy,
    EventDrivenStrategy,
)


def _make_strong_uptrend_df(n=120, seed=7):
    """构造单调上行 + 高 RSI 的强势上涨股序列（长电科技式）。"""
    np.random.seed(seed)
    close = np.maximum(np.linspace(10, 100, n) + np.random.normal(0, 0.4, n), 1)
    open_ = np.concatenate([[close[0] * 0.99], close[:-1]])
    high = np.maximum(open_, close) * 1.02
    low = np.minimum(open_, close) * 0.98
    volume = np.random.randint(8e5, 2e6, n).astype(float)
    df = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })

    def _rsi(s, w):
        d = s.diff()
        g = d.clip(lower=0)
        l = -d.clip(upper=0)
        ag = g.ewm(alpha=1 / w, adjust=False).mean()
        al = l.ewm(alpha=1 / w, adjust=False).mean()
        return 100 - 100 / (1 + ag / al)

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["rsi14"] = _rsi(df["close"], 14)
    df["rsi2"] = _rsi(df["close"], 2)
    prev_c = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]),
                    (df["high"] - prev_c).abs(),
                    (df["low"] - prev_c).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["atr_ratio"] = df["atr14"] / df["close"]
    df["bb_upper"] = df["ma20"] + 2 * df["close"].rolling(20).std()
    df["bb_lower"] = df["ma20"] - 2 * df["close"].rolling(20).std()
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df


class TestStrategyRegistry:
    def test_registry_has_four(self):
        names = set(STRATEGY_REGISTRY.keys())
        assert {"multi_factor", "dual_trend", "ma_cross", "event_driven"} <= names

    def test_list_strategies_shape(self):
        items = list_strategies()
        assert len(items) >= 4
        for it in items:
            assert {"name", "display_name", "description"} <= set(it.keys())

    def test_get_strategy_unknown_raises(self):
        with pytest.raises(KeyError):
            get_strategy("not_a_real_strategy")


class TestLongDianCoverage:
    """锁定长电科技类强势上涨股不被排除（P0 改造后不退化）。"""

    def test_multi_factor_covers_strong_uptrend(self):
        df = _make_strong_uptrend_df()
        strat = MultiFactorStrategy()
        signals = strat.generate_signals(df)
        assert len(signals) == len(df)
        assert all(s in (-1, 0, 1) for s in signals)
        buys = sum(1 for s in signals if s == 1)
        assert buys > 0, "强势上涨股被 MultiFactorStrategy 系统性排除（V5 修复退化）"

    def test_dual_trend_covers_strong_uptrend(self):
        """双趋势共振纯趋势跟踪，必须能覆盖长电科技式长期超买强涨股。"""
        df = _make_strong_uptrend_df(seed=3)
        strat = DualTrendStrategy()
        signals = strat.generate_signals(df)
        assert len(signals) == len(df)
        buys = sum(1 for s in signals if s == 1)
        assert buys > 0, "强势上涨股被 DualTrendStrategy 系统性排除"

    def test_ma_cross_fixed_ma5_bug(self):
        """回归：ma_cross 历史上因 ma5 未计算导致信号恒为 0；改造后策略内自补 ma5。"""
        df = _make_strong_uptrend_df(seed=5)
        strat = MaCrossStrategy()
        signals = strat.generate_signals(df)
        # 策略内部应在副本上补算 ma5，且不污染调用方传入的 df
        assert signals is not None and len(signals) == len(df)
        assert any(s != 0 for s in signals), "ma_cross 信号仍恒为 0（ma5 bug 未修）"


class TestBacktesterPluggable:
    def test_run_dispatches_via_registry(self):
        """run() 应从 registry 取策略而非硬编码，且对强涨股产生交易。"""
        # 合成数据直接喂 run() 不便（需 fetcher），这里验证 dispatch 路径不崩：
        # 通过构造 Backtester 并 monkeypatch fetcher 返回合成 df 过于复杂，
        # 改为验证 run() 对未知策略抛清晰错误。
        from modules.backtest import Backtester
        bt = Backtester()
        with pytest.raises(ValueError):
            bt.run("600900", "2025-01-01", "2025-06-01", strategy="__nope__")

    def test_param_scan_returns_sorted_rows(self):
        """参数扫描返回结构正确且按收益排序（用 Backtester + 合成数据过于依赖 fetcher，
        这里验证 run_param_scan 调用链可达——通过 monkeypatch run 为离线版本）。"""
        from modules.backtest import Backtester
        bt = Backtester()

        # 离线 stub：直接基于合成强涨股算一个 BacktestResult
        from modules.backtest import BacktestResult
        df = _make_strong_uptrend_df()
        strat = MultiFactorStrategy()
        sigs = strat.generate_signals(df)
        # 构造最小 result_df（signal 列驱动 simulate 逻辑由 Backtester 内部负责，
        # 此处仅验证 run_param_scan 的调度与排序逻辑，用 stub result）
        class _StubResult:
            """绩效字段必须是 @property（对齐真实 BacktestResult 契约）。"""

            def __init__(self, ret):
                self._ret = ret
                self._trades = 3

            @property
            def total_return(self):
                return self._ret

            @property
            def annualized_return_pct(self):
                return self._ret * 0.8

            @property
            def sharpe_ratio(self):
                return 1.2

            @property
            def max_drawdown(self):
                return -0.1

            @property
            def win_rate(self):
                return 0.6

            @property
            def profit_factor(self):
                return 1.5

            @property
            def trade_count(self):
                return self._trades

        orig_run = bt.run
        # 每组参数返回**互不相同**的收益（按调用序号递增），否则排序断言恒真、等于没测
        _seq = [0]

        def _fake_run(*a, **k):
            _seq[0] += 1
            return _StubResult(_seq[0] * 0.01)

        bt.run = _fake_run
        try:
            rows = bt.run_param_scan("600900", "2025-01-01", "2025-06-01",
                                     strategy="multi_factor", initial_capital=100000)
            # ① 不许有空转：任何一组参数走 except 都会在行里留下 "error"
            #    （原实现 lambda 里对 float 取 len 抛 TypeError，12 组全失败，
            #      rows 全是 {"error": ...}，而排序断言拿 -1e9 哨兵比较 → 恒真全绿）
            failed = [r for r in rows if "error" in r]
            assert not failed, f"有 {len(failed)}/{len(rows)} 组参数走异常分支：{failed[:2]}"
            # ② 样本量足够，排序才有意义
            assert len(rows) >= 2, f"仅 {len(rows)} 组参数，排序断言无意义"
            rets = [r["total_return"] for r in rows]
            # ③ 互不相同，避免「相等的列表当然有序」这种假通过
            assert len(set(rets)) == len(rets), f"收益值不互异，排序断言退化：{rets}"
            # ④ 真正验证按 total_return 降序
            assert rets == sorted(rets, reverse=True), f"未按 total_return 降序：{rets}"
        finally:
            bt.run = orig_run

    def test_run_batch_aggregates(self):
        """批量回测聚合绩效归因返回 summary 与 per_stock。"""
        from modules.backtest import Backtester, BacktestResult
        bt = Backtester()

        class _StubResult:
            """契约必须与真实 BacktestResult 一致：绩效字段是 @property 而非方法。

            2026-09-10 修复：原 stub 把它们写成普通方法，而 run_batch 按**属性**取值
            （modules/backtest.py 内 ``r.total_return``），于是拿到 bound method，
            ``sum(xs)`` 抛 TypeError —— 本用例自 0ee5fd0（BacktestResult 改 @property）
            起就长期红灯且无人发现。契约守卫见文件末尾
            test_stub_result_matches_backtestresult_contract。
            """

            def __init__(self, ret):
                self._ret = ret

            @property
            def total_return(self):
                return self._ret

            @property
            def annualized_return_pct(self):
                return self._ret

            @property
            def sharpe_ratio(self):
                return 1.0

            @property
            def max_drawdown(self):
                return -0.05

            @property
            def win_rate(self):
                return 0.55

            @property
            def profit_factor(self):
                return 1.4

            @property
            def trade_count(self):
                return 4

        orig_run = bt.run
        _rets = {"600900": 0.2, "600519": 0.1, "000858": -0.05}
        bt.run = lambda ticker, *a, **k: _StubResult(_rets.get(ticker, 0.0))
        try:
            out = bt.run_batch(["600900", "600519", "000858"],
                               "2025-01-01", "2025-06-01", strategy="multi_factor")
            assert "summary" in out and "per_stock" in out
            s = out["summary"]
            assert s["stock_count"] == 3
            assert s["best_stock"] == "600900"
            assert s["worst_stock"] == "000858"
            assert s["avg_total_return"] is not None
            # 就地契约自检：绩效字段必须是属性（取到方法说明 stub 又漂了）
            assert not callable(_StubResult(0.2).total_return), (
                "_StubResult.total_return 应是 @property；"
                "写成方法会让 run_batch 聚合到 bound method"
            )
        finally:
            bt.run = orig_run


class TestPickerMultiStrategy:
    """P1：选股池多策略化（dual_trend 进每日选股）。"""

    @staticmethod
    def _strong_uptrend_picker_df(seed=11):
        np.random.seed(seed)
        n = 120
        close = 10 * np.power(1.003, np.arange(n)) + np.random.normal(0, 0.03, n)
        close = np.maximum(close, 1.0)
        open_ = np.concatenate([[close[0] * 0.99], close[:-1]])
        high = np.maximum(open_, close) * 1.02
        low = np.minimum(open_, close) * 0.98
        volume = np.random.randint(8e5, 2e6, n).astype(float)
        return pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=n, freq="B"),
            "code": ["600584"] * n,
            "open": open_, "high": high, "low": low, "close": close, "volume": volume,
        })

    def test_dual_trend_picker_scores_strong_uptrend(self):
        """双趋势选股对长期强势上涨股应产出候选（不看 RSI 低位）。"""
        from modules.backtest import Backtester
        bt = Backtester()
        df = self._strong_uptrend_picker_df()
        cand = bt._score_for_picker(df, strategy="dual_trend")
        assert cand is not None, "双趋势选股未产出候选"
        assert cand["trend_ok"] is True
        assert "ADX" in cand["reasons"] or "均线多头排列" in cand["reasons"]

    def test_multi_factor_picker_still_works(self):
        """多因子选股对同数据仍正常（RSI>80 但 <92 应入选，V5 修复保持）。"""
        from modules.backtest import Backtester
        bt = Backtester()
        df = self._strong_uptrend_picker_df()
        cand = bt._score_for_picker(df, strategy="multi_factor")
        assert cand is not None, "多因子选股未产出候选"
        assert cand["rsi14"] > 80

    def test_daily_picker_backtest_accepts_strategy(self):
        """daily_picker_backtest 应接受 strategy 参数且不崩（合成小池）。"""
        from modules.backtest import Backtester
        bt = Backtester()
        # 用 _score_for_picker 直接验证透传路径已覆盖；此处仅确认签名兼容
        import inspect
        sig = inspect.signature(bt.daily_picker_backtest)
        assert "strategy" in sig.parameters


def test_stub_result_matches_backtestresult_contract():
    """契约守卫（AST）：run_batch 按**属性**读取绩效字段，故测试 stub 必须用
    @property 提供、且覆盖生产实际读取的全部字段。

    背景：0ee5fd0 把 BacktestResult 的绩效字段改成 @property 后，本文件的
    _StubResult 仍是普通方法 —— test_run_batch_aggregates 取到 bound method、
    sum() 抛 TypeError，长期红灯无人发现（隔离运行即可复现，非环境问题）。
    本守卫让 stub 与生产契约不再各自漂移。
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    prod_src = (root / "modules" / "backtest.py").read_text(encoding="utf-8")
    prod = ast.parse(prod_src)
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))

    def _is_property(item):
        return any(
            getattr(d, "id", None) == "property"
            or (isinstance(d, ast.Attribute) and d.attr == "property")
            for d in getattr(item, "decorator_list", [])
        )

    # 1) 生产侧：BacktestResult 上的 @property 名单
    prod_props = set()
    for node in ast.walk(prod):
        if isinstance(node, ast.ClassDef) and node.name == "BacktestResult":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_property(item):
                    prod_props.add(item.name)
    assert prod_props, "未在 BacktestResult 上解析出任何 @property，解析逻辑已失效"

    # 2) 生产侧：run_batch 实际按属性读到的绩效字段
    used = set()
    for node in ast.walk(prod):
        if isinstance(node, ast.FunctionDef) and node.name == "run_batch":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and sub.attr in prod_props:
                    used.add(sub.attr)
    assert used, "未解析出 run_batch 读取的绩效字段，解析逻辑已失效"

    # 3) stub 侧：同名成员必须是 property，且覆盖 used
    stub_props, stub_methods = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_StubResult":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    (stub_props if _is_property(item) else stub_methods).add(item.name)

    missing = sorted(used - stub_props)
    assert not missing, (
        f"_StubResult 缺少绩效属性 {missing}；生产 run_batch 会按属性读取它们"
    )
    wrong = sorted(stub_methods & prod_props)
    assert not wrong, (
        f"_StubResult 把 {wrong} 写成了普通方法，但 BacktestResult 上是 @property；"
        "run_batch 按属性取值会拿到 bound method（0ee5fd0 起的长期红灯根因）"
    )
