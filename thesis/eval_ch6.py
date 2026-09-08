"""
StockSignal 毕业论文 · 第6章 评估脚本（只读真实数据，不伪造）

读取：
  data/daily_snapshot.json        最新决策快照（首页直读）
  data/snapshots/*.json           每日归档（复盘/回测源）
  data/prediction_log.json        决策闭环「预测 vs 实际」落盘记录

产出（thesis/ch6_eval/）：
  metrics.json   真实指标（含样本量、clamp 校验、命中率）
  fig_*.html     论文用可交互图（同时尝试导出 png）
  report.md      可直接贴进论文第6章的「评估结果」草稿

说明：本脚本只统计真实跑出来的数据，样本不足时如实标注「样本量 n=… 不足以下结论」，
      绝不编造命中率。校准机制（calibration.py）在小样本下本就「只出建议不自动改规则」，
      这一设计在真实数据上得到验证。
"""
import json
import os
import glob
import sys
from datetime import datetime
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "thesis", "ch6_eval")
os.makedirs(OUT, exist_ok=True)

import plotly.graph_objects as go


def load_snapshots():
    snaps = {}
    latest_path = os.path.join(DATA, "daily_snapshot.json")
    if os.path.exists(latest_path):
        d = json.load(open(latest_path, encoding="utf-8"))
        snaps[d["date"]] = d
    for f in sorted(glob.glob(os.path.join(DATA, "snapshots", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        snaps[d["date"]] = d
    return [snaps[k] for k in sorted(snaps.keys())]


def main():
    snaps = load_snapshots()
    temps = [s.get("temperature") for s in snaps if s.get("temperature") is not None]
    # position 是 {pct, band, color, reasons} 结构；pct 为仓位数值，reasons 为可解释推导理由
    positions = [s["position"]["pct"] for s in snaps
                 if isinstance(s.get("position"), dict) and "pct" in s["position"]]
    reasons_samples = [s["position"].get("reasons") for s in snaps
                      if isinstance(s.get("position"), dict) and s["position"].get("reasons")]
    cycles = [s.get("cycle") for s in snaps if s.get("cycle") is not None]
    scenarios = [s.get("scenario") for s in snaps if s.get("scenario") is not None]

    # 仓位 clamp 校验：derive_position 必须落在 [5,95]
    clamp_ok = all(5 <= p <= 95 for p in positions) if positions else None

    pred_path = os.path.join(DATA, "prediction_log.json")
    preds = json.load(open(pred_path, encoding="utf-8")) if os.path.exists(pred_path) else []
    scored = [p for p in preds if p.get("hit") is not None]
    hit_rate = (sum(1 for p in scored if p.get("hit")) / len(scored)) if scored else None

    # 尝试用 decision_track 产出分周期/分组统计（若可导入）
    grouped = {}
    try:
        sys.path.insert(0, os.path.join(ROOT))
        from modules import decision_track as dt
        grouped["by_cycle"] = dt.by_cycle(min_samples=0)
        grouped["by_group"] = dt.by_group(min_samples=0)
        grouped["summary"] = dt.summary()
    except Exception as e:
        grouped["error"] = f"decision_track import skipped: {e}"

    metrics = {
        "snapshot_count": len(snaps),
        "snapshot_date_range": [snaps[0]["date"], snaps[-1]["date"]] if snaps else None,
        "temperature_min_max": [min(temps), max(temps)] if temps else None,
        "position_min_max": [min(positions), max(positions)] if positions else None,
        "position_clamp_5_95_ok": clamp_ok,
        "cycle_distribution": dict(Counter(cycles)),
        "scenario_samples": scenarios[:5],
        "explainability_samples": reasons_samples[:3],
        "prediction_count": len(preds),
        "prediction_scored": len(scored),
        "prediction_hit_rate": hit_rate,
        "note": "样本量小时如实标注，不推断统计显著性",
        "grouped_stats": grouped,
    }
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # ---- 累积历史（"持续累积"版：每次运行追加一条，毕业前攒出长周期趋势）----
    hist_path = os.path.join(OUT, "history.json")
    hist = json.load(open(hist_path, encoding="utf-8")) if os.path.exists(hist_path) else []
    run_rec = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot_count": len(snaps),
        "prediction_count": len(preds),
        "scored": len(scored),
        "hit_rate": hit_rate,
        "cycle_distribution": dict(Counter(cycles)),
        "by_group": [
            {"group": g["group"], "n_call": g["n_call"], "accuracy": g.get("accuracy")}
            for g in (grouped.get("by_group") or []) if isinstance(g, dict)
        ],
    }
    # 同一次运行（同 run_at 秒）去重，避免重复追加
    hist = [h for h in hist if h.get("run_at") != run_rec["run_at"]]
    hist.append(run_rec)
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    print(f"[history] 已追加本次运行记录，累计 {len(hist)} 条运行历史（见 {hist_path}）")

    # kaleido 是否在当前 python 可用（决定出 PNG 还是退回 HTML）
    try:
        import kaleido  # noqa: F401
        have_kaleido = True
    except Exception:
        have_kaleido = False

    def _emit(name, fig):
        """有 kaleido 出 PNG（论文用），无则退回 HTML，避免重复两份大文件。"""
        if fig is None:
            return
        if have_kaleido:
            try:
                fig.write_image(os.path.join(OUT, f"{name}.png"))
            except Exception as e:
                print(f"[png] {name} 导出失败: {e}")
        else:
            fig.write_html(os.path.join(OUT, f"{name}.html"))

    # ---- 图 1：每日仓位建议（验证 clamp 5~95）----
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=[s["date"] for s in snaps], y=positions, mode="lines+markers", name="仓位建议(%)"))
    fig1.add_hline(y=5, line_dash="dot", line_color="green", annotation_text="下限 5")
    fig1.add_hline(y=95, line_dash="dot", line_color="red", annotation_text="上限 95")
    fig1.update_layout(title="决策闭环：每日仓位建议（clamp 5~95 校验）",
                       xaxis_title="日期", yaxis_title="仓位 %")
    _emit("fig_position", fig1)

    # ---- 图 2：周期(cycle)分布 ----
    cc = Counter(cycles)
    fig2 = go.Figure(go.Bar(x=list(cc.keys()), y=list(cc.values())))
    fig2.update_layout(title="市场周期(cycle)分布", xaxis_title="周期", yaxis_title="覆盖天数")
    _emit("fig_cycle", fig2)

    # ---- 图 3：温度 vs 仓位（决策函数形态）----
    fig3 = go.Figure(go.Scatter(
        x=temps, y=positions, mode="markers", text=[s["date"] for s in snaps],
        textposition="top center", name="样本"))
    fig3.update_layout(title="温度(temp) vs 仓位(position)", xaxis_title="温度", yaxis_title="仓位 %")
    _emit("fig_temp_pos", fig3)

    # ---- 图 4：预测 vs 实际命中（已评分样本）----
    fig4 = None
    if scored:
        fig4 = go.Figure(go.Bar(
            x=[p["date"] for p in scored],
            y=[1 if p["hit"] else 0 for p in scored],
            text=[f"pct={p.get('pct')},real={p.get('realized')}" for p in scored],
        ))
        fig4.update_layout(title="预测 vs 实际命中（已评分样本，n=%d）" % len(scored),
                           xaxis_title="日期", yaxis_title="命中(1)/未中(0)")
    _emit("fig_hit", fig4)

    # ---- 图 5：预测 vs 实际「纵跨多日」趋势（命中率趋势图，毕业前随数据累积变实）----
    # 用 prediction_log 中已评分样本：预测仓位 pct vs 次日实际涨跌 realized，双线 + 命中散点
    fig5 = go.Figure()
    if scored:
        fig5.add_trace(go.Scatter(
            x=[p["date"] for p in scored], y=[p.get("pct") for p in scored],
            mode="lines+markers", name="预测仓位(%)", line=dict(color="#667eea")))
        fig5.add_trace(go.Scatter(
            x=[p["date"] for p in scored], y=[p.get("realized") for p in scored],
            mode="lines+markers", name="次日实际涨跌(%)", line=dict(color="#ee2a2a")))
        fig5.add_trace(go.Scatter(
            x=[p["date"] for p in scored],
            y=[10 if p.get("hit") else -10 for p in scored],
            mode="markers", name="命中/未中(±10)",
            marker=dict(size=12, color=["#00d486" if p.get("hit") else "#ee2a2a" for p in scored])))
    else:
        fig5.add_annotation(text="尚无已评分样本（每日自动化累积后自动填充）",
                            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig5.update_layout(title="预测 vs 实际趋势（纵跨多日，图 6-X）",
                       xaxis_title="日期", yaxis_title="%")
    _emit("fig_hit_trend", fig5)

    # ---- 图 6：评估运行累积趋势（history.json，验证「每日自动累积」机制本身）----
    fig6 = go.Figure()
    if len(hist) >= 1:
        xs = list(range(1, len(hist) + 1))
        fig6.add_trace(go.Scatter(x=xs, y=[h["snapshot_count"] for h in hist],
                                  mode="lines+markers", name="快照数"))
        fig6.add_trace(go.Scatter(x=xs, y=[h["scored"] for h in hist],
                                  mode="lines+markers", name="已评分预测数"))
    fig6.update_layout(title="评估数据累积趋势（每次运行 +1，图 6-Y）",
                       xaxis_title="运行序号", yaxis_title="数量")
    _emit("fig_history_trend", fig6)

    if have_kaleido:
        print(f"[png] 已导出 PNG 至 {OUT}（已跳过冗余 HTML）")
    else:
        print("[html] 未安装 kaleido，已退回 HTML 图表（装 kaleido 后可出 PNG）")

    # ---- report.md 草稿 ----
    lines = ["# 第6章 评估结果（草稿，来自真实运行数据）\n"]
    lines.append(f"- 决策快照样本量：{len(snaps)} 份（{metrics['snapshot_date_range']}）")
    lines.append(f"- 温度取值范围：{metrics['temperature_min_max']}")
    lines.append(f"- 仓位取值范围：{metrics['position_min_max']}，clamp[5,95] 校验：{'通过' if clamp_ok else '未通过'}")
    lines.append(f"- 周期分布：{metrics['cycle_distribution']}")
    lines.append(f"- 预测记录：共 {len(preds)} 条，已评分 {len(scored)} 条，命中率 {hit_rate}")
    lines.append("\n> 说明：当前为系统上线初期，样本量有限。第6章以「决策闭环功能正确性 + 校准机制设计正确性」为评估主线，")
    lines.append("> 纵向命中率统计作为趋势性证据呈现，**不**对小规模样本做显著性推断（与 calibration.py 小样本不表态的设计一致）。")
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(json.dumps({k: v for k, v in metrics.items() if k != "grouped_stats"},
                     ensure_ascii=False, indent=2))
    if "by_cycle" in grouped:
        print("\nby_cycle:", json.dumps(grouped["by_cycle"], ensure_ascii=False))
        print("by_group:", json.dumps(grouped["by_group"], ensure_ascii=False))


if __name__ == "__main__":
    main()
