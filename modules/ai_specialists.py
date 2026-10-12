"""modules/ai_specialists.py —— 星辰 AI 专家分工编排（T-271，规则版 Multi-Agent）。

对标说明（用户给的 Agent 平台能力清单）
--------------------------------------
* 多 Agent 协作：LLM 场景下是「项目经理/查资料/写稿/校对」分工；本项目未接 LLM，
  采用**规则版专家分工**——按问题性质分派给不同「专家 persona」，每个专家有
  独立的分析框架、触发词与数据路由，回答用户问题时给出**该专家视角的结构化
  分析框架**而非千篇一律的兜底模板。这是无 LLM 约束下 Multi-Agent 的诚实实现：
  分工是真的（不同专家不同框架不同数据路由），「智能」边界如实标注。
* Tool/MCP：专家的回答中声明各自依赖的工具（mcp_server 网关已实现统一调用），
  前端可据此路由到对应数据卡——工具层已有，本模块补「谁该用哪些工具」的分派层。

红线
----
* 专家回答只包含「分析框架 + 数据路由指引」，**绝不编造行情/结论**（无数据时
  如实说需要什么输入）；个股诊断类问题仍由 ai_engine 数据链路（有真实取数）承担。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SPECIALISTS: List[Dict[str, Any]] = [
    {
        "id": "tech", "name": "技术面分析师", "icon": "📈",
        "trigger": ["技术面", "均线", "趋势", "形态", "支撑", "压力", "突破", "回调",
                    "金叉", "死叉", "背离", "量价", "K线形态", "怎么分析走势"],
        "tools": ["analyze_technical", "get_kline", "get_realtime_quote"],
        "framework": (
            "**技术面分析框架（本专家的看图顺序）：**\n"
            "1. **趋势定位**——MA5/MA10/MA20 多空排列，价格在年线上方还是下方（先定大方向再看入场）；\n"
            "2. **动量与背离**——MACD 金叉/死叉的位置（零轴上/下）与顶/底背离（背离信号优先于金叉）；\n"
            "3. **量价配合**——放量上涨有效、缩量上涨存疑、放巨量滞涨警惕；\n"
            "4. **关键位**——前高/前低/密集交易区即支撑压力，ATR 定波动预期。\n\n"
            "把股票代码发我（如「600667 技术面」），我调 analyze_technical 拉真实指标逐条对照。"
        ),
    },
    {
        "id": "event", "name": "事件解读员", "icon": "📰",
        "trigger": ["公告", "利好", "利空", "事件", "消息面", "出什么事", "解读一下", "影响多大", "预期"],
        "tools": ["stock_news", "event_factor"],
        "framework": (
            "**事件解读框架（三问定实质）：**\n"
            "1. **影响利润还是仅情绪？**——订单/产能/并购可量化进估值；口号/战略合作多数只有情绪；\n"
            "2. **持续性多长？**——一次性补贴 vs 长期订单，前者只影响一个季度；\n"
            "3. **是否已被抢跑？**——公告前已大涨 = 预期兑现（利好出尽），低位突袭才有预期差。\n\n"
            "结合本平台：54 页「事件驱动看多榜」按 EV 因子排序，事件因子把公告/舆情量化后并入预测信号。"
        ),
    },
    {
        "id": "risk", "name": "风控官", "icon": "🛡️",
        "trigger": ["风险", "排雷", "雷", "安全", "回撤", "爆仓", "质押", "商誉", "减持"],
        "tools": ["risk_assess", "risk_scan"],
        "framework": (
            "**风控官排查清单（按杀伤力排序）：**\n"
            "1. **生存风险**——*ST/面值退市/审计非标（这类直接一票否决，不看便宜）；\n"
            "2. **财报质量**——商誉占净资产比、应收账款增速 vs 营收增速、存贷双高；\n"
            "3. **股东行为**——大股东质押率>70%、清仓式减持、解禁临期；\n"
            "4. **仓位保护**——单票上限、止损纪律（T+1 下隔夜跳空只能靠仓位兜）。\n\n"
            "结合本平台：荐股引擎 R1 六维排雷二道闸（stock_risk.scan_many）自动硬踢红旗标的，输入代码即可体检。"
        ),
    },
    {
        "id": "position", "name": "仓位顾问", "icon": "⚖️",
        "trigger": ["仓位", "买多少", "配仓", "加仓", "减仓", "资金分配", "满仓", "半仓"],
        "tools": ["portfolio_query"],
        "framework": (
            "**仓位顾问的配仓逻辑（本项目现役引擎同款）：**\n"
            "1. **先定总敞口**——由市场状态（牧羊人温度/广度）给市场建议仓位，情绪过热主动降；\n"
            "2. **再分单票**——信念维（信号强度归一 [0.6,1.5] 倍）× 风险维（排雷/陷阱分扣减），单票 clamp [1%,20%]；\n"
            "3. **预算守恒**——多看好不等于加杠杆，总敞口不超市场建议；\n"
            "4. **留子弹**——极端行情保留现金，T+1 下现金是唯一的日内纠错工具。\n\n"
            "结合本平台：54 页决策面板给出市场建议仓位，45 页持仓中心看组合集中度。"
        ),
    },
    {
        "id": "compare", "name": "对比分析师", "icon": "⚔️",
        "trigger": ["对比", "哪个好", "谁更", "比较", "vs", "VS", "还是"],
        "tools": ["analyze_technical", "get_realtime_quote"],
        "framework": (
            "**对比分析师的横评维度（同框架才可比）：**\n"
            "1. **同行业**才比估值（PE/PB 分位）；不同行业比成长与盈利质量；\n"
            "2. **趋势强度**——相对大盘 20 日强度（跑赢/跑输），而非绝对涨幅；\n"
            "3. **量价健康度**——谁在放量上攻、谁在缩量阴跌；\n"
            "4. **风险面**——谁的排雷报告更干净。\n\n"
            "把两只代码一起发我（如「600667 和 000001 对比」），走数据链路逐维横评并排序。"
        ),
    },
]


def dispatch(question: str) -> Optional[Dict[str, Any]]:
    """按问题性质分派专家：返回 {'specialist_id','name','icon','answer','tools'} 或 None。

    打分 = 触发词命中数；命中最多且 ≥1 的专家胜出；无命中返回 None
    （调用方继续原兜底）。回答只含「专家分析框架 + 数据路由」，不编造数据。
    """
    q = (question or "").strip()
    if not q:
        return None
    best = None
    for sp in SPECIALISTS:
        hits = sum(1 for kw in sp["trigger"] if kw.lower() in q.lower())
        if hits <= 0:
            continue
        if best is None or hits > best["_hits"]:
            best = {"_hits": hits, **sp}
    if best is None:
        return None
    answer = (
        f"{best['icon']} **{best['name']}** 就位。\n\n{best['framework']}"
    )
    return {
        "specialist_id": best["id"],
        "name": best["name"],
        "icon": best["icon"],
        "answer": answer,
        "tools": best["tools"],
    }


def list_specialists() -> list[dict]:
    """专家清单自省（供 FastAPI /api/ai/agents 与测试）。"""
    return [{"id": s["id"], "name": s["name"], "icon": s["icon"],
             "tools": s["tools"], "triggers": len(s["trigger"])} for s in SPECIALISTS]
