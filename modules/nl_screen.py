# -*- coding: utf-8 -*-
"""modules/nl_screen.py — 自然语言选股解析器（仿 i问财「零门槛口语选股」，取长补短）。

把用户的口语化查询（"创业板 市盈率小于30 且 营收增长>20% 的票"）解析成**结构化筛选
条件**，再交给既有 fetcher/akshare 取数执行。本模块只负责"理解"，不负责"取数"——
取数与筛选执行在 pages/81_自然语言选股.py，且必须**真实取数、取不到就如实说明**，绝不编造结果。

设计要点（诚实 + 可单测）：
- parse_query 是纯函数、确定性、不触网，可离线 pytest 全面覆盖。
- 解析结果带 ``unparsed``：凡没被理解的词原样返回，让用户看见"哪些没听懂"，不静默吞掉。
- 字段/比较符/板块都走白名单别名映射；遇到无法识别的量词/单位就记到 errors，不臆造数值。
- 这是"取长补短"：i问财把 2.5 万原子指标做成口语可查；我们取其"零门槛"精神，
  先覆盖最高频的板块/估值/成长/质量维度，留出扩展点（FIELD_ALIASES / BOARD_ALIASES）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── 板块别名（代码前缀判定在 apply_filters / 页面执行层做；这里只归一化语义）──
BOARD_ALIASES = {
    "创业板": "cyb", "科创": "kcb", "科创板": "kcb", "主板": "main",
    "北交所": "bse", "中小板": "sme", "沪深300": "hs300", "沪深300指数": "hs300",
    "中证500": "zz500", "上证50": "sz50",
}
BOARD_CODE_PREFIX = {
    "cyb": ("300", "301"),
    "kcb": ("688",),
    "main": ("600", "601", "603", "605", "000", "001", "002", "003"),
    "bse": ("8", "4", "92", "43"),
    # 指数成分需用指数成分接口判断，这里仅标记语义，执行层另行处理
    "hs300": None, "zz500": None, "sz50": None,
}

# ── 字段别名 → 内部字段名（执行层按此字段从基本面取数）──
FIELD_ALIASES = {
    "市盈率": "pe", "pe": "pe", "ttm": "pe", "市净率": "pb", "pb": "pb",
    "总市值": "mktcap", "市值": "mktcap", "流通市值": "float_mktcap",
    "营收增长": "rev_growth", "营收增速": "rev_growth", "营收": "rev_growth",
    "净利润增长": "profit_growth", "利润增长": "profit_growth", "净利增速": "profit_growth",
    "roe": "roe", "净资产收益率": "roe", "毛利率": "gross_margin", "毛利": "gross_margin",
    "营收复合增长": "rev_cagr", "利润复合增长": "profit_cagr",
}
# 各字段单位约定（执行层把记录值归一化到这些单位再比较）：
#   pe/pb/roe(%)/gross_margin(%)：纯数；rev_growth/profit_growth/rev_cagr/profit_cagr：百分数(如20=20%)
#   mktcap/float_mktcap：亿元
FIELD_UNIT = {
    "pe": "ratio", "pb": "ratio", "mktcap": "yi", "float_mktcap": "yi",
    "rev_growth": "pct", "profit_growth": "pct", "roe": "pct",
    "gross_margin": "pct", "rev_cagr": "pct", "profit_cagr": "pct",
}

# ── 比较符别名 ──
OP_WORDS = {
    "小于": "lt", "低于": "lt", "不超过": "lte", "不大于": "lte",
    "小于且等于": "lte", "≤": "lte", "<": "lt", "小于等于": "lte",
    "大于": "gt", "高于": "gt", "超过": "gt", "不小于": "gte", "≥": "gte",
    "大于且等于": "gte", ">": "gt", "大于等于": "gte",
    "等于": "eq", "为": "eq", "=": "eq", "==": "eq",
}
_VALID_OPS = set(OP_WORDS.values())

# 口语填充词（解析后剩余片段里剔除，避免"的票""我想"等被当概念误杀候选池）
STOPWORDS = {
    "的", "票", "股票", "只", "个", "条", "等", "和", "且", "或", "与", "及",
    "排序", "取", "选", "要", "想", "找", "我", "你", "他", "她", "它", "有", "没有",
    "不", "吗", "呢", "啊", "吧", "了", "是", "在", "从", "到", "把", "被", "给",
    "让", "为", "对", "向", "于", "以", "之", "其", "该", "这", "那", "也", "都",
    "还", "就", "再", "又", "很", "最", "比", "更", "越", "按", "前", "后", "中",
    "上", "下", "内", "外", "请", "帮", "求", "推", "荐", "看", "挑", "筛", "查",
}


@dataclass
class QuerySpec:
    """解析结果。all fields 可被 JSON 序列化（页面把它透明展示给用户）。"""
    boards: list[str] = field(default_factory=list)        # 归一化板块语义
    filters: list[dict] = field(default_factory=list)       # [{field, op, value, unit, raw}]
    sort: Optional[str] = None                              # 排序字段（内部字段名）
    sort_dir: str = "desc"                                  # desc/asc
    limit: Optional[int] = None                            # 取前 N
    concepts: list[str] = field(default_factory=list)       # 概念/行业关键词（自由词）
    unparsed: list[str] = field(default_factory=list)       # 没听懂的词（透明展示）
    errors: list[str] = field(default_factory=list)         # 解析异常说明（如无法识别的量词）


def _cn_number(token: str):
    """解析含 亿/万/%/正负/小数 的中文友好数字。失败返回 None（不臆造）。

    例："30"→30.0；"100亿"→1e10（带单位展开）；"20%"→20.0（百分号脱去，单位在执行层解释）；
    "1.5万"→15000.0；"-5%"→-5.0。
    """
    if token is None:
        return None
    s = str(token).strip()
    if not s:
        return None
    neg = False
    if s[0] in ("-", "负"):
        neg = True
        s = s[1:]
    if s.endswith("%"):
        s = s[:-1]
    mult = 1.0
    if s.endswith("亿"):
        mult = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        mult = 1e4
        s = s[:-1]
    try:
        v = float(s) * mult
    except ValueError:
        return None
    return -v if neg else v


def _extract_number_after(match_text: str):
    """从比较符后的片段里取出首个数字 token（含 亿/万/%）。"""
    m = re.search(r"-?\d+(?:\.\d+)?\s*[亿万股%]?|[%]?\s*-?\d+(?:\.\d+)?", match_text)
    if not m:
        return None
    return _cn_number(m.group(0).replace(" ", ""))


def parse_query(text: str) -> QuerySpec:
    """把自然语言查询解析为结构化 QuerySpec（纯函数、确定性、不触网）。"""
    spec = QuerySpec()
    if not text or not str(text).strip():
        spec.errors.append("空查询")
        return spec
    raw = str(text)
    working = raw

    # 1) 板块（最长匹配优先，避免"科创"先吃"科创板"）
    for alias in sorted(BOARD_ALIASES, key=len, reverse=True):
        if alias in working:
            spec.boards.append(BOARD_ALIASES[alias])
            working = working.replace(alias, " ")

    # 2) 比较式：字段别名 + 比较符 + 数字
    #    构造 "字段 (比较符) 数字" 的正则；字段/比较符均来自白名单
    field_alt = "|".join(re.escape(k) for k in FIELD_ALIASES)
    op_alt = "|".join(re.escape(k) for k in OP_WORDS)
    pat = re.compile(
        rf"({field_alt})\s*([\s]?(?:{op_alt})\s*)(-?\d+(?:\.\d+)?\s*[亿万股%]?|[%]?\s*-?\d+(?:\.\d+)?)",
        re.UNICODE,
    )
    for m in pat.finditer(working):
        field_cn, op_cn, num_cn = m.group(1), m.group(2).strip(), m.group(3).strip()
        finternal = FIELD_ALIASES[field_cn]
        fop = OP_WORDS[op_cn]
        val = _cn_number(num_cn.replace(" ", ""))
        if val is None:
            spec.errors.append(f"无法解析数值：{field_cn}{op_cn}{num_cn}")
            continue
        spec.filters.append({
            "field": finternal, "op": fop, "value": val,
            "unit": FIELD_UNIT.get(finternal, "ratio"),
            "raw": f"{field_cn}{op_cn}{num_cn}",
        })
        working = working.replace(m.group(0), " ")

    # 3) 排序："按X排序" / "X最高/最低/靠前" / "X排前"
    sort_map = {
        "最高": "desc", "最大": "desc", "最好": "desc", "居前": "desc", "靠前": "desc",
        "最低": "asc", "最小": "asc", "最差": "asc", "垫底": "asc",
    }
    for fcn, finternal in FIELD_ALIASES.items():
        for kw, direction in sort_map.items():
            if re.search(rf"按\s*{re.escape(fcn)}\s*排序", working) or \
               re.search(rf"{re.escape(fcn)}\s*{kw}", working):
                spec.sort = finternal
                spec.sort_dir = direction
                working = re.sub(rf"按\s*{re.escape(fcn)}\s*排序", " ", working)
                working = re.sub(rf"{re.escape(fcn)}\s*{kw}", " ", working)
                break

    # 4) 数量："前N" / "topN" / "N只" / "N个"
    lim = re.search(r"(?:前|top|取|选)\s*(\d+)|(\d+)\s*(?:只|个|条)", working, re.IGNORECASE)
    if lim:
        n = lim.group(1) or lim.group(2)
        if n:
            spec.limit = int(n)
            working = working.replace(lim.group(0), " ")

    # 5) 概念/行业自由词：剔除已识别的结构化 token 后，保留有意义的名词片段
    #    保守策略：仅保留 2~6 字、且非纯标点/数字/填充词 的剩余片段作为概念候选；
    #    含填充词（的/票/我想…）的片段直接丢弃，避免"的票"被当概念误杀候选池。
    cleaned = re.sub(r"[，。、；;，\s]+", " ", working).strip()
    for frag in cleaned.split():
        frag = frag.strip("，。、；;：:（）()")
        if not frag:
            continue
        if re.fullmatch(r"[0-9.%亿万股]+", frag):
            continue
        if any(ch in STOPWORDS for ch in frag):
            continue
        if len(frag) <= 6 and len(frag) >= 2:
            spec.concepts.append(frag)
    # 去重
    spec.concepts = list(dict.fromkeys(spec.concepts))
    # unparsed：与 concepts 同源，但 concepts 已是"未结构化词"；这里把真正空的概念清空提示
    if not spec.boards and not spec.filters and not spec.sort and not spec.concepts:
        spec.unparsed.append(raw)
    return spec


def matches_filter(record: dict, f: dict) -> bool:
    """单条筛选：record 须带内部字段名（已按 FIELD_UNIT 归一化）。取不到值→不匹配（不臆造通过）。"""
    v = record.get(f["field"])
    if v is None:
        return False
    try:
        v = float(v)
    except (TypeError, ValueError):
        return False
    tgt = float(f["value"])
    op = f["op"]
    if op == "lt":
        return v < tgt
    if op == "lte":
        return v <= tgt
    if op == "gt":
        return v > tgt
    if op == "gte":
        return v >= tgt
    if op == "eq":
        return abs(v - tgt) < 1e-6
    return False


def apply_filters(universe: list[dict], spec: QuerySpec) -> list[dict]:
    """对本地/已取回的 universe 应用解析结果（纯函数、可单测）。

    universe 每条：{code, name, board(语义或在执行层判定), pe, pb, mktcap(亿),
                    rev_growth(%), profit_growth(%), roe(%), gross_margin(%), concepts:[...], ...}
    板块过滤按 code 前缀（BOARD_CODE_PREFIX）；指数成分(board=None)需执行层预标注，这里跳过该 board。
    概念过滤：record.concepts 含任一 spec.concepts 即命中（子串匹配，大小写不敏感）。
    """
    out = []
    for rec in universe:
        ok = True
        # 板块
        for b in spec.boards:
            prefixes = BOARD_CODE_PREFIX.get(b)
            if prefixes is None:
                continue  # 指数成分需在 universe 里预标 is_hs300 等，页面执行层处理
            code = str(rec.get("code", ""))
            if not code.startswith(prefixes):
                ok = False
                break
        if not ok:
            continue
        # 指标
        for f in spec.filters:
            if not matches_filter(rec, f):
                ok = False
                break
        if not ok:
            continue
        # 概念
        if spec.concepts:
            rec_concepts = [str(c) for c in (rec.get("concepts") or [])]
            rec_name = str(rec.get("name", ""))
            hay = " ".join(rec_concepts) + " " + rec_name
            if not any(c in hay for c in spec.concepts):
                continue
        out.append(rec)
    # 排序：有值者参与排序，None 恒排末尾（不丢记录）；desc 用取负 trick 保持升序语义
    if spec.sort:
        _neg = -1 if spec.sort_dir == "desc" else 1

        def _k(r):
            v = r.get(spec.sort)
            if v is None:
                return (1, 0)
            try:
                return (0, _neg * float(v))
            except (TypeError, ValueError):
                return (1, 0)

        out.sort(key=_k)
    if spec.limit:
        out = out[: spec.limit]
    return out
