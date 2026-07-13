"""
modules/ai_engine.py
-------------------
星辰 AI 独立分析引擎：不依赖其他模块运行结果，自己也能基于量价/基本面/事件
给出见解；同时也支持结合当前页面上下文做更具体的分析。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from modules.fetcher import StockFetcher
from modules.analysis_engine import run_analysis


def _extract_codes_or_names(question: str) -> List[str]:
    """从问题中提取 6 位代码或候选名称。"""
    # 6 位数字代码
    codes = re.findall(r"\b\d{6}\b", question)
    # 可能的中文名（简单 heuristic：连续 2-8 个汉字）
    names = re.findall(r"[\u4e00-\u9fa5]{2,8}", question)
    return list(dict.fromkeys(codes + names))


def _resolve_stock(query: str) -> Optional[Dict[str, str]]:
    """把代码/名称/拼音解析成标准代码 + 名称。"""
    fetcher = StockFetcher()
    # 先尝试直接作为 6 位代码
    clean = str(query).strip().zfill(6)
    if len(clean) == 6 and clean.isdigit():
        try:
            _, name = fetcher.get_stock_basic(clean)
            if name and name != clean:
                return {"code": clean, "name": name}
        except Exception:
            pass
    # 名称搜索
    try:
        matches = fetcher.search_stocks(query, limit=5)
        if matches:
            return {"code": matches[0]["code"], "name": matches[0].get("name", query)}
    except Exception:
        pass
    # 兜底：返回 None，让 AI 给通用回复
    return None


def _independent_analysis(code: str) -> Dict[str, Any]:
    """独立拉取数据并运行分析。"""
    fetcher = StockFetcher()
    result = run_analysis(code, fetcher=fetcher)
    # 精简：后台返回时不需要完整 DataFrame，只留关键指标
    slim = {k: v for k, v in result.items() if k != "df"}
    slim["ticker"] = code
    return slim


def _format_analysis(name: str, result: Dict[str, Any]) -> str:
    """把分析结果格式化为自然语言结论。"""
    verdict = result.get("verdict", "持有")
    composite = result.get("composite", 50)
    price = result.get("current_price", 0) or 0
    change = result.get("change_pct", 0) or 0
    entry = result.get("entry_price", 0) or 0
    target = result.get("target_price", 0) or 0
    stop = result.get("stop_price", 0) or 0
    pos_pct = result.get("pos_pct", 0) or 0
    neg_pct = result.get("neg_pct", 0) or 0
    industry = result.get("industry", "—")
    tech = result.get("technical", {})
    trend = tech.get("trend", {})
    momentum = tech.get("momentum", {})
    volume = tech.get("volume", {})
    trend_label = trend.get("trend_label", "—") if "error" not in trend else "数据不足"
    mom_label = momentum.get("momentum_label", "—") if "error" not in momentum else "—"
    vol_label = volume.get("volume_price_label", "—") if "error" not in volume else "—"

    lines = [
        f"**{name}（{result.get('ticker', '')}）独立研判**",
        "",
        f"- 现价 ¥{price:.2f}（{change:+.2f}%），行业：{industry}",
        f"- 综合评分 **{composite}** 分，研判：**{verdict}**",
        f"- 技术面：趋势「{trend_label}」、动量「{mom_label}」、量能「{vol_label}」",
        f"- 新闻情绪：正面 {pos_pct:.0f}% / 负面 {neg_pct:.0f}%",
        f"- 操作建议：{result.get('position_advice', '')}",
        f"- 关键价位：入场 ¥{entry:.2f} / 目标 ¥{target:.2f} / 止损 ¥{stop:.2f}",
    ]
    return "\n".join(lines)


def ai_answer(question: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    回答用户投资问题。

    - 如果 context 里有当前个股/对比结果，优先结合上下文。
    - 如果问题中包含股票代码/名称，独立拉取数据生成见解。
    - 否则给出通用说明。
    """
    context = context or {}
    rows = context.get("_cmp_rows")
    analysis = context.get("analysis_result")
    history = context.get("history") or []

    # 1) 尝试从问题解析股票
    queries = _extract_codes_or_names(question)
    resolved = None
    for q in queries:
        resolved = _resolve_stock(q)
        if resolved:
            break

    parts = []
    # 组合上下文
    if rows:
        names = "、".join(r["name"] for r in rows)
        avg = sum(r["scores"]["composite"] for r in rows) / len(rows)
        ranked = sorted(rows, key=lambda r: r["scores"]["composite"], reverse=True)
        best, worst = ranked[0], ranked[-1]
        buy_count = sum(1 for r in rows if r["signal"] == "买入")
        sell_count = sum(1 for r in rows if r["signal"] == "卖出")
        parts.append(
            f"**当前组合：{names}（共 {len(rows)} 只）**\n\n"
            f"- 平均综合评分：**{avg:.0f}** 分\n"
            f"- 最强标的：**{best['name']}（{best['scores']['composite']} 分，{best['signal']}）**\n"
            f"- 最弱标的：**{worst['name']}（{worst['scores']['composite']} 分，{worst['signal']}）**\n"
            f"- 信号分布：买入 {buy_count} / 持有 {len(rows) - buy_count - sell_count} / 卖出 {sell_count}\n\n"
            f"建议优先关注 **{best['name']}**，其在趋势/动量维度领先；"
            f"**{worst['name']}** 评分偏弱，建议谨慎。"
        )
    elif analysis and isinstance(analysis, dict):
        name = analysis.get("display_name") or analysis.get("ticker", "")
        parts.append(f"**当前个股：{name}**\n\n" + _format_analysis(name, analysis))

    # 独立分析（如果问题里提到了具体股票）
    if resolved:
        independent = _independent_analysis(resolved["code"])
        parts.append("\n\n" + _format_analysis(resolved["name"], independent))

    if not parts:
        # 没有组合 / 个股上下文，也没有解析出具体股票时，
        # 若之前有对话，主动呼应，让对话「可持续」。
        continuity = ""
        if history:
            prev = [h.get("content", "") for h in history if h.get("role") == "user"]
            if prev:
                continuity = (
                    "（接你前面对「" + "、".join(prev[-2:]) + "」的提问）"
                    if len(prev) <= 2 else
                    "（延续我们之前的多次讨论）"
                )
        return {
            "answer": (
                "**★ 星辰 · 多市场智能股票分析师**\n\n"
                f"关于「{question or '投资分析'}」{continuity}：我可以基于量价、基本面与事件催化为你做横向对比与归因。"
                "请进入「多股对比」组建组合，或在「个股分析」查看单只标的后再来问我；"
                "也可以直接输入股票代码/名称，我会独立拉取数据给出研判。\n\n"
                "*以上为模型推演，不构成投资建议。*"
            ),
            "independent": True,
        }

    continuity_prefix = ""
    if history:
        prev_user = [h.get("content", "") for h in history if h.get("role") == "user"]
        if prev_user:
            continuity_prefix = (
                f"> 💬 结合你此前关于「{'、'.join(prev_user[-2:])}」的提问，进一步分析：\n\n"
            )

    answer = continuity_prefix + "\n\n".join(parts) + "\n\n*以上为模型推演，不构成投资建议，请独立决策并控制仓位。*"
    return {"answer": answer, "independent": bool(resolved)}
