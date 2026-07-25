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


def _safe_float(v, default: float = 0.0) -> float:
    """把任意值安全转 float；None / 空 / NaN 回落到 default（避免 NaN 经 `or 0.0` 泄漏）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(f) else f


def compute_atr(df: pd.DataFrame, period: int = 14) -> "float | None":
    """计算真实波幅 ATR（纯函数，可单测）。

    新能力：此前 ATR 仅在 ``stock_analysis_helpers._calc_trade_levels`` 内联计算，
    技术面模块缺少可复用的波动率原语。现抽出为通用纯函数，供风控/价位计算复用。

    返回 ATR 数值；数据不足或列缺失或结果为 NaN/非正时返回 ``None``（调用方决定兜底）。
    """
    if df is None or df.empty:
        return None
    if not all(c in df.columns for c in ("high", "low", "close")):
        return None
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    if len(tr) < period:
        return None
    atr = float(tr.rolling(period).mean().iloc[-1])
    if pd.isna(atr) or atr <= 0:
        return None
    return atr


def compute_rsi(df: pd.DataFrame, period: int = 14) -> "float | None":
    """计算相对强弱指数 RSI（纯函数，可单测）。

    新能力：技术面模块此前缺少可复用的 RSI 原语（仅 technical_agent 内散落实现），
    现抽出为通用纯函数，供个股分析 / 风控 / 量化策略统一调用。

    采用简单移动平均法（与 compute_atr 同一定价口径）：
      delta = close.diff()
      gain/loss 分别取 delta 的正/负部分均值，RS = avg_gain/avg_loss，
      RSI = 100 - 100/(1+RS)。
    返回 0-100 的 RSI；数据不足 / 缺 close 列 / 结果为 NaN 时返回 ``None``。
    全涨（无亏损）→ 100；全跌（无盈利）→ 0；持平（无波动）→ 50。
    """
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = df["close"].dropna()
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    g = float(avg_gain.iloc[-1])
    l = float(avg_loss.iloc[-1])
    if pd.isna(g) or pd.isna(l):
        return None
    if l == 0:
        return 100.0 if g > 0 else 50.0
    rs = g / l
    rsi = 100.0 - 100.0 / (1.0 + rs)
    if pd.isna(rsi):
        return None
    return round(float(rsi), 2)


def compute_ema(series: "pd.Series", span: int) -> "pd.Series | None":
    """指数移动平均（纯函数，可单测）。

    新能力：此前 MACD / 均线叠加等多处散落 ``ewm`` 计算，且未对 NaN 做剔除，
    单点 NaN 会沿序列向后污染整条 EMA。现抽出为带 NaN 守卫的单一实现。

    返回与输入等长的 EMA Series；输入非法（None / 长度不足 / 全 NaN）返回 None。
    """
    if series is None:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 1:
        return None
    return s.ewm(span=span, adjust=False, min_periods=max(2, span // 2)).mean()


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
                 ) -> "dict | None":
    """计算 MACD（纯函数，可单测）：DIF / DEA / MACD 柱。

    新能力：技术面模块此前缺少可复用的 MACD 原语（仅 technical_agent 内散落
    实现且未做 NaN 守卫）。现抽出为通用纯函数，供个股分析 / 量化策略统一调用。

    算法（与通达信/AKShare 同口径，EMA 不调整）：
      dif  = EMA(close, fast) - EMA(close, slow)
      dea  = EMA(dif, signal)
      macd = (dif - dea) * 2
    返回最新一根的 {dif, dea, macd}；数据不足 / 缺 close 列 / 结果为 NaN 时返回 None。
    隐性健壮化：先 ``dropna`` 再算 EMA，避免单点 NaN 向后污染整条 DIF/DEA。
    """
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < slow:
        return None
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=max(2, fast // 2)).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=max(2, slow // 2)).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False, min_periods=max(2, signal // 2)).mean()
    macd = (dif - dea) * 2
    try:
        out = {
            "dif": round(float(dif.iloc[-1]), 4),
            "dea": round(float(dea.iloc[-1]), 4),
            "macd": round(float(macd.iloc[-1]), 4),
        }
    except (ValueError, TypeError, IndexError):
        return None
    if any(pd.isna(v) for v in out.values()):
        return None
    return out


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
    # 隐性缺陷修复：close 为 NaN 时，下方所有 ``close > ma`` 比较恒为 False，
    # 会把本该判不出的趋势静默误归为「纠缠」，甚至错误给出空头排列。先显式拦截。
    if pd.isna(close):
        return {"error": "收盘价缺失/NaN，无法分析趋势"}
    # 隐性缺陷修复：旧实现 ``float(latest["ma{w}"])`` 在 ma 为 NaN 时会得到 nan，
    # 而 nan 进入 ``ordered`` 后所有大小比较恒为 False，使多头/空头排列永远判不出
    # （即便 ma5>ma10>ma20 也会被 nan 拖成"纠缠"）。现用 _safe_float 过滤 NaN，
    # 仅保留有效均线参与排列判断。
    ma_map = {}
    for w in (5, 10, 20, 60):
        if f"ma{w}" in df.columns:
            v = _safe_float(latest[f"ma{w}"], default=None)
            if v is not None:
                ma_map[w] = v

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
        "1日": _safe_float(latest.get("return_1d", 0.0)),
        "5日": _safe_float(latest.get("return_5d", 0.0)),
        "20日": _safe_float(latest.get("return_20d", 0.0)),
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
    change_pct = _safe_float(latest.get("change_pct", 0.0))
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


def overall_technical_score(trend_score, momentum_score, volume_score,
                            weights=(0.4, 0.35, 0.25)) -> float:
    """把趋势 / 动量 / 量能三维度得分(0-100)加权合成为综合技术面得分。

    任一维度为 None 或 NaN 时按中性 50 参与；超出 [0,100] 的得分先裁剪。
    权重默认为 趋势0.4 / 动量0.35 / 量能0.25。
    """
    total_w = sum(weights)
    if total_w <= 0:
        return 50.0
    acc = 0.0
    for s, w in zip((trend_score, momentum_score, volume_score), weights):
        if s is None or pd.isna(s):
            s = 50.0
        else:
            s = max(0.0, min(100.0, float(s)))
        acc += s * w
    return round(acc / total_w, 1)
