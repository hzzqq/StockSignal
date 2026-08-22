"""
生成《牧羊人指标》独立 HTML 报告（结构化指标表 + 2007 起真实历史折线图 + 年度汇总）。

读取 data/shepherd_history.csv（由 scripts/run_shepherd_reconstruct.py 重构得到，
2007-01-01 至今约 4700+ 交易日），输出 docs/shepherd_indicators_report.html。

历史数据说明：
- 涨跌家数 / 红盘占比：由新浪个股日线（前复权）按交易日聚合全 A 重构，2007 起连续；
- 涨停 / 跌停家数：长周期为「板块涨跌停幅度反算」近似（10%/20%/30%），仅近期
  约 12 个交易日为东财涨停池/跌停池真实数据；
- 连板高度 / 炸板率 / 昨日涨停表现：仅东财涨停池可得，近期真实、历史缺失（NaN）。
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules.shepherd import THRESHOLDS  # noqa: E402

CSV = os.path.join(ROOT, "data", "shepherd_history.csv")
OUT = os.path.join(ROOT, "docs", "shepherd_indicators_report.html")

IND_DESC = {
    "up_count": "全市场当日收盘上涨的个股数量。普涨>3000，普跌<1000。",
    "down_count": "全市场当日收盘下跌的个股数量。与上涨家数镜像，跌>3000 即防守信号。",
    "limit_up": "当日收盘封死涨停的个股数。>50 亢奋，<20 低迷。（2007起为板块规则近似，近期为东财真实涨停池）",
    "limit_down": "当日收盘跌停的个股数。>15 风险，>30 恐慌。（近似重构，近期为东财跌停池）",
    "zt_prev_ret": "昨日涨停个股今日平均涨跌幅(%)。>3% 赚钱效应炸裂，<0% 昨日打板今日吃面。（仅近期真实）",
    "red_ratio": "上涨家数/(上涨+下跌)×100%。>60% 普涨红盘，<45% 普跌。",
    "connect_hl": "当日市场最高连板数（涨停池 max 连板数）。≥6板 高风险偏好，<3板 冰点。（仅近期真实）",
    "zt_fail_ratio": "涨停池中「炸板次数>0」占比(%)——封板不稳代理。>50% 多空分歧大。（仅近期真实）",
}

ORDER = ["up_count", "down_count", "limit_up", "limit_down",
         "zt_prev_ret", "red_ratio", "connect_hl", "zt_fail_ratio"]

# 年度汇总里「长周期可靠」的核心列（涨停/连板/炸板/昨板历史为近似或缺失，不参与年度统计）
RELIABLE_YEAR = ["up_count", "down_count", "red_ratio", "limit_up", "limit_down"]


def build_table():
    rows = []
    for k in ORDER:
        th = THRESHOLDS[k]
        dir_txt = "越高越热 🔥" if th["dir"] > 0 else "越高越冷 🧊"
        if th["dir"] > 0:
            hot, warm, cold = f"≥{th['hot']}{th['unit']}", f"{th['warm']}~{th['hot']}{th['unit']}", f"<{th['warm']}{th['unit']}"
        else:
            hot, warm, cold = f"≤{th['hot']}{th['unit']}", f"{th['hot']}~{th['warm']}{th['unit']}", f">{th['warm']}{th['unit']}"
        rows.append(
            f"<tr><td><b>{th['name']}</b><br><span class='k'>{k}</span></td>"
            f"<td class='desc'>{IND_DESC[k]}</td>"
            f"<td class='hot'>{hot}</td><td class='warm'>{warm}</td><td class='cold'>{cold}</td>"
            f"<td>{dir_txt}</td><td><span class='tag'>牧羊人指标</span></td></tr>"
        )
    return "\n".join(rows)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def build_fig(df):
    """每日序列折线图（两行：家数 / 百分比）。"""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=("上涨 / 下跌 / 涨停 / 跌停家数（2007 起）", "红盘占比(%) / 昨日涨停表现(%)"),
        row_heights=[1, 1],
    )
    fam = dict(up_count=("#ee2a2a", "上涨家数"), down_count=("#3b82f6", "下跌家数"),
               limit_up=("#f59e0b", "涨停家数"), limit_down=("#16c2c2", "跌停家数"))
    for k, (col, name) in fam.items():
        if k in d.columns:
            s = _num(d[k]).dropna()
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=d["date"], y=s.values, name=name, mode="lines",
                line=dict(width=1.2, color=col),
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.0f}}<extra></extra>",
            ), row=1, col=1)
    pct = dict(red_ratio=("#ee2a2a", "红盘占比%"), zt_prev_ret=("#7c5cff", "昨日涨停表现%"))
    for k, (col, name) in pct.items():
        if k in d.columns:
            s = _num(d[k]).dropna()
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=d["date"], y=s.values, name=name, mode="lines",
                line=dict(width=1.2, color=col),
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.2f}}%<extra></extra>",
            ), row=2, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="#9aa", row=1, col=1,
                  annotation_text="涨停50(亢奋)", annotation_font_size=9)
    fig.add_hline(y=0, line_dash="dot", line_color="#9aa", row=2, col=1)
    fig.add_hline(y=3, line_dash="dot", line_color="#9aa", row=2, col=1,
                  annotation_text="昨板3%(炸裂)", annotation_font_size=9)
    fig.update_layout(
        height=600, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0.5, xanchor="center", font=dict(size=11)),
        margin=dict(l=55, r=25, t=50, b=40), hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6e6e6"),
        xaxis=dict(gridcolor="#2a2a3a", rangeslider_visible=True),
        yaxis=dict(gridcolor="#2a2a3a"),
    )
    fig.update_xaxes(tickangle=-30)
    return fig


def yearly_stats(df):
    """按年聚合：交易日数、日均上涨/下跌、年均红盘占比、最大涨停/跌停、恐慌/亢奋日数。"""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"])
    for c in RELIABLE_YEAR:
        if c in d.columns:
            d[c] = _num(d[c])
    d["year"] = d["date"].dt.year
    out = []
    for year, g in d.groupby("year"):
        rec = {"year": int(year), "days": int(len(g))}
        rec["avg_up"] = float(g["up_count"].mean()) if "up_count" in g else np.nan
        rec["avg_down"] = float(g["down_count"].mean()) if "down_count" in g else np.nan
        rec["avg_red"] = float(g["red_ratio"].mean()) if "red_ratio" in g else np.nan
        rec["max_up"] = float(g["up_count"].max()) if "up_count" in g else np.nan
        rec["min_up"] = float(g["up_count"].min()) if "up_count" in g else np.nan
        if "limit_up" in g and g["limit_up"].notna().any():
            rec["max_lu"] = float(g["limit_up"].max())
            rec["euphoria_days"] = int((g["limit_up"] >= 80).sum())
        else:
            rec["max_lu"], rec["euphoria_days"] = np.nan, 0
        if "limit_down" in g and g["limit_down"].notna().any():
            rec["max_ld"] = float(g["limit_down"].max())
            rec["panic_days"] = int((g["limit_down"] > 30).sum())
        else:
            rec["max_ld"], rec["panic_days"] = np.nan, 0
        out.append(rec)
    return pd.DataFrame(out)


def build_year_fig(yearly):
    """年度汇总图：日均上涨家数(柱) + 年均红盘占比(线, 右轴)。"""
    y = yearly.copy()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=y["year"], y=y["avg_up"], name="日均上涨家数",
        marker_color="#ee2a2a", opacity=0.75,
        hovertemplate="%{x}年<br>日均上涨：%{y:.0f} 家<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=y["year"], y=y["avg_red"], name="年均红盘占比%", mode="lines+markers",
        line=dict(color="#7c5cff", width=2.2), marker=dict(size=5),
        hovertemplate="%{x}年<br>年均红盘占比：%{y:.1f}%<extra></extra>",
    ), secondary_y=True)
    fig.add_hline(y=50, line_dash="dot", line_color="#9aa", secondary_y=True,
                  annotation_text="红盘50%", annotation_font_size=9)
    fig.update_layout(
        height=380, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0.5, xanchor="center", font=dict(size=11)),
        margin=dict(l=55, r=25, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6e6e6"),
        xaxis=dict(gridcolor="#2a2a3a", dtick=1), yaxis=dict(gridcolor="#2a2a3a"),
        yaxis2=dict(gridcolor="#2a2a3a"),
    )
    return fig


def build_year_table(yearly):
    rows = []
    for _, r in yearly.iterrows():
        panic = f"<span class='panic'>{int(r['panic_days'])}</span>" if r["panic_days"] else "0"
        euph = f"<span class='hot'>{int(r['euphoria_days'])}</span>" if r["euphoria_days"] else "0"
        rows.append(
            f"<tr><td><b>{int(r['year'])}</b></td><td>{int(r['days'])}</td>"
            f"<td>{r['avg_up']:.0f}</td><td>{r['avg_down']:.0f}</td><td>{r['avg_red']:.1f}%</td>"
            f"<td>{r['min_up']:.0f}</td><td>{r['max_up']:.0f}</td>"
            f"<td>{r['max_lu']:.0f}</td><td>{r['max_ld']:.0f}</td>"
            f"<td>{euph}</td><td>{panic}</td></tr>"
        )
    return "\n".join(rows)


def latest_snapshot(df):
    if df is None or df.empty:
        return "<p>暂无最新快照（网络受限）。</p>"
    row = df.iloc[-1]
    cells = []
    for k in ORDER:
        if k in df.columns and pd.notna(row[k]):
            v = row[k]
            th = THRESHOLDS[k]
            if th["unit"] == "%":
                val = f"{v:.2f}%"
            elif th["unit"] == "板":
                val = f"{v:.0f}板"
            else:
                val = f"{v:,.0f}"
            cells.append(f"<div class='snap'><span class='snap-k'>{th['name']}</span>"
                         f"<span class='snap-v'>{val}</span></div>")
    return "\n".join(cells)


def main():
    if not os.path.exists(CSV):
        print("ERROR: 未找到回测数据", CSV, "——请先运行 `python -m scripts.run_shepherd_reconstruct`")
        return 1
    df = pd.read_csv(CSV)
    if df.empty:
        print("ERROR: 回测数据为空")
        return 1
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    fig = build_fig(df)
    yearly = yearly_stats(df)
    year_fig = build_year_fig(yearly)
    fig_json = fig.to_json()
    year_json = year_fig.to_json()
    table = build_table()
    snap = latest_snapshot(df)
    year_table = build_year_table(yearly)
    n = len(df)
    rng = f"{df['date'].iloc[0]:%Y-%m-%d} ~ {df['date'].iloc[-1]:%Y-%m-%d}"
    ny = len(yearly)
    # 数据覆盖统计
    cover = {}
    for c in ORDER:
        if c in df.columns:
            cover[c] = int(df[c].notna().sum())
        else:
            cover[c] = 0
    cover_txt = " · ".join(f"{THRESHOLDS[c]['name']}<b>{cover[c]}</b>天" for c in ORDER)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>牧羊人指标 · 情绪温度计（2007 起）</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
  body{{margin:0;background:#0f0f23;color:#e6e6e6;font-family:-apple-system,'Segoe UI',Roboto,'Microsoft YaHei',sans-serif;}}
  .wrap{{max-width:1120px;margin:0 auto;padding:28px 20px 60px;}}
  .hero{{background:linear-gradient(135deg,#667eea,#764ba2);border-radius:16px;padding:26px 28px;margin-bottom:22px;}}
  .hero h1{{margin:0 0 6px;font-size:26px;}}
  .hero p{{margin:4px 0;opacity:.95;font-size:14px;}}
  .note{{background:#1a1a2e;border:1px solid #2c2c4a;border-radius:10px;padding:12px 16px;font-size:13px;color:#b9b9d6;margin-bottom:22px;}}
  h2{{font-size:19px;margin:26px 0 12px;border-left:4px solid #764ba2;padding-left:10px;}}
  table{{width:100%;border-collapse:collapse;font-size:13px;background:#1a1a2e;border-radius:10px;overflow:hidden;}}
  th,td{{padding:9px 11px;border-bottom:1px solid #2c2c4a;text-align:left;vertical-align:top;}}
  th{{background:#232342;color:#c9c9ee;font-weight:600;}}
  td.desc{{color:#c2c2da;}}
  .k{{color:#8a8ab0;font-size:11px;font-family:monospace;}}
  .hot{{color:#ff8a8a;}} .warm{{color:#ffd28a;}} .cold{{color:#8ab6ff;}} .panic{{color:#ff6b6b;font-weight:700;}}
  .tag{{background:#764ba233;color:#b9a6ff;padding:2px 8px;border-radius:8px;font-size:11px;}}
  #chart,#chart2{{background:#1a1a2e;border-radius:12px;padding:10px;margin-top:8px;}}
  .snaps{{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;}}
  .snap{{background:#1a1a2e;border:1px solid #2c2c4a;border-radius:10px;padding:10px 14px;min-width:120px;}}
  .snap-k{{display:block;font-size:12px;color:#b9b9d6;}}
  .snap-v{{display:block;font-size:20px;font-weight:700;margin-top:2px;}}
  .cover{{font-size:12px;color:#9a9ac0;margin-top:6px;}}
  .footer{{margin-top:30px;font-size:12px;color:#7a7a9a;text-align:center;}}
</style></head>
<body><div class="wrap">
  <div class="hero">
    <h1>🐑 牧羊人指标 · 情绪温度计</h1>
    <p>源自抖音博主「股海牧羊人」《炒股绕不开的第一步》——不盯指数红绿，先看大盘脸色。</p>
    <p>涨跌家数 · 涨停跌停家数 · 昨日涨停表现，三招判断市场冷热。历史回溯至 2007 年。</p>
  </div>
  <div class="note">
    ⚠️ <b>数据来源与口径</b>：共 <b>{n}</b> 个交易日（{rng}）。涨跌家数 / 红盘占比由新浪个股日线
    聚合全 A 重构（存在幸存者偏差，仅含当前上市股票）；涨停/跌停家数长周期为板块涨跌停幅度
    （10%/20%/30%）反算近似，<b>近期约 12 个交易日为东财涨停池/跌停池真实数据</b>；连板高度、
    炸板率、昨日涨停表现仅近期真实可得。指标数据覆盖：{cover_txt}。
  </div>

  <h2>一、牧羊人指标表（8 项）</h2>
  <table>
    <thead><tr><th>指标</th><th>含义 / 算法</th><th>高温阈值</th><th>常温阈值</th><th>低温阈值</th><th>方向</th><th>归类</th></tr></thead>
    <tbody>{table}</tbody>
  </table>

  <h2>二、每日序列（真实历史，2007 起）</h2>
  <div id="chart"></div>

  <h2>三、年度汇总（{ny} 个年份）</h2>
  <div id="chart2"></div>
  <table style="margin-top:12px;">
    <thead><tr><th>年份</th><th>交易日</th><th>日均上涨</th><th>日均下跌</th><th>年均红盘%</th>
      <th>最差日上涨</th><th>最好日上涨</th><th>年度最多涨停</th><th>年度最多跌停</th><th>亢奋日(涨停≥80)</th><th>恐慌日(跌停>30)</th></tr></thead>
    <tbody>{year_table}</tbody>
  </table>

  <h2>四、最新快照</h2>
  <div class="snaps">{snap}</div>

  <h2>五、操作口诀（情绪温度计）</h2>
  <p style="line-height:1.9;font-size:14px;color:#c2c2da;">
    涨超三千可出手，跌超三千先防守；涨停多家情绪高，跌停一片快逃跑；<br>
    昨板大涨可接力，昨板吃面别着急；高温重仓常温半，低温空仓最划算。
  </p>

  <div class="footer">StockSignal · 牧羊人指标 · 数据源 akshare（长周期新浪日线重构 + 近期东财涨停池，绝不编造曲线）</div>
</div>
<script>
  var fig = {fig_json};
  Plotly.newPlot('chart', fig.data, fig.layout, {{displayModeBar:false, responsive:true}});
  var fig2 = {year_json};
  Plotly.newPlot('chart2', fig2.data, fig2.layout, {{displayModeBar:false, responsive:true}});
</script>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK ->", OUT, f"({n} 交易日, {rng}, {ny} 年)")


if __name__ == "__main__":
    sys.exit(main())
