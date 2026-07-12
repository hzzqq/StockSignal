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
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis

# ── 白天模式配色（参照 compare-analysis-20260710-light.html，绿涨红跌）──
UP = "#009e60"      # 涨 / 强 / 买入（绿）
DOWN = "#dc2626"    # 跌 / 弱 / 卖出（红）
AMBER = "#d97706"   # 中性 / 持有（琥珀）
ACC1 = "#4f46e5"    # 靛蓝
ACC2 = "#7c3aed"    # 紫
SF = {
    "bg": "#f5f7fa", "card": "#ffffff", "border": "#e2e8f0",
    "txt": "#1e293b", "txt2": "#64748b",
    "up": UP, "down": DOWN, "hold": AMBER, "acc1": ACC1, "acc2": ACC2,
}
# 每只股票一条折线/填充色（用于雷达图图例，白底需足够鲜明）
SERIES_COLORS = ["#009e60", "#dc2626", "#4f46e5", "#d97706", "#7c3aed",
                 "#0891b2", "#ca8a04", "#9333ea"]


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
    _fill_business_correlation(rows)
    return rows


def _build_row(fetcher: StockFetcher, code: str, period_days: int) -> Dict[str, Any]:
    """构建单只股票对比行；优先本地数据库名称，失败再远程兜底。"""
    name = ""
    try:
        # 1) 本地缓存最可靠，且会自动 warm-up
        _, basic_name = fetcher.get_stock_basic(code)
        if basic_name and str(basic_name).strip() and str(basic_name).strip() != code:
            name = basic_name.strip()
    except Exception:
        pass

    # 2) 本地无名称时，尝试 BaoStock 并解析 "600519(贵州茅台)"
    if not name:
        try:
            raw = fetcher.get_stock_name(code) or ""
            if raw and str(raw).strip() and str(raw).strip() != code:
                raw = raw.strip()
                if "(" in raw and ")" in raw:
                    name = raw.split("(", 1)[1].split(")", 1)[0].strip()
                else:
                    name = raw
        except Exception:
            pass

    # 3) 兜底：代码本身
    if not name:
        name = code

    row: Dict[str, Any] = {"code": code, "name": name}

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

    _fill_fundamentals(row, fetcher)
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


# 行业大类映射：用于「业务关联度」的板块亲和度判断
_INDUSTRY_GROUPS = {
    "电子半导体": ["半导体", "消费电子", "元件", "光学光电子", "电子制造", "其他电子", "电子"],
    "工程建筑": ["工程", "建设", "建筑", "装修", "设计"],
    "金属材料": ["金属", "材料"],
    "医药生物": ["医药", "生物", "医疗", "制药", "疫苗"],
    "汽车": ["汽车", "零部件"],
    "金融": ["银行", "证券", "保险", "金融"],
    "消费": ["白酒", "饮料", "食品", "家电", "零售", "消费"],
    "电力能源": ["电力", "能源", "煤炭", "燃气", "光伏", "电池"],
    "化工": ["化工", "化学"],
    "计算机": ["计算机", "软件", "通信", "互联网"],
    "机械军工": ["机械", "军工", "设备"],
}


def _biz_groups(industry: str) -> List[str]:
    return [g for g, kws in _INDUSTRY_GROUPS.items()
            if any(k in industry for k in kws)]


def _biz_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """两只股票的业务相似度（0-100）：同行业最高，同大类次之，否则弱相关。"""
    ia, ib = (a.get("industry") or ""), (b.get("industry") or "")
    if not ia or not ib:
        return 0.0
    if ia == ib:
        return 90.0
    if ia in ib or ib in ia:
        return 60.0
    ga, gb = _biz_groups(ia), _biz_groups(ib)
    if ga and gb and set(ga) & set(gb):
        return 55.0
    return 12.0


def _fill_business_correlation(rows: List[Dict[str, Any]]) -> None:
    """以组内业务相似度均值作为「业务关联度」（替代原价格相关性关联度）。"""
    for r in rows:
        others = [o for o in rows if o is not r]
        if others:
            sims = [_biz_similarity(r, o) for o in others]
            r["business_corr"] = float(sum(sims) / len(sims))
        else:
            r["business_corr"] = 0.0


def _fill_fundamentals(row: Dict[str, Any], fetcher: "StockFetcher" = None) -> None:
    """基本面（东方财富 push2，稳定可用）：总市值(亿) / 市盈率TTM / 行业。
    失败则留空，由页面显示「—」。"""
    row["market_cap"] = None
    row["pe_ttm"] = None
    row["industry"] = None
    try:
        if fetcher is None:
            fetcher = StockFetcher()
        f = fetcher.get_fundamentals(row["code"])
        if f:
            row["market_cap"] = f.get("market_cap")
            row["pe_ttm"] = f.get("pe_ttm")
            ind = f.get("industry") or ""
            row["industry"] = ind
            # 本地名称缺失时用东方财富名称兜底
            if (not row.get("name") or row["name"] == row["code"]) and f.get("name"):
                row["name"] = f["name"]
    except Exception as e:  # noqa: BLE001
        print(f"[compare] 基本面获取失败 {row['code']}: {e}")


# =====================================================================
# 前端（白天模式 .compare-wrap 风格，1:1 还原参考 HTML）
# =====================================================================
def compare_css() -> str:
    """一次性注入对比页样式（与 compare-analysis-20260710-light.html 同构，白天模式）。"""
    return f"""
<style>
.compare-wrap{{max-width:1200px;margin:0 auto;color:{SF['txt']};
  font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.55}}
.compare-wrap .header{{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:10px;margin-bottom:18px;padding:14px 18px;
  background:linear-gradient(90deg,#f0f1ff,#ede9fe);border:1px solid {SF['border']};border-radius:14px}}
.compare-wrap .header .brand{{font-size:15px;color:{SF['txt2']};letter-spacing:1px}}
.compare-wrap .header .brand b{{color:{SF['acc1']}}}
.compare-wrap .card{{background:{SF['card']};border:1px solid {SF['border']};
  border-radius:14px;padding:18px;margin-top:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.compare-wrap .card h2{{font-size:16px;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
.compare-wrap .card h2::before{{content:"";width:4px;height:16px;
  background:linear-gradient(180deg,{SF['acc1']},{SF['acc2']});border-radius:3px}}
.compare-wrap .one-line{{font-size:14.5px;font-weight:700;color:{SF['up']};
  background:rgba(0,158,96,.07);border-left:3px solid {SF['up']};padding:10px 14px;border-radius:8px;margin-bottom:14px}}
.compare-wrap .one-line.hold{{color:{SF['hold']};background:rgba(217,119,6,.07);border-left-color:{SF['hold']}}}
.compare-wrap table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
.compare-wrap th,.compare-wrap td{{padding:9px 8px;text-align:center;border-bottom:1px solid {SF['border']}}}
.compare-wrap th{{color:{SF['txt2']};font-weight:600;font-size:12px;background:#f8fafc}}
.compare-wrap td.l{{text-align:left}}
.compare-wrap .up{{color:{SF['up']};font-weight:700}}
.compare-wrap .down{{color:{SF['down']};font-weight:700}}
.compare-wrap .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:14px;font-weight:600}}
.compare-wrap .tag.win{{background:rgba(0,158,96,.10);color:{SF['up']};border:1px solid rgba(0,158,96,.35)}}
.compare-wrap .tag.mid{{background:rgba(217,119,6,.10);color:{SF['hold']};border:1px solid rgba(217,119,6,.35)}}
.compare-wrap .tag.weak{{background:rgba(220,38,38,.08);color:{SF['down']};border:1px solid rgba(220,38,38,.35)}}
.compare-wrap .tag.neu{{background:rgba(100,116,139,.08);color:{SF['txt2']};border:1px solid {SF['border']}}}
.compare-wrap .vs{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}}
.compare-wrap .vsbox{{background:#f8fafc;border:1px solid {SF['border']};border-radius:10px;padding:14px}}
.compare-wrap .vsbox h3{{font-size:14px;margin-bottom:8px}}
.compare-wrap .vsbox .verdict{{font-size:13px;font-weight:700;margin:8px 0;padding:6px 10px;border-radius:8px}}
.compare-wrap .verdict.b{{background:rgba(0,158,96,.08);color:{SF['up']}}}
.compare-wrap .verdict.o{{background:rgba(217,119,6,.08);color:{SF['hold']}}}
.compare-wrap .vsbox ul{{margin:6px 0 0 16px;font-size:12.5px;color:{SF['txt2']}}}
.compare-wrap .vsbox ul li{{margin:3px 0}}
.compare-wrap .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.compare-wrap .note{{font-size:12.5px;color:{SF['txt2']};margin-top:10px;line-height:1.7}}
.compare-wrap .alert{{border-radius:10px;padding:12px 14px;margin-top:12px;font-size:13px}}
.compare-wrap .alert.risk{{background:rgba(220,38,38,.06);border:1px solid rgba(220,38,38,.25);color:#991b1b}}
.compare-wrap .alert.cat{{background:rgba(0,158,96,.06);border:1px solid rgba(0,158,96,.25);color:#166534}}
.compare-wrap .alert b{{display:block;margin-bottom:4px;font-size:13.5px}}
.compare-wrap .foot{{font-size:12px;color:{SF['txt2']};margin-top:6px}}
.compare-wrap .disclaimer{{margin-top:14px;font-size:11.5px;color:#94a3b8;
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
    # 业务关联度 / 订单催化 / 弹性 / 综合 / 信号
    corr_cells = "".join(f"<td>{_corr_tag(r.get('business_corr', 0.0))}</td>" for r in rows)
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
    <tr><td class="l">业务关联度</td>{corr_cells}</tr>
    <tr><td class="l">订单 / 催化</td>{cat_cells}</tr>
    <tr><td class="l">弹性特征</td>{elas_cells}</tr>
    <tr><td class="l">综合评分</td>{comp_cells}</tr>
    <tr><td class="l">信号</td>{sig_cells}</tr>
  </tbody>
</table>
<div class="note">注：业务关联度 = 与同组其它股票基于行业归属的业务相似度均值（同行业最高、同一大类次之）；
订单/催化、弹性为基于量价与技术形态的启发式代理指标；基本面（总市值/市盈率/行业）来自东方财富行情接口，
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
        f'弹性 {r.get("elasticity", 0):.0f}% · 业务关联度 {r.get("business_corr", 0):.0f}',
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
    <div style="margin-top:6px"><b style="color:{SF['txt']}">分析框架：</b>星辰多市场智能分析 · 量价技术面 + 业务关联度 + 订单催化/弹性代理 + 分层操作建议。</div>
    <div class="disclaimer">⚠ 免责声明：本对比仅供学习和研究参考，不构成任何投资建议。股市有风险，投资需谨慎；评分为模型推演，请独立决策并严格控制仓位。</div>
  </div>
</div>
"""


# =====================================================================
# 对比方法框架（短期/长期/价值/板块/业绩/政策/宏观/微观/事件）
# =====================================================================
METHODS = {
    "短期": "聚焦动量、量能与近期涨跌幅，捕捉短线交易机会。",
    "长期": "聚焦趋势强度、形态与稳定性，适合中线持有。",
    "价值": "聚焦市盈率(TTM)、市值与基本面，挖掘低估标的。",
    "板块": "聚焦组内业务关联度，识别同板块/同产业链核心标的。",
    "业绩": "聚焦订单催化与盈利质量（催化代理分）。",
    "政策": "聚焦政策敏感行业（半导体/新能源/医药/消费等）与事件导向。",
    "宏观": "聚焦价格弹性（波动率），衡量对宏观与大盘的敏感度。",
    "微观": "聚焦技术面微观结构（均线排列/趋势强度）。",
    "事件": "输入一个事件，对比各股在该事件上的业务关联度与利好/利空。",
}

# 政策友好型行业大类（用于「政策」方法打分）
_POLICY_FRIENDLY = ["半导体", "电子", "新能源", "汽车", "医药", "生物", "军工",
                   "计算机", "软件", "通信", "消费", "白酒", "光伏", "电池", "芯片"]
_BULL_CUES = ["扩产", "利好", "增长", "扶持", "政策", "回暖", "复苏", "突破",
              "中标", "订单", "签约", "涨价", "上调", "补贴"]
_BEAR_CUES = ["处罚", "减持", "暴跌", "利空", "下滑", "亏损", "暴雷", "下调",
              "退市", "调查", "风险", "制裁", "限购", "退坡"]

# 事件关键词 → 行业大类（用于「事件」方法计算业务关联度）
_EVENT_INDUSTRY_MAP = {
    "芯片": "电子半导体", "半导体": "电子半导体", "AI": "电子半导体",
    "人工智能": "电子半导体", "电子": "电子半导体", "手机": "电子半导体",
    "消费电子": "电子半导体", "面板": "电子半导体", "光学": "电子半导体",
    "新能源": "电力能源", "光伏": "电力能源", "电池": "电力能源", "储能": "电力能源",
    "汽车": "汽车", "整车": "汽车", "零部件": "汽车",
    "医药": "医药生物", "生物": "医药生物", "医疗": "医药生物", "疫苗": "医药生物",
    "创新药": "医药生物", "医疗器械": "医药生物",
    "军工": "机械军工", "国防": "机械军工",
    "金融": "金融", "银行": "金融", "证券": "金融", "保险": "金融",
    "消费": "消费", "白酒": "消费", "食品": "消费", "零售": "消费",
    "地产": "工程建筑", "基建": "工程建筑", "工程": "工程建筑", "建筑": "工程建筑",
    "化工": "化工", "化学": "化工", "材料": "金属材料", "金属": "金属材料", "钢铁": "金属材料",
    "计算机": "计算机", "软件": "计算机", "通信": "计算机", "互联网": "计算机",
}


def _safe(v, d: float = 0.0) -> float:
    try:
        f = float(v)
        return f if (not np.isnan(f)) else d
    except Exception:
        return d


def _norm(vals: List[float]) -> List[float]:
    """把一组值线性映射到 [50,100]，保持组内相对强弱。"""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return [50.0 for _ in vals]
    return [50 + (v - lo) / (hi - lo) * 50 for v in vals]


def _event_stance(stock: Dict[str, Any], event_text: str) -> Tuple[float, str]:
    """计算单只股票对某事件的业务关联度(0-100)与多空立场。"""
    ind = stock.get("industry") or ""
    name = stock.get("name") or ""
    text = event_text or ""
    # 抽取事件关键词：中文 2+ 连串 + 其 2-gram + 英文大写词
    cn_runs = re.findall(r"[\u4e00-\u9fa5]{2,}", text)
    tokens = list(cn_runs)
    for run in cn_runs:
        for i in range(len(run) - 1):
            tokens.append(run[i:i + 2])
    tokens += [w.upper() for w in re.findall(r"[A-Za-z]{2,}", text)]
    matched = {_EVENT_INDUSTRY_MAP[t] for t in set(tokens) if t in _EVENT_INDUSTRY_MAP}
    stock_groups = set(_biz_groups(ind))
    overlap = matched & stock_groups
    if not matched:
        rel = 0.0
    elif overlap:
        rel = 85.0
    else:
        rel = 30.0
    bull = any(c in text for c in _BULL_CUES)
    bear = any(c in text for c in _BEAR_CUES)
    if bull and not bear:
        stance = "利好"
    elif bear and not bull:
        stance = "利空"
    elif bull and bear:
        stance = "多空交织"
    else:
        stance = "中性"
    return rel, stance


def compute_method_scores(rows: List[Dict[str, Any]], method: str,
                          event: Optional[str] = None) -> Dict[str, float]:
    """返回该方法下每只股票的综合得分(0-100)。"""
    if method == "事件":
        return {r["code"]: _event_stance(r, event)[0] for r in rows}
    if method == "短期":
        mom = [_safe(r["scores"]["momentum"]) for r in rows]
        vol = [_safe(r["scores"]["volume"]) for r in rows]
        chg = _norm([_safe(r.get("chg_pct")) for r in rows])
        return {r["code"]: 0.45 * mom[i] + 0.30 * vol[i] + 0.25 * chg[i]
                for i, r in enumerate(rows)}
    if method == "长期":
        trend = [_safe(r["scores"]["trend"]) for r in rows]
        pat = [_safe(r["scores"]["pattern"]) for r in rows]
        elas = _norm([_safe(r.get("elasticity")) for r in rows])
        stab = [100 - e for e in elas]
        return {r["code"]: 0.50 * trend[i] + 0.30 * pat[i] + 0.20 * stab[i]
                for i, r in enumerate(rows)}
    if method == "价值":
        pes = [(_safe(r.get("pe_ttm")) if r.get("pe_ttm") else 200.0) for r in rows]
        pe_inv = _norm([200 - p for p in pes])           # 低 PE → 高分
        caps = _norm([_safe(r.get("market_cap")) for r in rows])
        return {r["code"]: 0.60 * pe_inv[i] + 0.40 * caps[i]
                for i, r in enumerate(rows)}
    if method == "板块":
        biz = [min(100.0, _safe(r.get("business_corr")) * 1.4 + 30) for r in rows]
        return {r["code"]: biz[i] for i, r in enumerate(rows)}
    if method == "业绩":
        cat = [_safe(r.get("catalyst", 50)) for r in rows]
        return {r["code"]: cat[i] for i, r in enumerate(rows)}
    if method == "政策":
        out = []
        for r in rows:
            ind = r.get("industry") or ""
            base = 60.0 if any(k in ind for k in _POLICY_FRIENDLY) else 35.0
            out.append(base + 0.1 * _safe(r["scores"]["composite"]) - 5)
        return {r["code"]: max(10.0, min(100.0, v)) for r, v in zip(rows, out)}
    if method == "宏观":
        elas = _norm([_safe(r.get("elasticity")) for r in rows])
        return {r["code"]: elas[i] for i, r in enumerate(rows)}
    if method == "微观":
        trend = [_safe(r["scores"]["trend"]) for r in rows]
        return {r["code"]: trend[i] for i, r in enumerate(rows)}
    # 默认：综合评分
    return {r["code"]: _safe(r["scores"]["composite"]) for r in rows}


def _ranked(rows, scores):
    return sorted(rows, key=lambda r: _safe(scores.get(r["code"])), reverse=True)


def _method_summary(rows: List[Dict[str, Any]], method: str,
                    scores: Dict[str, float], event: Optional[str] = None) -> str:
    ranked = _ranked(rows, scores)
    best, worst = ranked[0], ranked[-1]
    bs = _safe(scores.get(best["code"]))
    ws = _safe(scores.get(worst["code"]))
    if method == "事件":
        rels = [(r, *_event_stance(r, event)) for r in rows]
        rels.sort(key=lambda x: x[1], reverse=True)
        top = rels[0]
        return (f'在事件「{event or ""}」下，<b>{top[0]["name"]}</b>业务关联度最高'
                f'（{top[1]:.0f}，{top[2]}），为最直接受影响标的；'
                f'其余标的关联度依次递减，应区别对待。')
    return (f'在【{method}】视角下，<b>{best["name"]}</b>（{bs:.0f}分）相对占优，'
            f'<b>{worst["name"]}</b>（{ws:.0f}分）偏弱；'
            f'建议优先关注排名靠前且信号为「买入/持有」的标的。')


def build_method_card(rows: List[Dict[str, Any]], method: str,
                      event: Optional[str] = None) -> str:
    """单个对比方法的卡片：排名 + 每标的要点 + 该方法的总结。"""
    scores = compute_method_scores(rows, method, event)
    ranked = _ranked(rows, scores)
    lis = []
    for r in ranked:
        s = _safe(scores.get(r["code"]))
        if method == "事件":
            rel, stance = _event_stance(r, event)
            extra = f'业务关联度 {rel:.0f} · {stance}'
            cls = "win" if stance == "利好" else ("weak" if stance == "利空" else "neu")
            lis.append(f'<li><b>{r["name"]}</b>（{r["code"]}）'
                       f' {_tag(extra, cls)}</li>')
        else:
            kind = "win" if s >= 60 else ("mid" if s >= 45 else "weak")
            lis.append(f'<li><b>{r["name"]}</b>（{r["code"]}）'
                       f' 方法得分 {s:.0f} · 信号 {_tag(r["signal"], "win" if r["signal"]=="买入" else ("mid" if r["signal"]=="持有" else "weak"))}</li>')
    lis_html = "".join(lis)
    summary = _method_summary(rows, method, scores, event)
    return f"""
<div class="card">
  <h2>对比方法 · {method}</h2>
  <div class="one-line">{summary}</div>
  <ul style="margin:10px 0 0 18px;font-size:13px;color:{SF['txt2']};line-height:1.9">{lis_html}</ul>
</div>
"""


def build_aggregate_card(rows: List[Dict[str, Any]],
                         event: Optional[str] = None) -> str:
    """底部大汇总：汇总全部 9 种对比方法的各自结论。"""
    items = []
    for m in METHODS:
        ev = event if m == "事件" else None
        scores = compute_method_scores(rows, m, ev)
        s = _method_summary(rows, m, scores, ev)
        # 去掉 <b> 标签只留纯文本用于汇总列表
        plain = re.sub(r"<[^>]+>", "", s)
        items.append(f'<li><b>{m}</b>：{plain}</li>')
    lis_html = "".join(items)
    return f"""
<div class="card">
  <h2>大汇总 · 九维对比结论</h2>
  <ul style="margin:10px 0 0 18px;font-size:13px;color:{SF['txt2']};line-height:1.9">{lis_html}</ul>
  <div class="note">以上为各对比维度（短期/长期/价值/板块/业绩/政策/宏观/微观/事件）的分别结论汇总，
  综合研判时建议结合多维度信号、控制好仓位，并关注组内集体异动风险。</div>
</div>
"""

