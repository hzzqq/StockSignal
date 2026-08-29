"""
tests/test_shepherd_note_backtest.py — 历史情绪真机回测

覆盖：
  · analyze_history 在「含 zt_prev_ret」的合成历史上能产出有效准确率（规律验证闭环）
  · backtest_real 走 get_shepherd_indicators_range(backfill=True) 拉真实区间，
    离线 monkeypatch 数据源后返回非空 analysis（不抛异常）
"""
import pandas as pd

import modules.shepherd_note as _sn


def _make_mainrise_df(n=12):
    """构造一段「主升高潮」合成历史：高度打开 + 封板稳 + 有溢价 → 次日偏强。"""
    dates = pd.date_range("2026-03-01", periods=n, freq="B")
    rows = []
    for i in range(n):
        rows.append(dict(
            date=dates[i],
            limit_up=120.0, limit_down=2.0, connect_hl=7.0,
            connect_2b=20.0, zt_fail_ratio=10.0, zt_prev_ret=3.0,
            median_chg=1.5, red_ratio=85.0,
        ))
    return pd.DataFrame(rows)


def test_analyze_history_produces_accuracy():
    df = _make_mainrise_df(12)
    a = _sn.analyze_history(df)
    assert a["rows"], "应产出逐日明细"
    assert a["accuracy"]["total"] == 11      # n-1 对
    assert a["accuracy"]["valid"] == 11      # zt_prev_ret 全可得
    assert a["accuracy"]["rate"] == 100.0    # 主升→次日偏强 全命中
    assert a["by_cycle"], "应按情绪阶段聚合"
    # 主升高潮阶段应出现且次日偏强胜率 100
    main = [b for b in a["by_cycle"] if b["cycle_id"] == "main"]
    assert main, "应识别到主升高潮阶段"
    assert main[0]["win_rate"] == 100.0


def test_analyze_history_empty_on_short():
    df = _make_mainrise_df(2)   # <3 行
    a = _sn.analyze_history(df)
    assert a["rows"] == []


def test_backtest_real_offline(monkeypatch):
    df = _make_mainrise_df(20)

    def _fake_range(start, end, backfill=False):
        return df, {"available": ["limit_up", "zt_prev_ret"], "missing_columns": {}, "unavailable": []}

    monkeypatch.setattr("modules.shepherd.get_shepherd_indicators_range", _fake_range)
    analysis, meta = _sn.backtest_real(60)
    assert analysis["rows"], "真机回测应返回逐日明细"
    assert meta.get("available") == ["limit_up", "zt_prev_ret"]
    assert analysis["accuracy"]["rate"] == 100.0


def test_backtest_real_handles_network_error(monkeypatch):
    def _fake_range(start, end, backfill=False):
        raise RuntimeError("network down")

    monkeypatch.setattr("modules.shepherd.get_shepherd_indicators_range", _fake_range)
    analysis, meta = _sn.backtest_real(60)
    assert analysis["rows"] == []
    assert "error" in meta
