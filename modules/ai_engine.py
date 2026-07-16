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
import time
import threading
import pandas as pd
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from modules.fetcher import StockFetcher
from modules.analysis_engine import run_analysis
from modules import llm_client

# 事件 / 新闻类提问关键词
EVENT_KW = ["事件", "新闻", "公告", "消息", "舆情", "资讯", "报道", "利好", "利空", "最近发生", "近期"]


# ═══════════════════════════════════════════════════════════════════════════
#  结果缓存（性能优化：避免每次提问都重抓全量行情 + 重算技术面）
#  - 分析结果与新闻按代码缓存，TTL 内复用，同一标的多次追问近乎瞬时
#  - 进程内字典 + 单锁，线程安全（_build_llm_prompt 用线程池并发取数）
# ═══════════════════════════════════════════════════════════════════════════
_ANALYSIS_TTL = 90     # 行情类结果缓存 90s（会话内足够，又不过度陈旧）
_NEWS_TTL = 600        # 新闻缓存 10min
_CACHE: Dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def _cache_get(key: str, ttl: int):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and (time.time() - item[1]) < ttl:
            return item[0]
    return None


def _cache_set(key: str, val: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (val, time.time())


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


def _safe_eval(expr: str) -> Optional[float]:
    """仅对简单四则运算做安全求值（只允许数字、+ - * / 和括号）。"""
    if not re.match(r"^[0-9+\-*/().\s]+$", expr):
        return None
    try:
        return float(eval(expr, {"__builtins__": {}}, {}))
    except Exception:
        return None


def _quick_answer(question: str) -> Optional[str]:
    """
    对常见简单问题直接返回答案，避免走 LLM（网络/免费模型慢时体验差）。
    覆盖：问候、自我介绍、简单算术、常见常识。
    """
    q = question.strip().lower()
    q_no_space = q.replace(" ", "")

    # 问候与简单闲聊
    if q in {"你好", "您好", "hello", "hi", "在吗", "在嘛"}:
        return "你好！我是星辰 AI，可以帮你分析 A 股行情、个股基本面、行业对比，也可以解答投资问题。请直接告诉我你想了解的股票或问题～"

    if q in {"你是谁", "你是", "介绍一下", "你能做什么", "你会做什么"}:
        return "我是 **星辰 AI**（StockSignal 内置分析助手），能帮你：\n\n- 分析个股技术面、基本面、消息面\n- 对比多只股票\n- 解读行业、板块、大盘主线\n- 回答投资相关问题\n\n你可以直接说股票代码或名称，比如「分析一下贵州茅台」或「600519 怎么样」。"

    # 简单算术（1+1=? / 2*(3+4)=? 等）
    math_match = re.match(r"^\s*([0-9+\-*/().\s]+)\s*=\s*\?\s*$", question.strip())
    if math_match:
        result = _safe_eval(math_match.group(1))
        if result is not None:
            return f"**{question.strip().rstrip('?').strip()} = {result:g}**\n\n这是一个简单的数学运算，答案是 **{result:g}**。"

    # 直接问 1+1（没有等号）
    if q_no_space in {"1+1", "1+1=", "1+1=?"} or re.match(r"^1\s*\+\s*1\s*=?\s*\??$", question.strip()):
        return "**1 + 1 = 2**\n\n答案是 **2**。"

    return None


def _raw_independent_analysis(code: str) -> Dict[str, Any]:
    """独立拉取数据并运行分析（无缓存原始版）。"""
    fetcher = StockFetcher()
    result = run_analysis(code, fetcher=fetcher)
    # 精简：后台返回时不需要完整 DataFrame，只留关键指标
    slim = {k: v for k, v in result.items() if k != "df"}
    slim["ticker"] = code
    return slim


def _independent_analysis(code: str) -> Dict[str, Any]:
    """带 TTL 缓存的独立分析；同一标的短时间内多次追问直接命中缓存。"""
    key = f"ai:analysis:{code}"
    cached = _cache_get(key, _ANALYSIS_TTL)
    if cached is None:
        cached = _raw_independent_analysis(code)
        _cache_set(key, cached)
    return cached


def _raw_fetch_news(code: str, name: str, limit: int = 4) -> List[Dict[str, str]]:
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


def _fetch_news(code: str, name: str, limit: int = 4) -> List[Dict[str, str]]:
    """带 TTL 缓存的新闻拉取；同一标的 10min 内复用，避免重复请求数据源。"""
    key = f"ai:news:{code}:{limit}"
    cached = _cache_get(key, _NEWS_TTL)
    if cached is None:
        cached = _raw_fetch_news(code, name, limit)
        _cache_set(key, cached)
    return cached


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


def _compact_block(name: str, result: Dict[str, Any], news: Optional[List[Dict[str, str]]], is_event_q: bool) -> str:
    """给 LLM 的精简数据块：只给关键指标，避免把规则引擎散文塞进上下文（省 token、提速）。"""
    if not isinstance(result, dict):
        return f"- {name}：无可用数据"
    tech = result.get("technical", {}) or {}
    trend = tech.get("trend", {}).get("trend_label", "—") if isinstance(tech, dict) else "—"
    mom = tech.get("momentum", {}).get("momentum_label", "—") if isinstance(tech, dict) else "—"
    vol = tech.get("volume", {}).get("volume_price_label", "—") if isinstance(tech, dict) else "—"
    lines = [
        f"- {name}（{result.get('ticker', name)}）：{result.get('verdict', '持有')}，"
        f"综合{result.get('composite', 50)}分，现价¥{(result.get('current_price', 0) or 0):.2f}"
        f"（{result.get('change_pct', 0) or 0:+.2f}%），行业{result.get('industry', '—')}",
        f"  技术：趋势「{trend}」/动量「{mom}」/量能「{vol}」；"
        f"情绪正面{result.get('pos_pct', 0) or 0:.0f}%/负面{result.get('neg_pct', 0) or 0:.0f}%",
        f"  策略：入场¥{(result.get('entry_price', 0) or 0):.2f}/目标¥{(result.get('target_price', 0) or 0):.2f}"
        f"/止损¥{(result.get('stop_price', 0) or 0):.2f}",
    ]
    if news:
        for n in news[:3]:
            lines.append(f"  要闻（{n.get('date', '')}）{n.get('title', '')}（{n.get('source', '')}）")
    return "\n".join(lines)


def _gather_one_stock(code: str, name: str):
    """并发单元：取单只股票的分析 + 新闻（内部各自有 TTL 缓存）。"""
    try:
        res = _independent_analysis(code)
        news = _fetch_news(code, name)
        return code, name, res, news
    except Exception:  # noqa: BLE001
        return code, name, None, []


def _build_llm_prompt(
    question: str,
    resolved: List[Dict[str, str]],
    history_stock: Optional[Dict[str, str]],
    rows: Optional[List[Dict[str, Any]]],
    analysis: Optional[Dict[str, Any]],
    is_event_q: bool,
) -> str:
    """把本地数据汇总成一段给 LLM 的上下文（并发取数 + 精简指标，省 token）。"""
    # 1) 收集所有需要取数的股票，去重
    jobs = [(r["code"], r["name"]) for r in resolved]
    if history_stock and not resolved:
        jobs.append((history_stock["code"], history_stock["name"]))
    if analysis and isinstance(analysis, dict) and analysis.get("ticker"):
        jobs.append((analysis["ticker"], analysis.get("display_name") or analysis.get("ticker", "")))
    seen = set()
    uniq = []
    for c, n in jobs:
        if c not in seen:
            seen.add(c)
            uniq.append((c, n))

    # 2) 并发拉取（分析/新闻内部各有 TTL 缓存）
    ctx_map: Dict[str, Any] = {}
    if uniq:
        with ThreadPoolExecutor(max_workers=min(6, len(uniq))) as ex:
            futs = {ex.submit(_gather_one_stock, c, n): (c, n) for c, n in uniq}
            for fut in as_completed(futs):
                c, _ = futs[fut]
                try:
                    code, name, res, news = fut.result()
                    ctx_map[code] = (name, res, news)
                except Exception:  # noqa: BLE001
                    pass

    blocks = []

    # 3) 组装上下文（用精简块，不用规则引擎散文）
    if resolved:
        blocks.append("【已解析股票】")
        for r in resolved:
            v = ctx_map.get(r["code"])
            if v:
                name, res, news = v
                blocks.append(_compact_block(name, res, news, is_event_q))
            else:
                blocks.append(f"- {r['name']}（{r['code']}）：分析失败")

    if history_stock and not resolved:
        v = ctx_map.get(history_stock["code"])
        if v:
            name, res, news = v
            blocks.append(f"【用户此前在问的股票】{name}（{history_stock['code']}）")
            blocks.append(_compact_block(name, res, news, is_event_q))

    if rows:
        blocks.append("【当前页面对比组合】")
        for r in rows:
            blocks.append(
                f"- {r['name']}：综合评分 {r['scores'].get('composite', 0)} 分，信号 {r.get('signal', '—')}，"
                f"收盘价 {r.get('close', 0):.2f}"
            )

    if analysis and isinstance(analysis, dict):
        code = analysis.get("ticker", "")
        name = analysis.get("display_name") or code
        blocks.append(f"【当前页面个股】{name}")
        v = ctx_map.get(code) if code else None
        if v:
            _, res, news = v
            blocks.append(_compact_block(name, res, news, is_event_q))
        else:
            blocks.append(_compact_block(name, analysis, None, is_event_q))

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

    # 0) 快速通道：简单问题直接回答，避免 LLM 等待
    quick = _quick_answer(question)
    if quick:
        return {"answer": quick, "independent": True}

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
        # 咨询场景专用超时：单模型 30s、整条链 ≤60s 即回退规则引擎（瞬时），
        # 免费模型排队或异常慢时快速 fallback，避免用户干等。
        answer = llm_client.answer_with_llm(
            SYSTEM_PROMPT, llm_prompt, history=history, max_tokens=900, timeout=30
        )
        if answer:
            return {"answer": answer, "independent": True}
        # LLM 调用失败/超时则回退到规则模板

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
