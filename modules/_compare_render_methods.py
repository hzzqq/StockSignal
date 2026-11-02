"""多股票横向对比 —— 方法论评分与卡片（_compare_render 二级拆分·方法域）。

职责：四类方法论打分（compute_method_scores）/ 排名 / 方法卡与汇总卡。
零业务逻辑改动：源码自 ``modules/_compare_render.py`` 按函数名原样搬运。
"""
from __future__ import annotations

import logging
import re

import numpy as np
from modules._compare_render_base import (
    _biz_groups,
    _fmt_pct,
    _hex_to_rgba,
    _norm,
    _row_score,
    _safe,
    _sf,
    _stock_type_label,
)

logger = logging.getLogger(__name__)

METHODS = {
    "短期": "聚焦动量、量能与近期涨跌幅，捕捉短线交易机会。",
    "长期": "聚焦趋势强度、形态与稳定性，适合中线持有。",
    "价值": "聚焦市盈率(TTM)、市值与基本面，挖掘低估标的。",
    "板块": "聚焦组内业务关联度，识别同板块/同产业链核心标的。",
    "业绩": "聚焦订单催化与盈利质量（催化代理分）。",
    "资金": "聚焦个股主力资金净流入与主力占比，识别资金 actively 流入的标的。",
    "政策": "聚焦政策敏感行业（半导体/新能源/医药/消费等）与事件导向。",
    "宏观": "聚焦价格弹性（波动率），衡量对宏观与大盘的敏感度。",
    "微观": "聚焦技术面微观结构（均线排列/趋势强度）。",
    "事件": "输入一个事件，对比各股在该事件上的业务关联度与利好/利空。",
}

_POLICY_FRIENDLY = ["半导体", "电子", "新能源", "汽车", "医药", "生物", "军工",
                   "计算机", "软件", "通信", "消费", "白酒", "光伏", "电池", "芯片"]

_BULL_CUES = ["扩产", "利好", "增长", "扶持", "政策", "回暖", "复苏", "突破",
              "中标", "订单", "签约", "涨价", "上调", "补贴"]

_BEAR_CUES = ["处罚", "减持", "暴跌", "利空", "下滑", "亏损", "暴雷", "下调",
              "退市", "调查", "风险", "制裁", "限购", "退坡"]

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

def _event_stance(stock: Dict[str, Any], event_text: str) -> Tuple[float, str]:
    """计算单只股票对某事件的业务关联度(0-100)与多空立场。"""
    ind = stock.get("industry") or ""
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
    """返回该方法下每只股票的综合得分(0-100)。空列表安全返回 {}。"""
    if not rows:
        return {}
    if method == "事件":
        return {r["code"]: _event_stance(r, event)[0] for r in rows}
    if method == "短期":
        mom = [_row_score(r, "momentum") for r in rows]
        vol = [_row_score(r, "volume") for r in rows]
        chg = _norm([_safe(r.get("chg_pct")) for r in rows])
        return {r["code"]: 0.45 * mom[i] + 0.30 * vol[i] + 0.25 * chg[i]
                for i, r in enumerate(rows)}
    if method == "长期":
        trend = [_row_score(r, "trend") for r in rows]
        pat = [_row_score(r, "pattern") for r in rows]
        elas = _norm([_safe(r.get("elasticity")) for r in rows])
        stab = [100 - e for e in elas]
        return {r["code"]: 0.50 * trend[i] + 0.30 * pat[i] + 0.20 * stab[i]
                for i, r in enumerate(rows)}
    if method == "价值":
        pes = [(_safe(r.get("pe_ttm")) if r.get("pe_ttm") else 200.0) for r in rows]
        pbs = [(_safe(r.get("pb")) if r.get("pb") else 20.0) for r in rows]
        dvs = [(_safe(r.get("dv_ttm")) if r.get("dv_ttm") else 0.0) for r in rows]
        pe_inv = _norm([200 - p for p in pes])           # 低 PE → 高分
        pb_inv = _norm([20 - p for p in pbs])           # 低 PB → 高分
        dv_norm = _norm(dvs)                            # 高股息 → 高分
        return {r["code"]: 0.45 * pe_inv[i] + 0.30 * pb_inv[i] + 0.25 * dv_norm[i]
                for i, r in enumerate(rows)}
    if method == "板块":
        biz = [min(100.0, _safe(r.get("business_corr")) * 1.4 + 30) for r in rows]
        return {r["code"]: biz[i] for i, r in enumerate(rows)}
    if method == "资金":
        nets = [(_safe(r.get("fund_main_net")) if r.get("fund_main_net") is not None else 50.0)
                 for r in rows]
        if all(n == 50.0 for n in nets):
            return {r["code"]: 50.0 for r in rows}
        norm = _norm(nets)
        return {r["code"]: norm[i] for i, r in enumerate(rows)}
    if method == "业绩":
        cat = [_safe(r.get("catalyst", 50)) for r in rows]
        return {r["code"]: cat[i] for i, r in enumerate(rows)}
    if method == "政策":
        out = []
        for r in rows:
            ind = r.get("industry") or ""
            base = 60.0 if any(k in ind for k in _POLICY_FRIENDLY) else 35.0
            out.append(base + 0.1 * _row_score(r, "composite") - 5)
        return {r["code"]: max(10.0, min(100.0, v)) for r, v in zip(rows, out)}
    if method == "宏观":
        elas = _norm([_safe(r.get("elasticity")) for r in rows])
        return {r["code"]: elas[i] for i, r in enumerate(rows)}
    if method == "微观":
        trend = [_row_score(r, "trend") for r in rows]
        return {r["code"]: trend[i] for i, r in enumerate(rows)}
    # 默认：综合评分
    return {r["code"]: _row_score(r, "composite") for r in rows}

def _ranked(rows, scores):
    if not rows:
        return []
    return sorted(rows, key=lambda r: _safe(scores.get(r["code"])), reverse=True)

def rank_methods(rows: List[Dict[str, Any]], event: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """返回每个对比方法下综合占优的标的（结构化结果，供 API / 其它模块复用，不依赖 HTML）。

    新能力（R1）：此前对比结论只能以 HTML 卡片形式产出，无法被非 UI 场景（如后端
    聚合接口、单元测试、量化调度）消费。这里给出纯数据的「每维度赢家」映射，
    与 build_* HTML 渲染共享 compute_method_scores / _ranked 同一套评分逻辑。
    """
    if not rows:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for m in METHODS:
        ev = event if m == "事件" else None
        sc = compute_method_scores(rows, m, ev)
        ranked = _ranked(rows, sc)
        if ranked:
            top = ranked[0]
            out[m] = {
                "method": m,
                "winner_code": top["code"],
                "winner_name": top["name"],
                "score": _safe(sc.get(top["code"])),
            }
    return out

def _method_summary(rows: List[Dict[str, Any]], method: str,
                    scores: Dict[str, float], event: Optional[str] = None) -> str:
    ranked = _ranked(rows, scores)
    if not ranked:
        return "暂无对比标的，无法生成结论。"
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
    if method == "资金":
        inflows = [r for r in rows if (r.get("fund_main_net") or 0) >= 0]
        top = ranked[0]
        return (f'在【资金】视角下，<b>{top["name"]}</b>（{bs:.0f}分）主力净流入表现最突出，'
                f'组内 {len(inflows)}/{len(rows)} 只呈主力净流入；'
                f'建议优先关注主力持续流入且信号为「买入/持有」的标的，警惕主力大幅流出个股。')
    return (f'在【{method}】视角下，<b>{best["name"]}</b>（{bs:.0f}分）相对占优，'
            f'<b>{worst["name"]}</b>（{ws:.0f}分）偏弱；'
            f'建议优先关注排名靠前且信号为「买入/持有」的标的。')

def _method_analysis(method: str, scores: Dict[str, float],
                     ranked: List[Dict[str, Any]], event: Optional[str]) -> str:
    """生成 image #12 所需的详细分析过程。"""
    if not ranked:
        return "暂无对比标的。"
    best, worst = ranked[0], ranked[-1]
    bs = _safe(scores.get(best["code"]))
    ws = _safe(scores.get(worst["code"]))
    spread = bs - ws
    focus = {
        "短期": "动量、量能与近期涨跌幅",
        "长期": "趋势强度、形态稳定性与波动率",
        "价值": "市盈率(TTM)、总市值、市净率与股息率",
        "板块": "组内业务关联度与板块共振",
        "资金": "主力资金净流入与主力占比",
        "业绩": "订单催化与盈利质量代理分",
        "政策": "政策敏感行业属性与题材导向",
        "宏观": "价格弹性（波动率）与大盘敏感度",
        "微观": "技术结构（均线排列、趋势强度）",
        "事件": f"事件「{event or ''}」的业务关联度与利好/利空立场",
    }.get(method, "综合评分")

    def _dim(r):
        s = r.get("scores", {})
        if method == "短期":
            return f"动量{s.get('momentum', 0):.0f} / 量能{s.get('volume', 0):.0f} / 涨跌幅{r.get('chg_pct', 0):+.1f}%"
        if method == "长期":
            return f"趋势{s.get('trend', 0):.0f} / 形态{s.get('pattern', 0):.0f} / 弹性{_safe(r.get('elasticity'), 0):.0f}%"
        if method == "价值":
            cap = r.get("market_cap")
            pe = r.get("pe_ttm")
            pb = r.get("pb")
            dv = r.get("dv_ttm")
            parts = []
            if cap:
                parts.append(f"市值{cap:.0f}亿")
            if pe:
                parts.append(f"PE {pe:.1f}")
            if pb:
                parts.append(f"PB {pb:.2f}")
            if dv:
                parts.append(f"股息{dv:.2f}%")
            return " / ".join(parts) if parts else "估值数据未获取"
        if method == "板块":
            return f"业务关联度 {_safe(r.get('business_corr'), 0):.0f}"
        if method == "业绩":
            return f"催化分 {_safe(r.get('catalyst', 50), 0):.0f}"
        if method == "宏观":
            return f"年化弹性 {_safe(r.get('elasticity'), 0):.0f}%"
        if method == "资金":
            mn = r.get("fund_main_net")
            mp = r.get("fund_main_net_pct")
            if mn is not None:
                yi = mn / 1e8
                return f"主力净流入 {yi:.2f}亿（{_fmt_pct(mp)}）"
            return "资金数据未获取"
        if method == "微观":
            return f"趋势{s.get('trend', 0):.0f} / 动量{s.get('momentum', 0):.0f}"
        if method == "事件":
            rel, stance = _event_stance(r, event)
            return f"关联度{rel:.0f} · {stance}"
        return f"综合{s.get('composite', 0):.0f}"

    why_best = _dim(best)
    why_worst = _dim(worst)
    action = (
        f"建议优先关注 <b>{best['name']}</b>，其在【{method}】维度得分 {bs:.0f} 领先；"
        f"<b>{worst['name']}</b> 得分 {ws:.0f} 偏弱，可作为反向观察或等待修复信号。"
    )
    return (
        f'本维度以【{method}】为核心，重点关注{focus}。'
        f'得分分布上，<b>{best["name"]}</b> 以 {bs:.0f} 分居首，'
        f'核心支撑为 {why_best}；'
        f'<b>{worst["name"]}</b> 以 {ws:.0f} 分垫底，关键短板为 {why_worst}。'
        f'组内分差 {spread:.0f} 分，{"区分度明显" if spread >= 15 else "区分度一般"}。{action}'
    )

def _method_score_badge(r: Dict[str, Any], method: str,
                        scores: Dict[str, float], event: Optional[str] = None) -> str:
    """方法维度下的分数徽章（BUY/HOLD/WATCH）。"""
    s = _safe(scores.get(r["code"]))
    if method == "事件":
        rel, stance = _event_stance(r, event)
        label = f"{rel:.0f} · {stance}"
        cls = "win" if stance == "利好" else ("weak" if stance == "利空" else "neu")
    else:
        if s >= 70:
            label = f"{s:.0f}分 · 看多(BUY)"
            cls = "win"
        elif s <= 40:
            label = f"{s:.0f}分 · 谨慎(WATCH)"
            cls = "weak"
        else:
            label = f"{s:.0f}分 · 持有(HOLD)"
            cls = "mid"
    return f'<span class="score-badge {cls}">{label}</span>'

def _method_vs_box(r: Dict[str, Any], other: Dict[str, Any], method: str,
                   scores: Dict[str, float], event: Optional[str] = None) -> str:
    """方法对比单卡：用于 build_method_card 的左右两列。"""
    sr = _safe(scores.get(r["code"]))
    so = _safe(scores.get(other["code"]))
    win = sr >= so
    cls = "b" if win else "o"
    verdict = f"{'领先' if win else '落后'} {other['name']}（{sr:.0f} vs {so:.0f}）"
    s = r.get("scores", {})
    lis = []
    if method == "短期":
        lis.append(f"动量 <b>{s.get('momentum', 0):.0f}</b> · 量能 <b>{s.get('volume', 0):.0f}</b>")
        lis.append(f"近期涨跌幅 <b>{r.get('chg_pct', 0):+.1f}%</b>")
    elif method == "长期":
        lis.append(f"趋势 <b>{s.get('trend', 0):.0f}</b> · 形态 <b>{s.get('pattern', 0):.0f}</b>")
        lis.append(f"年化弹性 <b>{_safe(r.get('elasticity'), 0):.0f}%</b>")
    elif method == "价值":
        cap = r.get("market_cap")
        pe = r.get("pe_ttm")
        pb = r.get("pb")
        dv = r.get("dv_ttm")
        if cap:
            lis.append(f"总市值 <b>{cap:.0f}亿</b>")
        else:
            lis.append("总市值未获取")
        if pe:
            lis.append(f"TTM市盈率 <b>{pe:.1f}</b>")
        else:
            lis.append("TTM市盈率未获取")
        if pb:
            lis.append(f"市净率 <b>{pb:.2f}</b>")
        if dv is not None:
            lis.append(f"股息率 <b>{dv:.2f}%</b>")
    elif method == "资金":
        mn = r.get("fund_main_net")
        mp = r.get("fund_main_net_pct")
        if mn is not None:
            yi = mn / 1e8
            lis.append(f"主力净流入 <b>{yi:.2f}亿</b>（{_fmt_pct(mp)}）")
        else:
            lis.append("主力资金数据未获取")
        sig = r.get("signal", "持有")
        lis.append(f"信号 <b>{sig}</b>")
    elif method == "板块":
        lis.append(f"业务关联度 <b>{_safe(r.get('business_corr'), 0):.0f}</b>")
        lis.append(f"行业 <b>{r.get('industry') or '未知行业'}</b>")
    elif method == "业绩":
        lis.append(f"催化分 <b>{_safe(r.get('catalyst', 50), 0):.0f}</b>")
        lis.append(f"综合评分 <b>{s.get('composite', 0):.0f}</b>")
    elif method == "政策":
        ind = r.get("industry") or ""
        friendly = "政策敏感" if any(k in ind for k in _POLICY_FRIENDLY) else "政策中性"
        lis.append(f"行业属性 <b>{friendly}</b>")
        lis.append(f"综合评分 <b>{s.get('composite', 0):.0f}</b>")
    elif method == "宏观":
        lis.append(f"年化弹性 <b>{_safe(r.get('elasticity'), 0):.0f}%</b>")
    elif method == "微观":
        lis.append(f"趋势 <b>{s.get('trend', 0):.0f}</b> · 动量 <b>{s.get('momentum', 0):.0f}</b>")
    elif method == "事件":
        rel, stance = _event_stance(r, event)
        lis.append(f"事件关联度 <b>{rel:.0f}</b>")
        lis.append(f"事件立场 <b>{stance}</b>")
    else:
        lis.append(f"综合评分 <b>{s.get('composite', 0):.0f}</b>")
    sig = r.get("signal", "持有")
    lis.append(f"信号 <b>{sig}</b>")
    lis_html = "".join(f"<li>{x}</li>" for x in lis)
    return f"""
<div class="vsbox">
  <h3>{r['name']} <span style="font-weight:500;font-size:12px;color:{_sf()['txt2']}">{r['code']}</span>
    <span class="type">· {_stock_type_label(r)}</span>
  </h3>
  <div class="score-row">{_method_score_badge(r, method, scores, event)} <span class="verdict {cls}">{verdict}</span></div>
  <ul>{lis_html}</ul>
</div>"""

def _method_pair_conclusion(a: Dict[str, Any], b: Dict[str, Any], method: str,
                            scores: Dict[str, float], event: Optional[str]) -> str:
    """星辰分析师口吻：方法维度下 top2 标的对比结论。"""
    sa = _safe(scores.get(a["code"]))
    sb = _safe(scores.get(b["code"]))
    spread = sa - sb
    focus = {
        "短期": "动量、量能与近期涨跌幅",
        "长期": "趋势强度、形态稳定性与波动率",
        "价值": "市盈率(TTM)、总市值、市净率与股息率",
        "板块": "组内业务关联度与板块共振",
        "资金": "主力资金净流入与主力占比",
        "业绩": "订单催化与盈利质量代理分",
        "政策": "政策敏感行业属性与题材导向",
        "宏观": "价格弹性（波动率）与大盘敏感度",
        "微观": "技术结构（均线排列、趋势强度）",
        "事件": f"事件「{event or ''}」的业务关联度与利好/利空立场",
    }.get(method, "综合评分")
    return (
        f"<b>结论：</b>从【{method}】维度看，<b>{a['name']}</b>（{sa:.0f}分）"
        f"{'明显优于' if spread >= 15 else '优于'}<b>{b['name']}</b>（{sb:.0f}分），"
        f"分差 {spread:.0f} 分，{'区分度明显' if spread >= 15 else '区分度一般'}。"
        f"本维度重点关注{focus}，{a['name']} 在{focus.split('、')[0].split('(')[0]}上表现更优，"
        f"可作为{method}视角下的首选；{b['name']} 相对偏弱，建议作为对照观察或等待信号修复。"
        f"以上仅为模型推演，不构成投资建议。"
    )

def build_method_card(rows: List[Dict[str, Any]], method: str,
                      event: Optional[str] = None) -> str:
    """单个对比方法的卡片：图4 左右对比 + 星辰分析师结论。"""
    scores = compute_method_scores(rows, method, event)
    ranked = _ranked(rows, scores)
    if len(ranked) < 2:
        return (f'<div class="card"><h2>对比方法 · {method}</h2>'
                f'<div class="note">标的不足 2 只，无法生成对比。</div></div>')
    a, b = ranked[0], ranked[1]
    va = _method_vs_box(a, b, method, scores, event)
    vb = _method_vs_box(b, a, method, scores, event)
    summary = _method_summary(rows, method, scores, event)
    conclusion = _method_pair_conclusion(a, b, method, scores, event)
    return f"""
<div class="card">
  <h2>★ 星辰 · 多市场智能股票分析师：对比方法 · {method}</h2>
  <div class="one-line">{summary}</div>
  <div class="vs">{va}{vb}</div>
  <div class="alert cat">{conclusion}</div>
</div>
"""

def build_aggregate_card(rows: List[Dict[str, Any]],
                         event: Optional[str] = None) -> str:
    """底部大汇总：九维对比结论表格。"""
    if not rows:
        return ('<div class="card"><h2>大汇总 · 九维对比结论</h2>'
                '<div class="note">暂无对比标的，无法生成汇总。</div></div>')
    tr = []
    for m in METHODS:
        ev = event if m == "事件" else None
        scores = compute_method_scores(rows, m, ev)
        ranked = _ranked(rows, scores)
        best, worst = ranked[0], ranked[-1]
        bs = _safe(scores.get(best["code"]))
        ws = _safe(scores.get(worst["code"]))
        summary = _method_summary(rows, m, scores, ev)
        plain = re.sub(r"<[^>]+>", "", summary)
        # 截断过长的结论，保持表格整洁
        if len(plain) > 60:
            plain = plain[:58] + "…"
        tr.append(
            f'<tr><td class="l"><b>{m}</b></td>'
            f'<td class="up">{best["name"]} ({bs:.0f})</td>'
            f'<td class="down">{worst["name"]} ({ws:.0f})</td>'
            f'<td class="l">{plain}</td></tr>'
        )
    return f"""
<div class="card">
  <h2>大汇总 · 九维对比结论</h2>
  <table class="aggregate-table">
    <thead><tr><th>维度</th><th>占优标的</th><th>偏弱标的</th><th>关键结论</th></tr></thead>
    <tbody>{''.join(tr)}</tbody>
  </table>
  <div class="note">以上为各对比维度（短期/长期/价值/板块/业绩/政策/宏观/微观/事件）的分别结论汇总，
  综合研判时建议结合多维度信号、控制好仓位，并关注组内集体异动风险。</div>
</div>
"""
