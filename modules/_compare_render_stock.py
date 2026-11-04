"""多股票横向对比 —— 个股对比渲染（_compare_render 二级拆分·个股域）。

职责：逐股要点 / 对比结论 / 成对卡 / 榜单表 / 雷达图 / 行动方案 / 页脚。
零业务逻辑改动：源码自 ``modules/_compare_render.py`` 按函数名原样搬运。
"""
from __future__ import annotations  # noqa: I001

import logging
import re  # noqa: F401

import numpy as np  # noqa: F401
from modules.colors import _hex_to_rgba
from modules.time_utils import now_cst_str
from modules._compare_render_base import (
    SERIES_COLORS,
    _biz_groups,  # noqa: F401
    _catalyst_tag,
    _corr_tag,
    _elasticity_label,
    _fmt,
    _fmt_pct,
    _fund_yi_cell,
    _hex_to_rgba,  # noqa: F811
    _row_score,
    _safe,
    _sf,
    _sig_tag,
    _stock_type_label,
    _tag,
    _score_badge,
    _is_dark,  # noqa: F401
)

logger = logging.getLogger(__name__)

def _stock_bullets(r: Dict[str, Any]) -> List[str]:  # noqa: F821
    """生成 image #9 风格的单股要点 bullets。"""
    bullets = []
    s = r.get("scores", {})
    ind = r.get("industry") or "未知行业"
    cap = r.get("market_cap")
    pe = r.get("pe_ttm")
    elas = _safe(r.get("elasticity"), 0)
    corr = _safe(r.get("business_corr"), 0)
    # 1) 行业/题材定位
    bullets.append(f"行业：<b>{ind}</b> · 业务关联度 {_corr_tag(corr)}")
    # 2) 估值/市值
    if cap is not None and pe is not None:
        bullets.append(f"市值 <b>{cap:.0f}亿</b> · TTM <b>{pe:.1f}</b> 倍")
    elif cap is not None:
        bullets.append(f"市值 <b>{cap:.0f}亿</b> · 市盈率暂未获取")
    elif pe is not None:
        bullets.append(f"TTM <b>{pe:.1f}</b> 倍 · 总市值暂未获取")
    else:
        if ind and ind != "未知行业":
            bullets.append(f"估值数据波动：市值/市盈率暂未拉取（行业：<b>{ind}</b>，以技术面为主）")
        else:
            bullets.append("基本面数据暂未获取，以技术面为主")
    # 3) 技术面四维
    bullets.append(
        f"趋势 {s.get('trend', 0):.0f} / 动量 {s.get('momentum', 0):.0f} / "
        f"量能 {s.get('volume', 0):.0f} / 形态 {s.get('pattern', 0):.0f}"
    )
    # 4) 弹性/催化
    bullets.append(f"弹性 {_elasticity_label(elas)} · 催化 {_catalyst_tag(s.get('catalyst', 50))}")
    # 4.5) 估值补充（PB/PS/股息率）
    pb = r.get("pb"); ps = r.get("ps"); dv = r.get("dv_ttm")  # noqa: E702
    if pb is not None or ps is not None or dv is not None:
        parts = []
        if pb is not None:
            parts.append(f"PB {pb:.2f}")
        if ps is not None:
            parts.append(f"PS {ps:.2f}")
        if dv is not None:
            parts.append(f"股息率 {dv:.2f}%")
        bullets.append("估值补充：" + " · ".join(parts))
    # 4.6) 财务（ROE/营收同比/净利润同比）
    roe = r.get("roe"); ry = r.get("revenue_yoy"); py = r.get("profit_yoy")  # noqa: E702
    if roe is not None or ry is not None or py is not None:
        parts = []
        if roe is not None:
            parts.append(f"ROE {roe:.1f}%")
        if ry is not None:
            parts.append(f"营收同比 {ry:.1f}%")
        if py is not None:
            parts.append(f"净利同比 {py:.1f}%")
        bullets.append("财务：" + " · ".join(parts))
    # 4.7) 资金面（主力净流入）
    mn = r.get("fund_main_net"); mp = r.get("fund_main_net_pct")  # noqa: E702
    if mn is not None:
        yi = mn / 1e8
        tag = "流入" if yi >= 0 else "流出"
        bullets.append(f"主力资金{tag} {abs(yi):.2f}亿（{_fmt_pct(mp)}）")
    # 5) 价格/支撑压力
    if r.get("close") is not None:
        price = r["close"]
        sup = r.get("support")
        res = r.get("resistance")
        if sup is not None and res is not None:
            bullets.append(f"现价 ¥{price:.2f} · 支撑 ¥{sup:.2f} · 压力 ¥{res:.2f}")
        else:
            bullets.append(f"现价 ¥{price:.2f} · 支撑/压力未计算")
    return bullets

def _pair_conclusion(a: Dict[str, Any], b: Dict[str, Any]) -> str:  # noqa: F821
    """生成两两对比的详细结论。"""
    ca = int(round(_safe(a.get("scores", {}).get("composite"), 50)))
    cb = int(round(_safe(b.get("scores", {}).get("composite"), 50)))
    winner, loser = (a, b) if ca >= cb else (b, a)
    cw = int(round(_safe(winner.get("scores", {}).get("composite"), 50)))
    cl = int(round(_safe(loser.get("scores", {}).get("composite"), 50)))
    wa = _safe(winner.get("scores", {}).get("trend"), 50)
    wb = _safe(loser.get("scores", {}).get("trend"), 50)
    ma = _safe(winner.get("scores", {}).get("momentum"), 50)
    mb = _safe(loser.get("scores", {}).get("momentum"), 50)
    ea = _safe(winner.get("elasticity"), 0)
    eb = _safe(loser.get("elasticity"), 0)
    reasons = []
    if wa - wb >= 8:
        reasons.append(f"{winner['name']} 在趋势强度上更占优（{wa:.0f} vs {wb:.0f}）")
    if ma - mb >= 8:
        reasons.append(f"{winner['name']} 动量更强（{ma:.0f} vs {mb:.0f}）")
    if ea - eb >= 10:
        reasons.append(f"{winner['name']} 弹性空间更大（{ea:.0f}% vs {eb:.0f}%）")
    if not reasons:
        reasons.append(f"{winner['name']} 综合评分领先（{cw} vs {cl}）")
    reason_txt = "；".join(reasons[:2])
    return (
        f'<b>结论：</b>{winner["name"]} 明显优于 {loser["name"]}（{cw} vs {cl} 分）。'
        f'{reason_txt}。{loser["name"]} 相对偏弱，'
        f'若从“{winner["industry"] or "同组"}”逻辑选股，优先关注 {winner["name"]}；'
        f'{loser["name"]} 仅适合题材博弈或等回调后再评估。'
    )

def build_pairwise_card(a: Dict[str, Any], b: Dict[str, Any], idx: int = 1) -> str:  # noqa: F821
    """1:1 横向还原：左卡 | VS | 右卡，结论框在下方。严格等宽，绝不纵向堆叠。"""
    va = _vs_box_v2(a, b)
    vb = _vs_box_v2(b, a)
    conclusion = _pair_conclusion(a, b)
    return f"""
<div class="compare-wrap">
  <div class="card">
    <h2>对比{idx}：{a['name']} vs {b['name']}</h2>
    <div class="pw-grid">
      <div class="pw-box">{va}</div>
      <div class="pw-vs"><span>VS</span></div>
      <div class="pw-box">{vb}</div>
    </div>
    <div class="alert cat">{conclusion}</div>
  </div>
</div>
"""

def _vs_box_v2(r: Dict[str, Any], other: Dict[str, Any]) -> str:  # noqa: F821
    """image #9 单卡：标题+类型+分数徽章+bullets。"""
    win = _row_score(r, "composite") >= _row_score(other, "composite")
    verdict = (
        f'{"领先" if win else "落后"} {other["name"]} '
        f'（{_row_score(r, "composite"):.0f} vs {_row_score(other, "composite"):.0f}）'
    )
    cls = "b" if win else "o"
    lis = "".join(f"<li>{b}</li>" for b in _stock_bullets(r))
    return f"""
<div class="vsbox">
  <h3>{r['name']} <span style="font-weight:500;font-size:12px;color:{_sf()['txt2']}">{r['code']}</span>
    <span class="type">· {_stock_type_label(r)}</span>
  </h3>
  <div class="score-row">{_score_badge(r)} <span class="verdict {cls}">{verdict}</span></div>
  <ul>{lis}</ul>
</div>"""

def build_header(rows: List[Dict[str, Any]], period_days: int) -> str:  # noqa: F821
    now = now_cst_str("%Y-%m-%d %H:%M")
    asof = max((r.get("asof", now[:10]) for r in rows), default=now[:10])
    codes = "、".join(f'{r["name"]}({r["code"]})' for r in rows)
    return f"""
<div class="header">
  <div><div class="brand">★ <b>星辰</b> · 多市场智能股票分析师</div>
  <div style="font-size:12px;color:{_sf()['txt2']};margin-top:4px">多股对比 · {len(rows)} 股同屏</div></div>
  <div style="font-size:12px;color:{_sf()['txt2']}">分析时间：{now} (GMT+8) · 行情基准 {asof} 收盘 · 回看 {period_days} 天</div>
</div>
<div style="font-size:12px;color:{_sf()['txt2']};margin-bottom:6px">标的：{codes}</div>
"""

def build_one_line(rows: List[Dict[str, Any]]) -> str:  # noqa: F821
    if not rows:
        return ""
    ranked = sorted(rows, key=lambda r: _row_score(r, "composite"), reverse=True)
    best, worst = ranked[0], ranked[-1]
    hold_cls = "" if best["signal"] == "买入" else " hold"
    tags = " ".join(
        _tag(f'{r["name"]}：{_row_score(r, "composite"):.0f}分({r["signal"]})',
              "win" if r["signal"] == "买入" else ("mid" if r["signal"] == "持有" else "weak"))
        for r in ranked
    )
    summary = (
        f'综合来看：<b>{best["name"]}</b>（{_row_score(best, "composite"):.0f}分）动能与趋势最强，'
        f'为首选弹性标的；<b>{worst["name"]}</b>（{_row_score(worst, "composite"):.0f}分）评分偏弱、'
        f'信号「{worst["signal"]}」，建议谨慎。各标的评分与信号如下：'
    )
    return f'<div class="one-line{hold_cls}">{summary}</div><div style="margin-top:10px">{tags}</div>'

def build_table(rows: List[Dict[str, Any]]) -> str:  # noqa: F821
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
    biz_cells = "".join(
        f"<td title='{_fmt(r.get('core_business') or r.get('industry'))}'>"
        f"{_fmt(r.get('core_business') or r.get('industry'))}</td>"
        for r in rows
    )
    # 估值补充：市净率 / 市销率 / 股息率(TTM)
    pb_cells = "".join(f"<td>{_fmt(r.get('pb'), is_num=True)}</td>" for r in rows)
    ps_cells = "".join(f"<td>{_fmt(r.get('ps'), is_num=True)}</td>" for r in rows)
    dv_cells = "".join(f"<td>{_fmt(r.get('dv_ttm'), is_num=True)}</td>" for r in rows)
    # 财务：ROE / 营收同比 / 净利润同比
    roe_cells = "".join(f"<td>{_fmt(r.get('roe'), is_num=True)}</td>" for r in rows)
    rev_cells = "".join(f"<td>{_fmt(r.get('revenue_yoy'), is_num=True)}</td>" for r in rows)
    pro_cells = "".join(f"<td>{_fmt(r.get('profit_yoy'), is_num=True)}</td>" for r in rows)
    # 资金面：主力净流入(亿) / 主力占比 / 大单净流入(亿)
    fund_cells = "".join(_fund_yi_cell(r, "fund_main_net") for r in rows)
    fund_pct_cells = "".join(f"<td>{_fmt_pct(r.get('fund_main_net_pct'))}</td>" for r in rows)
    fund_big_cells = "".join(_fund_yi_cell(r, "fund_big_net") for r in rows)
    # 业务关联度 / 订单催化 / 弹性 / 综合 / 信号
    corr_cells = "".join(f"<td>{_corr_tag(r.get('business_corr', 0.0))}</td>" for r in rows)
    cat_cells = "".join(f"<td>{_catalyst_tag(r.get('catalyst', 50))}</td>" for r in rows)
    elas_cells = "".join(f"<td>{_elasticity_label(r.get('elasticity', 0.0))}</td>" for r in rows)
    comp_cells = "".join(f'<td><b>{_row_score(r, "composite"):.0f}</b></td>' for r in rows)
    sig_cells = "".join(f"<td>{_sig_tag(r['signal'])}</td>" for r in rows)

    return f"""
<table>
  <thead><tr>{head}</tr></thead>
  <tbody>
    <tr><td class="l">收盘价 / 涨跌</td>{price_cells}</tr>
    <tr><td class="l">总市值</td>{cap_cells}</tr>
    <tr><td class="l">TTM 市盈率</td>{pe_cells}</tr>
    <tr><td class="l">核心业务</td>{biz_cells}</tr>
    <tr><td class="l">市净率 PB</td>{pb_cells}</tr>
    <tr><td class="l">市销率 PS</td>{ps_cells}</tr>
    <tr><td class="l">股息率(TTM)</td>{dv_cells}</tr>
    <tr><td class="l">ROE(%)</td>{roe_cells}</tr>
    <tr><td class="l">营收同比(%)</td>{rev_cells}</tr>
    <tr><td class="l">净利润同比(%)</td>{pro_cells}</tr>
    <tr><td class="l">主力净流入(亿)</td>{fund_cells}</tr>
    <tr><td class="l">主力占比</td>{fund_pct_cells}</tr>
    <tr><td class="l">大单净流入(亿)</td>{fund_big_cells}</tr>
    <tr><td class="l">业务关联度</td>{corr_cells}</tr>
    <tr><td class="l">订单 / 催化</td>{cat_cells}</tr>
    <tr><td class="l">弹性特征</td>{elas_cells}</tr>
    <tr><td class="l">综合评分</td>{comp_cells}</tr>
    <tr><td class="l">信号</td>{sig_cells}</tr>
  </tbody>
</table>
<div class="note">注：核心业务 = 同花顺主营构成（主营业务/主营产品），更贴近个股真实业务；
获取失败时回退显示行业标签。业务关联度 = 与同组其它股票基于行业归属的业务相似度均值（同行业最高、同一大类次之）；
订单/催化、弹性为基于量价与技术形态的启发式代理指标；估值补充（PB/PS/股息率TTM）来自百度估值接口，
财务（ROE/营收同比/净利润同比）来自同花顺财务指标，资金面（主力净流入/大单）来自东方财富个股主力资金（失败则量价估算兜底），
获取失败显示「—」，净流入/大单为正显示红色（流入）、为负显示绿色（流出）。综合评分为趋势/动量/量能/形态四维加权，仅供研究参考。</div>
"""

def build_extra_card(rows: List[Dict[str, Any]]) -> str:  # noqa: F821
    """新增维度专卡：估值补充 / 财务 / 资金面，密集横向对比（与主表互补）。"""
    head = "<th>维度</th>" + "".join(
        f'<th>{r["name"]}<br>{r["code"]}</th>' for r in rows)
    pb = "".join(f"<td>{_fmt(r.get('pb'), is_num=True)}</td>" for r in rows)
    ps = "".join(f"<td>{_fmt(r.get('ps'), is_num=True)}</td>" for r in rows)
    dv = "".join(f"<td>{_fmt(r.get('dv_ttm'), is_num=True)}</td>" for r in rows)
    roe = "".join(f"<td>{_fmt(r.get('roe'), is_num=True)}</td>" for r in rows)
    rev = "".join(f"<td>{_fmt(r.get('revenue_yoy'), is_num=True)}</td>" for r in rows)
    pro = "".join(f"<td>{_fmt(r.get('profit_yoy'), is_num=True)}</td>" for r in rows)
    fund = "".join(_fund_yi_cell(r, "fund_main_net") for r in rows)
    fp = "".join(f"<td>{_fmt_pct(r.get('fund_main_net_pct'))}</td>" for r in rows)
    big = "".join(_fund_yi_cell(r, "fund_big_net") for r in rows)
    return f"""
<div class="card">
  <h2>估值 · 财务 · 资金面（新增维度）</h2>
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>
      <tr><td class="l">市净率 PB</td>{pb}</tr>
      <tr><td class="l">市销率 PS</td>{ps}</tr>
      <tr><td class="l">股息率(TTM)</td>{dv}</tr>
      <tr><td class="l">ROE(%)</td>{roe}</tr>
      <tr><td class="l">营收同比(%)</td>{rev}</tr>
      <tr><td class="l">净利润同比(%)</td>{pro}</tr>
      <tr><td class="l">主力净流入(亿)</td>{fund}</tr>
      <tr><td class="l">主力占比</td>{fp}</tr>
      <tr><td class="l">大单净流入(亿)</td>{big}</tr>
    </tbody>
  </table>
  <div class="note">估值补充来自百度估值（市净率/市销率/股息率TTM）；财务指标来自同花顺财务指标（ROE/营收同比/净利润同比）；
  资金面来自东方财富个股主力资金（失败则量价估算兜底），净流入/大单为正显示红色（流入）、为负显示绿色（流出）。数据缺失显示「—」。</div>
</div>
"""

def build_vs_cards(rows: List[Dict[str, Any]]) -> str:  # noqa: F821
    if len(rows) < 2:
        return ""
    ranked = sorted(rows, key=lambda r: _row_score(r, "composite"), reverse=True)
    pairs = list(zip(ranked[:-1], ranked[1:]))[:4]  # 至多 4 组相邻对比  # noqa: B905
    cards = []
    for i, (a, b) in enumerate(pairs, 1):
        a_win = _row_score(a, "composite") >= _row_score(b, "composite")
        va = _vs_box(a, a_win, b)
        vb = _vs_box(b, not a_win, a)
        conclusion = (
            f'<div class="alert cat"><b>结论：</b>'
            f'从综合评分看，<span class="hl">{a["name"]}</span>（{_row_score(a, "composite"):.0f}分）'
            f'{"领先" if a_win else "落后"}于 <span class="hr">{b["name"]}</span>（{_row_score(b, "composite"):.0f}分）'
            f'——{a["name"]} 在趋势/动量维度更占优，{b["name"]} 相对{"偏弱" if a_win else "抗跌/稳健"}。</div>'
        )
        cards.append(f"""
<div class="card">
  <h2>对比{i}：{a['name']} vs {b['name']}</h2>
  <div class="vs">{va}{vb}</div>
  {conclusion}
</div>""")
    return "\n".join(cards)

def _vs_box(r: Dict[str, Any], win: bool, other: Dict[str, Any]) -> str:  # noqa: F821
    verdict = (
        f'综合评分 {_row_score(r, "composite"):.0f} · {"领先" if win else "落后"} '
        f'{other["name"]}({_row_score(other, "composite"):.0f})'
    )
    cls = "b" if win else "o"
    s = r.get("scores") or {}
    bullets = [
        f'收盘 ¥{r["close"]:.2f}（{r["chg_pct"]:+.1f}%）' if r.get("close") is not None
        else '行情数据缺失',
        f'趋势 {_safe(s.get("trend"), 50):.0f} / 动量 {_safe(s.get("momentum"), 50):.0f} / 量能 {_safe(s.get("volume"), 50):.0f}',
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

def build_radar(rows: List[Dict[str, Any]]):  # noqa: F821
    """综合评分雷达（每只股票一条，5 维：趋势/动量/量能/形态/综合）。"""
    import plotly.graph_objects as go
    dims = [("趋势强度", "trend"), ("动量动能", "momentum"),
            ("量价配合", "volume"), ("形态信号", "pattern"), ("综合评分", "composite")]
    fig = go.Figure()
    for i, r in enumerate(rows):
        s = r.get("scores") or {}
        vals = [_safe(s.get(d[1]), 50) for d in dims]
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
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=_sf()["border"],
                            tickfont=dict(color=_sf()["txt2"], size=9)),
            angularaxis=dict(gridcolor=_sf()["border"],
                            tickfont=dict(color=_sf()["txt"], size=11)),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(font=dict(color=_sf()["txt2"], size=11), orientation="h", yanchor="bottom", y=-0.18, x=0.5, xanchor="center"),
        font=dict(color=_sf()["txt"]),
        height=430, margin=dict(l=40, r=40, t=30, b=80),
    )
    return fig

def _one_liner(r: Dict[str, Any]) -> str:  # noqa: F821
    """image #13 风格的一句话定性。"""
    comp = _safe(r.get("scores", {}).get("composite"), 50)
    elas = _safe(r.get("elasticity"), 0)
    cat = _safe(r.get("catalyst", 50))
    sig = r.get("signal", "持有")
    if comp >= 70:
        if elas >= 30:
            return "综合评分领先，弹性较大，可重点关注"
        return "综合评分领先，质地稳健，适合底仓"
    if comp >= 55:
        if cat >= 60:
            return "订单/催化积极，趋势向好，可逢回调参与"
        return "评分中等偏上，关注催化落地"
    if sig == "卖出":
        return "评分偏弱，信号偏空，谨慎观望"
    return "评分中性，跟踪催化剂与趋势变化"

def build_radar_right(rows: List[Dict[str, Any]]) -> str:  # noqa: F821
    """雷达图右侧：image #13 评分标签云 + 统一风险提示。"""
    ranked = sorted(rows, key=lambda r: _row_score(r, "composite"), reverse=True)
    chips = []
    for r in ranked:
        comp = int(round(_row_score(r, "composite")))
        kind = "win" if r["signal"] == "买入" else ("mid" if r["signal"] == "持有" else "weak")
        chips.append(
            f'<div class="chip">'
            f'<span class="tag {kind}">{r["name"]} {comp}</span>'
            f'<span>{_one_liner(r)}</span></div>'
        )
    cloud = '<div class="score-cloud">' + "".join(chips) + '</div>'
    # 统一风险提示
    avg_comp = sum(_row_score(r, "composite") for r in rows) / len(rows) if rows else 50
    overheat = len([r for r in rows if r.get("chg_pct", 0) >= 9]) >= 2
    heat_hint = "组内多只出现大涨，短期情绪过热，追高性价比低；" if overheat else ""
    risk = (
        f'<div class="alert risk"><b>统一风险提示</b>'
        f'{heat_hint}评分为模型基于量价与技术面的推演，非投资建议；'
        f'组内平均评分 {avg_comp:.0f}，若平均偏高需警惕集体回调，宜分批建仓、严格控制仓位。'
        f'</div>'
    )
    return f'<div style="font-size:13px;line-height:1.8;margin-top:4px">{cloud}</div>{risk}'

def build_action_plan(rows: List[Dict[str, Any]]) -> str:  # noqa: F821
    """image #10 模板：分层操作建议表。"""
    ranked = sorted(rows, key=lambda r: _row_score(r, "composite"), reverse=True)
    tr = []
    for idx, r in enumerate(ranked):
        sig = r["signal"]
        stype = _stock_type_label(r)
        elas = _safe(r.get("elasticity"), 0)
        # 角色定位
        if sig == "买入" and idx == 0:
            role = f"{stype}（进攻首选）"
        elif sig == "买入":
            role = f"{stype}（进攻）"
        elif sig == "持有":
            role = f"{stype}（稳健）"
        else:
            role = f"{stype}（观望）"
        # 策略
        if sig == "买入":
            if elas >= 35:
                strategy = "回踩5日/10日线分批低吸，不追涨停"
            else:
                strategy = "沿趋势持有，回踩均线分批加仓"
        elif sig == "持有":
            strategy = "回调至支撑区低吸，跌破均线减仓"
        else:
            strategy = "观望，等回调至支撑区且缩量再考虑"
        # 关注位
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
    <div><b style="color:{_sf()['txt']}">数据来源：</b>akshare / BaoStock / 新浪财经 / 东方财富（经 StockFetcher 四级降级链），技术指标由 modules.technical 计算。</div>
    <div style="margin-top:6px"><b style="color:{_sf()['txt']}">分析框架：</b>星辰多市场智能分析 · 量价技术面 + 业务关联度 + 订单催化/弹性代理 + 分层操作建议。</div>
    <div class="disclaimer">⚠ 免责声明：本对比仅供学习和研究参考，不构成任何投资建议。股市有风险，投资需谨慎；评分为模型推演，请独立决策并严格控制仓位。</div>
  </div>
</div>
"""
