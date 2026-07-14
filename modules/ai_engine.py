"""
modules/ai_engine.py
-------------------
星辰 AI 独立分析引擎：不依赖其他模块运行结果，自己也能基于量价/基本面/事件
给出见解；同时也支持结合当前页面上下文做更具体的分析。

v2 变更：
- 增加 LLM 层（OpenAI 兼容接口），回答问题更自然、更能处理开放式/非股票问题；
- 未配置 LLM 时回退到规则模板，模板本身也优化了措辞与覆盖面；
- 改进股票解析歧义处理（“相关股票”“哪个更好”等都能识别多只）。
"""
from __future__ import annotations

import re
import pandas as pd
from typing import Any, Dict, List, Optional

from modules.fetcher import StockFetcher
from modules.analysis_engine import run_analysis
from modules import llm_client

# 事件 / 新闻类提问关键词
EVENT_KW = ["事件", "新闻", "公告", "消息", "舆情", "资讯", "报道", "利好", "利空", "最近发生", "近期"]


def _extract_codes_or_names(question: str) -> List[str]:
    """从问题中提取 6 位代码或候选名称。"""
    # 6 位数字代码
    codes = re.findall(r"\b\d{6}\b", question)
    # 可能的中文名（简单 heuristic：连续 2-8 个汉字）
    names = re.findall(r"[\u4e00-\u9fa5]{2,8}", question)
    # 把「A 和 B 哪个更好」这种并列结构也拆出来
    for sep in ["和", "与", "、", " vs ", " VS ", " vs. ", " VS. "]:
        if sep in question:
            for part in question.split(sep):
                m = re.search(r"[\u4e00-\u9fa5]{2,8}", part)
                if m:
                    names.append(m.group(0))
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


def _resolve_multiple(question: str) -> List[Dict[str, str]]:
    """解析问题中可能提到的多只股票，并去重。"""
    queries = _extract_codes_or_names(question)
    resolved = []
    seen = set()
    for q in queries:
        # 过滤常见非股票词（如「哪个更好」「怎么」）
        if q in {"怎么样", "怎么", "哪个", "谁更", "更值", "值得买", "相关", "股票"}:
            continue
        r = _resolve_stock(q)
        if r and r["code"] not in seen:
            resolved.append(r)
            seen.add(r["code"])
    return resolved


def _independent_analysis(code: str) -> Dict[str, Any]:
    """独立拉取数据并运行分析。"""
    fetcher = StockFetcher()
    result = run_analysis(code, fetcher=fetcher)
    # 精简：后台返回时不需要完整 DataFrame，只留关键指标
    slim = {k: v for k, v in result.items() if k != "df"}
    slim["ticker"] = code
    return slim


def _fetch_news(code: str, name: str, limit: int = 4) -> List[Dict[str, str]]:
    """拉取个股近期新闻/公告（按名称检索，回退代码），返回 [{date,title,source}]。"""
    try:
        from modules.news import NewsFetcher

        nf = NewsFetcher()
        df = nf.fetch(keyword=name, source="auto", limit=limit)
        if df is None or df.empty:
            df = nf.fetch(keyword=code, source="auto", limit=limit)
        if df is None or df.empty:
            return []
        items = []
        for _, row in df.head(limit).iterrows():
            d = row.get("date")
            try:
                ds = pd.to_datetime(d).strftime("%m-%d") if d is not None and str(d) != "NaT" else ""
            except Exception:
                ds = ""
            items.append({
                "date": ds,
                "title": str(row.get("title", ""))[:60],
                "source": str(row.get("source", "")),
            })
        return items
    except Exception as e:  # noqa: BLE001
        print(f"[ai_engine] 新闻获取失败 ({code}): {e}")
        return []


def _format_analysis(name: str, result: Dict[str, Any], news: Optional[List[Dict[str, str]]] = None) -> str:
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

    # 近期要闻（事件 / 舆情）— 让结论「有依据」
    news_block = ""
    if news:
        lines = "\n".join(
            f"- （{n.get('date', '')}）{n.get('title', '')}（{n.get('source', '')}）"
            for n in news[:4]
        )
        if lines.strip():
            news_block = f"\n【近期要闻】\n{lines}\n"

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
{news_block}
【风险提示】
以上信号基于量价模型与新闻情绪推演，若大盘出现系统性波动或个股突发利空，需重新评估止损与仓位。*以上为模型推演，不构成投资建议，请独立决策并控制仓位。*"""


def _format_events(name: str, news: List[Dict[str, str]], result: Dict[str, Any]) -> str:
    """事件 / 舆情类提问的专项回答：列要闻 + 解读。"""
    verdict = result.get("verdict", "持有")
    if not news:
        return (
            f"**{name} · 事件 / 舆情追踪**\n\n"
            f"目前未检索到近期相关新闻（数据源暂不可用，或该标的公开报道较少）。"
            f"建议结合个股公告原文与技术面独立判断，避免仅凭传闻交易。"
            f"\n\n*以上为模型推演，不构成投资建议。*"
        )
    lines = "\n".join(
        f"- （{n.get('date', '')}）{n.get('title', '')}（{n.get('source', '')}）"
        for n in news[:5]
    )
    return f"""**{name} · 事件 / 舆情追踪**

【近期要闻】
{lines}

【解读】
需重点甄别「实质性催化」与「情绪扰动」：产能扩张 / 订单中标 / 政策扶持偏利好；
减持 / 监管问询 / 业绩下修偏利空。当前模型综合研判为「{verdict}」——
事件面须与量价趋势结合：若利好出现而股价未反应（量价背离），可能蕴含预期差机会；
若利好兑现却放量滞涨，则需警惕「利好出尽」。

*以上为模型推演，不构成投资建议，请独立决策并控制仓位。*"""


def _format_compare(items: List[Dict[str, Any]], news_map: Optional[Dict[str, List[Dict[str, str]]]] = None) -> str:
    """对 2~N 只股票做横向对比分析。"""
    if not items:
        return ""
    if len(items) == 1:
        news = (news_map or {}).get(items[0]["result"].get("ticker", "")) if news_map else None
        return _format_analysis(items[0]["name"], items[0]["result"], news=news)

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
        reason = (
            f"- **{it['name']}**：趋势「{trend}」、动量「{mom}」、量能「{vol}」；"
            f"情绪正面 {r.get('pos_pct',0):.0f}% / 负面 {r.get('neg_pct',0):.0f}%。"
        )
        if news_map:
            nm = news_map.get(r.get("ticker", ""))
            if nm:
                reason += f" 最新动态：{nm[0].get('title','')[:28]}…"
        reasons.append(reason)

    return f"""**横向对比：{' vs '.join(it['name'] for it in items)}**

【排序结果】
{header}

【关键差异】
{chr(10).join(reasons)}

【综合建议】
- 相对优势：**{best['name']}**（{best['result'].get('composite',0)} 分，{best['result'].get('verdict','')}），可作为优先关注标的。
- 相对劣势：**{worst['name']}**（{worst['result'].get('composite',0)} 分，{worst['result'].get('verdict','')}），建议谨慎或等待回调后再评估。

*以上为模型推演，不构成投资建议，请独立决策并控制仓位。*"""


# ═══════════════════════════════════════════════════════════════════════════
#  LLM 层：自然语言回答（OpenAI 兼容接口）
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是「星辰 AI」，一位专业的 A 股多市场智能分析师。你的任务是用自然、专业、有逻辑的中文回答用户的投资问题。

回答原则：
1. 基于提供的数据说话，不要编造股票代码或财务数据；
2. 个股诊断给出核心结论 + 关键观察 + 操作策略 + 风险提示；
3. 多股对比给出排序、关键差异、综合建议；
4. 事件/新闻类问题先列要闻，再区分「实质催化」与「情绪扰动」；
5. 开放式/非股票问题友好、简洁地回答，可解释你能做什么；
6. 若用户提到的标的无法解析或未上市，说明情况并给出可替代的分析对象；
7. 所有投资建议类结尾必须注明：*以上为模型推演，不构成投资建议。*

使用 markdown：标题加粗、要点列表、引用块。"""


def _build_llm_prompt(
    question: str,
    resolved: List[Dict[str, str]],
    history_stock: Optional[Dict[str, str]],
    rows: Optional[List[Dict[str, Any]]],
    analysis: Optional[Dict[str, Any]],
    is_event_q: bool,
) -> str:
    """把本地数据汇总成一段给 LLM 的上下文。"""
    blocks = []

    # 解析到的股票与其分析
    if resolved:
        blocks.append("【已解析股票】")
        for r in resolved:
            try:
                res = _independent_analysis(r["code"])
                news = _fetch_news(r["code"], r["name"])
                blocks.append(_format_analysis(r["name"], res, news=news))
            except Exception as e:
                blocks.append(f"- {r['name']}（{r['code']}）：分析失败，{e}")

    # 追问历史股票
    if history_stock and not resolved:
        blocks.append(f"【用户此前在问的股票】{history_stock['name']}（{history_stock['code']}）")
        try:
            res = _independent_analysis(history_stock["code"])
            news = _fetch_news(history_stock["code"], history_stock["name"])
            if is_event_q:
                blocks.append(_format_events(history_stock["name"], news, res))
            else:
                blocks.append(_format_analysis(history_stock["name"], res, news=news))
        except Exception as e:
            blocks.append(f"分析失败：{e}")

    # 当前页面组合上下文
    if rows:
        blocks.append("【当前页面对比组合】")
        for r in rows:
            blocks.append(
                f"- {r['name']}：综合评分 {r['scores'].get('composite',0)} 分，信号 {r.get('signal','—')}，"
                f"收盘价 {r.get('close',0):.2f}"
            )

    # 当前页面个股上下文
    if analysis and isinstance(analysis, dict):
        name = analysis.get("display_name") or analysis.get("ticker", "")
        blocks.append(f"【当前页面个股】{name}")
        code = analysis.get("ticker", "")
        if code:
            news = _fetch_news(code, name)
        else:
            news = None
        blocks.append(_format_analysis(name, analysis, news=news))

    # 用户意图
    blocks.append("【用户意图】")
    if is_event_q:
        blocks.append("这是事件/新闻/舆情类提问，请重点解读事件实质影响。")
    else:
        blocks.append("按问题本身意图作答，可结合数据给出研判或操作建议。")

    blocks.append(f"\n用户问题：{question}")
    return "\n\n".join(blocks)


def _fallback_general_answer(question: str) -> str:
    """未配置 LLM、且未解析到股票时的通用回答。"""
    q = question.strip()
    if any(k in q for k in ["你好", "你是谁", "你能做什么", "有什么功能", "可以做什么"]):
        return (
            "你好，我是 **🌟 星辰 AI** —— 你的 A股分析搭档。\n\n"
            "我可以帮你：\n"
            "- **个股诊断**：输入股票代码或名称，拉取最新行情、技术面、新闻情绪给出研判；\n"
            "- **横向对比**：同时问多只股票，自动排序并指出优劣；\n"
            "- **事件解读**：追踪近期新闻、公告，区分实质催化与情绪扰动；\n"
            "- **持仓建议**：结合当前市场与组合给出操作建议。\n\n"
            "请直接输入股票代码或名称，例如：\n"
            "- 600667\n"
            "- 太极实业怎么样\n"
            "- 深科技和贵州茅台谁更值得买\n\n"
            "*以上为模型推演，不构成投资建议。*"
        )
    if any(k in q for k in ["谢谢", "再见", "拜拜"]):
        return "不客气，有任何投资问题随时找我聊。祝投资顺利！"
    return (
        "我目前理解你的问题，但没找到明确的 A 股标的。\n\n"
        "你可以这样问我：\n"
        "- **个股诊断**：「太极实业 600667 怎么样？」\n"
        "- **横向对比**：「对比贵州茅台和五粮液谁更值得买？」\n"
        "- **事件解读**：「最近半导体有哪些重要事件？」\n"
        "- **持仓建议**：「当前市场环境下适合建仓吗？」\n\n"
        "*以上为模型推演，不构成投资建议。*"
    )


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
    resolved = _resolve_multiple(question)

    # 2) 从对话历史里尝试找上一只股票（用于追问「那风险在哪？」这种）
    history_stock = None
    if not resolved and history:
        for h in reversed(history):
            if h.get("role") == "user":
                resolved_hist = _resolve_multiple(h.get("content", ""))
                if resolved_hist:
                    history_stock = resolved_hist[0]
                    break

    # 辅助：从对话历史中生成简短追问提示
    def _continuity_prefix():
        prev_user = [h.get("content", "") for h in history if h.get("role") == "user"]
        if prev_user:
            return f"> 💬 结合你此前关于「{'、'.join(prev_user[-2:])}」的提问，进一步分析：\n\n"
        return ""

    # 事件 / 新闻类提问标识
    is_event_q = any(k in question for k in EVENT_KW)

    # 3) LLM 路径（若配置）：把数据丢给 LLM，让它自然回答
    if llm_client.is_configured():
        llm_prompt = _build_llm_prompt(question, resolved, history_stock, rows, analysis, is_event_q)
        answer = llm_client.answer_with_llm(SYSTEM_PROMPT, llm_prompt, history=history)
        if answer:
            return {"answer": answer, "independent": True}
        # LLM 调用失败则回退到规则模板

    # 4) 规则模板路径
    # 4a) 用户明确提到了多只具体股票 → 横向对比
    if len(resolved) >= 2:
        items = [{"name": r["name"], "result": _independent_analysis(r["code"])} for r in resolved]
        news_map = {
            it["result"].get("ticker", ""): _fetch_news(it["result"].get("ticker", ""), it["name"])
            for it in items
        }
        answer = _continuity_prefix() + _format_compare(items, news_map=news_map)
        return {"answer": answer, "independent": True}

    # 4b) 用户明确提到了单只股票 → 直接独立分析（事件类提问走专项解读）
    if len(resolved) == 1:
        independent = _independent_analysis(resolved[0]["code"])
        news = _fetch_news(resolved[0]["code"], resolved[0]["name"])
        if is_event_q:
            answer = _continuity_prefix() + _format_events(resolved[0]["name"], news, independent)
        else:
            answer = _continuity_prefix() + _format_analysis(resolved[0]["name"], independent, news=news)
        return {"answer": answer, "independent": True}

    # 4c) 追问型问题（没有新股票）但历史里提到过股票 → 延续分析该股票
    if history_stock:
        independent = _independent_analysis(history_stock["code"])
        news = _fetch_news(history_stock["code"], history_stock["name"])
        answer = (
            f"> 💬 你此前问过「{history_stock['name']}」，针对「{question}」继续分析：\n\n"
            + _format_analysis(history_stock["name"], independent, news=news)
        )
        return {"answer": answer, "independent": True}

    # 4d) 没有解析到股票，才使用当前页面上下文
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
        code = analysis.get("ticker", "") or ""
        news = _fetch_news(code, name) if code else None
        parts.append(f"**当前个股：{name}**\n\n" + _format_analysis(name, analysis, news=news))

    if parts:
        answer = _continuity_prefix() + "\n\n".join(parts)
        return {"answer": answer, "independent": False}

    # 4e) 什么都没有：简短直接引导
    return {
        "answer": _fallback_general_answer(question),
        "independent": True,
    }
