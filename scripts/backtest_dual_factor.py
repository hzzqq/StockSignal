# -*- coding: utf-8 -*-
"""
scripts/backtest_dual_factor.py — T-182 双因子决策增强 大样本回测

目的（服务「决策科学」主线 + 论文创新点）：
    在 4092 个真实交易日（data/shepherd_history.csv）上，把 T-182 两个新因子
    以控制变量方式叠加到同一基线决策（temp=红盘比代理 + bias=同日广度推导，
    无前视），量化各自与合并的边际贡献：
      因子 A（regime 门控）：market_regime 五状态 × _state_confidence 置信度，
                            暴跌→封顶 50 / 恐慌→封顶 60（decision.REGIME_CAPS）
      因子 B（羊群拥挤）：herd_crowding 拥挤度，红挤极端 -8pt / 中度 -4pt，
                         绿挤不调节（与冰点超卖语义自洽）

四组：baseline / regime / herd / dual —— 共享同一基线入参，组间差异纯来自新因子。

⚠️ 诚实披露（论文必须如实写）：
    · 门控与反向因子**只调仓位、不改方向**：不设「方向命中率」指标（方向归
      backtest_decision_closure.json 的六阶段口径）；主指标为仓位加权次日收益
      与尾部风险暴露。
    · temp/bias 为离线代理口径（同 backtest_decision_closure.py），结论验证
      「因子在真实数据上的统计行为」，非实盘收益。
    · 涨停/跌停分位只用截至前一日的历史分布（无前视）；streak 含当日（收盘后
      可知，供次日决策合法）。
    · 拥挤度/状态置信度取不到的日子如实降级（不臆造），组内 n 如实披露。

输入：data/shepherd_history.csv（只读）
输出：reports/backtest_dual_factor.json + 控制台摘要
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime

_HERE0 = os.path.dirname(os.path.abspath(__file__))
_ROOT0 = os.path.dirname(_HERE0)
if _ROOT0 not in sys.path:
    sys.path.insert(0, _ROOT0)

import pandas as pd

from modules.decision import REGIME_CAPS, derive_position
from modules.herd_crowding import MILD_CROWD, STRONG_CROWD, crowding_from_history
from modules.market_regime import _state_confidence, classify_state
from modules.time_utils import now_cst_naive

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DATA_DIR = os.environ.get("SS_DATA_DIR", os.path.join(_ROOT, "data"))
_BREADTH_FILE = os.path.join(DATA_DIR, "shepherd_history.csv")
OUT_PATH = os.environ.get(
    "BACKTEST_DUAL_OUT",
    os.path.join(_ROOT, "reports", "backtest_dual_factor.json"),
)

GROUPS = ("baseline", "regime", "herd", "dual", "dual_cap")
TAIL_DROP_PCT = -2.0  # 尾部风险日口径：次日中位收益 < -2%

# 封顶变体（T-183，仅回测未进生产）：红挤极端日以「仓位封顶 60%」替代 -8pt
# delta，中度红挤维持 -4pt。用于量化「delta vs cap」的敏感性，供生产规则
# 升级决策参考——改生产规则须老板拍板 + 重跑全量守卫。
HERD_CAP_VARIANT = 60.0

# 基线 bias 推导：与 backtest_decision_closure._proxy_bias 同口径（无前视）。
# 不直接 import 兄弟脚本（scripts 非稳定包），此规则仅两处且都有测试钉住；
# 若漂移，test_backtest_dual_factor 与 test_backtest_decision_closure 会分别红。
def _proxy_bias(red, mchg) -> str:
    if red is None:
        return "中性"
    up = mchg is not None and mchg > 0
    down = mchg is not None and mchg < 0
    if red >= 55 and up:
        return "偏多"
    if red <= 45 and down:
        return "偏空"
    return "中性"


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _max_drawdown(cum_curve: list[float]) -> float:
    """净值曲线最大回撤（0~1）。cum_curve 为 (1+w) 累乘序列。"""
    peak = -float("inf")
    mdd = 0.0
    for v in cum_curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def run(breadth_file: str | None = None) -> dict:
    path = breadth_file or _BREADTH_FILE
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.sort_values("date").reset_index(drop=True)

    stat = {g: {
        "n": 0, "sum_w": 0.0, "sum_p": 0.0,        # 加权收益和(pct·day) / 仓位和
        "sum_w_loss_tail": 0.0, "n_tail": 0, "sum_p_tail": 0.0,
        "curve": [1.0],
    } for g in GROUPS}
    regime_extra = {"capped_days": 0, "cap_by_state": {"暴跌": 0, "恐慌": 0}}
    herd_extra = {"greed_strong_days": 0, "greed_mild_days": 0, "fear_days": 0,
                  "unavailable_days": 0}
    state_seen: dict[str, int] = {}

    rows = df.to_dict("records")
    for i in range(1, len(rows) - 1):  # 首日无历史分位；末日无次日真值
        today = rows[i]
        red = _num(today.get("red_ratio"))
        mchg = _num(today.get("median_chg"))
        next_mchg = _num(rows[i + 1].get("median_chg"))
        if red is None or next_mchg is None:
            continue  # 当日红盘比或次日真值缺失 → 诚实跳过（不计入任何组）

        state = classify_state(today)
        conf = float(_state_confidence(today, state))
        state_seen[state] = state_seen.get(state, 0) + 1

        herd = crowding_from_history(df, i)
        if herd.get("status") == "ok" and herd.get("score") is not None:
            h_score, h_side = herd["score"], herd["side"]
        else:
            h_score, h_side = None, None
            herd_extra["unavailable_days"] += 1

        bias = _proxy_bias(red, mchg)
        base_kw = dict(temp=red, bias=bias)
        outs = {
            "baseline": derive_position(**base_kw),
            "regime": derive_position(**base_kw, regime_state=state,
                                      regime_confidence=conf),
            "herd": derive_position(**base_kw, herd_score=h_score, herd_side=h_side),
            "dual": derive_position(**base_kw, regime_state=state,
                                    regime_confidence=conf,
                                    herd_score=h_score, herd_side=h_side),
        }

        w_next = next_mchg / 100.0  # 次日真实收益（小数）
        tail_day = next_mchg < TAIL_DROP_PCT
        # 封顶变体（仅回测）：红挤极端日 min(无herd仓位, 60)；其余日与 dual 同
        if h_side == "greed" and h_score is not None and h_score >= STRONG_CROWD:
            _cap_out = derive_position(**base_kw, regime_state=state,
                                       regime_confidence=conf)
            outs["dual_cap"] = {"pct": min(_cap_out["pct"], HERD_CAP_VARIANT)}
        else:
            outs["dual_cap"] = outs["dual"]
        for g, out in outs.items():
            p = out["pct"] / 100.0
            w = p * w_next  # 仓位加权次日收益（小数）
            s = stat[g]
            s["n"] += 1
            s["sum_w"] += w * 100.0          # 折成「百分点·日」口径
            s["sum_p"] += p
            s["curve"].append(s["curve"][-1] * (1.0 + w))
            if tail_day:
                s["n_tail"] += 1
                s["sum_w_loss_tail"] += w * 100.0
                s["sum_p_tail"] += p

        # 因子作用面统计（以 dual 组的实际生效为准）
        if outs["regime"]["pct"] < outs["baseline"]["pct"] or \
           (outs["dual"]["pct"] < outs["herd"]["pct"] and state in REGIME_CAPS):
            regime_extra["capped_days"] += 1
            if state in regime_extra["cap_by_state"]:
                regime_extra["cap_by_state"][state] += 1
        if h_side == "greed" and h_score is not None:
            if h_score >= STRONG_CROWD:
                herd_extra["greed_strong_days"] += 1
            elif h_score >= MILD_CROWD:
                herd_extra["greed_mild_days"] += 1
        elif h_side == "fear":
            herd_extra["fear_days"] += 1

    try:
        src_label = os.path.relpath(path, _ROOT)
    except ValueError:  # 跨盘符（如测试 tmp 在 C:）→ 用原始路径
        src_label = str(path)

    def _finalize(g: str) -> dict:
        s = stat[g]
        n = s["n"]
        curve = s.pop("curve")
        return {
            "n": n,
            "avg_position": round(s["sum_p"] / n, 4) if n else None,
            "avg_weighted_ret_bp": round(s["sum_w"] / n, 4) if n else None,  # 每日 bp
            "cum_ret_pct": round((curve[-1] - 1.0) * 100.0, 4) if n else None,
            "max_drawdown_pct": round(_max_drawdown(curve) * 100.0, 4) if n else None,
            "tail_days": s["n_tail"],
            "tail_avg_position": round(s["sum_p_tail"] / s["n_tail"], 4) if s["n_tail"] else None,
            "tail_avg_weighted_loss_bp": round(s["sum_w_loss_tail"] / s["n_tail"], 4)
            if s["n_tail"] else None,
        }

    groups = {g: _finalize(g) for g in GROUPS}
    groups["regime"].update(regime_extra)
    groups["herd"].update(herd_extra)

    return {
        "meta": {
            "generated_at": now_cst_naive().isoformat(timespec="seconds"),
            "source": src_label,
            "n_trading_days_scored": groups["baseline"]["n"],
            "baseline_rule": "temp=red_ratio 代理 + bias=同日广度推导（无前视），"
                             "无周期/晋级率/事件输入——纯因子对照实验",
            "factor_a": f"regime 门控 {REGIME_CAPS}（conf≥0.5 启用，仅封顶不抬底）",
            "factor_b": f"羊群拥挤反向：greed ≥{STRONG_CROWD:.0f} → -8pt / "
                        f"≥{MILD_CROWD:.0f} → -4pt / fear 不调节",
            "tail_rule": f"尾部风险日 = 次日 median_chg < {TAIL_DROP_PCT}%",
            "variants": {"dual_cap": f"红挤极端(≥{STRONG_CROWD:.0f})以封顶 "
                          f"{HERD_CAP_VARIANT:.0f}% 替代 -8pt（仅回测对照，未进生产）"},
            "disclosure": "门控与反向因子只调仓位不改方向，故不设方向命中率"
                          "（方向口径见 backtest_decision_closure.json）；"
                          "temp/bias 为离线代理，结论验证统计行为而非实盘收益。",
            "state_days": state_seen,
        },
        "groups": groups,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[backtest_dual_factor] report → {OUT_PATH}")
    for g, s in report["groups"].items():
        print(f"  {g:9s} n={s['n']:5d} avgPos={s['avg_position']} "
              f"avgRet={s['avg_weighted_ret_bp']}bp/day cum={s['cum_ret_pct']}% "
              f"mdd={s['max_drawdown_pct']}% tailPos={s['tail_avg_position']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
