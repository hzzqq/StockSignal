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
    """把分析结果格式化为「智能分析师」风格结论，而非简单指标列表。"""
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
    advice = result.get("position_advice", "")

    #  verdict 对应颜色标签（纯文本）
    verdict_tag = verdict
    if verdict == "买入":
        verdict_tag = "偏多/买入"
    elif verdict == "卖出":
        verdict_tag = "偏空/卖出"
    elif verdict == "持有":
        verdict_tag = "中性/持有"

    # 趋势强度描述
    if composite >= 75:
        strength = "强势"
    elif composite >= 55:
        strength = "偏强"
    elif composite >= 45:
        strength = "中性"
    else:
        strength = "偏弱"

    return f"""**{name}（{result.get('ticker', '')}）· {verdict_tag} · 综合评分 {composite} 分**

【核心结论】
当前股价 **¥{price:.2f}**（{change:+.2f}%），所属行业 **{industry}**。综合评分 **{composite}** 分，整体趋势判定为 **{strength}**（{verdict}）。技术面呈现「{trend_label}」，动量「{mom_label}」，量能「{vol_label}」。近期新闻情绪正面 **{pos_pct:.0f}%** / 负面 **{neg_pct:.0f}%。

【关键观察】
1. **趋势结构**：{trend_label}。
2. **动量状态**：{mom_label}。
3. **量价配合**：{vol_label}。
4. **情绪/事件**：正面占比 {pos_pct:.0f}%，负面占比 {neg_pct:.0f}%。

【操作策略】
{advice}
- 参考入场：¥{entry:.2f}
- 目标价位：¥{target:.2f}
- 止损纪律：¥{stop:.2f}

【风险提示】
以上信号基于量价模型与新闻情绪推演，若大盘出现系统性波动或个股突发利空，需重新评估止损与仓位。*以上为模型推演，不构成投资建议，请独立决策并控制仓位。*"""


def _format_compare(items: List[Dict[str, Any]]) -> str:
    """对 2~N 只股票做横向对比分析。"""
    if not items:
        return ""
    if len(items) == 1:
        return _format_analysis(items[0]["name"], items[0]["result"])

    # 按综合评分排序
    ranked = sorted(items, key=lambda x: x["result"].get("composite", 50), reverse=True)
    best = ranked[0]
    worst = ranked[-1]

    header = "\n".join(
        f"{i+1}. **{it['name']}（{it['result'].get('ticker','')}）**："
        f"评分 {it['result'].get('composite',0)} 分，{it['result'].get('verdict','持有')}，"
        f"现价 ¥{it['result'].get('current_price',0):.2f}（{it['result'].get('change_pct',0):+.2f}%）"
        for i, it in enumerate(ranked)
    )

    reasons = []
    for it in ranked:
        r = it["result"]
        tech = r.get("technical", {})
        trend = tech.get("trend", {}).get("trend_label", "—")
        mom = tech.get("momentum", {}).get("momentum_label", "—")
        vol = tech.get("volume", {}).get("volume_price_label", "—")
        reasons.append(
            f"- **{it['name']}**：趋势「{trend}」、动量「{mom}」、量能「{vol}」；"
            f"情绪正面 {r.get('pos_pct',0):.0f}% / 负面 {r.get('neg_pct',0):.0f}%。"
        )

    return f"""**横向对比：{' vs '.join(it['name'] for it in items)}**

【排序结果】
{header}

【关键差异】
{chr(10).join(reasons)}

【综合建议】
- 相对优势：**{best['name']}**（{best['result'].get('composite',0)} 分，{best['result'].get('verdict','')}），可作为优先关注标的。
- 相对劣势：**{worst['name']}**（{worst['result'].get('composite',0)} 分，{worst['result'].get('verdict','')}），建议谨慎或等待回调后再评估。

*以上为模型推演，不构成投资建议，请独立决策并控制仓位。*"""


def ai_answer(question: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    回答用户投资问题。

    核心原则：用户问题里提到的股票优先于当前页面上下文。
    - 先解析问题中的股票代码/名称，若命中则回答这些股票（单只给深度研判，多只给横向对比）。
    - 若问题没提到股票，再看当前页面（组合/个股）上下文。
    - 若都没有，给出简短可用的引导，避免模板化废话。
    """
    context = context or {}
    rows = context.get("_cmp_rows")
    analysis = context.get("analysis_result")
    history = context.get("history") or []

    # 1) 从用户问题里提取股票（最高优先级）
    queries = _extract_codes_or_names(question)
    resolved = []
    seen = set()
    for q in queries:
        r = _resolve_stock(q)
        if r and r["code"] not in seen:
            resolved.append(r)
            seen.add(r["code"])

    # 2) 从对话历史里尝试找上一只股票（用于追问「那风险在哪？」这种）
    history_stock = None
    if not resolved and history:
        for h in reversed(history):
            if h.get("role") == "user":
                hq = _extract_codes_or_names(h.get("content", ""))
                for q in hq:
                    hsv = _resolve_stock(q)
                    if hsv:
                        history_stock = hsv
                        break
                if history_stock:
                    break

    # 辅助：从对话历史中生成简短追问提示
    def _continuity_prefix():
        prev_user = [h.get("content", "") for h in history if h.get("role") == "user"]
        if prev_user:
            return f"> 💬 结合你此前关于「{'、'.join(prev_user[-2:])}」的提问，进一步分析：\n\n"
        return ""

    # 3) 用户明确提到了多只具体股票 → 横向对比
    if len(resolved) >= 2:
        items = [{"name": r["name"], "result": _independent_analysis(r["code"])} for r in resolved]
        answer = _continuity_prefix() + _format_compare(items)
        return {"answer": answer, "independent": True}

    # 4) 用户明确提到了单只股票 → 直接独立分析
    if len(resolved) == 1:
        independent = _independent_analysis(resolved[0]["code"])
        answer = _continuity_prefix() + _format_analysis(resolved[0]["name"], independent)
        return {"answer": answer, "independent": True}

    # 5) 追问型问题（没有新股票）但历史里提到过股票 → 延续分析该股票
    if history_stock:
        independent = _independent_analysis(history_stock["code"])
        answer = (
            f"> 💬 你此前问过「{history_stock['name']}」，针对「{question}」继续分析：\n\n"
            + _format_analysis(history_stock["name"], independent)
        )
        return {"answer": answer, "independent": True}

    # 6) 没有解析到股票，才使用当前页面上下文
    parts = []
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

    if parts:
        answer = _continuity_prefix() + "\n\n".join(parts)
        return {"answer": answer, "independent": False}

    # 7) 什么都没有：简短直接引导
    return {
        "answer": (
            "你好，我是 **★ 星辰 AI**，可以帮你分析个股、对比组合或解读当前持仓。\n\n"
            "请直接输入股票代码或名称，例如：\n"
            "- 600667\n"
            "- 太极实业怎么样\n"
            "- 深科技和贵州茅台谁更值得买\n\n"
            "我会独立拉取最新数据并给出研判。*以上为模型推演，不构成投资建议。*"
        ),
        "independent": True,
    }
