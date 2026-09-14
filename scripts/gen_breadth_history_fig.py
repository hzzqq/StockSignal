"""生成「A 股全市场广度历史」图（红盘率 + 涨跌家数逐年走势）。

为什么需要这个脚本
──────────────────
论文第 6.6 节与项目作品集页都展示并声明「全市场广度历史（4094 交易日）」，
引用的却是 ``thesis/ch6_eval/fig_history_trend.png`` —— 而该文件实际由
``thesis/eval_ch6.py`` 写成「评估数据累积趋势（每次运行 +1）」，
与广度历史毫无关系（**文件名撞车导致的图注与图片不符**）。
仓库里此前**并不存在**任何生成广度历史图的脚本，本脚本补上这一缺口。

数据口径（全部由 CSV 实算，不写死任何数字）
────────────────────────────────────────
- 输入：``data/shepherd_history.csv``（列含 date / up_count / down_count / flat_count / red_ratio）
- 输出：``docs/assets/fig_breadth_history.png``
- 柱 = 年度平均红盘率(%)（主轴）；折线（副轴）= 年度日均上涨 / 下跌家数
- 交易日数、起止日期、覆盖年数均从数据推导，供调用方复用（见 ``breadth_stats()``）

用法
────
    python scripts/gen_breadth_history_fig.py
    python scripts/gen_breadth_history_fig.py --out docs/assets/fig_breadth_history.png
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "shepherd_history.csv")
OUT_DEFAULT = os.path.join(ROOT, "docs", "assets", "fig_breadth_history.png")

# 配色遵循 A 股约定：涨/红盘 = 红，跌 = 绿
C_RED_RATIO = "#ff4d4f"   # 红盘率（红）
C_UP = "#ff7875"          # 上涨家数（浅红）
C_DOWN = "#00d486"        # 下跌家数（绿）


def load_rows(csv_path: str = CSV_PATH) -> list[dict]:
    """读取广度 CSV；保持原样返回，不做任何填充/插值。"""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("date") or "").strip()]


def _fnum(v):
    """空串/None → None（缺失不补零），否则 float。"""
    s = str(v if v is not None else "").strip()
    if s in ("", "None", "nan", "NaN"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def breadth_stats(csv_path: str = CSV_PATH) -> dict:
    """从 CSV 推导广度基座的口径事实（供作品集页/测试复用，避免各处写死）。"""
    rows = load_rows(csv_path)
    if not rows:
        return {"days": 0, "first": "", "last": "", "first_year": "", "last_year": "",
                "years": 0, "years_label": "", "span_label": "",
                "annual": [], "rows": []}
    dates = sorted((r["date"] or "").strip() for r in rows if (r.get("date") or "").strip())
    first, last = dates[0], dates[-1]
    fy, ly = first[:4], last[:4]
    years = int(ly) - int(fy) + 1

    buckets: dict[str, dict] = defaultdict(lambda: {"red": [], "up": [], "down": []})
    for r in rows:
        y = (r.get("date") or "")[:4]
        if not y:
            continue
        rr = _fnum(r.get("red_ratio"))
        if rr is not None:
            buckets[y]["red"].append(rr)
        u, d = _fnum(r.get("up_count")), _fnum(r.get("down_count"))
        if u is not None:
            buckets[y]["up"].append(u)
        if d is not None:
            buckets[y]["down"].append(d)

    annual = []
    for y in sorted(buckets):
        b = buckets[y]
        if not b["red"]:
            continue
        annual.append({
            "year": y,
            "red_ratio": sum(b["red"]) / len(b["red"]),
            "up": (sum(b["up"]) / len(b["up"])) if b["up"] else None,
            "down": (sum(b["down"]) / len(b["down"])) if b["down"] else None,
            "days": len(b["red"]),
        })

    return {
        "days": len(rows),
        "first": first, "last": last,
        "first_year": fy, "last_year": ly,
        "years": years,
        "years_label": f"近 {years} 年" if years >= 3 else f"{years} 年",
        "span_label": f"{fy}–{ly}",
        "annual": annual,
        "rows": rows,
    }


def build_figure(stats: dict, dark: bool = False):
    """构造广度历史图；无有效数据返回 None（调用方跳过，不产出假图）。"""
    annual = stats.get("annual") or []
    if len(annual) < 2:
        return None
    import plotly.graph_objects as go

    xs = [a["year"] for a in annual]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=xs, y=[round(a["red_ratio"], 2) for a in annual],
        name="年度平均红盘率(%)", marker=dict(color=C_RED_RATIO, opacity=0.85),
        yaxis="y", hovertemplate="%{x}<br>红盘率 %{y:.2f}%<extra></extra>",
    ))
    up = [None if a["up"] is None else round(a["up"], 1) for a in annual]
    down = [None if a["down"] is None else round(a["down"], 1) for a in annual]
    if any(v is not None for v in up):
        fig.add_trace(go.Scatter(
            x=xs, y=up, mode="lines+markers", name="日均上涨家数",
            line=dict(color=C_UP, width=2), marker=dict(size=6), yaxis="y2",
            hovertemplate="%{x}<br>上涨 %{y:.1f} 家<extra></extra>",
        ))
    if any(v is not None for v in down):
        fig.add_trace(go.Scatter(
            x=xs, y=down, mode="lines+markers", name="日均下跌家数",
            line=dict(color=C_DOWN, width=2), marker=dict(size=6), yaxis="y2",
            hovertemplate="%{x}<br>下跌 %{y:.1f} 家<extra></extra>",
        ))
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        height=440, margin=dict(l=62, r=66, t=96, b=64),
        title=dict(
            text=f"A 股全市场广度历史（{stats['span_label']}，{stats['days']} 个交易日）",
            x=0.01, xanchor="left", y=0.975, yanchor="top",
        ),
        barmode="group",
        legend=dict(orientation="h", y=1.10, x=0, yanchor="bottom", xanchor="left"),
        yaxis=dict(title="年度平均红盘率(%)", range=[0, 100]),
        yaxis2=dict(title="日均家数", overlaying="y", side="right", showgrid=False),
        xaxis=dict(title="年份"),
    )
    return fig


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 A 股全市场广度历史图（真实 CSV）")
    ap.add_argument("--csv", default=CSV_PATH, help="广度历史 CSV（默认 data/shepherd_history.csv）")
    ap.add_argument("--out", default=OUT_DEFAULT, help="输出 PNG 路径")
    ap.add_argument("--dark", action="store_true", help="暗色主题")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(f"[skip] 广度 CSV 不存在：{args.csv}（gitignore，未随仓库分发）——不生成、不造假")
        return 0

    stats = breadth_stats(args.csv)
    print(f"[data] {stats['days']} 个交易日，{stats['first']} ~ {stats['last']}（{stats['years_label']}）")
    fig = build_figure(stats, dark=args.dark)
    if fig is None:
        print("[skip] 有效年度不足 2 个，跳过出图")
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fig.write_image(args.out, scale=2)
    print(f"[png] 已写出 {os.path.relpath(args.out, ROOT)}（{os.path.getsize(args.out)} B）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
