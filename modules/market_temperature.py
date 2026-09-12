"""市场温度计：牧羊人 8 指标合成 0-100 综合温度 + 五档分档 + 极端区历史回测。

设计原则（与 P3 / 市场状态机一致的诚实口径）：
* 温度合成复用 ``shepherd.shepherd_temperature``（经验分位打分，跨年代可比）；
* 分档阈值由温度区间定（冰点 / 偏冷 / 中性 / 活跃 / 狂热）；
* 极端区历史回测 = 两大已实证能力：
    - ``sentiment_edge.panic_reversal``：极端恐慌 → 次日红盘（全历史 296 天 z=+4.36，可发布）；
    - ``market_regime.find_analogs``：对今日广度向量在全历史找最近相似日，统计其后市表现
      （无前视泄漏，历史相似≠预测）；
* 实时数据来自 ``shepherd.get_shepherd_today``；缺失优雅降级，绝不抛红错。

温度是**描述性**指标（市场当前冷热），不声称预测能力；极端区信号仅「恐慌出清后反弹」
这一条有统计依据，其余时刻明确弃权。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from modules import shepherd
from modules import sentiment_edge
from modules import market_regime as mr

logger = logging.getLogger(__name__)

# 温度分档：cold→hot 用蓝→红渐变（温度计语义，独立于 A 股红涨绿跌）。
# lo 含、hi 不含（100 由最后一档兜底）。
BANDS = [
    dict(level=0, lo=0, hi=20, label="冰点", color="#2563eb",
         advice="市场极度悲观、交投清淡。防守为主；可关注恐慌出清后的反转机会（见下方极端区信号）。"),
    dict(level=1, lo=20, hi=40, label="偏冷", color="#0891b2",
         advice="情绪偏弱、风险偏好低。控制仓位，等待右侧确认信号再出手。"),
    dict(level=2, lo=40, hi=60, label="中性", color="#d97706",
         advice="多空均衡、结构性机会为主。不追高，聚焦主线与事件驱动。"),
    dict(level=3, lo=60, hi=80, label="活跃", color="#ea580c",
         advice="风险偏好回升、赚钱效应好转。可积极围绕主线做多，但需留意内部分化。"),
    dict(level=4, lo=80, hi=101, label="狂热", color="#dc2626",
         advice="情绪过热、一致性预期强。注意分歧与兑现风险，避免高位接力。"),
]

# 历史情境类比所用的广度特征（必须与 market_regime._FEATURES 完全一致，
# find_analogs 内部按该常量构造 z-score 特征矩阵）。
ANALOG_FEATURES = ["red_ratio", "limit_up", "limit_down"]


def temperature_band(temp) -> dict:
    """把 0-100 温度映射到分档字典（含 label/color/advice/level）。

    非数值 / NaN 兜底为中性（50）。纯函数，可单测。
    """
    try:
        t = float(temp)
    except (TypeError, ValueError):
        t = 50.0
    if t != t:  # NaN
        t = 50.0
    t = max(0.0, min(100.0, t))
    for b in BANDS:
        if b["lo"] <= t < b["hi"]:
            return b
    return BANDS[-1]


def composite_temperature(today: dict, hist_days: int = 2000) -> float:
    """综合温度（0-100）。默认用长历史分位（2007 起）更稳。"""
    return float(shepherd.shepherd_temperature(today, hist_days))


def temperature_contributions(today: dict, hist_days: int = 2000) -> dict:
    """综合温度 + 各指标贡献明细。"""
    return shepherd.shepherd_temperature_detail(today, hist_days)


def extreme_zone_signal(today: dict) -> dict:
    """极端区信号：包 ``sentiment_edge.panic_reversal``（极端恐慌→次日红盘）。

    返回其完整结果字典；校准件缺失/指标缺失时返回 available=False / evaluated=False，
    页面据此诚实降级，绝不编造方向。
    """
    try:
        return sentiment_edge.panic_reversal(today)
    except Exception as e:  # noqa: BLE001
        logger.warning("[market_temperature] 极端区信号失败: %s", e)
        return dict(available=False, triggered=False, evaluated=False, hits=[],
                    abstain=True, statement=f"极端区信号计算异常：{e}")


def historical_analogs(today: dict, k: int = 8) -> dict:
    """对今日广度向量做历史相似日回看（无前视泄漏），返回 market_regime 的 analogs。

    做法：把今日实时广度（red_ratio/limit_up/limit_down）追加为历史 df 的最后一行，
    再对末行调用 find_analogs（其内部已排除目标日及邻近窗口，只回看过去）。
    今日某特征缺失时用历史末值兜底，避免 NaN 污染距离。

    :returns: {"available": bool, "today_metrics": {...}, "analogs": [...], "reason": str}
    """
    try:
        df = mr.load_breadth_history()
    except Exception as e:  # noqa: BLE001
        logger.warning("[market_temperature] 广度历史加载失败: %s", e)
        return {"available": False, "reason": f"广度历史加载失败：{e}", "analogs": [], "today_metrics": {}}
    if df is None or df.empty:
        return {"available": False, "reason": "广度历史为空", "analogs": [], "today_metrics": {}}

    row = {}
    for c in ANALOG_FEATURES:
        v = today.get(c)
        if v is None or (isinstance(v, float) and v != v):
            v = df[c].iloc[-1] if c in df.columns else 0.0
        try:
            row[c] = float(v)
        except (TypeError, ValueError):
            row[c] = float(df[c].iloc[-1]) if c in df.columns else 0.0

    new_row = df.iloc[-1:].copy()
    for c in ANALOG_FEATURES:
        new_row[c] = row[c]
    # 用今天日期，确保不会与历史某日命中（find_analogs 本就排除目标日，这里只是防御）
    new_row["date"] = pd.Timestamp.now().normalize()
    combined = pd.concat([df, new_row], ignore_index=True)
    target_idx = len(combined) - 1

    try:
        analogs = mr.find_analogs(combined, target_idx, k=k)
    except Exception as e:  # noqa: BLE001
        logger.warning("[market_temperature] 类比失败: %s", e)
        return {"available": False, "reason": f"类比失败：{e}", "analogs": [], "today_metrics": row}

    return {"available": True, "today_metrics": row, "analogs": analogs, "reason": ""}
