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

融合：各算法在候选集内 min-max 归一化 → 加权求和 → Top-K。
买入方案：入场=现价，目标/止损=ATR14 倍数（2×止损 / 3×目标），
仓位提示 = derive_position 市场仓位 / 推荐只数（等权、单票上限 20%）。

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
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

# 融合权重（和为 1；逐标的缺失某算法时按可用权重重归一化）
ALGO_WEIGHTS = {
    "multi_factor": 0.30,
    "dual_trend": 0.25,
    "fund_flow": 0.20,
    "event_factor": 0.15,
    "momentum": 0.10,
}
ALGO_LABELS = {
    "multi_factor": "多因子 V5（趋势+超跌反弹）",
    "dual_trend": "双趋势共振（GMMA+一目+ADX）",
    "fund_flow": "主力资金净流入",
    "event_factor": "P1 事件因子",
    "momentum": "20 日动量+量能",
}

DISCLAIMER = (
    "推荐由多算法融合筛选生成，附历史模拟统计，不构成投资建议；"
    "方向预测≈随机（4092 交易日回测结论），价值在筛选漏斗+风控方案+成本感知，请独立决策。"
)


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
def _momentum_score(df: pd.DataFrame) -> dict:
    """A5：20 日动量 + 量能放大（0~100）。"""
    close, vol = df["close"], df["volume"]
    if len(close) < 21:
        return None
    ret20 = close.iloc[-1] / close.iloc[-21] - 1
    vol_ratio = vol.tail(5).mean() / max(vol.tail(60).mean(), 1)
    score = 50.0
    if ret20 > 0:
        score += min(ret20 * 250, 30)          # 20 日涨幅最多 +30
    else:
        score += max(ret20 * 250, -30)
    score += min((vol_ratio - 1) * 25, 20)      # 量能放大最多 +20
    reasons = []
    reasons.append(f"20日动量 {ret20:+.1%}")
    if vol_ratio >= 1.2:
        reasons.append(f"量能放大 {vol_ratio:.2f}x")
    return {"score": round(max(0.0, min(100.0, score)), 1), "reasons": reasons}


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
    def _fetch_one(code):
        start = (datetime.now() - timedelta(days=260)).strftime("%Y-%m-%d")
        df = fetcher.get_daily(code, start=start,
                               end=datetime.now().strftime("%Y-%m-%d"))
        return df

    tasks = [(f"df_{c}", lambda c=c: _fetch_one(c)) for c in codes]
    dfs = fetch_many(tasks, max_workers=8, timeout=240)

    candidates = {}
    unavailable_a1 = unavailable_a2 = 0
    for code in codes:
        df = dfs.get(f"df_{code}")
        if df is None or not isinstance(df, pd.DataFrame) or len(df) < 90:
            continue
        a1 = bt._score_for_picker(df.copy(), strategy="multi_factor")
        a2 = bt._score_for_picker(df.copy(), strategy="dual_trend")
        if a1 is None:
            unavailable_a1 += 1
        if a2 is None:
            unavailable_a2 += 1
        a5 = _momentum_score(df)
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
            },
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
    if progress:
        progress(0.75, "富集完成，融合排序…")

    # ── 阶段 3：融合 → Top-K ──
    rows = []
    for c, v in scored.items():
        algo_raw = {}
        for k in ALGO_WEIGHTS:
            item = v["algo"].get(k)
            algo_raw[k] = item.get("score") if item else None
        composite, breakdown = fusion_score(algo_raw)
        if composite is None:
            continue
        df = dfs.get(f"df_{c}")
        levels = trade_levels(float(df["close"].iloc[-1]), atr14(df))
        reasons = []
        for k in ALGO_WEIGHTS:
            item = v["algo"].get(k)
            if item and item.get("reasons"):
                reasons.extend(f"[{ALGO_LABELS[k]}] {r}" for r in item["reasons"][:2])
        rows.append({"code": c, "name": v["name"], "composite": composite,
                     "algorithms": breakdown, "reasons": reasons[:10],
                     "data_as_of": v["data_as_of"], "df": df})

    rows.sort(key=lambda r: -r["composite"])
    # 市场上下文（决策快照，取不到即标注）
    market_ctx = _safe_market_context()
    pos_base = (market_ctx.get("position") or {}).get("pct") if market_ctx.get("position") else None
    per_stock_cap = 20.0
    picks = []
    for r in rows[:top_k]:
        df = r.pop("df")
        hint = None
        if isinstance(pos_base, (int, float)) and pos_base > 0:
            hint = round(min(pos_base / max(top_k, 1), per_stock_cap), 1)
        picks.append({**r, "plan": {
            **levels,
            "position_pct_hint": hint,
            "position_note": (f"按市场建议仓位 {pos_base}% 等权 {top_k} 只、单票上限 {per_stock_cap}% 估算"
                               if hint else "市场仓位快照不可用，请自行确定仓位"),
        }})

    rec = {
        "status": "ok", "date": _today_str(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe_size": len(codes), "scored_size": len(scored),
        "algo_unavailable": {"multi_factor": unavailable_a1, "dual_trend": unavailable_a2},
        "market_context": market_ctx,
        "picks": picks, "disclaimer": DISCLAIMER,
        "weights": ALGO_WEIGHTS,
    }
    save_recommendation(rec, data_dir)
    if progress:
        progress(1.0, f"完成：{len(picks)} 只推荐已落盘")
    return rec


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


def _safe_market_context() -> dict:
    try:
        from modules.decision import load_snapshot
        snap = load_snapshot() or {}
        return {"date": snap.get("date"), "temperature": snap.get("temperature"),
                "cycle": snap.get("cycle"), "position": snap.get("position")}
    except Exception as e:  # noqa: BLE001
        logger.info("[recommend_engine] 决策快照不可用（如实降级）: %s", e)
        return {}
