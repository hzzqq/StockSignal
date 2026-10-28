# -*- coding: utf-8 -*-
"""T-342 论文扩展：周期刻度校准的组合级效果回测（只读分析，不写数据文件）。

口径（论文 5.4.x 专用，与 derive_position 的 CYCLE_ADJ 常数一字不差）：
- 刻度组合：pos(d) = clamp(50 + CYCLE_ADJ[phase(d-1)], 5, 95)
  —— 单变量隔离口径：其余维度（温度基准/方向/晋级率/事件）固定中性，
     只量化"周期刻度校准"这一个变量的历史贡献；方向维度历史回填必然前视，
     故不纳入（论文如实声明）。
- 基准组合：固定 50% 仓位。
- 收益代理：当日全市场中位涨幅 median_chg（与论文 49.1%/22.8pp 回测同源同段
  2009-11-02 起，median_chg <2009-11-02 稀疏段如实剔除）。
- 防前视：d 日仓位由 d-1 日周期判定决定（locate_cycle 生产同口径纯函数）。
- 诚实边界：模拟组合非实盘、无交易成本、中位数代理≠可投资指数。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from modules.shepherd_forecast import locate_cycle

CSV = ROOT / "data" / "shepherd_history.csv"
OUT_DIR = ROOT / "thesis" / "素材" / "论文扩展_分析产物"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CYCLE_ADJ = {"主升高潮": 5, "修复确认": 3, "修复试探": 0,
             "高潮分化": -5, "退潮": -10, "冰点": 5}
# locate_cycle 返回英文 id，映射到 CYCLE_ADJ 的中文键（与 thesis_ext_analysis GROUPS 同构）
CNAME = {"main": "主升高潮", "confirm": "修复确认", "probe": "修复试探",
         "diverge": "高潮分化", "retreat": "退潮", "ice": "冰点"}
CLAMP_LO, CLAMP_HI = 5, 95
ANNUAL_DAYS = 244  # A 股年交易日近似，口径在论文中声明


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df = df[df["median_chg"].notna()].reset_index(drop=True)
    # 复用生产 locate_cycle：逐日判定（与 thesis_ext_analysis / 论文 5.4 同口径）
    rows = df.to_dict("records")
    df["phase"] = [CNAME[locate_cycle(r, rows[i - 1] if i else None)["id"]]
                   for i, r in enumerate(rows)]
    return df


def equity(pos: pd.Series, ret: pd.Series) -> pd.Series:
    daily = pos / 100.0 * ret / 100.0
    return (1.0 + daily).cumprod(), daily


def stats(nav: pd.Series, daily: pd.Series) -> dict:
    years = len(daily) / ANNUAL_DAYS
    total = float(nav.iloc[-1] - 1.0)
    ann = float(nav.iloc[-1] ** (1.0 / years) - 1.0)
    dd = float((nav / nav.cummax() - 1.0).min())
    vol = float(daily.std(ddof=0) * math.sqrt(ANNUAL_DAYS))
    sharpe = float(daily.mean() / daily.std(ddof=0) * math.sqrt(ANNUAL_DAYS)) if daily.std(ddof=0) > 0 else 0.0
    return {"total_ret": round(total * 100, 1), "ann_ret": round(ann * 100, 2),
            "max_dd": round(dd * 100, 1), "ann_vol": round(vol * 100, 1),
            "sharpe": round(sharpe, 3)}


def main() -> None:
    df = load()
    ret = df["median_chg"]
    # 防前视：d 日仓位 = f(d-1 日周期)
    adj_d1 = df["phase"].shift(1).map(CYCLE_ADJ).fillna(0.0)
    pos_scale = (50.0 + adj_d1).clip(CLAMP_LO, CLAMP_HI)
    pos_base = pd.Series(50.0, index=df.index)

    nav_s, daily_s = equity(pos_scale, ret)
    nav_b, daily_b = equity(pos_base, ret)
    s_s, s_b = stats(nav_s, daily_s), stats(nav_b, daily_b)

    # 分周期：贡献按"驱动仓位差的周期"（前一日周期）归组，而非当日周期
    spread = ((pos_scale - pos_base) / 100.0 * ret / 100.0)
    drv_phase = df["phase"].shift(1)
    grp = pd.DataFrame({"spread": spread, "drv": drv_phase}).dropna()
    by_phase = grp.groupby("drv")["spread"].agg(["sum", "count"])
    by_phase_out = {k: {"contrib_pct": round(float(v["sum"]) * 100, 2),
                        "days": int(v["count"])}
                    for k, v in by_phase.iterrows()}

    out = {
        "meta": {
            "start": str(df["date"].iloc[0]), "end": str(df["date"].iloc[-1]),
            "days": int(len(df)), "annual_days": ANNUAL_DAYS,
            "scale_rule": "pos(d)=clamp(50+CYCLE_ADJ[phase(d-1)],5,95)",
            "benchmark": "fixed 50%",
            "proxy": "median_chg (same source as 49.1%/22.8pp backtests)",
            "caveats": [
                "模拟组合非实盘，无交易成本与滑点",
                "全市场中位涨幅为收益代理，不等于可投资指数",
                "单变量隔离口径：仅启用周期刻度调节，温度/方向/晋级率/事件固定中性",
                "周期判定 locate_cycle 与生产同口径；其派生指标依赖见 5.4 caveat",
            ],
        },
        "scale": s_s, "benchmark": s_b,
        "delta": {k: round(s_s[k] - s_b[k], 2) for k in s_s},
        "contrib_by_phase_pct": by_phase_out,
    }
    out_path = OUT_DIR / "scale_backtest_combo.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("days", len(df), out["meta"]["start"], "->", out["meta"]["end"])
    print("scale    :", s_s)
    print("benchmark:", s_b)
    print("delta    :", out["delta"])
    print("by_phase :", by_phase_out)
    print("saved ->", out_path)


if __name__ == "__main__":
    main()
