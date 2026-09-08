"""
StockSignal 毕业论文 · 第6.4节 回测成本模型有效性验证脚本（只读真实数据，不伪造）

思路：同一标的、同一策略、同一区间跑两遍——
  A 组：含真实成本（佣金 0.001 + 滑点 0.001 + 印花税 0.001 仅卖出）
  B 组：全部成本置 0
比较两组净值曲线与总收益，用差额证明成本模型确实被扣除，而非形同虚设。

产出（thesis/ch6_eval/）：
  backtest_cost_metrics.json   两组指标 + 差额
  fig_backtest_equity.png      两条净值曲线对比图（论文用）

说明：需联网取真实日线；取数失败时脚本以非零码退出，论文中不填任何编造数字。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "thesis", "ch6_eval")
os.makedirs(OUT, exist_ok=True)

TICKER = "000001"
START = "2024-01-01"
END = "2026-09-06"
STRATEGY = "ma_cross"
CAPITAL = 100000


def main():
    from modules.backtest import Backtester  # 引擎类名为 Backtester

    runner = Backtester()

    print(f"[run] A 组 含成本  {TICKER} {START}~{END} strategy={STRATEGY}")
    a = runner.run(TICKER, START, END, strategy=STRATEGY, initial_capital=CAPITAL)
    print(f"[run] B 组 零成本  {TICKER} {START}~{END} strategy={STRATEGY}")
    b = runner.run(TICKER, START, END, strategy=STRATEGY, initial_capital=CAPITAL,
                   commission=0.0, slippage_pct=0.0, stamp_tax_pct=0.0)

    def metrics(res):
        # 注意：BacktestResult 的绩效指标均为 property，不是方法
        return {
            "total_return_pct": round(res.total_return, 4),
            "annualized_return_pct": round(res.annualized_return_pct, 4),
            "max_drawdown_pct": round(res.max_drawdown, 4),
            "win_rate_pct": round(res.win_rate, 4),
            "profit_factor": round(res.profit_factor, 4),
            "trade_count": res.trade_count,
        }

    mA, mB = metrics(a), metrics(b)
    out = {
        "ticker": TICKER, "strategy": STRATEGY, "start": START, "end": END,
        "initial_capital": CAPITAL,
        "with_cost": mA,
        "zero_cost": mB,
        "cost_drag_pct": round(mB["total_return_pct"] - mA["total_return_pct"], 4),
        "final_equity_with_cost": round(CAPITAL * (1 + mA["total_return_pct"] / 100), 2),
        "final_equity_zero_cost": round(CAPITAL * (1 + mB["total_return_pct"] / 100), 2),
    }
    with open(os.path.join(OUT, "backtest_cost_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # 净值曲线对比
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        xa = [str(d)[:10] for d in a.df["date"]]
        xb = [str(d)[:10] for d in b.df["date"]]
        fig.add_trace(go.Scatter(x=xa, y=list(a.df["total_asset"]),
                                 mode="lines", name="含交易成本"))
        fig.add_trace(go.Scatter(x=xb, y=list(b.df["total_asset"]),
                                 mode="lines", name="零成本（对照）"))
        fig.update_layout(
            title=f"回测净值曲线：成本模型开关对比（{TICKER} · {STRATEGY} · {START}~{END}）",
            xaxis_title="日期", yaxis_title="总资产（元）",
            legend=dict(x=0.02, y=0.98))
        fig.write_image(os.path.join(OUT, "fig_backtest_equity.png"))
        print("[png] fig_backtest_equity.png 已导出")
    except Exception as e:
        print(f"[png] 导出失败: {e}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
