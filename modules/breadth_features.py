"""
模块 breadth_features：牧羊人离线真值的数据可用性闸门（方案⑥–⑩ 共用）

背景（诚实声明，经实测确认，2026-09-11）：
  · 健康真值镜像 `data/shepherd_history.json`（4771 行，2007 起）实际只可靠填充 7 个广度字段：
      up_count / down_count / flat_count / limit_up / limit_down / red_ratio (+ date)
  · `connect_hl` / `zt_fail_ratio` / `zt_prev_ret` 虽在 JSON 结构里，但 99.7% 为 NaN（仅约 14 行有值），
    不足以支撑任何时间序列/相关性/聚类分析 → 视为离线缺真值。
  · `connect_2b` / `fc_ratio` / `touch_down` / `median_chg` / `hb_wave10` / `avg_price` / `turnover_amt`
    根本不在 JSON 中，`load_breadth_history` 会填 0.0 → 全 0 常数，不可用。

因此：所有新页只允许使用 REAL_FEATURES，并对候选维度做「非空率 + 方差」闸门，
把不可用维度显式剔除并说明原因，绝不把全 0/全 NaN 当真实数据画进图表。
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 离线健康镜像中 *可靠* 填充的广度字段（均 ~100% 非空）
REAL_FEATURES = ["up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio"]

# 8 指标广度体系中「离线缺真值」的维度（用于页面诚实声明，不进入计算）
OFFLINE_MISSING = {
    "connect_hl": "连板高度（离线健康镜像 99.7% 为 NaN）",
    "connect_2b": "连板家数≥2板（离线镜像无此字段，被填 0）",
    "zt_fail_ratio": "炸板率（离线健康镜像 99.7% 为 NaN）",
    "fc_ratio": "平均封成比（离线镜像无此字段，被填 0）",
    "zt_prev_ret": "昨日涨停表现（离线健康镜像 99.7% 为 NaN）",
    "touch_down": "倒跌停家数（离线镜像无此字段，被填 0）",
    "median_chg": "中位数涨跌幅（离线镜像无此字段，被填 0）",
    "hb_wave10": "回头波>10%家数（离线镜像无此字段，被填 0）",
    "avg_price": "平均股价（离线镜像无此字段，被填 0）",
    "turnover_amt": "全A成交额（离线镜像无此字段，被填 0）",
}

_LABELS = {
    "up_count": "上涨家数", "down_count": "下跌家数", "flat_count": "平盘家数",
    "limit_up": "涨停家数", "limit_down": "跌停家数", "red_ratio": "红盘占比(%)",
}


def labels() -> dict:
    return dict(_LABELS)


def _nonnull_ratio(s: pd.Series) -> float:
    num = pd.to_numeric(s, errors="coerce")
    return float(num.notna().mean())


def _coef_variation(s: pd.Series) -> float:
    num = pd.to_numeric(s, errors="coerce").dropna()
    if len(num) < 2:
        return 0.0
    m = num.mean()
    if m == 0 or m != m:
        sd = num.std()
        return float(sd)
    return float(num.std() / abs(m))


def usable_dims(df: pd.DataFrame, candidate=None, min_nonnull: float = 0.2,
                min_cv: float = 1e-6) -> tuple:
    """对候选维度做数据质量闸门，返回 (可用维度列表, 被剔除{维度: 原因})。

    剔除规则：
      · 列不存在 → "离线无真值"
      · 非空率 < min_nonnull → "非空率过低(缺失主导)"
      · 变异系数 < min_cv（近似常数）→ "近乎常数(无信息)"
    """
    candidate = candidate or REAL_FEATURES
    usable, dropped = [], {}
    for c in candidate:
        if c not in df.columns:
            dropped[c] = OFFLINE_MISSING.get(c, "离线无真值（字段缺失）")
            continue
        s = df[c]
        nr = _nonnull_ratio(s)
        if nr < min_nonnull:
            dropped[c] = f"非空率 {nr*100:.1f}% 过低（缺失主导）"
            continue
        cv = _coef_variation(s)
        if cv < min_cv:
            dropped[c] = f"变异系数≈0（近乎常数，无信息）"
            continue
        usable.append(c)
    return usable, dropped


def availability_report(df: pd.DataFrame) -> dict:
    """生成诚实的数据可用性报告（覆盖 8 指标广度体系全部维度）。"""
    all_dims = list(REAL_FEATURES) + list(OFFLINE_MISSING.keys())
    report = {}
    for c in all_dims:
        if c in df.columns:
            nr = _nonnull_ratio(df[c])
            if nr >= 0.2:
                report[c] = dict(status="available", nonnull_pct=round(nr * 100, 1))
            else:
                report[c] = dict(status="sparse", nonnull_pct=round(nr * 100, 1),
                                 reason=OFFLINE_MISSING.get(c, "缺失主导"))
        else:
            report[c] = dict(status="missing", reason=OFFLINE_MISSING.get(c, "离线无此字段"))
    return report
