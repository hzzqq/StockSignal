# -*- coding: utf-8 -*-
"""analyze_history 周期分类回归护栏：锁死「全期坍缩成修复试探」回归。

历史 bug：zt_pool 指标仅近 ~30 天 → analyze_history 全期 99.6% 判成「修复试探」。
修复点（modules/shepherd_reconstruct._enrich_zt_from_cache + shepherd_forecast 守卫）
后，现代交易段（2015+）已正常分化。本测试双保险：

1. test_analyze_history_no_collapse_on_varied_data：合成多级（牛/熊/修复/退潮）数据，
   断言阶段种类 ≥3 且「修复试探」占比 < 95% —— 锁死逻辑层不再坍缩（可移植，不依赖真实文件）。
2. test_analyze_history_real_history_modern_non_collapsed：若仓库内存在真实
   data/shepherd_history.csv（4094 行全历史），断言其现代段（2015+，已知已修复）非退化。
   真实文件被 gitignore 且不随仓库分发，故缺失时跳过（不阻塞 CI）；本机可锁真实产物。

验证目标：未来若 locate_cycle / _enrich_zt_from_cache 回归导致「单阶段霸屏 95%+」，
或真实历史表被错误重跑覆盖成退化数据，本测试会立刻报警。
"""
import os

import numpy as np
import pandas as pd
import pytest

from modules.shepherd_note import analyze_history
from modules.shepherd_reconstruct import _BREADTH_FILE


def _row(date, lu, ld, red, med, chl, zfr, zpr):
    return dict(
        date=date, limit_up=lu, limit_down=ld, red_ratio=red, median_chg=med,
        connect_hl=chl, zt_fail_ratio=zfr, zt_prev_ret=zpr,
        touch_down=0, zt_fail_count=0, hb_wave10=0, avg_price=10.0,
        up_count=lu, down_count=ld, flat_count=0,
    )


def _make_history(n_days, gen):
    dates = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rows = [_row(d.strftime("%Y-%m-%d"), *gen(i)) for i, d in enumerate(dates)]
    return pd.DataFrame(rows)


def test_analyze_history_no_collapse_on_varied_data():
    """合成牛/熊/修复/退潮混合序列 → 不得全判修复试探（锁死坍缩回归）。"""
    def gen(i):
        phase = i % 40
        if phase < 10:       # 主升高潮：高涨停、低炸板、高连板、次日强
            return (20, 1, 80, 3.0, 8, 10.0, 6.0)
        elif phase < 20:     # 冰点：低涨停、高跌停、次日弱
            return (1, 30, 20, -5.0, 1, 40.0, -2.0)
        elif phase < 30:     # 退潮：中涨停、中跌停
            return (5, 8, 45, -1.0, 3, 30.0, -1.0)
        else:                # 修复试探
            return (6, 2, 55, 1.0, 2, 25.0, 2.0)

    df = _make_history(240, gen)
    res = analyze_history(df)
    assert res["by_cycle"], "analyze_history 未产出任何阶段（应至少分类出若干阶段）"
    names = {b["name"] for b in res["by_cycle"]}
    assert len(names) >= 3, f"阶段种类过少（疑似坍缩）: {sorted(names)}"
    total = sum(b["count"] for b in res["by_cycle"])
    probe = next((b for b in res["by_cycle"] if b["name"] == "修复试探"), None)
    if probe is not None:
        share = probe["count"] / total * 100
        assert share < 95, f"修复试探占比 {share:.1f}%，仍坍缩成单阶段"


def test_analyze_history_real_history_modern_non_collapsed():
    """真实 shepherd_history.csv（若存在）现代段 2015+ 必须非退化。

    已知事实：2009-2013 广度退化（limit_up 全 0），2015+ 已修复。
    此测试锁住「现代段不再坍缩」这一已达成的事实，防止被错误重跑覆盖后静默回退。
    """
    if not os.path.exists(_BREADTH_FILE):
        pytest.skip("真实 shepherd_history.csv 不在（gitignore，未随仓库分发）")
    df = pd.read_csv(_BREADTH_FILE)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    modern = df[df["date"].dt.year >= 2015]
    if len(modern) < 50:
        pytest.skip(f"现代段样本不足（{len(modern)} 行），疑似被错误覆盖，人工核查")

    res = analyze_history(modern)
    assert res["by_cycle"], "现代段 analyze_history 未产出阶段"
    names = {b["name"] for b in res["by_cycle"]}
    assert len(names) >= 3, f"现代段阶段种类过少（坍缩？）: {sorted(names)}"
    total = sum(b["count"] for b in res["by_cycle"])
    probe = next((b for b in res["by_cycle"] if b["name"] == "修复试探"), None)
    if probe is not None:
        share = probe["count"] / total * 100
        assert share < 95, f"现代段修复试探占比 {share:.1f}%，修复应已生效却退化"
    # 高信噪「主升高潮」应被识别（现代段必有牛市段）
    climax = next((b for b in res["by_cycle"] if b["name"] == "主升高潮"), None)
    assert climax is not None, "现代段未识别到「主升高潮」——周期定位逻辑可能回退"
