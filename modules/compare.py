"""多股票横向对比引擎 + 前端

模仿 compare-analysis-20260710.html 的暗色 .sf-* 视觉风格（卡片 / 横向对比表 /
两两 VS 卡 / 综合评分雷达 / 分层操作建议）。

数据来源（全部程序化、可离线降级）：
  - modules.fetcher.StockFetcher.get_daily / get_stock_name
  - modules.cleaner.DataCleaner.full_pipeline
  - modules.technical.full_analysis  （趋势/动量/量能/形态 四维打分）
  - 价格相关性（横截 Pearson）作为「关联度」
  - 启发式「订单催化 / 弹性」代理指标
  - best-effort：akshare 个股信息（总市值 / 行业）与估值（TTM 市盈率）

配色严格遵循 A 股约定：涨/利好/买入=红(#ff4d4f)，跌/利空/卖出=绿(#00d486)，
中性/持有=琥珀(#ffa502)。这与本仓库 K 线及个股分析页一致。
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis

# ── 暗色 .sf-* 配色（A 股语义：红涨绿跌）──
UP = "#ff4d4f"      # 涨 / 强 / 买入
DOWN = "#00d486"    # 跌 / 弱 / 卖出
AMBER = "#ffa502"    # 中性 / 持有
ACC1 = "#667eea"
ACC2 = "#764ba2"
SF = {
    "bg": "#0f0f23", "card": "#1a1a2e", "border": "#2d2d44",
    "txt": "#e2e8f0", "txt2": "#94a3b8",
    "up": UP, "down": DOWN, "hold": AMBER, "acc1": ACC1, "acc2": ACC2,
}
# 每只股票一条折线/填充色（用于雷达图图例）
SERIES_COLORS = ["#ff4d4f", "#00d486", "#667eea", "#ffa502", "#764ba2",
                  "#36cfc9", "#ffc53d", "#9254de"]


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """把 #rrggbb / #rgb 转成 rgba(r,g,b,a)，供 Plotly fillcolor 使用。

    注：当前 Plotly 版本拒绝 8 位 hex（#rrggbbaa）作为 fillcolor，必须用 rgba。
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# =====================================================================
# 数据层
# =====================================================================
def fetch_compare(codes: List[str], period_days: int = 120) -> List[Dict[str, Any]]:
    """对每只股票拉取数据并计算所有对比维度，返回 list[dict]（一只一个）。"""
    fetcher = StockFetcher()
    rows: List[Dict[str, Any]] = []
    for code in codes:
        rows.append(_build_row(fetcher, str(code).strip().zfill(6), period_days))
    _fill_correlation(rows)
    return rows


def _build_row(fetcher: StockFetcher, code: str, period_days: int) -> Dict[str, Any]:
    name = ""
    try:
        name = fetcher.get_stock_name(code) or fetcher.get_stock_basic(code)[1] or code
    except Exception:
        name = code
    # 若 get_stock_name 返回空字符串，仍尝试 get_stock_basic
    if not name or not str(name).strip():
        try:
            name = fetcher.get_stock_basic(code)[1] or code
        except Exception:
            name = code
    row: Dict[str, Any] = {"code": code, "name": name if name and str(name).strip() else code}

    end = _dt.datetime.now().strftime("%Y-%m-%d")
    start = (_dt.datetime.now() - _dt.timedelta(days=period_days)).strftime("%Y-%m-%d")
    try:
        df = fetcher.get_daily(code, start=start, end=end)
        df = DataCleaner.full_pipeline(df)
        row["df"] = df
        row["asof"] = str(df.iloc[-1]["date"])[:10]
        last = df.iloc[-1]
        row["close"] = float(last["close"])
        row["chg_pct"] = float(last.get("return_1d", 0.0) or 0.0)

        ta = full_analysis(df)
        row["ta"] = ta
        trend = float(ta["trend"]["trend_score"])
        mom = float(ta["momentum"]["momentum_score"])
        vol = float(ta["volume"]["volume_price_score"])
        pat = _pattern_score(ta.get("patterns", []))
        composite = int(round(0.30 * trend + 0.25 * mom + 0.20 * vol + 0.25 * pat))
        row["scores"] = {"trend": trend, "momentum": mom, "volume": vol,
                         "pattern": pat, "composite": composite}
        # 弹性（年化波动率 %）
        rets = df["close"].pct_change().dropna()
        row["elasticity"] = float(rets.std() * np.sqrt(242) * 100) if len(rets) > 1 else 0.0
        row["signal"] = _signal_from(composite, ta)
        row["catalyst"] = _catalyst_score(ta)
        recent = df.tail(60)
        row["support"] = float(recent["low"].min())
        row["resistance"] = float(recent["high"].max())
    except Exception as e:  # 行情不可用 → 中性默认，不影响整体渲染
        row["error"] = str(e)
        row["df"] = None
        row["asof"] = end
        row["close"] = None
        row["chg_pct"] = 0.0
        row["scores"] = {"trend": 50, "momentum": 50, "volume": 50,
                         "pattern": 50, "composite": 50}
        row["elasticity"] = 0.0
        row["signal"] = "持有"
        row["catalyst"] = 50
        row["support"] = None
        row["resistance"] = None

    _fill_fundamentals(row)
    return row


def _pattern_score(patterns) -> float:
    """形态信号打分：看涨 +12 / 看跌 -12 / 中性 0，封顶 0-100。"""
    s = 50.0
    for p in (patterns or []):
        bias = str(p.get("bias", ""))
        if "看涨" in bias:
            s += 12
        elif "看跌" in bias:
            s -= 12
    return float(max(0, min(100, s)))


def _catalyst_score(ta) -> float:
    """订单/催化代理分（0-100）：动量 + 量能 + 形态突破。"""
    mom = float(ta["momentum"]["momentum_score"])
    vol = float(ta["volume"]["volume_price_score"])
    pat = _pattern_score(ta.get("patterns", []))
    s = 50 + (mom - 50) * 0.45 + (vol - 50) * 0.30 + (pat - 50) * 0.35
    return float(max(0, min(100, s)))


def _signal_from(composite: int, ta) -> str:
    mom_label = str(ta.get("momentum", {}).get("momentum_label", ""))
    strong = any(k in mom_label for k in ("上攻", "走强", "上涨"))
    if composite >= 68 and strong:
        return "买入"
    if composite >= 55:
        return "持有"
    return "卖出"


def _fill_correlation(rows: List[Dict[str, Any]]) -> None:
    """以横截收益率 Pearson 相关系数绝对值均值作为「关联度」。"""
    rets: Dict[str, pd.Series] = {}
    for r in rows:
        df = r.get("df")
        if df is not None and not df.empty and "close" in df:
            rets[r["code"]] = df["close"].pct_change().dropna().rename(r["code"])
    if len(rets) >= 2:
        m = pd.DataFrame(rets).dropna(how="any")
        if m.shape[0] >= 3:
            corr = m.corr().abs()
            for r in rows:
                c = r["code"]
                others = [o for o in corr.columns if o != c]
                r["correlation"] = float(corr.loc[c, others].mean() * 100) if others else 0.0
                return
    for r in rows:
        r["correlation"] = 0.0


def _fill_fundamentals(row: Dict[str, Any]) -> None:
    """best-effort 基本面（akshare）。失败则留空，由页面显示「—」。"""
    row["market_cap"] = None
    row["pe_ttm"] = None
    row["industry"] = None
    try:
        import akshare as ak  # 延迟导入，失败不影响其它维度
        info = ak.stock_individual_info_em(symbol=row['code'])
        d = dict(zip(info["item"], info["value"]))
        row["market_cap"] = d.get("总市值")
        row["industry"] = d.get("行业")
    except Exception:
        pass
    try:
        import akshare as ak
        ind = ak.stock_a_indicator_lg(symbol=row['code'])
        if ind is not None and not ind.empty:
            v = ind.iloc[-1].get("市盈率(TTM)")
            if v is not None and str(v) not in ("", "nan", "None"):
                row["pe_ttm"] = float(v)
    except Exception:
        pass


# =====================================================================
# 前端（暗色 .sf-* 风格）
# =====================================================================
def compare_css() -> str:
    """一次性注入对比页样式（与 compare-analysis-20260710.html 同构，A 股配色）。"""
    return f"""
<style>
.compare-wrap{{max-width:1200px;margin:0 auto;color:{SF['txt']};
  font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.55}}
.compare-wrap .header{{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:10px;margin-bottom:18px;padding:14px 18px;
  background:linear-gradient(90deg,#1a1a2e,#241b3a);border:1px solid {SF['border']};border-radius:14px}}
.compare-wrap .header .brand{{font-size:15px;color:{SF['txt2']};letter-spacing:1px}}
.compare-wrap .header .brand b{{color:{SF['acc1']}}}
.compare-wrap .card{{background:{SF['card']};border:1px solid {SF['border']};
  border-radius:14px;padding:18px;margin-top:16px}}
.compare-wrap .card h2{{font-size:16px;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
.compare-wrap .card h2::before{{content:"";width:4px;height:16px;
  background:linear-gradient(180deg,{SF['acc1']},{SF['acc2']});border-radius:3px}}
.compare-wrap .one-line{{font-size:14.5px;font-weight:700;color:{SF['up']};
  background:rgba(255,77,79,.08);border-left:3px solid {SF['up']};padding:10px 14px;border-radius:8px;margin-bottom:14px}}
.compare-wrap .one-line.hold{{color:{SF['hold']};background:rgba(255,165,2,.08);border-left-color:{SF['hold']}}}
.compare-wrap table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
.compare-wrap th,.compare-wrap td{{padding:9px 8px;text-align:center;border-bottom:1px solid {SF['border']}}}
.compare-wrap th{{color:{SF['txt2']};font-weight:600;font-size:12px;background:#15152a}}
.compare-wrap td.l{{text-align:left}}
.compare-wrap .up{{color:{SF['up']};font-weight:700}}
.compare-wrap .down{{color:{SF['down']};font-weight:700}}
.compare-wrap .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:14px;font-weight:600}}
.compare-wrap .tag.win{{background:rgba(255,77,79,.16);color:{SF['up']};border:1px solid rgba(255,77,79,.4)}}
.compare-wrap .tag.mid{{background:rgba(255,165,2,.16);color:{SF['hold']};border:1px solid rgba(255,165,2,.4)}}
.compare-wrap .tag.weak{{background:rgba(0,212,134,.14);color:{SF['down']};border:1px solid rgba(0,212,134,.4)}}
.compare-wrap .tag.neu{{background:rgba(148,163,184,.12);color:{SF['txt2']};border:1px solid {SF['border']}}}
.compare-wrap .vs{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}}
.compare-wrap .vsbox{{background:#15152a;border:1px solid {SF['border']};border-radius:10px;padding:14px}}
.compare-wrap .vsbox h3{{font-size:14px;margin-bottom:8px}}
.compare-wrap .vsbox .verdict{{font-size:13px;font-weight:700;margin:8px 0;padding:6px 10px;border-radius:8px}}
.compare-wrap .verdict.b{{background:rgba(255,77,79,.12);color:{SF['up']}}}
.compare-wrap .verdict.o{{background:rgba(255,165,2,.12);color:{SF['hold']}}}
.compare-wrap .vsbox ul{{margin:6px 0 0 16px;font-size:12.5px;color:{SF['txt2']}}}
.compare-wrap .vsbox ul li{{margin:3px 0}}
.compare-wrap .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.compare-wrap .note{{font-size:12.5px;color:{SF['txt2']};margin-top:10px;line-height:1.7}}
.compare-wrap .alert{{border-radius:10px;padding:12px 14px;margin-top:12px;font-size:13px}}
.compare-wrap .alert.risk{{background:rgba(0,212,134,.10);border:1px solid rgba(0,212,134,.45);color:#7ef0c0}}
.compare-wrap .alert.cat{{background:rgba(255,77,79,.10);border:1px solid rgba(255,77,79,.45);color:#ffb3b9}}
.compare-wrap .alert b{{display:block;margin-bottom:4px;font-size:13.5px}}
.compare-wrap .foot{{font-size:12px;color:{SF['txt2']};margin-top:6px}}
.compare-wrap .disclaimer{{margin-top:14px;font-size:11.5px;color:#6b7280;
  border-top:1px dashed {SF['border']};padding-top:10px}}
.compare-wrap .hl{{color:{SF['up']};font-weight:700}}
.compare-wrap .hr{{color:{SF['down']};font-weight:700}}
@media(max-width:780px){{.compare-wrap .vs,.compare-wrap .two-col{{grid-template-columns:1fr}}}}
</style>
"""


def _tag(text: str, kind: str) -> str:
    return f'<span class="tag {kind}">{text}</span>'


def _sig_tag(signal: str) -> str:
    if signal == "买入":
        return _tag("BUY", "win")
    if signal == "卖出":
        return _tag("SELL", "weak")
    return _tag("HOLD", "mid")


def _corr_tag(v: float) -> str:
    if v >= 70:
        return _tag(f"强·{v:.0f}", "win")
    if v >= 40:
        return _tag(f"中·{v:.0f}", "mid")
    return _tag(f"弱·{v:.0f}", "weak")


def _catalyst_tag(v: float) -> str:
    if v >= 70:
        return _tag(f"强·{v:.0f}", "win")
    if v >= 50:
        return _tag(f"中·{v:.0f}", "mid")
    return _tag(f"弱·{v:.0f}", "weak")


def _elasticity_label(v: float) -> str:
    if v >= 40:
        return f"高弹性·{v:.0f}%"
    if v >= 20:
        return f"中弹性·{v:.0f}%"
    return f"稳健·{v:.0f}%"


def build_header(rows: List[Dict[str, Any]], period_days: int) -> str:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    asof = max((r.get("asof", now[:10]) for r in rows), default=now[:10])
    codes = "、".join(f'{r["name"]}({r["code"]})' for r in rows)
    return f"""
<div class="header">
  <div><div class="brand">★ <b>星辰</b> · 多市场智能股票分析师</div>
  <div style="font-size:12px;color:{SF['txt2']};margin-top:4px">多股对比 · {len(rows)} 股同屏</div></div>
  <div style="font-size:12px;color:{SF['txt2']}">分析时间：{now} (GMT+8) · 行情基准 {asof} 收盘 · 回看 {period_days} 天</div>
</div>
<div style="font-size:12px;color:{SF['txt2']};margin-bottom:6px">标的：{codes}</div>
"""


def build_one_line(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    ranked = sorted(rows, key=lambda r: r["scores"]["composite"], reverse=True)
    best, worst = ranked[0], ranked[-1]
    hold_cls = "" if best["signal"] == "买入" else " hold"
    tags = " ".join(
        _tag(f'{r["name"]}：{r["scores"]["composite"]}分({r["signal"]})',
              "win" if r["signal"] == "买入" else ("mid" if r["signal"] == "持有" else "weak"))
        for r in ranked
    )
    summary = (
        f'综合来看：<b>{best["name"]}</b>（{best["scores"]["composite"]}分）动能与趋势最强，'
        f'为首选弹性标的；<b>{worst["name"]}</b>（{worst["scores"]["composite"]}分）评分偏弱、'
        f'信号「{worst["signal"]}」，建议谨慎。各标的评分与信号如下：'
    )
    return f'<div class="one-line{hold_cls}">{summary}</div><div style="margin-top:10px">{tags}</div>'


def build_table(rows: List[Dict[str, Any]]) -> str:
    head = "<th>维度</th>" + "".join(
        f'<th>{r["name"]}<br>{r["code"]}</th>' for r in rows)
    # 收盘价 / 涨跌
    price_cells = "".join(
        (f'<td class="up">¥{r["close"]:.2f} +{r["chg_pct"]:.1f}%</td>' if r["chg_pct"] >= 0
         else f'<td class="down">¥{r["close"]:.2f} {r["chg_pct"]:.1f}%</td>') if r.get("close") is not None
        else '<td>—</td>'
        for r in rows)
    # 总市值 / 市盈率 / 核心业务
    cap_cells = "".join(f"<td>{_fmt(r.get('market_cap'))}</td>" for r in rows)
    pe_cells = "".join(f"<td>{_fmt(r.get('pe_ttm'), is_num=True)}</td>" for r in rows)
    biz_cells = "".join(f"<td>{_fmt(r.get('industry'))}</td>" for r in rows)
    # 关联度 / 订单催化 / 弹性 / 综合 / 信号
    corr_cells = "".join(f"<td>{_corr_tag(r.get('correlation', 0.0))}</td>" for r in rows)
    cat_cells = "".join(f"<td>{_catalyst_tag(r.get('catalyst', 50))}</td>" for r in rows)
    elas_cells = "".join(f"<td>{_elasticity_label(r.get('elasticity', 0.0))}</td>" for r in rows)
    comp_cells = "".join(f'<td><b>{r["scores"]["composite"]}</b></td>' for r in rows)
    sig_cells = "".join(f"<td>{_sig_tag(r['signal'])}</td>" for r in rows)

    return f"""
<table>
  <thead><tr>{head}</tr></thead>
  <tbody>
    <tr><td class="l">收盘价 / 涨跌</td>{price_cells}</tr>
    <tr><td class="l">总市值</td>{cap_cells}</tr>
    <tr><td class="l">TTM 市盈率</td>{pe_cells}</tr>
    <tr><td class="l">核心业务</td>{biz_cells}</tr>
    <tr><td class="l">关联度（价格相关性）</td>{corr_cells}</tr>
    <tr><td class="l">订单 / 催化</td>{cat_cells}</tr>
    <tr><td class="l">弹性特征</td>{elas_cells}</tr>
    <tr><td class="l">综合评分</td>{comp_cells}</tr>
    <tr><td class="l">信号</td>{sig_cells}</tr>
  </tbody>
</table>
<div class="note">注：关联度 = 与同组其它股票日收益率 Pearson 相关系数绝对值均值（越高代表走势越同步）；
订单/催化、弹性为基于量价与技术形态的启发式代理指标；基本面（市值/市盈率/行业）来自公开行情接口，
获取失败显示「—」。综合评分为趋势/动量/量能/形态四维加权，仅供研究参考。</div>
"""


def _fmt(v, is_num: bool = False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if is_num:
        try:
            return f"{float(v):.1f}"
        except Exception:
            return str(v)
    return str(v)


def build_vs_cards(rows: List[Dict[str, Any]]) -> str:
    if len(rows) < 2:
        return ""
    ranked = sorted(rows, key=lambda r: r["scores"]["composite"], reverse=True)
    pairs = list(zip(ranked[:-1], ranked[1:]))[:4]  # 至多 4 组相邻对比
    cards = []
    for i, (a, b) in enumerate(pairs, 1):
        a_win = a["scores"]["composite"] >= b["scores"]["composite"]
        va = _vs_box(a, a_win, b)
        vb = _vs_box(b, not a_win, a)
        conclusion = (
            f'<div class="alert cat"><b>结论：</b>'
            f'从综合评分看，<span class="hl">{a["name"]}</span>（{a["scores"]["composite"]}分）'
            f'{"领先" if a_win else "落后"}于 <span class="hr">{b["name"]}</span>（{b["scores"]["composite"]}分）'
            f'——{a["name"]} 在趋势/动量维度更占优，{b["name"]} 相对{"偏弱" if a_win else "抗跌/稳健"}。</div>'
        )
        cards.append(f"""
<div class="card">
  <h2>对比{i}：{a['name']} vs {b['name']}</h2>
  <div class="vs">{va}{vb}</div>
  {conclusion}
</div>""")
    return "\n".join(cards)


def _vs_box(r: Dict[str, Any], win: bool, other: Dict[str, Any]) -> str:
    verdict = (
        f'综合评分 {r["scores"]["composite"]} · {"领先" if win else "落后"} '
        f'{other["name"]}({other["scores"]["composite"]})'
    )
    cls = "b" if win else "o"
    s = r["scores"]
    bullets = [
        f'收盘 ¥{r["close"]:.2f}（{r["chg_pct"]:+.1f}%）' if r.get("close") is not None
        else '行情数据缺失',
        f'趋势 {s["trend"]:.0f} / 动量 {s["momentum"]:.0f} / 量能 {s["volume"]:.0f}',
        f'弹性 {r.get("elasticity", 0):.0f}% · 关联度 {r.get("correlation", 0):.0f}',
        f'信号 {r["signal"]} · 催化 {r.get("catalyst", 50):.0f}',
    ]
    lis = "".join(f"<li>{b}</li>" for b in bullets)
    return f"""
<div class="vsbox">
  <h3>{r['name']} {r['code']}</h3>
  <div class="verdict {cls}">{verdict}</div>
  <ul>{lis}</ul>
</div>"""


def build_radar(rows: List[Dict[str, Any]]):
    """综合评分雷达（每只股票一条，5 维：趋势/动量/量能/形态/综合）。"""
    import plotly.graph_objects as go
    dims = [("趋势强度", "trend"), ("动量动能", "momentum"),
            ("量价配合", "volume"), ("形态信号", "pattern"), ("综合评分", "composite")]
    fig = go.Figure()
    for i, r in enumerate(rows):
        s = r["scores"]
        vals = [s[d[1]] for d in dims]
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        theta = [d[0] for d in dims] + [dims[0][0]]
        rvals = vals + [vals[0]]
        fig.add_trace(go.Scatterpolar(
            r=rvals, theta=theta, fill="toself", name=f'{r["name"]}',
            line_color=color, fillcolor=_hex_to_rgba(color, 0.2),
            line=dict(width=2),
        ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=SF["border"],
                            tickfont=dict(color=SF["txt2"], size=9)),
            angularaxis=dict(gridcolor=SF["border"],
                            tickfont=dict(color=SF["txt"], size=11)),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(font=dict(color=SF["txt2"], size=11), orientation="h", yanchor="bottom", y=-0.18, x=0.5, xanchor="center"),
        font=dict(color=SF["txt"]),
        height=430, margin=dict(l=40, r=40, t=30, b=80),
    )
    return fig


def build_radar_right(rows: List[Dict[str, Any]]) -> str:
    """雷达图右侧：评分排行 + 统一风险提示。"""
    ranked = sorted(rows, key=lambda r: r["scores"]["composite"], reverse=True)
    items = []
    for r in ranked:
        kind = "win" if r["signal"] == "买入" else ("mid" if r["signal"] == "持有" else "weak")
        label = f'{r["name"]} {r["scores"]["composite"]}'
        items.append(
            f'<div style="margin-top:6px">{_tag(label, kind)} '
            f'{_elasticity_label(r.get("elasticity", 0.0))}</div>'
        )
    ranked_list = "".join(items)
    risk = (
        f'<div class="alert risk"><b>统一风险提示</b>'
        f'评分与结论为模型基于量价与技术面的推演，非投资建议；'
        f'若组内出现集体大涨需警惕短期情绪过热，宜逢回调分批，忌一日追齐。</div>'
    )
    return f'<div style="font-size:13px;line-height:1.9;margin-top:4px">{ranked_list}</div>{risk}'


def build_action_plan(rows: List[Dict[str, Any]]) -> str:
    ranked = sorted(rows, key=lambda r: r["scores"]["composite"], reverse=True)
    tr = []
    for idx, r in enumerate(ranked):
        sig = r["signal"]
        if sig == "买入" and idx == 0:
            role = "首选弹性（进攻）"
        elif sig == "买入":
            role = "弹性 / 进攻"
        elif sig == "持有":
            role = "稳健持有"
        else:
            role = "防御 / 观望"
        if sig == "买入":
            strategy = "回踩 MA5/MA10 分批低吸，不追高"
        elif sig == "持有":
            strategy = "沿趋势持有，破 MA20 减仓"
        else:
            strategy = "观望，等回调至支撑区再考虑"
        if r.get("support") is not None and r.get("resistance") is not None:
            focus = f'支撑 ¥{r["support"]:.2f}，压力 ¥{r["resistance"]:.2f}'
        else:
            focus = "—"
        tr.append(
            f'<tr><td class="l"><b>{r["name"]}</b> {r["code"]}</td>'
            f'<td>{role}</td><td>{strategy}</td><td>{focus}</td></tr>'
        )
    return f"""
<div class="card">
  <h2>分层操作建议</h2>
  <table>
    <thead><tr><th>标的</th><th>角色定位</th><th>策略</th><th>关注位</th></tr></thead>
    <tbody>{''.join(tr)}</tbody>
  </table>
</div>
"""


def build_footer() -> str:
    return f"""
<div class="card">
  <div class="foot">
    <div><b style="color:{SF['txt']}">数据来源：</b>akshare / BaoStock / 新浪财经 / 东方财富（经 StockFetcher 四级降级链），技术指标由 modules.technical 计算。</div>
    <div style="margin-top:6px"><b style="color:{SF['txt']}">分析框架：</b>星辰多市场智能分析 · 量价技术面 + 价格相关性关联度 + 订单催化/弹性代理 + 分层操作建议。</div>
    <div class="disclaimer">⚠ 免责声明：本对比仅供学习和研究参考，不构成任何投资建议。股市有风险，投资需谨慎；评分为模型推演，请独立决策并严格控制仓位。</div>
  </div>
</div>
"""
