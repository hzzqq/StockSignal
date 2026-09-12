"""
模块 temperature_backtest：全温度档历史回测（方案⑤ 离线版）

设计原则（与 P3 / 市场温度计 / 市场状态机一致的诚实口径）：
* 温度档复用 market_temperature.BANDS 的五档语义（冰点/偏冷/中性/活跃/狂热），
  档位由当日「红盘率 red_ratio」（0-100 广度温度计）映射——红盘率本身是温度计的主导输入，
  同尺度可直接套用分档阈值，单一分档真理源。
* 回测刻画的是**广度均值回归结构**，不是收益预测：
    - 对落在某温度档的每一个历史交易日，看其后 1 日 / 5 日的红盘率变化；
    - 统计该档「次日红盘率改善率」（next 红盘率 > 当日）与「次日平均变化」，
      以及 5 日对应值；并给出全样本基准做对照。
* 全程离线（shepherd_history.json，4771 天，2007-2026），零网络、零编造指数收益。
* 小样本档（如冰点日极少）明确标注低置信，绝不夸大。
* 取数失败优雅降级（available=False）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from modules import market_regime as mr
from modules import market_temperature as mt

logger = logging.getLogger(__name__)


def load_breadth() -> pd.DataFrame:
    return mr.load_breadth_history()


def _band_level(v):
    """把 red_ratio 映射到温度档 level(0-4)；非数值/NaN→None。纯函数。"""
    try:
        rr = float(v)
    except (TypeError, ValueError):
        return None
    if rr != rr:  # NaN
        return None
    return int(mt.temperature_band(rr)["level"])


def band_backtest(df: pd.DataFrame | None = None) -> dict:
    """全温度档历史回测（次日 / 5 日 红盘率均值回归结构）。

    返回：
    {
      available: bool,
      reason: str (失败时),
      data: {rows, start, end},
      baseline: {n, next_mean_delta, next_impr_rate, d5_mean_delta, d5_impr_rate},
      bands: [ {level, label, color, n, available,
                next_mean_delta, next_impr_rate,
                d5_mean_delta, d5_impr_rate,
                avg_next_red, avg_d5_red} × 5 ],
      note: str (方法学声明)
    }
    """
    if df is None:
        try:
            df = load_breadth()
        except Exception as exc:  # pragma: no cover
            logger.warning("[temperature_backtest] 广度历史加载失败: %s", exc)
            return dict(available=False, reason=f"广度历史加载失败：{exc}")
    if df is None or len(df) == 0:
        return dict(available=False, reason="广度历史为空（数据缺失）")

    d = df.copy()
    d["rr"] = pd.to_numeric(d.get("red_ratio"), errors="coerce")
    if "date" in d.columns:
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    d = d.dropna(subset=["rr"])
    if len(d) == 0:
        return dict(available=False, reason="red_ratio 全缺失")

    d["band"] = d["rr"].apply(_band_level)
    # 前瞻位移（须按日期升序，已在上面保证）
    d["rr_next"] = d["rr"].shift(-1)
    d["rr_d5"] = d["rr"].shift(-5)
    d = d.dropna(subset=["rr_next", "rr_d5"])
    if len(d) == 0:
        return dict(available=False, reason="无足够前瞻样本（历史末尾不足 5 日）")

    d["next_delta"] = d["rr_next"] - d["rr"]
    d["d5_delta"] = d["rr_d5"] - d["rr"]
    d["next_up"] = d["next_delta"] > 0
    d["d5_up"] = d["d5_delta"] > 0

    baseline = dict(
        n=int(len(d)),
        next_mean_delta=round(float(d["next_delta"].mean()), 2),
        next_impr_rate=round(float(d["next_up"].mean() * 100), 1),
        d5_mean_delta=round(float(d["d5_delta"].mean()), 2),
        d5_impr_rate=round(float(d["d5_up"].mean() * 100), 1),
    )

    bands = []
    for lvl in range(5):
        sub = d[d["band"] == lvl]
        bmeta = mt.BANDS[lvl]
        if len(sub) == 0:
            bands.append(dict(level=lvl, label=bmeta["label"], color=bmeta["color"],
                              n=0, available=False))
            continue
        bands.append(dict(
            level=lvl,
            label=bmeta["label"],
            color=bmeta["color"],
            n=int(len(sub)),
            available=True,
            next_mean_delta=round(float(sub["next_delta"].mean()), 2),
            next_impr_rate=round(float(sub["next_up"].mean() * 100), 1),
            d5_mean_delta=round(float(sub["d5_delta"].mean()), 2),
            d5_impr_rate=round(float(sub["d5_up"].mean() * 100), 1),
            avg_next_red=round(float(sub["rr_next"].mean()), 2),
            avg_d5_red=round(float(sub["rr_d5"].mean()), 2),
        ))

    return dict(
        available=True,
        data=dict(
            rows=int(len(df)),
            start=str(pd.to_datetime(df["date"]).iloc[0].date()) if "date" in df.columns else "",
            end=str(pd.to_datetime(df["date"]).iloc[-1].date()) if "date" in df.columns else "",
        ),
        baseline=baseline,
        bands=bands,
        note=(
            "温度档由当日红盘率(red_ratio)经 market_temperature.BANDS 映射；"
            "回测统计各档后 1 日 / 5 日红盘率变化（次日改善率=次日红盘率高于当日占比），"
            "刻画广度均值回归结构，非收益预测。全程离线，零编造指数收益。"
            "小样本档(样本<50)置信低，仅供结构参考。"
        ),
    )


def _empty():
    return dict(available=False, reason="空数据")


if __name__ == "__main__":
    r = band_backtest()
    if not r.get("available"):
        print("回测失败：", r.get("reason"))
    else:
        print(f"全样本 {r['data']['rows']} 天 {r['data']['start']}~{r['data']['end']}")
        print(f"基准：次日改善率 {r['baseline']['next_impr_rate']}% ｜ "
              f"次日均变 {r['baseline']['next_mean_delta']} ｜ "
              f"5日改善率 {r['baseline']['d5_impr_rate']}% ｜ "
              f"5日均变 {r['baseline']['d5_mean_delta']}")
        for b in r["bands"]:
            if b.get("available"):
                print(f"  {b['label']:>3} (n={b['n']:>4}) 次日改善 {b['next_impr_rate']}% "
                      f"次日均变 {b['next_mean_delta']:>6} ｜ 5日改善 {b['d5_impr_rate']}% "
                      f"5日均变 {b['d5_mean_delta']:>6}")
            else:
                print(f"  {b['label']:>3} 样本为 0")
