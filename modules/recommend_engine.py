"""
modules/recommend_engine.py
===========================
每日荐股引擎（T-233）：多算法融合选股 + 买入方案 + 逐算法解释。

五路算法（每路独立打分，缺失即诚实标注并按可用算法重归一化）：
  A1 multi_factor  —— Backtester._score_for_picker V5 评分（趋势 50+超跌 35+动量+量能）
  A2 dual_trend    —— 双趋势共振评分（GMMA+一目+ADX，纯趋势不依赖 RSI 低位）
  A3 fund_flow     —— 个股主力净流入（东财，仅对候选 Top-N 富集，控制网络开销）
  A4 event_factor  —— P1 事件因子多头榜（EV 模型；无信号目录时如实 unavailable）
  A5 momentum      —— 20 日动量 + 量能放大（纯价量，本地计算）
  A6 breakout      —— 放量新高突破（R2/T-246）：52 周新高闸 + 巨量 + 连站 MA5 +
                      3 日成交额门槛；换手率数据链无字段 → 如实标注按可用子集打分

R3 Value Trap（T-246）：value_trap_score 纯本地 4 分量（长期低位/跌势未止/深跌/
持续阴跌），富集段 PE/PB 低位确认加分；陷阱分 ≥50 时 A1 分数 ×0.7 并注明——
防「超跌接飞刀」，直击 A1 结构性弱点。

融合：各算法在候选集内 min-max 归一化 → 加权求和 → Top-K。
买入方案：入场=现价，目标/止损=ATR14 倍数（2×止损 / 3×目标），
仓位提示 = derive_position 市场仓位 / 推荐只数（等权、单票上限 20%）。

R1 六维排雷二道闸（T-245）：融合排序后对闸门段（max(enrich_top, top_k)）逐股跑
stock_risk 六维扫描，overall_level=high（ST/商誉/质押/解禁/减持/诉讼任一高危）
硬红旗踢出；排雷不可得如实降级 not_scanned，绝不阻塞主流程、绝不把没查到当安全。

诚实语义：
- 数据不可得的算法在该标的记 unavailable，不编造分数；
- 行情不足 90 日的标的直接跳过；
- 每份推荐带 data_as_of / generated_at / 免责声明；
- 持久化抄 daily_snapshot 范式：data/recommendations/YYYY-MM-DD.json（归档）
  + data/daily_recommendation.json（最新），按日幂等。
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from modules.stock_risk import DIMENSIONS, RISK_HIGH, RISK_MEDIUM
from modules.technical import detect_bullish_divergence  # R7/T-333：MACD 底背离确认

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

# 融合权重（和为 1；逐标的缺失某算法时按可用权重重归一化）。
# T-246：新增 A6 breakout=0.15，六路重分配（R2 右侧强势路与 A1 超跌路对冲）
ALGO_WEIGHTS = {
    "multi_factor": 0.22,   # -0.03（给 financial_health 挪份额）
    "dual_trend": 0.17,     # -0.03
    "fund_flow": 0.18,
    "event_factor": 0.12,
    "momentum": 0.09,       # -0.01
    "breakout": 0.12,       # -0.03
    "financial_health": 0.10,  # R8/T-363：F-Score + Altman Z' + Beneish M
}
ALGO_LABELS = {
    "multi_factor": "多因子 V5（趋势+超跌反弹）",
    "dual_trend": "双趋势共振（GMMA+一目+ADX）",
    "fund_flow": "主力资金净流入",
    "event_factor": "P1 事件因子",
    "momentum": "20 日动量+量能",
    "breakout": "放量新高突破（右侧强势）",
    "financial_health": "财务健康（F+Z+M 三合一）",
}

DISCLAIMER = (
    "推荐由多算法融合筛选生成，附历史模拟统计，不构成投资建议；"
    "方向预测≈随机（4092 交易日回测结论），价值在筛选漏斗+风控方案+成本感知，请独立决策。"
)


def _normalize_reasons(raw):
    """reasons 归一为字符串列表。

    缺陷背景（2026-10-13 浏览器实测发现）：`Backtester._score_for_picker` 返回的
    reasons 是逗号拼接的**单个字符串**（backtest.py `"reasons": ",".join(reasons)`），
    组装处若直接对其迭代 `[:2]` 只会取到前两个**字符**（「强」「趋」这类单字碎句）。
    此处统一收口：str → 按逗号拆分；list/tuple → 原样；其余（None 等）→ 空列表。
    """
    if isinstance(raw, str):
        return [seg.strip() for seg in raw.split(",") if seg.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(r) for r in raw if str(r).strip()]
    return []


# ══════════════════════════════════════════════════════
# T-272②：引擎取数参数单一真理源
# cache_warmer 预热与本模块 _fetch_one 必须逐字节同参（cache_key 由参数拼接，
# 参数不同＝写引擎读不到的键＝预热白拉，T-250 铁律）。两侧共同引用本函数，
# 键一致性从「文档约定」升级为「机器保证」，杜绝复刻漂移。
# ══════════════════════════════════════════════════════
def engine_fetch_params() -> tuple:
    """荐股引擎日线取数参数 (start, end, adjust)：260 天窗口 + 今日 + 前复权。"""
    now = datetime.now()
    start = (now - timedelta(days=260)).strftime("%Y-%m-%d")
    return start, now.strftime("%Y-%m-%d"), "qfq"


# ══════════════════════════════════════════════════════
# R4/T-270：市况自适应权重（纯函数，温度档 → ALGO_WEIGHTS 微调）
# 依据（ashare 市况搭配通识 + 本项目融合网格实测 T-265）：高温期趋势/动量延续性强
# → 偏 momentum/breakout/dual_trend；低温期超跌反弹与资金抄底占优 → 偏
# multi_factor（超跌反弹路）/fund_flow。幅度克制（±0.05 内），和恒为 1；
# 中间档或快照不可得（None/非数值）→ None（调用方回落静态默认，诚实降级）。
# ══════════════════════════════════════════════════════
def market_regime_weights(temperature) -> Optional[dict]:
    """温度档 → 自适应融合权重；不适用时返回 None（回落 ALGO_WEIGHTS 静态默认）。"""
    try:
        t = float(temperature)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(t):
        return None
    w = dict(ALGO_WEIGHTS)
    if t >= 70:      # 高温：偏趋势/动量
        w["momentum"] += 0.05
        w["breakout"] += 0.05
        w["dual_trend"] += 0.03
        w["multi_factor"] -= 0.05
        w["fund_flow"] -= 0.05
        w["event_factor"] -= 0.03
    elif t <= 30:    # 低温：偏超跌反弹/资金
        w["multi_factor"] += 0.05
        w["fund_flow"] += 0.05
        w["momentum"] -= 0.04
        w["breakout"] -= 0.04
        w["dual_trend"] -= 0.02
    else:            # 中间档：静态默认最优（无证据支持偏移）
        return None
    total = sum(w.values())
    if abs(total - 1.0) > 1e-6:   # 守恒校验失败宁可不调（回静态）
        return None
    return {k: round(v, 4) for k, v in w.items()}


def _safe_market_temperature():
    """快照温度（R4 输入）；不可得返回 None（诚实降级）。"""
    try:
        return (_safe_market_context() or {}).get("temperature")
    except Exception as e:  # noqa: BLE001
        logger.info("[recommend_engine] 温度快照不可用（R4 如实降级）: %s", e)
        return None


# ══════════════════════════════════════════════════════
# 纯函数（可单测）
# ══════════════════════════════════════════════════════
def minmax_normalize(values: dict) -> dict:
    """对 {key: score} 做 min-max 归一化到 0~1。

    - 全部相同/不足 2 个有效值 → 全 0.5（无区分度时不假装有区分度）；
    - None/NaN 值原样保留为 None（调用方按缺失处理）。
    """
    valid = {k: float(v) for k, v in values.items()
             if v is not None and not (isinstance(v, float) and np.isnan(v))}
    if len(valid) < 2:
        return {k: (0.5 if k in valid else None) for k in values}
    lo, hi = min(valid.values()), max(valid.values())
    span = hi - lo
    out = {}
    for k, v in values.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            out[k] = None
        elif span == 0:
            out[k] = 0.5
        else:
            out[k] = (float(v) - lo) / span
    return out


def atr14(df: pd.DataFrame) -> float:
    """14 日 ATR（真实波幅均值）。数据不足或列缺失返回 NaN。"""
    need = {"high", "low", "close"}
    if df is None or len(df) < 15 or not need.issubset(df.columns):
        return float("nan")
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return float(tr.tail(14).mean())


def trade_levels(close: float, atr: float) -> dict:
    """买入方案价位：入场=现价，止损=2×ATR，目标=3×ATR（盈亏比 1.5）。"""
    if (close is None or atr is None
            or not np.isfinite(float(close)) or float(close) <= 0
            or not np.isfinite(atr) or atr <= 0):
        return {"entry": close, "target": None, "stop": None, "atr": None}
    return {
        "entry": round(float(close), 2),
        "target": round(float(close) + 3 * atr, 2),
        "stop": round(float(close) - 2 * atr, 2),
        "atr": round(float(atr), 3),
    }


def fusion_score(algo_scores: dict, weights: dict = None) -> tuple:
    """加权融合分（0~100）。缺失算法按可用权重重归一化；无可用算法返回 (None, {})。

    :param algo_scores: {algo_name: raw_score_or_None}
    :return: (composite_or_None, breakdown_dict{name: {raw, weight, effective_weight, normalized}})
    """
    weights = weights or ALGO_WEIGHTS
    avail = {k: v for k, v in algo_scores.items()
             if v is not None and k in weights}
    if not avail:
        return None, {}
    w_total = sum(weights[k] for k in avail)
    norm = minmax_normalize(avail)
    composite, breakdown = 0.0, {}
    for k in weights:
        if k in avail:
            raw = algo_scores[k]
            ew = weights[k] / w_total
            composite += ew * norm[k] * 100.0
            breakdown[k] = {"raw": round(float(raw), 2), "weight": weights[k],
                            "effective_weight": round(ew, 3),
                            "normalized": round(norm[k], 3)}
        else:
            breakdown[k] = {"raw": None, "weight": weights[k],
                            "effective_weight": 0.0, "normalized": None}
    return round(composite, 1), breakdown


# ══════════════════════════════════════════════════════
# 持久化（抄 daily_snapshot 双文件范式，data_dir 可注入便于测试）
# ══════════════════════════════════════════════════════
def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def rec_paths(data_dir: str = None) -> tuple:
    d = data_dir or _DEFAULT_DATA_DIR
    return (os.path.join(d, "recommendations", f"{_today_str()}.json"),
            os.path.join(d, "daily_recommendation.json"))


def save_recommendation(rec: dict, data_dir: str = None) -> tuple:
    """写入当日归档 + 最新两份 JSON。返回 (archive_path, latest_path)。"""
    archive, latest = rec_paths(data_dir)
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    for p in (archive, latest):
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    return archive, latest


def assess_data_staleness(data_as_of_list, today=None, max_lag_days: int = 5) -> dict:
    """T-235：汇总各标的行情最新日，评估荐股依据的数据时效（data-source-staleness-guard 范式）。

    :param data_as_of_list: 各标的 data_as_of（YYYY-MM-DD 或 None）
    :param max_lag_days: 自然日滞后阈值（跨一个周末 ≈ 5 天；日线数据周五数据周一拉 lag=3 不算过期）
    :return: {latest, lag_days, stale, note}；无任何日期 → stale=True（诚实：无数据可考即视为过时）
    """
    today = today or datetime.now().date()
    if hasattr(today, "strftime"):
        today = today.strftime("%Y-%m-%d")
    dates = sorted({str(d)[:10] for d in (data_as_of_list or []) if d}, reverse=True)
    if not dates:
        return {"latest": None, "lag_days": None, "stale": True,
                "note": "无任何行情日期可考（数据源全部不可用）"}
    latest = dates[0]
    try:
        lag = (datetime.strptime(str(today), "%Y-%m-%d") - datetime.strptime(latest, "%Y-%m-%d")).days
    except ValueError:
        return {"latest": latest, "lag_days": None, "stale": True, "note": "行情日期解析失败"}
    stale = lag > max_lag_days
    note = (f"行情数据最新 {latest}，滞后 {lag} 天（>{max_lag_days} 天，荐股依据可能过时）"
            if stale else f"行情数据最新 {latest}（滞后 {lag} 天，≤{max_lag_days} 天）")
    return {"latest": latest, "lag_days": lag, "stale": stale, "note": note}


def load_latest_recommendation(data_dir: str = None) -> dict:
    """读最新推荐；不存在/损坏 → {'status':'unavailable', reason}（诚实语义）。"""
    _, latest = rec_paths(data_dir)
    try:
        with open(latest, encoding="utf-8") as f:
            rec = json.load(f)
        if isinstance(rec, dict) and rec.get("status") == "ok":
            return rec
        return {"status": "unavailable", "reason": "最新推荐文件结构异常"}
    except FileNotFoundError:
        return {"status": "unavailable", "reason": "今日尚未生成推荐（每交易日收盘后自动生成）"}
    except Exception as e:  # noqa: BLE001
        logger.warning("[recommend_engine] 读取推荐失败: %s", e)
        return {"status": "unavailable", "reason": f"读取失败：{type(e).__name__}"}


def load_recommendation_by_date(date_str: str, data_dir: str = None) -> dict:
    # 纵深防御（T-238）：date 直接拼进文件路径，非法格式（含 Windows 反斜杠穿越形态）
    # 一律拒绝，绝不触碰文件系统。
    import re as _re

    if not (isinstance(date_str, str) and _re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str)):
        return {"status": "unavailable", "reason": "日期格式非法（须为 YYYY-MM-DD）"}
    d = data_dir or _DEFAULT_DATA_DIR
    path = os.path.join(d, "recommendations", f"{date_str}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"{date_str} 无推荐记录"}


def today_generated(data_dir: str = None) -> bool:
    archive, _ = rec_paths(data_dir)
    return os.path.exists(archive)


# ══════════════════════════════════════════════════════
# 主流程：生成当日推荐
# ══════════════════════════════════════════════════════
def _index_ret20_safe() -> Optional[float]:
    """R5/T-270：上证指数 20 日收益（相对大盘强度基准，循环外一次性调用）；
    不可得返回 None（_momentum_score 如实回落绝对动量并标注）。"""
    try:
        from datetime import date, timedelta
        from modules.fetcher import StockFetcher
        f = StockFetcher()
        end = date.today()
        start = end - timedelta(days=90)
        df = f.get_index("000001", start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"))
        close = df["close"].astype(float).reset_index(drop=True)
        if len(close) < 21:
            return None
        return float(close.iloc[-1] / close.iloc[-21] - 1)
    except Exception as e:  # noqa: BLE001 - 指数取数失败不影响整体推荐，但必须留痕
        logger.info("[recommend_engine] 指数日线不可得（R5 如实降级为绝对动量）: %s", e)
        return None


def continuous_risk_penalty(df: pd.DataFrame) -> dict:
    """R6/T-330：连续价量风险惩罚（0~14 分）——五路「只奖不罚」的结构性补位。

    - 振幅分量 amp5 = 近 5 日 mean((high-low)/prev_close)；
      penalty_amp = clamp((amp5 - 0.05) × 120, 0, 8)（5% 起罚，每 +1pp 罚 1.2 分，
      封顶 8）——高振幅=博彩式波动特征反向项；
    - 回撤分量 dd20 = 1 - close[-1] / max(close[-20:])；
      penalty_dd = clamp((dd20 - 0.20) × 60, 0, 6)（20% 起罚，每 +10pp 罚 6 分，封顶 6）；
      注：买入条件要求 close>MA20，故受罚候选=「站上 MA20 但近 20 日剧烈下摆」的
      高波动股；处于 20 日新高的右侧强势股 dd20=0 不受罚；
    - 换手率：本引擎数据链无字段 → components.turnover 恒 unavailable
      （reasons 如实标注，绝不默认 0、绝不假装扫过）；
    - 任一分量取不到（缺列/样本不足）→ 该分量 unavailable 不计分母（诚实降级）。

    返回 ``{"penalty": float, "components": {...}, "reasons": [...]}``。
    """
    comps: dict = {}
    reasons: list = []
    total = 0.0

    # 振幅分量
    if all(c in df.columns for c in ("high", "low", "close")) and len(df) >= 6:
        c = df["close"].astype(float)
        prev = c.shift(1)
        amp = ((df["high"].astype(float) - df["low"].astype(float)) / prev).tail(5)
        amp = amp.dropna()
        if len(amp) >= 3:
            amp5 = float(amp.mean())
            p_amp = min(max((amp5 - 0.05) * 120, 0.0), 8.0)
            comps["amplitude"] = {"status": "ok", "value": round(amp5, 4),
                                  "penalty": round(p_amp, 2)}
            total += p_amp
            if p_amp > 0:
                reasons.append(f"近5日均振幅 {amp5:.1%} 过热（-{p_amp:.1f} 分）")
        else:
            comps["amplitude"] = {"status": "unavailable",
                                  "reason": "有效振幅样本不足"}
            reasons.append("振幅分量不可得（样本不足）")
    else:
        comps["amplitude"] = {"status": "unavailable", "reason": "行情缺 high/low 列"}
        reasons.append("振幅分量不可得（缺 high/low 列）")

    # 回撤分量
    if "close" in df.columns and len(df) >= 21:
        close = df["close"].astype(float)
        dd20 = 1.0 - float(close.iloc[-1]) / float(close.tail(20).max())
        p_dd = min(max((dd20 - 0.20) * 60, 0.0), 6.0)
        comps["drawdown"] = {"status": "ok", "value": round(dd20, 4),
                             "penalty": round(p_dd, 2)}
        total += p_dd
        if p_dd > 0:
            reasons.append(f"20日回撤 {dd20:.1%} 过深（-{p_dd:.1f} 分）")
    else:
        comps["drawdown"] = {"status": "unavailable",
                             "reason": "收盘样本不足 21 日"}
        reasons.append("回撤分量不可得（样本不足）")

    # 换手率分量：数据链无字段，恒 unavailable（诚实语义，绝不默认 0）
    comps["turnover"] = {"status": "unavailable",
                         "reason": "数据链无换手率字段（恒不可得）"}
    reasons.append("换手率分量不可得（数据链无字段）")

    return {"penalty": round(total, 2),
            "components": comps, "reasons": reasons}


def apply_unlock_penalty(rows: list, scan_map: dict) -> list:
    """R6/T-330：解禁临近扣分（复用 R1 闸门 scan_many 已取数据，零额外网络成本）。

    - 仅 ``risk_scan.status=="scanned"`` 的行取 ``scan_map[code].components.unlock``；
    - ``unlock.value`` = 未来 90 日最大解禁占流通市值 %（stock_risk 口径），
      level ∈ {medium, high} → penalty = clamp(value × 0.4, 0, 8)
      （10%→4 分，20%→8 分封顶）；
    - unknown / low / 组件或数值缺失 → 不罚（不编造、不假装查过）；
    - composite 相应扣减（floor 0），reasons 追加 ``[风险]`` 条目，
      ``risk_penalty.unlock`` 透明记录；
    - 返回按 composite 降序重排的列表（R1 闸门成员资格已定，此处只改顺位）。
    """
    for r in rows:
        rs = r.get("risk_scan") or {}
        if rs.get("status") != "scanned":
            continue
        scan = scan_map.get(str(r.get("code", "")).zfill(6)) or {}
        comp = (scan.get("components") or {}).get("unlock") or {}
        lvl = comp.get("level")
        val = comp.get("value")
        if lvl not in (RISK_MEDIUM, RISK_HIGH) or not isinstance(val, (int, float)) \
                or not math.isfinite(float(val)):
            continue
        p = min(max(float(val) * 0.4, 0.0), 8.0)
        if p <= 0:
            continue
        r["composite"] = round(max(0.0, float(r.get("composite") or 0.0) - p), 1)
        r["reasons"] = list(r.get("reasons") or []) + [
            f"[风险] 未来90日解禁占流通市值 {float(val):g}%（-{p:.1f} 分）"]
        rp = r.get("risk_penalty") or {}
        rp["unlock"] = {"status": "ok", "value": float(val), "level": lvl,
                        "penalty": round(p, 2)}
        r["risk_penalty"] = rp
    return sorted(rows, key=lambda r: -float(r.get("composite") or 0.0))


# R7/T-333：底背离确认加分幅度（克制：确认信号级别，封顶 100）
_DIVERGENCE_BOOST = 5.0


def apply_divergence_confirm(a1, dv: dict | None):
    """R7/T-333：MACD 底背离确认加分（benchmark 采纳清单 L153，作 A1 加分确认）。

    - a1 为 None（A1 不可得）→ None；
    - dv 无效（None / 非 dict / status != "ok" / divergence 为 False）→
      a1 **原样返回**（确认信号不存在＝维持原分，不编造、不加词）；
    - 命中 → a1 的**副本**：score = min(100, score + 5)（``_DIVERGENCE_BOOST``，
      确认加分封顶 100），reasons 归一化后追加「MACD底背离确认（放量）」并保持
      逗号拼接 str 形态（与 _score_for_picker 输出形态一致，阶段 3
      _normalize_reasons 兼容）。

    只影响每日荐股的 A1 候选分；**不动 backtest._score_for_picker 本体**
    （回测口径零影响）。
    """
    if a1 is None:
        return None
    if not isinstance(dv, dict) or dv.get("status") != "ok" \
            or not dv.get("divergence"):
        return a1
    try:
        base = float(a1.get("score"))
    except (TypeError, ValueError):
        return a1
    out = dict(a1)
    out["score"] = round(min(100.0, base + _DIVERGENCE_BOOST), 1)
    rs = _normalize_reasons(out.get("reasons"))
    rs.append("MACD底背离确认（放量）" if dv.get("volume_confirm") else "MACD底背离确认")
    out["reasons"] = ",".join(rs)
    return out


def _momentum_score(df: pd.DataFrame, index_ret20: Optional[float] = None) -> dict:
    """A5：20 日动量 + 量能放大（0~100）。

    R5/T-270：传入 index_ret20（指数 20 日收益）时改用**相对大盘强度**
    （个股 20 日收益 − 指数 20 日收益）打分——消除普涨/普跌日绝对动量的
    区分度归零；index_ret20=None（指数不可得）时如实回落绝对动量并标注。
    """
    close, vol = df["close"], df["volume"]
    if len(close) < 21:
        return None
    ret20 = close.iloc[-1] / close.iloc[-21] - 1
    if index_ret20 is not None and np.isfinite(float(index_ret20)):
        ret_eff = ret20 - float(index_ret20)
        basis = f"20日相对大盘 {ret_eff:+.1%}（个股 {ret20:+.1%} − 指数 {float(index_ret20):+.1%}）"
    else:
        ret_eff = ret20
        basis = "20日动量 {:+.1%}（大盘强度不可得，用绝对动量）".format(ret20)
    vol_ratio = vol.tail(5).mean() / max(vol.tail(60).mean(), 1)
    score = 50.0
    if ret_eff > 0:
        score += min(ret_eff * 250, 30)          # 相对动量最多 +30
    else:
        score += max(ret_eff * 250, -30)
    score += min((vol_ratio - 1) * 25, 20)      # 量能放大最多 +20
    reasons = [basis]
    if vol_ratio >= 1.2:
        reasons.append(f"量能放大 {vol_ratio:.2f}x")
    return {"score": round(max(0.0, min(100.0, score)), 1), "reasons": reasons}


def _breakout_score(df: pd.DataFrame) -> dict:
    """A6 放量新高突破（R2/T-246，纯本地，qfq 日线含 volume/amount）。

    - C1 52周新高闸：close > 前 min(250, n-1) 日最高收盘；未过闸 → 0 分（非右侧强势股）；
    - C2 巨量：当日量 ≥ 前20日均量×2 或 近3日均量 ≥ 前60日均量×1.5；
    - C3 连站 MA5：近 3 日 close 均高于当日 MA5；
    - C4 成交额：近 3 日 amount 累计 > 24 亿（列缺失 → 该条件 unavailable 不计分母）；
    - C5 换手 ≤50%：本引擎数据链无换手率字段 → 恒 unavailable，reasons 如实标注；
    - score = 100×(0.4 + 0.6×命中数/可用数)，C1 是闸门不是加分项。
    """
    n = len(df)
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    w = min(250, n - 1)
    prev_high = float(close.iloc[-(w + 1):-1].max())
    if not (float(close.iloc[-1]) > prev_high):
        return {"score": 0.0,
                "reasons": [f"未创{w}日新高（非右侧强势）", "换手率不可得（数据链无字段）"]}
    reasons = [f"创52周新高（{w}日窗口 {close.iloc[-1]:.2f}>{prev_high:.2f}）"]
    hits, available = 0, 0
    # C2 巨量
    available += 1
    ma20 = float(vol.iloc[-21:-1].mean()) if n > 21 else None
    c2_today = ma20 is not None and float(vol.iloc[-1]) >= 2 * ma20
    c2_3d = (n > 61 and
             float(vol.iloc[-3:].mean()) >= 1.5 * float(vol.iloc[-61:-1].mean()))
    if c2_today or c2_3d:
        hits += 1
        if ma20:
            reasons.append(f"巨量 {float(vol.iloc[-1]) / max(ma20, 1e-9):.1f}x@20日均量")
        else:
            reasons.append("巨量（3日均量放大1.5x）")
    else:
        reasons.append("量能未达巨量阈值")
    # C3 连站 MA5
    available += 1
    ma5 = close.rolling(5).mean()
    if n >= 6 and bool((close.iloc[-3:] > ma5.iloc[-3:]).all()):
        hits += 1
        reasons.append("连续3日站上MA5")
    else:
        reasons.append("未连续3日站上MA5")
    # C4 3日累计成交额
    if "amount" in df.columns:
        available += 1
        amt3 = float(df["amount"].astype(float).iloc[-3:].sum())
        if amt3 > 24e8:
            hits += 1
            reasons.append(f"3日成交额 {amt3 / 1e8:.1f} 亿")
        else:
            reasons.append(f"3日成交额 {amt3 / 1e8:.1f} 亿未达 24 亿门槛")
    else:
        reasons.append("成交额不可得（数据无 amount 列）")
    reasons.append("换手率不可得（数据链无字段）")
    score = round(100.0 * (0.4 + 0.6 * hits / max(available, 1)), 1)
    return {"score": min(score, 100.0), "reasons": reasons}


def value_trap_score(df: pd.DataFrame) -> dict:
    """R3 Value Trap 轻量评分（T-246，纯本地价格分量）。

    - V1 长期低位：250 日价格分位 ≤0.25；
    - V2 跌势未止：20 日收益 <0 且 close < MA60；
    - V3 深跌：120 日收益 < -30%（历史不足 121 日 → 该分量 unavailable）；
    - V4 持续阴跌：近 20 日创 20 日新低次数 ≥5；
    - score = 100×命中数/可用分量数（诚实归一，不把取不到当 0 或当命中）。

    返回 ``{"score", "flags", "unavailable"}``；PE/PB 确认项由富集段叠加（pe_pb_low_pct_boost）。
    """
    close = df["close"].astype(float)
    n = len(close)
    flags: list = []
    unavailable: list = []

    w1 = min(250, n)
    window1 = close.iloc[-w1:]
    pct1 = float((window1 < float(close.iloc[-1])).mean())
    v1 = pct1 <= 0.25
    if v1:
        flags.append(f"250日低位分位 {pct1:.0%}")

    ret20 = float(close.iloc[-1] / close.iloc[-21] - 1) if n > 20 else 0.0
    ma60 = float(close.rolling(60).mean().iloc[-1]) if n >= 60 else None
    v2 = ret20 < 0 and ma60 is not None and float(close.iloc[-1]) < ma60
    if v2:
        flags.append(f"跌势未止（20日 {ret20:+.1%} 且低于MA60）")

    if n >= 121:
        ret120 = float(close.iloc[-1] / close.iloc[-121] - 1)
        v3 = ret120 < -0.30
        if v3:
            flags.append(f"深跌（120日 {ret120:+.1%}）")
    else:
        v3 = None
        unavailable.append("120日深跌分量不可得（历史不足121日）")

    roll_min = close.rolling(20).min()
    new_lows = int((close.iloc[-20:] <= roll_min.iloc[-20:]).sum())
    v4 = new_lows >= 5
    if v4:
        flags.append(f"近20日 {new_lows} 次创20日新低")

    checks = [c for c in (v1, v2, v3, v4) if c is not None]
    hits = sum(1 for c in checks if c)
    score = round(100.0 * hits / max(len(checks), 1), 1)
    return {"score": score, "flags": flags, "unavailable": unavailable}


def pe_pb_low_pct_boost(pe_pct, pb_pct) -> int:
    """R3 富集段确认项：PE/PB 处于自身历史低位（≤30% 分位）→ 陷阱确认加分。

    PE 低位 +6 / PB 低位 +4；任一取不到就不加对应分（绝不默认 0 分位）。
    """
    boost = 0
    if pe_pct is not None and pe_pct <= 0.3:
        boost += 6
    if pb_pct is not None and pb_pct <= 0.3:
        boost += 4
    return boost


def generate_daily_recommendation(universe_limit: int = 200, enrich_top: int = 30,
                                  top_k: int = 5, data_dir: str = None,
                                  progress=None) -> dict:
    """生成当日推荐并落盘。全程真实数据，任何取数失败按缺失处理不编造。"""
    from modules.backtest import Backtester
    from modules.fetch_parallel import fetch_many
    from modules.fetcher import StockFetcher

    t0 = datetime.now()
    fetcher = StockFetcher()
    bt = Backtester()
    codes = fetcher.get_all_codes(limit=universe_limit)
    if not codes:
        rec = {"status": "unavailable", "reason": "股票池为空（网络或数据源不可用）",
               "generated_at": t0.isoformat(timespec="seconds"), "disclaimer": DISCLAIMER}
        save_recommendation(rec, data_dir)
        return rec

    if progress:
        progress(0.1, f"拉取 {len(codes)} 只标的行情…")

    # ── 阶段 1：行情 → A1/A2/A5 打分（并行取数，评分本地）──
    fetch_metas = {}

    def _fetch_one(code):
        # T-272②：参数单源化（engine_fetch_params），与 cache_warmer 预热逐字节同键
        start, end, adjust = engine_fetch_params()
        meta = {}
        try:
            df = fetcher.get_daily(code, start=start, end=end, adjust=adjust,
                                   meta_out=meta)
        finally:
            # T-248：诚实元数据随行取回（L5 兜底命中 → is_stale=True）
            fetch_metas[f"df_{code}"] = meta if isinstance(meta, dict) else {}
        return df

    tasks = [(f"df_{c}", lambda c=c: _fetch_one(c)) for c in codes]
    dfs = fetch_many(tasks, max_workers=8, timeout=240)

    candidates = {}
    unavailable_a1 = unavailable_a2 = 0
    # R5/T-270：指数 20 日收益（循环外一次性取，全候选共用同一基准）
    _idx_ret20 = _index_ret20_safe()
    for code in codes:
        df = dfs.get(f"df_{code}")
        if df is None or not isinstance(df, pd.DataFrame) or len(df) < 90:
            continue
        a1 = bt._score_for_picker(df.copy(), strategy="multi_factor")
        # R7/T-333：MACD 底背离确认加分（benchmark L153）——命中 +5 且 reasons
        # 透明标注；未命中/不可得原样返回，不动 backtest 本体（回测口径零影响）
        a1 = apply_divergence_confirm(a1, detect_bullish_divergence(df))
        a2 = bt._score_for_picker(df.copy(), strategy="dual_trend")
        if a1 is None:
            unavailable_a1 += 1
        if a2 is None:
            unavailable_a2 += 1
        a5 = _momentum_score(df, index_ret20=_idx_ret20)
        name = ""
        try:
            _, name = fetcher.get_stock_basic(code)
        except Exception:  # noqa: BLE001
            name = ""
        candidates[code] = {
            "name": name or code, "data_as_of": str(df["date"].iloc[-1])[:10],
            "algo": {
                "multi_factor": ({"score": a1.get("score"), "reasons": a1.get("reasons", [])}
                                  if a1 else None),
                "dual_trend": ({"score": a2.get("score"), "reasons": a2.get("reasons", [])}
                                if a2 else None),
                "momentum": a5,
                # R2/T-246：A6 放量新高突破（纯本地）
                "breakout": _breakout_score(df),
            },
            # R3/T-246：Value Trap 本地分量（PE/PB 确认在富集段叠加）
            "value_trap": value_trap_score(df),
        }

    scored = {c: v for c, v in candidates.items()
              if v["algo"]["multi_factor"] or v["algo"]["dual_trend"]}
    if progress:
        progress(0.5, f"价格类算法完成：{len(scored)}/{len(codes)} 有效")

    # ── 阶段 2：富集 Top-N（资金流 + 事件因子）──
    prelim = {}
    for c, v in scored.items():
        s = [v["algo"]["multi_factor"]["score"] if v["algo"]["multi_factor"] else None,
             v["algo"]["dual_trend"]["score"] if v["algo"]["dual_trend"] else None]
        s = [x for x in s if x is not None]
        prelim[c] = sum(s) / len(s) if s else 0.0
    enrich_codes = [c for c, _ in sorted(prelim.items(), key=lambda kv: -kv[1])[:enrich_top]]

    ff_tasks = [(f"ff_{c}", lambda c=c: _safe_fund_flow(c)) for c in enrich_codes]
    ff_map = fetch_many(ff_tasks, max_workers=6, timeout=90)
    event_map = _safe_event_long_list()
    # R8/T-363：财务健康三因子富集（与 fund_flow 并行取数，控制网络开销）
    fh_tasks = [(f"fh_{c}", lambda c=c: _safe_financial_health(c, fetcher)) for c in enrich_codes]
    fh_map = fetch_many(fh_tasks, max_workers=4, timeout=120)

    for c in enrich_codes:
        ff = ff_map.get(f"ff_{c}")
        if isinstance(ff, dict) and ff.get("main_net") is not None:
            mn = ff["main_net"]
            candidates[c]["algo"]["fund_flow"] = {
                "score": round(max(0.0, min(100.0, 50 + mn / 1e8 * 10)), 1),
                "reasons": [f"主力净流入 {mn / 1e8:+.2f} 亿"],
                "main_net": mn,
            }
        if event_map and c in event_map:
            ev = event_map[c]
            candidates[c]["algo"]["event_factor"] = {
                "score": ev.get("score"), "reasons": [f"P1 事件因子排名 {ev.get('raw_rank', '—')}"],
            }
        # R8/T-363：财务健康三合一（F+Z+M）进 algo → fusion 自动加权
        fh = fh_map.get(f"fh_{c}")
        if isinstance(fh, dict) and fh.get("score") is not None:
            candidates[c]["algo"]["financial_health"] = {
                "score": fh["score"],
                "reasons": fh.get("reasons", []),
                "meta": fh.get("meta", {}),
            }
        # R3/T-246：Value Trap 富集段——PE/PB 低位确认加分，≥50 时 A1 分数 ×0.7
        vt = candidates[c].get("value_trap")
        if isinstance(vt, dict):
            pb = _safe_pe_pb_series(c)
            boost = pe_pb_low_pct_boost((pb or {}).get("pe_pct"),
                                        (pb or {}).get("pb_pct"))
            vt["pe_boost"] = boost
            vt_total = min(100.0, float(vt.get("score", 0.0)) + boost)
            vt["total"] = vt_total
            if pb is None:
                vt["flags"] = list(vt.get("flags") or []) + ["估值序列不可得（确认项未计）"]
            a1 = candidates[c]["algo"].get("multi_factor")
            if vt_total >= 50 and a1 and a1.get("score") is not None:
                a1["score"] = round(float(a1["score"]) * 0.7, 1)
                vt_note = "；".join(vt.get("flags") or []) or "陷阱特征命中过半"
                a1["reasons"] = list(a1.get("reasons") or []) + [
                    f"[ValueTrap] 陷阱分 {vt_total:.0f}（{vt_note}），A1 已×0.7"]
    if progress:
        progress(0.75, "富集完成，融合排序…")

    # ── 阶段 3：融合 → Top-K ──
    # R4/T-270：温度档 → 自适应权重（中间档/快照不可得 → None 回落静态默认，
    # 来源与温度值如实写入 pick 元数据防「悄悄换权重」）
    regime_temperature = _safe_market_temperature()
    regime_weights = market_regime_weights(regime_temperature)
    regime_meta = {
        "weights_source": "regime" if regime_weights else "static_default",
        "temperature": regime_temperature,
    }
    rows = []
    for c, v in scored.items():
        algo_raw = {}
        for k in ALGO_WEIGHTS:
            item = v["algo"].get(k)
            algo_raw[k] = item.get("score") if item else None
        composite, breakdown = fusion_score(algo_raw, weights=regime_weights)
        if composite is None:
            continue
        df = dfs.get(f"df_{c}")
        # R6/T-330：连续价量风险惩罚（振幅过热/20日深回撤），罚分如实入 reasons；
        # risk_penalty 元数据恒落 row（0 分也存，防「悄悄不罚」）
        rp = continuous_risk_penalty(df)
        if rp["penalty"] > 0:
            composite = round(max(0.0, composite - rp["penalty"]), 1)
        levels = trade_levels(float(df["close"].iloc[-1]), atr14(df))
        reasons = []
        for k in ALGO_WEIGHTS:
            item = v["algo"].get(k)
            if item and item.get("reasons"):
                # _score_for_picker 的 reasons 是逗号拼接字符串，必须先归一（单字碎句缺陷）
                norm = _normalize_reasons(item["reasons"])
                reasons.extend(f"[{ALGO_LABELS[k]}] {r}" for r in norm[:2])
        if rp["penalty"] > 0:
            reasons.extend(f"[风险] {x}" for x in rp["reasons"][:2])
        rows.append({"code": c, "name": v["name"], "composite": composite,
                     "algorithms": breakdown, "reasons": reasons[:10],
                     "data_as_of": v["data_as_of"], "df": df,
                     "regime": regime_meta,
                     "index_ret20": _idx_ret20,
                     "risk_penalty": rp})

    rows.sort(key=lambda r: -r["composite"])
    # ── R1 六维排雷二道闸（T-245）：闸门段逐股六维扫描，硬红旗踢出；
    #    排雷不可得如实降级（not_scanned），不阻塞主流程 ──
    gate_n = max(enrich_top, top_k)
    try:
        scan_map = _safe_risk_scan([(r["code"], r.get("name") or r["code"])
                                    for r in rows[:gate_n]])
    except Exception as e:  # noqa: BLE001 - 双保险：闸源异常也按不可得降级
        logger.info("[recommend_engine] 排雷闸异常（如实降级）: %s", e)
        scan_map = {}
    rows, gate_summary = apply_risk_gate(rows, scan_map, top_k, gate_n)
    # R6/T-330：解禁临近扣分（复用闸门已取数据），扣后按 composite 重排
    rows = apply_unlock_penalty(rows, scan_map)
    if progress:
        progress(0.85, f"排雷完成：踢出 {len(gate_summary['kicked'])} 只，融合排序…")
    # 市场上下文（决策快照，取不到即标注）
    market_ctx = _safe_market_context()
    pos_base = (market_ctx.get("position") or {}).get("pct") if market_ctx.get("position") else None
    per_stock_cap = 20.0
    picks = []
    # T-256：信念×风险二维配仓（预算守恒、单票上下限）；pos_base 不可得 → None 走原降级
    sizing = size_positions(rows[:top_k], pos_base, per_stock_cap=per_stock_cap)
    for r in rows[:top_k]:
        df = r.pop("df")
        # fix（T-256 顺带）：levels 必须逐票重算——原写法引用 rows 循环泄漏的尾值，
        # 导致所有推荐共享最后一只票的 ATR 价位（串票）。
        levels = trade_levels(float(df["close"].iloc[-1]), atr14(df))
        if sizing:
            hint = sizing["hints"].get(r["code"])
            b = sizing["basis"].get(r["code"], {})
            note = (f"信念×风险二维配仓：信念倍数 {b.get('conviction_mult', 1.0)}×"
                    f"风险因子 {b.get('risk_factor', 1.0)}，总敞口≈市场建议仓位 "
                    f"{sizing['pos_base']:g}%、单票 [{sizing['floor']:g},{sizing['cap']:g}]%"
                    + ("（单票上下限约束致略超预算，如实标注）" if sizing.get("budget_over") else ""))
        elif isinstance(pos_base, (int, float)) and pos_base > 0:
            hint = round(min(pos_base / max(top_k, 1), per_stock_cap), 1)
            note = f"按市场建议仓位 {pos_base}% 等权 {top_k} 只、单票上限 {per_stock_cap}% 估算"
        else:
            hint = None
            note = "市场仓位快照不可用，请自行确定仓位"
        picks.append({**r, "plan": {
            **levels,
            "position_pct_hint": hint,
            "position_note": note,
        }})

    rec = {
        "status": "ok", "date": _today_str(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe_size": len(codes), "scored_size": len(scored),
        "algo_unavailable": {"multi_factor": unavailable_a1, "dual_trend": unavailable_a2},
        "market_context": market_ctx,
        "picks": picks, "disclaimer": DISCLAIMER,
        "weights": ALGO_WEIGHTS,
        # T-248：本次推荐有 N 只标的的行情来自 L5 旧缓存兜底（is_stale），如实落盘
        "stale_count": sum(1 for m in fetch_metas.values()
                           if isinstance(m, dict) and m.get("is_stale")),
        # R1 六维排雷二道闸（T-245）：kicked=被踢明细；unscanned_picks=入选中未过闸数
        "risk_gate": {**gate_summary,
                      "unscanned_picks": sum(1 for p in picks
                                             if p.get("risk_scan", {}).get("status")
                                             != "scanned")},
        # T-235 数据时效护栏：行情整体滞后超阈值时 stale=True，36 页显著告警
        "data_staleness": assess_data_staleness([r.get("data_as_of") for r in rows]),
    }
    save_recommendation(rec, data_dir)
    if progress:
        progress(1.0, f"完成：{len(picks)} 只推荐已落盘")
    return rec


def apply_risk_gate(rows: list, scan_map: dict, top_k: int, gate_n: int) -> tuple:
    """R1 六维排雷二道闸（纯逻辑，可单测）。

    rows：已按 composite 降序的候选列表（元素含 code/name，原列表顺位不变）；
    scan_map：{code6: scan_stock 结果（含 report/components）}；空 dict = 排雷不可得。

    规则（T-245 spec 冻结）：
    - 闸门段 = rows[:max(gate_n, top_k)]，overall_level == high → 硬红旗踢出；
    - unknown ≠ guilty：unknown/medium/low 一律保留，只如实携带 risk_scan 元数据；
    - 被踢后不足 top_k → 从闸门段之外顺位补入，补入者标 not_scanned（不静默）；
    - scan_map 为空 → 全部标 not_scanned，status=unavailable，主流程不阻塞。

    返回 (gated_rows, gate_summary)；gated_rows 元素新增 ``risk_scan`` 字段。
    """
    gate_n = max(int(gate_n), int(top_k))
    head, tail = rows[:gate_n], rows[gate_n:]
    if not scan_map:
        for r in rows:
            r["risk_scan"] = {"status": "not_scanned"}
        summary = {"status": "unavailable", "gate_size": len(head), "scanned": 0,
                   "kicked": [],
                   "reason": "六维排雷扫描不可用（网络或接口失败），如实降级不阻塞"}
        return list(rows), summary

    kept: list = []
    kicked: list = []
    for r in head:
        scan = scan_map.get(str(r.get("code", "")).zfill(6))
        report = (scan or {}).get("report") or {}
        if report.get("overall_level") == RISK_HIGH:
            reasons = []
            for key, cn, _unit in DIMENSIONS:
                comp = (scan.get("components") or {}).get(key) or {}
                if comp.get("level") == RISK_HIGH:
                    note = str(comp.get("note") or "").strip()
                    reasons.append(f"{cn}·{note}"[:60] if note else cn)
            kicked.append({"code": r.get("code"), "name": r.get("name"),
                           "overall_level": RISK_HIGH,
                           "n_high": report.get("n_high"), "reasons": reasons})
            continue
        r["risk_scan"] = {"status": "scanned",
                          "overall_level": report.get("overall_level"),
                          "risk_score": report.get("risk_score"),
                          "reliable": report.get("reliable"),
                          "n_high": report.get("n_high", 0)}
        kept.append(r)
    for r in tail:
        r["risk_scan"] = {"status": "not_scanned"}
    summary = {"status": "ok", "gate_size": len(head), "scanned": len(scan_map),
               "kicked": kicked, "reason": ""}
    return kept + tail, summary


def size_positions(picks: list, pos_base, per_stock_cap: float = 20.0,
                   floor: float = 1.0):
    """信念×风险二维配仓（T-256，benchmark stock-evaluator 采纳清单 R3 落地遗留）。

    - 信念维：picks 内 composite min-max 归一 → 倍数 [0.6, 1.5]（全相同 = 1.0）；
    - 风险维：risk_scan.medium ×0.8、reliable=False ×0.85、value_trap.total≥50 ×0.85
      （乘积叠加；not_scanned/字段缺失 = 1.0，不惩罚也不假装扫过）；
    - 预算守恒：Σhint ≈ pos_base（总敞口不放大市场建议仓位）；单票 clamp [floor, cap]，
      下限为硬约束（再弱保留最小试探仓），届时可略超预算并如实标注 budget_over；
    - pos_base 不可得/非正/无票 → None（引擎走「自行确定仓位」诚实降级）。

    返回 ``{"hints": {code: pct}, "basis": {code: {...}}, "pos_base", "cap", "floor",
    "budget_over"}`` 或 None。
    """
    if not picks or not isinstance(pos_base, (int, float)) or pos_base <= 0:
        return None
    comps = [float(p.get("composite") or 0.0) for p in picks]
    lo, hi = min(comps), max(comps)
    span = hi - lo
    raw: dict = {}
    basis: dict = {}
    for p, c in zip(picks, comps):
        mult = 1.0 if span == 0 else 0.6 + 0.9 * (c - lo) / span
        risk = 1.0
        rs = p.get("risk_scan") or {}
        if rs.get("status") == "scanned":
            if rs.get("overall_level") == "medium":
                risk *= 0.8
            if rs.get("reliable") is False:
                risk *= 0.85
        vt = (p.get("value_trap") or {}).get("total")
        if isinstance(vt, (int, float)) and vt >= 50:
            risk *= 0.85
        raw[p["code"]] = mult * risk
        basis[p["code"]] = {"conviction_mult": round(mult, 3),
                            "risk_factor": round(risk, 3)}
    total_raw = sum(raw.values())
    budget = float(pos_base)
    hints = {k: v / total_raw * budget for k, v in raw.items()}
    hints = {k: min(max(v, floor), per_stock_cap) for k, v in hints.items()}
    s = sum(hints.values())
    if s > budget:
        hints = {k: v * budget / s for k, v in hints.items()}
        hints = {k: max(v, floor) for k, v in hints.items()}  # 下限硬约束
    rounded = {k: round(v, 1) for k, v in hints.items()}
    diff = round(budget - sum(rounded.values()), 1)
    if abs(diff) >= 0.1 and rounded:
        # 差额只补给未顶格的最大票（顶格票不得突破 cap；补不进去就留 ≤0.1 舍入 slack）
        for k in sorted(rounded, key=lambda k: -rounded[k]):
            if rounded[k] < per_stock_cap:
                rounded[k] = round(max(rounded[k] + diff, floor), 1)
                break
    budget_over = sum(rounded.values()) > budget + 0.05
    return {"hints": rounded, "basis": basis, "pos_base": budget,
            "cap": per_stock_cap, "floor": floor, "budget_over": budget_over}


def _safe_risk_scan(codes_with_names) -> dict:
    """六维排雷批量扫描（R1 二道闸数据源）。失败返回 {}（诚实降级，不阻塞荐股）。"""
    try:
        from modules.stock_risk import scan_many

        results = scan_many(list(codes_with_names), max_workers=4) or []
        return {str(r.get("code", "")).zfill(6): r
                for r in results if isinstance(r, dict) and r.get("code")}
    except Exception as e:  # noqa: BLE001 - 排雷不可得≠有罪，如实降级并留痕
        logger.info("[recommend_engine] 六维排雷不可用（如实降级）: %s", e)
        return {}


def _safe_pe_pb_series(code: str):
    """估值序列分位（R3 Value Trap 确认项数据源）。失败返回 None（诚实降级）。

    返回 ``{"pe_pct": 0~1, "pb_pct": 0~1}``（当前值在自身历史中的分位，越低越便宜）。
    """
    try:
        from modules.valuation import fetch_pe_pb_series

        data = fetch_pe_pb_series(code)
        if not isinstance(data, dict):
            return None
        out = {}
        for key in ("pe", "pb"):
            series = [float(v) for v in (data.get(key) or [])
                      if isinstance(v, (int, float)) and math.isfinite(float(v))]
            if series:
                cur = series[-1]
                out[f"{key}_pct"] = sum(1 for v in series if v <= cur) / len(series)
        return out or None
    except Exception as e:  # noqa: BLE001 - 估值不可得≠无陷阱，如实降级并留痕
        logger.info("[recommend_engine] 估值序列不可用（%s）: %s", code, e)
        return None


def _safe_fund_flow(code):
    """个股主力净流入（A3 富集源）。

    ⚠️ 修复（T-233 回归揪出）：原误调 `fetcher.get_individual_fund_flow()`——
    StockFetcher 上不存在该方法，会被宽泛 except 静默吞掉 → A3 算法恒不可用。
    正确入口是 modules.fundflow 模块函数（与 MCP fund_flow 工具同源）。
    """
    try:
        from modules import fundflow

        r = fundflow.get_individual_fund_flow(code)
        return r if isinstance(r, dict) else None
    except Exception as e:  # noqa: BLE001 - 单标的资金流失败不影响整体推荐，但必须留痕
        logger.info("[recommend_engine] 资金流不可用（%s）: %s", code, e)
        return None


def _safe_event_long_list() -> dict:
    """P1 事件因子多头榜 → {symbol(6位): {score, raw_rank}}；不可用返回 {}。"""
    try:
        from modules.event_factor import event_driven_long_list
        rows = event_driven_long_list(top_n=50, model="ev") or []
        return {str(r.get("symbol", "")).zfill(6): r for r in rows if r.get("symbol")}
    except Exception as e:  # noqa: BLE001
        logger.info("[recommend_engine] 事件因子不可用（如实降级）: %s", e)
        return {}


def _safe_financial_health(code: str, fetcher=None) -> dict:
    """R8/T-363：财务健康三合一 → 0-100 融合分。

    三模型独立评分后平均：F-Score(0-9→0-100) / Altman Z'(1.81危险→20, 3.0安全→90) /
    Beneish M(-1.78正常→40, ≤-3→90, ≥0→10)；任一不可用按可用部分平均+warning；
    全不可用 → status="unavailable" 不编造。
    """
    try:
        from modules import financial_health as fh

        f = fh.f_score(code, fetcher)
        z = fh.altman_z(code, fetcher)
        m = fh.beneish_m(code, fetcher)

        scores: list[float] = []
        reasons: list[str] = []
        meta = {"f": f["status"], "z": z["status"], "m": m["status"]}

        # F-Score: 0-9 → 0-100
        if f["score"] is not None:
            f_s = round(min(100.0, max(0.0, f["score"] / 9 * 100)), 1)
            scores.append(f_s)
            reasons.append(f"F-Score={f['score']}/9")

        # Altman Z': 1.81→20, 3.0→90 线性
        if z["score"] is not None:
            zv = z["score"]
            if zv <= 1.81:
                z_s = 20.0
            elif zv >= 3.0:
                z_s = 90.0
            else:
                z_s = round(20.0 + (zv - 1.81) / 1.19 * 70.0, 1)
            scores.append(z_s)
            reasons.append(f"Altman Z'={zv:.2f}")

        # Beneish M: ≤-3→90, -1.78→40, ≥0→10 线性
        if m["score"] is not None:
            mv = m["score"]
            if mv <= -3.0:
                m_s = 90.0
            elif mv >= 0.0:
                m_s = 10.0
            elif mv <= -1.78:
                m_s = round(40.0 + (-1.78 - mv) / 1.22 * 50.0, 1)
            else:
                m_s = round(20.0 * (1.0 + mv / -1.78), 1)
            scores.append(m_s)
            reasons.append(f"Beneish M={mv:.2f}")

        if not scores:
            return {"score": None, "reasons": [], "status": "unavailable", "meta": meta}

        avg = round(sum(scores) / len(scores), 1)
        ok_count = len(scores)
        total = 3
        status = "ok" if ok_count == total else "warning"
        if ok_count < total:
            reasons.append(f"（{ok_count}/{total} 因子可用，缺失按诚实降级处理）")
        return {"score": avg, "reasons": reasons, "status": status, "meta": meta}

    except Exception as e:  # noqa: BLE001
        logger.info("[recommend_engine] %s financial_health 异常（如实降级）: %s", code, e)
        return {"score": None, "reasons": [], "status": "unavailable", "meta": {}}


def _safe_market_context() -> dict:
    try:
        from modules.decision import load_snapshot
        snap = load_snapshot() or {}
        return {"date": snap.get("date"), "temperature": snap.get("temperature"),
                "cycle": snap.get("cycle"), "position": snap.get("position")}
    except Exception as e:  # noqa: BLE001
        logger.info("[recommend_engine] 决策快照不可用（如实降级）: %s", e)
        return {}
