# -*- coding: utf-8 -*-
"""modules/herd_crowding.py — 羊群拥挤度指标（T-182 双因子决策增强 · 因子 B）。

行为金融「羊群效应」的量化：散户一致性极端化（红盘比远离 50 + 方向端
涨/跌停家数历史分位极端 + 连续同向天数累积）时，次日均值回归风险最高。

创新口径（与 T-182 提案一致）：
  · 真值数据自有：shepherd_history 2007 年起全市场广度真值库
  · 无前视：涨停/跌停家数分位只用「截至前一日」的历史分布（昨日及以前
    对今日决策合法可知）；streak 为含当日的过去连续同向段（收盘后可知，
    供次日决策）
  · 诚实降级：任一核心输入缺失 → status="unavailable" + score=None，
    绝不默认 0（项目诚实数据语义铁律）

权重：score = 100 × (0.40×一致性 align + 0.35×极端参与 heat + 0.25×连势 streak)
  · align  = |red_ratio - 50| / 50            （0~1，方向无关的「一致性」）
  · heat   = 方向端家数历史分位               （greed 端取涨停分位，fear 端取跌停分位）
  · streak = min(连续同向天数, 5) / 5         （连势封顶 5 天，防无限连势虚高）

side 语义（供 decision.py 决策端使用）：
  · greed（红挤）：追涨拥挤 → 次日均值回归风险高 → 反向减仓
  · fear（绿挤）  ：恐慌杀跌 → 与决策链「冰点 +5 超卖试探」既有语义自洽，
    不反向加仓也不减仓（方向信号仍由 bias 承担）
  · None：red_ratio 恰为 50（多空对轰、无一致性），heat 不参与
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 拥挤度合成权重（契约常量，测试钉住；改权重=改创新点口径，须回测重跑）
WEIGHT_ALIGN = 0.40
WEIGHT_HEAT = 0.35
WEIGHT_STREAK = 0.25

# 决策阈值（decision.py 引用同一常量，单一真理源）
STRONG_CROWD = 85.0  # 极端拥挤 → -8pt
MILD_CROWD = 70.0    # 中度拥挤 → -4pt

STREAK_CAP = 5       # 连势封顶天数
_CONF_MIN = 0.0      # 占位：与 regime 置信度门控（decision 端）区分，本模块无置信度概念


def compute_crowding(red_ratio, limit_up_pct, limit_down_pct, streak_days) -> dict:
    """纯函数：由当日广度特征合成羊群拥挤度。

    :param red_ratio: 红盘比（0~100）
    :param limit_up_pct: 涨停家数历史分位（0~1，截至前一日分布）
    :param limit_down_pct: 跌停家数历史分位（0~1，截至前一日分布）
    :param streak_days: 连续同向天数（含当日；红盘比为正侧）
    :return: dict(status="ok"|"unavailable", score, side, parts)
             score: 0~100 float（unavailable 时为 None）
             side: "greed"|"fear"|None
             parts: {align, heat, streak_norm, streak_days, limit_up_pct, limit_down_pct}
    """
    def _bad(name, value):
        logger.warning("[herd] %s 缺失（%r）→ 拥挤度 unavailable", name, value)

    if red_ratio is None or red_ratio != red_ratio:  # None 或 NaN
        _bad("red_ratio", red_ratio)
        return _unavailable()
    if limit_up_pct is None or limit_down_pct is None:
        _bad("limit_up/down_pct", (limit_up_pct, limit_down_pct))
        return _unavailable()
    if streak_days is None:
        _bad("streak_days", streak_days)
        return _unavailable()

    rr = float(red_ratio)
    lu = float(limit_up_pct)
    ld = float(limit_down_pct)
    streak = max(0, int(streak_days))

    align = abs(rr - 50.0) / 50.0
    if rr > 50.0:
        side = "greed"
        heat = lu
    elif rr < 50.0:
        side = "fear"
        heat = ld
    else:
        side = None
        heat = 0.0  # 多空对轰无一致性，极端参与不计分
    streak_norm = min(streak, STREAK_CAP) / STREAK_CAP

    score = 100.0 * (WEIGHT_ALIGN * align + WEIGHT_HEAT * heat + WEIGHT_STREAK * streak_norm)
    return {
        "status": "ok",
        "score": round(score, 1),
        "side": side,
        "parts": {
            "align": round(align, 4),
            "heat": round(heat, 4),
            "streak_norm": round(streak_norm, 4),
            "streak_days": streak,
            "limit_up_pct": round(lu, 4),
            "limit_down_pct": round(ld, 4),
        },
    }


def _unavailable() -> dict:
    return {"status": "unavailable", "score": None, "side": None, "parts": {}}


def crowding_from_history(df, idx: int) -> dict:
    """历史辅助入口：从广度历史 DataFrame 的第 idx 行（当日）算拥挤度。

    无前视纪律：
      · 涨停/跌停分位：用 df.iloc[:idx]（昨日及以前）的家数分布
      · streak：从 idx 向回数连续同向天数（含当日）
      · 首日（历史为空）→ unavailable（不臆造分位）

    :param df: 需含列 red_ratio / limit_up / limit_down（按日期升序）
    :param idx: 当日行号
    :return: compute_crowding 同构 dict
    """
    try:
        row = df.iloc[idx]
    except (IndexError, TypeError):
        logger.warning("[herd] 行号越界 %r", idx)
        return _unavailable()

    rr = row.get("red_ratio")
    lu_today = row.get("limit_up")
    ld_today = row.get("limit_down")
    if (rr is None or rr != rr or lu_today is None or lu_today != lu_today
            or ld_today is None or ld_today != ld_today):
        logger.warning("[herd] 当日行（idx=%s）关键列缺失 → unavailable", idx)
        return _unavailable()

    hist = df.iloc[:idx]
    if len(hist) == 0:
        logger.warning("[herd] 首日无历史分布 → unavailable（不臆造分位）")
        return _unavailable()

    # 方向端极端参与分位：仅用「截至前一日」历史（无前视）
    up_pct = float((hist["limit_up"].dropna() < float(lu_today)).mean())
    down_pct = float((hist["limit_down"].dropna() < float(ld_today)).mean())

    # 连续同向天数（含当日）：从当日向回数，red_ratio 与当日同侧才算连续
    side_today = 1 if float(rr) > 50.0 else (-1 if float(rr) < 50.0 else 0)
    streak = 0
    if side_today != 0:
        i = idx
        while i >= 0:
            v = df.iloc[i]["red_ratio"]
            if v is None or v != v:
                break
            s = 1 if float(v) > 50.0 else (-1 if float(v) < 50.0 else 0)
            if s != side_today:
                break
            streak += 1
            i -= 1

    out = compute_crowding(red_ratio=float(rr), limit_up_pct=up_pct,
                           limit_down_pct=down_pct, streak_days=streak)
    return out
