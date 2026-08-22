"""
生成《牧羊人指标》独立 HTML 报告（结构化指标表 + 真实历史折线图）。

读取 data/shepherd_history.csv（由 modules.shepherd __main__ 回测得到），
输出 docs/shepherd_indicators_report.html。
"""
import os
import sys
import json

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
    "limit_up": "当日收盘封死涨停的个股数（东财涨停池）。>50 亢奋，<20 低迷。",
    "limit_down": "当日收盘跌停的个股数（全A快照反算，涨跌幅≤-9.5%）。>15 风险，>30 恐慌。",
    "zt_prev_ret": "昨日涨停个股今日平均涨跌幅(%)。>3% 赚钱效应炸裂，<0% 昨日打板今日吃面。",
    "red_ratio": "上涨家数/(上涨+下跌)×100%。>60% 普涨红盘，<45% 普跌。",
    "connect_hl": "当日市场最高连板数（涨停池 max 连板数）。≥6板 高风险偏好，<3板 冰点。",
    "zt_fail_ratio": "涨停池中「炸板次数>0」占比(%)——封板不稳代理。>50% 多空分歧大。",
}

ORDER = ["up_count", "down_count", "limit_up", "limit_down",
         "zt_prev_ret", "red_ratio", "connect_hl", "zt_fail_ratio"]


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


def build_fig(df):
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=("涨跌 / 涨停 / 跌停家数", "昨日涨停表现(%) / 红盘占比(%)"),
        row_heights=[1, 1],
    )
    fam = dict(up_count=("#ee2a2a", "上涨家数"), down_count=("#3b82f6", "下跌家数"),
               limit_up=("#f59e0b", "涨停家数"), limit_down=("#16c2c2", "跌停家数"))
    for k, (col, name) in fam.items():
        if k in d.columns:
            s = pd.to_numeric(d[k], errors="coerce").dropna()
            if s.empty:
                continue
            is_pt = len(s) < 2
            tr = dict(x=d["date"], y=s.values, name=name + ("" if not is_pt else " (今)"),
                      mode="markers" if is_pt else "lines",
                      line=dict(width=1.8, color=col),
                      hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.0f}}<extra></extra>")
            if is_pt:
                tr["marker"] = dict(size=11, symbol="diamond", color=col)
            fig.add_trace(go.Scatter(**tr), row=1, col=1)
    pct = dict(zt_prev_ret=("#7c5cff", "昨日涨停表现%"), red_ratio=("#ee2a2a", "红盘占比%"))
    for k, (col, name) in pct.items():
        if k in d.columns:
            s = pd.to_numeric(d[k], errors="coerce").dropna()
            if s.empty:
                continue
            is_pt = len(s) < 2
            tr = dict(x=d["date"], y=s.values, name=name + ("" if not is_pt else " (今)"),
                      mode="markers" if is_pt else "lines",
                      line=dict(width=1.8, color=col),
                      hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}：%{{y:.2f}}%<extra></extra>")
            if is_pt:
                tr["marker"] = dict(size=11, symbol="diamond", color=col)
            fig.add_trace(go.Scatter(**tr), row=2, col=1)
    if "limit_up" in d.columns:
        fig.add_hline(y=50, line_dash="dot", line_color="#9aa", row=1, col=1,
                      annotation_text="涨停50(亢奋)", annotation_font_size=9)
    if "zt_prev_ret" in d.columns:
        fig.add_hline(y=0, line_dash="dot", line_color="#9aa", row=2, col=1)
        fig.add_hline(y=3, line_dash="dot", line_color="#9aa", row=2, col=1,
                      annotation_text="昨板3%(炸裂)", annotation_font_size=9)
    fig.update_layout(
        height=560, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0.5, xanchor="center", font=dict(size=11)),
        margin=dict(l=55, r=25, t=50, b=40), hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6e6e6"),
        xaxis=dict(gridcolor="#2a2a3a"), yaxis=dict(gridcolor="#2a2a3a"),
    )
    fig.update_xaxes(tickangle=-30)
    return fig


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
        print("ERROR: 未找到回测数据", CSV, "——请先运行 `python -m modules.shepherd`")
        return 1
    df = pd.read_csv(CSV)
    fig = build_fig(df)
    fig_json = fig.to_json()
    table = build_table()
    snap = latest_snapshot(df)
    n = len(df)
    rng = ""
    if n:
        rng = f"{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>牧羊人指标 · 情绪温度计</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
  body{{margin:0;background:#0f0f23;color:#e6e6e6;font-family:-apple-system,'Segoe UI',Roboto,'Microsoft YaHei',sans-serif;}}
  .wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 60px;}}
  .hero{{background:linear-gradient(135deg,#667eea,#764ba2);border-radius:16px;padding:26px 28px;margin-bottom:22px;}}
  .hero h1{{margin:0 0 6px;font-size:26px;}}
  .hero p{{margin:4px 0;opacity:.95;font-size:14px;}}
  .note{{background:#1a1a2e;border:1px solid #2c2c4a;border-radius:10px;padding:12px 16px;font-size:13px;color:#b9b9d6;margin-bottom:22px;}}
  h2{{font-size:19px;margin:26px 0 12px;border-left:4px solid #764ba2;padding-left:10px;}}
  table{{width:100%;border-collapse:collapse;font-size:13px;background:#1a1a2e;border-radius:10px;overflow:hidden;}}
  th,td{{padding:10px 12px;border-bottom:1px solid #2c2c4a;text-align:left;vertical-align:top;}}
  th{{background:#232342;color:#c9c9ee;font-weight:600;}}
  td.desc{{color:#c2c2da;}}
  .k{{color:#8a8ab0;font-size:11px;font-family:monospace;}}
  .hot{{color:#ff8a8a;}} .warm{{color:#ffd28a;}} .cold{{color:#8ab6ff;}}
  .tag{{background:#764ba233;color:#b9a6ff;padding:2px 8px;border-radius:8px;font-size:11px;}}
  #chart{{background:#1a1a2e;border-radius:12px;padding:10px;margin-top:8px;}}
  .snaps{{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;}}
  .snap{{background:#1a1a2e;border:1px solid #2c2c4a;border-radius:10px;padding:10px 14px;min-width:120px;}}
  .snap-k{{display:block;font-size:12px;color:#b9b9d6;}}
  .snap-v{{display:block;font-size:20px;font-weight:700;margin-top:2px;}}
  .footer{{margin-top:30px;font-size:12px;color:#7a7a9a;text-align:center;}}
</style></head>
<body><div class="wrap">
  <div class="hero">
    <h1>🐑 牧羊人指标 · 情绪温度计</h1>
    <p>源自抖音博主「股海牧羊人」《炒股绕不开的第一步》——不盯指数红绿，先看大盘脸色。</p>
    <p>涨跌家数 · 涨停跌停家数 · 昨日涨停表现，三招判断市场冷热。</p>
  </div>
  <div class="note">
    ⚠️ <b>数据来源说明</b>：抖音视频直链需 App 内打开，无法直接抓取。本指标集合基于该视频的
    「情绪温度计」方法论，并与多篇同源「情绪温度计/大盘脸色」教程交叉验证后凝结。
    折线图使用 <b>akshare 真实历史数据</b>（涨停池 / 昨日涨停池 / 全A快照按交易日回测，共 {n} 个交易日，{rng}）。
  </div>

  <h2>一、牧羊人指标表（8 项）</h2>
  <table>
    <thead><tr><th>指标</th><th>含义 / 算法</th><th>高温阈值</th><th>常温阈值</th><th>低温阈值</th><th>方向</th><th>归类</th></tr></thead>
    <tbody>{table}</tbody>
  </table>

  <h2>二、牧羊人指标折线图（真实历史）</h2>
  <div id="chart"></div>

  <h2>三、最新快照</h2>
  <div class="snaps">{snap}</div>

  <h2>四、操作口诀（情绪温度计）</h2>
  <p style="line-height:1.9;font-size:14px;color:#c2c2da;">
    涨超三千可出手，跌超三千先防守；涨停多家情绪高，跌停一片快逃跑；<br>
    昨板大涨可接力，昨板吃面别着急；高温重仓常温半，低温空仓最划算。
  </p>

  <div class="footer">StockSignal · 牧羊人指标 · 数据源 akshare（单源失败优雅降级，绝不编造曲线）</div>
</div>
<script>
  var fig = {fig_json};
  Plotly.newPlot('chart', fig.data, fig.layout, {{displayModeBar:false, responsive:true}});
</script>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK ->", OUT, f"({n} 交易日, {rng})")


if __name__ == "__main__":
    sys.exit(main())
