"""
技术面分析模块
对清洗后的行情 DataFrame 计算四类技术指标解读：
  1) 均线 / 趋势状态
  2) 动量 / 涨跌幅
  3) 量能分析
  4) K 线形态识别

所有函数都是纯计算（不入数据库），便于在 Streamlit 直接展示。
约定输入：DataCleaner.full_pipeline() 之后的 DataFrame，
        至少包含列 [date, open, high, low, close, volume,
                    return_1d, return_5d, return_20d,
                    ma5, ma10, ma20, ma60]
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


# ============================================================
# 1) 均线 / 趋势状态
# ============================================================
def analyze_trend(df: pd.DataFrame) -> Dict[str, Any]:
    """
    分析均线趋势状态。

    返回字段：
      ma_values   : 各均线最新值
      price       : 最新收盘价
      arrangement : 多头 / 空头 / 纠缠
      above_count : 收盘价站上 N 条均线之上
      trend_label : 简明文字标签
      trend_score : 0-100 趋势强度
    """
    if df is None or df.empty:
        return {"error": "数据为空"}
    if "close" not in df.columns:
        return {"error": "缺少 close 列"}

    latest = df.iloc[-1]
    close = float(latest["close"])
    ma_map = {w: float(latest[f"ma{w}"]) for w in (5, 10, 20, 60) if f"ma{w}" in df.columns}

    # 站上均线数
    above_count = sum(1 for v in ma_map.values() if close > v)

    # 多空排列判断
    arr_text, arr_score = "纠缠", 50
    ordered = [ma_map.get(5), ma_map.get(10), ma_map.get(20), ma_map.get(60)]
    ordered = [v for v in ordered if v is not None]
    if len(ordered) >= 3:
        # 严格多头：ma5 > ma10 > ma20 > ma60 且 close > ma5
        if all(ordered[i] > ordered[i + 1] for i in range(len(ordered) - 1)) and close > ordered[0]:
            arr_text, arr_score = "多头排列", 85
        # 严格空头：ma5 < ma10 < ma20 < ma60 且 close < ma5
        elif all(ordered[i] < ordered[i + 1] for i in range(len(ordered) - 1)) and close < ordered[0]:
            arr_text, arr_score = "空头排列", 15
        # 部分多头：close > ma20 且 ma5 > ma20
        elif close > ordered[-1] and ordered[0] > ordered[-1]:
            arr_text, arr_score = "偏多", 65
        # 部分空头：close < ma20 且 ma5 < ma20
        elif close < ordered[-1] and ordered[0] < ordered[-1]:
            arr_text, arr_score = "偏空", 35

    trend_label = f"{arr_text} · 站上{above_count}条均线"

    return {
        "price": close,
        "ma_values": ma_map,
        "arrangement": arr_text,
        "above_count": above_count,
        "trend_label": trend_label,
        "trend_score": arr_score,
    }


# ============================================================
# 2) 动量 / 涨跌幅
# ============================================================
def analyze_momentum(df: pd.DataFrame) -> Dict[str, Any]:
    """
    动量分析：1/5/20 日涨跌幅 + 与大盘（HS300）对比。

    注意：本函数不主动拉取 HS300 数据，只读 df 里的 return_* 字段。
    若外部已传入基准对照值（bench_returns dict），会一起返回对比结果。
    """
    if df is None or df.empty:
        return {"error": "数据为空"}

    latest = df.iloc[-1]
    rets = {
        "1日": float(latest.get("return_1d", 0.0) or 0.0),
        "5日": float(latest.get("return_5d", 0.0) or 0.0),
        "20日": float(latest.get("return_20d", 0.0) or 0.0),
    }

    # 动量强度打分：5日涨幅 0~10% 映射到 50~100；负值扣分
    r5 = rets["5日"]
    if r5 >= 10:
        score = 90
    elif r5 >= 5:
        score = 75
    elif r5 >= 2:
        score = 65
    elif r5 >= 0:
        score = 55
    elif r5 >= -3:
        score = 40
    elif r5 >= -7:
        score = 25
    else:
        score = 10

    return {
        "returns": rets,
        "momentum_label": _momentum_label(r5),
        "momentum_score": score,
    }


def _momentum_label(r5: float) -> str:
    if r5 >= 10:
        return "强势上攻"
    if r5 >= 5:
        return "明显走强"
    if r5 >= 2:
        return "温和上涨"
    if r5 >= -2:
        return "震荡整理"
    if r5 >= -5:
        return "弱势回调"
    return "加速下跌"


# ============================================================
# 3) 量能分析
# ============================================================
def analyze_volume(df: pd.DataFrame) -> Dict[str, Any]:
    """
    量能分析：
      - vol_ratio: 今日量 / 5日均量
      - vol_change_pct: 今日量相对昨日的变化
      - consecutive_volume_days: 连续放量/缩量天数
      - volume_price_label: 量价配合判断
    """
    if df is None or df.empty or "volume" not in df.columns:
        return {"error": "数据为空"}

    if len(df) < 6:
        return {"error": "数据不足6日，无法量能分析"}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    vol_today = float(latest["volume"])
    # 「今日之前的 5 个交易日」均量：用 iloc[-6:-1] 严格排除今日
    vol_avg5 = float(df["volume"].iloc[-6:-1].mean()) if len(df) >= 6 else float(df["volume"].iloc[:-1].mean())
    vol_ratio = vol_today / vol_avg5 if vol_avg5 > 0 else 1.0
    vol_change_pct = (vol_today - float(prev["volume"])) / float(prev["volume"]) * 100 if prev["volume"] > 0 else 0.0

    # 连续放量/缩量：只看最近若干天，从倒数第二根开始逐日比较
    consecutive = 0
    direction = None
    if len(df) >= 2:
        # 先用最后两根确定 direction
        if float(df["volume"].iloc[-1]) > float(df["volume"].iloc[-2]):
            direction = "up"
            consecutive = 1
        elif float(df["volume"].iloc[-1]) < float(df["volume"].iloc[-2]):
            direction = "down"
            consecutive = 1
        # 继续向前比较
        for i in range(len(df) - 2, 0, -1):
            cur, pre = float(df["volume"].iloc[i + 1]), float(df["volume"].iloc[i])
            if direction == "up" and cur > pre:
                consecutive += 1
            elif direction == "down" and cur < pre:
                consecutive += 1
            else:
                break

    # 量价配合
    change_pct = float(latest.get("change_pct", 0.0) or 0.0)
    if vol_ratio >= 1.5 and change_pct > 0:
        vp_label, vp_score = "量价齐升", 85
    elif vol_ratio >= 1.2 and change_pct > 0:
        vp_label, vp_score = "温和放量上涨", 70
    elif vol_ratio >= 1.2 and change_pct < 0:
        vp_label, vp_score = "放量下跌(警惕)", 25
    elif vol_ratio <= 0.7 and change_pct < 0:
        vp_label, vp_score = "缩量回调(健康)", 55
    elif vol_ratio <= 0.7 and change_pct > 0:
        vp_label, vp_score = "缩量上涨(动能不足)", 45
    else:
        vp_label, vp_score = "量能平稳", 50

    return {
        "vol_today": vol_today,
        "vol_avg5": vol_avg5,
        "vol_ratio": vol_ratio,
        "vol_change_pct": vol_change_pct,
        "consecutive_direction": direction or "none",
        "consecutive_days": consecutive,
        "volume_price_label": vp_label,
        "volume_price_score": vp_score,
    }


# ============================================================
# 4) K 线形态识别
# ============================================================
def detect_patterns(df: pd.DataFrame, lookback: int = 30) -> List[Dict[str, Any]]:
    """
    在最近 lookback 根 K 线中识别常见形态。

    支持：
      - 锤子线：下影线 >= 实体 2 倍，上影线很短
      - 上吊线：上影线 >= 实体 2 倍，下影线很短
      - 看涨吞没：前阴后阳，阳线实体完全覆盖前阴线
      - 看跌吞没：前阳后阴，阴线实体完全覆盖前阳线
      - 十字星：实体 < 影线 1/4
      - 突破 MA20：close 上穿 ma20（最近5日内首次）
    """
    if df is None or df.empty or len(df) < 3:
        return []

    patterns: List[Dict[str, Any]] = []
    sub = df.tail(lookback).reset_index(drop=True)
    n = len(sub)

    def _body(i):
        return abs(sub["close"].iloc[i] - sub["open"].iloc[i])

    def _upper_shadow(i):
        return sub["high"].iloc[i] - max(sub["close"].iloc[i], sub["open"].iloc[i])

    def _lower_shadow(i):
        return min(sub["close"].iloc[i], sub["open"].iloc[i]) - sub["low"].iloc[i]

    # 单根 K 线形态（扫最近 10 根）
    # 优先级：锤子/上吊 > 十字星（实体的相对大小）
    for i in range(max(0, n - 10), n):
        body = _body(i)
        up = _upper_shadow(i)
        lo = _lower_shadow(i)
        total_range = sub["high"].iloc[i] - sub["low"].iloc[i]

        if total_range <= 0:
            continue

        # 锤子线：下影线 >= 实体 2 倍，上影线 < 总影线 25%（实锤的锤子）
        if lo >= body * 2 and up < total_range * 0.25 and body > 0:
            patterns.append({
                "date": sub["date"].iloc[i],
                "name": "锤子线",
                "bias": "看涨",
                "desc": "下影线长，暗示下方有承接",
            })
        # 上吊线：上影线 >= 实体 2 倍，下影线 < 总影线 25%
        elif up >= body * 2 and lo < total_range * 0.25 and body > 0:
            patterns.append({
                "date": sub["date"].iloc[i],
                "name": "上吊线",
                "bias": "看跌",
                "desc": "上影线长，警惕上方抛压",
            })
        # 十字星：实体非常小（< 总影线 15%），且上下影线都不为 0
        elif body < total_range * 0.15 and up > 0 and lo > 0:
            patterns.append({
                "date": sub["date"].iloc[i],
                "name": "十字星",
                "bias": "中性",
                "desc": "买卖力量均衡，警惕方向选择",
            })

    # 双根 K 线形态
    for i in range(1, n):
        prev_open, prev_close = sub["open"].iloc[i - 1], sub["close"].iloc[i - 1]
        cur_open, cur_close = sub["open"].iloc[i], sub["close"].iloc[i]
        prev_bear = prev_close < prev_open
        cur_bull = cur_close > cur_open
        prev_bull = prev_close > prev_open
        cur_bear = cur_close < cur_open

        if prev_bear and cur_bull and cur_open < prev_close and cur_close > prev_open:
            patterns.append({
                "date": sub["date"].iloc[i],
                "name": "看涨吞没",
                "bias": "看涨",
                "desc": "阳线完全覆盖前阴线，反转信号",
            })
        if prev_bull and cur_bear and cur_open > prev_close and cur_close < prev_open:
            patterns.append({
                "date": sub["date"].iloc[i],
                "name": "看跌吞没",
                "bias": "看跌",
                "desc": "阴线完全覆盖前阳线，反转信号",
            })

    # 突破 MA20：最近 5 天内首次 close > ma20（前一日 close <= ma20）
    if "ma20" in sub.columns and n >= 6:
        for i in range(n - 5, n):
            if i <= 0:
                continue
            cur_close = float(sub["close"].iloc[i])
            cur_ma20 = float(sub["ma20"].iloc[i])
            prev_close = float(sub["close"].iloc[i - 1])
            prev_ma20 = float(sub["ma20"].iloc[i - 1])
            if cur_close > cur_ma20 and prev_close <= prev_ma20:
                patterns.append({
                    "date": sub["date"].iloc[i],
                    "name": "突破MA20",
                    "bias": "看涨",
                    "desc": "收盘价上穿20日均线，短期走强信号",
                })
                break

    # 同一根 K 线可能识别出多个形态，全部展示
    # 按时间倒序（最近优先），最多 5 个
    deduped = sorted(patterns, key=lambda x: x["date"], reverse=True)
    return deduped[:5]


# ============================================================
# 综合函数：一键返回 4 类分析
# ============================================================
def full_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    一键执行所有技术面分析，返回结构化字典，供 Streamlit 直接展示。
    """
    return {
        "trend": analyze_trend(df),
        "momentum": analyze_momentum(df),
        "volume": analyze_volume(df),
        "patterns": detect_patterns(df),
    }
