"""
scripts/simulate_virtual_users.py
---------------------------------
万级虚拟用户蒙特卡洛模拟（T-233）：验证荐股方案（策略+参数+入场时点）在真实历史行情上的
回报分布 / 回撤 / 胜率 / 正收益占比，为商业可行性提供分布级证据。

诚实框架（写进 meta，不删）：
- 这是蒙特卡洛回测模拟，非实盘；
- 股票池基于现存上市代码 → 存在幸存者偏差，已披露；
- 方向预测≈随机是 4092 日回测已证结论（论文 6.6），本模拟验证的是
  「筛选+风控参数+成本」在分布上的表现，不承诺高成功率；
- 所有用户共享真实日线（BaoStock/东财，data/cache.db 缓存），成本模型全开。

实现（最省算力）：
  每 (ticker, strategy) 只预计算一次 df+signals（清洗/指标/信号与用户参数无关），
  1 万用户仅循环 Backtester._simulate（纯参数模拟，逐行 Python），
  切片 = 随机入场日 + 180 交易日窗口 → 分钟级完成，无需进程池。

用法：
  python scripts/simulate_virtual_users.py            # 默认 10000 用户
  python scripts/simulate_virtual_users.py --users 2000   # 快速冒烟
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime

import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

REPORT_PATH = os.path.join(_PROJECT_ROOT, "reports", "virtual_users_sim.json")
CHART_PATH = os.path.join(_PROJECT_ROOT, "reports", "virtual_users_dist.png")

STRATEGIES = ("multi_factor", "dual_trend")
UNIVERSE_SIZE = 300
WINDOW = 180          # 每个虚拟用户的持有考察窗口（交易日）
START, END = "2024-01-01", "2026-09-30"

STOP_GRID = (0.03, 0.05, 0.08)
TP_GRID = (0.03, 0.05, 0.10)
HOLD_GRID = (10, 15, 30)


def _pct(arr, q):
    return round(float(np.percentile(arr, q)), 2) if len(arr) else None


def main(n_users: int = 10000, universe_size: int = UNIVERSE_SIZE, seed: int = 20261011) -> int:
    t0 = time.time()
    rng = random.Random(seed)
    np.random.seed(seed)

    from modules.backtest import Backtester, BacktestResult
    from modules.cleaner import DataCleaner
    from modules.fetch_parallel import fetch_many
    from modules.fetcher import StockFetcher
    from modules.strategies.registry import get_strategy

    fetcher = StockFetcher()
    bt = Backtester()
    codes = fetcher.get_all_codes(limit=universe_size)
    codes = [c for c in codes if c] if codes else []
    if len(codes) < 20:
        print(f"[sim] 股票池过小（{len(codes)}），中止（诚实失败，不编造）")
        return 1
    print(f"[sim] 股票池 {len(codes)} 只 · 用户 {n_users} · 窗口 {WINDOW} 交易日 · 成本模型全开")

    # ── 阶段 1：每 (ticker, strategy) 预计算 df+signals 一次 ──
    def _precompute(code):
        try:
            raw = fetcher.get_daily(code, start=START, end=END)
            if raw is None or len(raw) < WINDOW + 60:
                return None
            df = bt._add_indicators(DataCleaner.full_pipeline(raw.copy()))
            out = {}
            for strat in STRATEGIES:
                cls = get_strategy(strat)
                inst = cls()
                if getattr(cls, "needs_context", False):
                    continue  # event_driven 需上下文，蒙特卡洛不含（如实排除）
                sig = inst.generate_signals(df.copy())
                out[strat] = (df, sig)
            return code, out
        except Exception:  # noqa: BLE001 — 单标的失败不拖垮（如实计数）
            return None

    tasks = [(f"pc_{c}", lambda c=c: _precompute(c)) for c in codes]
    got = fetch_many(tasks, max_workers=8, timeout=600)
    pool = {}
    skipped = 0
    for c in codes:
        r = got.get(f"pc_{c}")
        if r:
            pool[c] = r[1]
        else:
            skipped += 1
    pool = {c: v for c, v in pool.items() if v}
    print(f"[sim] 预计算完成：{len(pool)}/{len(codes)} 有效（跳过 {skipped}），耗时 {time.time()-t0:.0f}s")
    if not pool:
        print("[sim] 无可用预计算数据，中止")
        return 1

    # ── 阶段 2：虚拟用户循环（纯 _simulate，无网络）──
    codes_list = list(pool.keys())
    returns, maxdds, winrates = [], [], []
    per_profile = {}   # (strategy, stop, tp, hold) -> [returns]
    for i in range(n_users):
        code = rng.choice(codes_list)
        strat = rng.choice(STRATEGIES)
        df, sig = pool[code][strat]
        n = len(df)
        if n <= WINDOW + 5:
            continue
        e0 = rng.randint(0, n - WINDOW - 1)
        e1 = e0 + WINDOW
        df_w = df.iloc[e0:e1].reset_index(drop=True)
        sig_w = list(sig[e0:e1]) + [0] * (WINDOW - len(sig[e0:e1]))
        params = dict(
            stop_loss_pct=rng.choice(STOP_GRID),
            take_profit_pct=rng.choice(TP_GRID),
            max_holding=rng.choice(HOLD_GRID),
            min_holding=2,
        )
        try:
            res_df, trades = bt._simulate(df_w, sig_w, initial_capital=100000, **params)
            br = BacktestResult(code, strat, res_df, 100000, trades)
            ret = float(br.total_return_pct)
            dd = float(br.max_drawdown_pct)
            wr = float(br.win_rate_pct) if trades else 0.0
        except Exception:  # noqa: BLE001
            continue
        returns.append(ret)
        maxdds.append(dd)
        winrates.append(wr)
        key = (strat, params["stop_loss_pct"], params["take_profit_pct"], params["max_holding"])
        per_profile.setdefault(key, []).append(ret)
        if (i + 1) % 2000 == 0:
            print(f"[sim] {i+1}/{n_users} 用户完成 · {time.time()-t0:.0f}s")

    if len(returns) < 100:
        print(f"[sim] 有效样本过少（{len(returns)}），中止（诚实失败）")
        return 1

    returns_a = np.array(returns)
    aggregate = {
        "n_effective": len(returns),
        "return_mean_pct": round(float(returns_a.mean()), 2),
        "return_median_pct": _pct(returns_a, 50),
        "return_p5_pct": _pct(returns_a, 5),
        "return_p25_pct": _pct(returns_a, 25),
        "return_p75_pct": _pct(returns_a, 75),
        "return_p95_pct": _pct(returns_a, 95),
        "pct_positive": round(float((returns_a > 0).mean() * 100), 2),
        "maxdd_avg_pct": round(float(np.mean(maxdds)), 2),
        "maxdd_worst_pct": _pct(np.array(maxdds), 5),
        "winrate_avg_pct": round(float(np.mean(winrates)), 2),
    }
    profiles = []
    for (strat, stop, tp, hold), rs in sorted(per_profile.items()):
        a = np.array(rs)
        if len(a) < 30:
            continue
        profiles.append({
            "strategy": strat, "stop_loss_pct": stop, "take_profit_pct": tp,
            "max_holding": hold, "n": len(a),
            "return_median_pct": _pct(a, 50), "return_p5_pct": _pct(a, 5),
            "pct_positive": round(float((a > 0).mean() * 100), 2),
        })
    profiles.sort(key=lambda p: -p["return_median_pct"])

    meta = {
        "n_users": n_users, "seed": seed, "universe_size": len(codes),
        "pool_valid": len(pool), "skipped_tickers": skipped,
        "start": START, "end": END, "window": WINDOW,
        "strategies": list(STRATEGIES), "cost_model": "commission 0.001 / slippage 0.001 / stamp_tax 0.001",
        "duration_s": round(time.time() - t0, 1),
        "honesty_note": (
            "蒙特卡洛回测模拟非实盘；股票池为现存上市代码存在幸存者偏差；"
            "方向预测≈随机（4092 日回测已证），本模拟验证筛选+风控+成本的分布表现，"
            "不承诺高成功率；结果不构成投资建议"),
    }
    report = {"meta": meta, "aggregate": aggregate, "profiles": profiles}
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # ── 分布直方图（plotly + kaleido，范式抄 gen_backtest_eval）──
    try:
        import plotly.graph_objects as go
        fig = go.Figure(go.Histogram(x=returns_a, nbinsx=80,
                                     marker_color="#2b8aef", opacity=0.85))
        fig.update_layout(
            title=f"虚拟用户回报分布（n={len(returns)}，含成本，{START}~{END}）",
            xaxis_title="总回报 %", yaxis_title="用户数", height=520, width=1200,
            template="plotly_white", margin=dict(l=60, r=30, t=60, b=50),
        )
        fig.write_image(CHART_PATH)
    except Exception as e:  # noqa: BLE001 — 图表失败不掩盖数据
        print(f"[sim] 直方图导出失败（JSON 不受影响）: {e}")

    print(json.dumps({"aggregate": aggregate,
                      "top3_profiles": profiles[:3]}, ensure_ascii=False, indent=1))
    print(f"[sim] 报告已写 {REPORT_PATH} · 总耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=10000)
    ap.add_argument("--universe", type=int, default=UNIVERSE_SIZE)
    ap.add_argument("--seed", type=int, default=20261011)
    args = ap.parse_args()
    sys.exit(main(n_users=args.users, universe_size=args.universe, seed=args.seed))
