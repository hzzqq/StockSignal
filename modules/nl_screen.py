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

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
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

# ── 行业/题材显式白名单（2026-11-03 扩充，承接「非白酒板块」修复的下一缺口）────
# 目的：
#   1) 排除通道：5 字以上行业名（如「电力设备新能源」）此前被通用规则 {1,5} 长度卡住；
#      白名单词整词精确匹配且后缀可省（「非白酒」「剔除白酒板块」均可）。
#   2) 正向通道：7 字以上行业名此前被 step5 的 2~6 字片段窗口漏掉，白名单词整词入 concepts。
#   3) 整词匹配无通配（最长优先）→「非常看好半导体板块」类日常句不会被误拆
#      （"看"在 STOPWORDS 亦兜底）。
# 已知边界：复合词冲突（电子 vs 电子烟）按最长优先收录化解；未收录行业仍走
#   {1,5}+后缀 通用规则；未收录复合词可能被拆到父词（_show_spec 透明可见，可换说法）。
# 注：刻意不收「综合」（申万一级但口语高频歧义，"综合来看"会误命中）；
#   交易所板块别名（创业板/科创板等）走 BOARD_ALIASES，不在此表。
INDUSTRY_ALIASES = frozenset({
    # 申万一级行业（30，除"综合"）
    "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "家用电器", "食品饮料",
    "纺织服饰", "轻工制造", "医药生物", "公用事业", "交通运输", "房地产",
    "商贸零售", "社会服务", "建筑装饰", "建筑材料", "电力设备", "国防军工",
    "计算机", "传媒", "通信", "银行", "非银金融", "汽车", "机械设备", "环保",
    "美容护理", "煤炭", "石油石化",
    # 高频长行业/题材（重点覆盖 5 字以上）
    "新能源汽车", "电力设备新能源", "电子化学品", "第三代半导体", "新质生产力",
    "可控核聚变", "新型工业化", "汽车零部件", "房地产开发", "炼化及贸易",
    "半导体材料", "消费电子", "电子元件", "航空航天", "船舶制造", "化学制药",
    "医疗器械", "生物医药", "白色家电", "煤炭开采", "油服工程", "电网设备",
    "光伏设备", "风电设备", "能源金属", "工业金属", "黄金珠宝",
    # 高频短行业/题材（省后缀排除 + 复合词最长优先）
    "白酒", "光伏", "风电", "锂电池", "储能", "券商", "保险", "半导体", "创新药",
    "中药", "黄金", "白银", "稀土", "猪肉", "养殖", "种业", "游戏", "影视",
    "教育", "氢能", "核电", "充电桩", "军工", "低空经济", "固态电池", "数字经济",
    "人工智能", "专精特新", "数据要素", "算力", "芯片", "碳中和", "元宇宙",
    "机器人", "中特估", "电子烟", "新能源", "医药",
})

# ── 字段别名 → 内部字段名（执行层按此字段从基本面取数）──
FIELD_ALIASES = {
    "市盈率": "pe", "pe": "pe", "ttm": "pe", "市净率": "pb", "pb": "pb",
    "总市值": "mktcap", "市值": "mktcap", "流通市值": "float_mktcap",
    "营收增长": "rev_growth", "营收增速": "rev_growth", "营收": "rev_growth",
    "净利润增长": "profit_growth", "利润增长": "profit_growth", "净利增速": "profit_growth",
    "roe": "roe", "净资产收益率": "roe", "毛利率": "gross_margin", "毛利": "gross_margin",
    "营收复合增长": "rev_cagr", "利润复合增长": "profit_cagr",
    # 技术面/动量维度（扩维：涨跌幅/换手率/量比/振幅，真实行情口径）
    "涨跌幅": "chg_pct", "换手率": "turnover", "量比": "volume_ratio", "振幅": "amplitude",
}
# 各字段单位约定（执行层把记录值归一化到这些单位再比较）：
#   pe/pb/roe(%)/gross_margin(%)：纯数；rev_growth/profit_growth/rev_cagr/profit_cagr：百分数(如20=20%)
#   mktcap/float_mktcap：亿元
FIELD_UNIT = {
    "pe": "ratio", "pb": "ratio", "mktcap": "yi", "float_mktcap": "yi",
    "rev_growth": "pct", "profit_growth": "pct", "roe": "pct",
    "gross_margin": "pct", "rev_cagr": "pct", "profit_cagr": "pct",
    "chg_pct": "pct", "turnover": "pct", "volume_ratio": "ratio", "amplitude": "pct",
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
    exclude_boards: list[str] = field(default_factory=list)   # 排除板块语义（剔除/非/排除）
    exclude_concepts: list[str] = field(default_factory=list) # 排除概念/名字片段（剔除ST等）
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
        # ui_audit_exempt: 输入类型/取值非法时返回空，防御性契约（非数据缺失）
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

    # 0) 排除/否定：
    #    - 剔除/排除/不要/去掉/不含/别选 + 板块或概念 → 板块走 BOARD_ALIASES 归一，否则概念/名字片段排除。
    #    - "非<板块>" 单独处理（规范交易所板块 → exclude_boards），并可带 板块/行业/概念/产业/股 后缀。
    #    - "非<命名行业/概念词>(板块/行业/概念/产业/股)" → 排除概念（如"非白酒板块"）：
    #      补足原逻辑只认交易所板块、把命名行业当正向概念的缺口；核心词剥后缀入 exclude_concepts。
    #      限制行业词 1~5 字 + 后缀锚定，避免"非常看好半导体板块"类日常句被误拆为排除（误排 > 漏排）。
    _BOARD_NEG_SUFFIX = r"(?:板块|行业|概念|产业|股)"
    # 0a) 行业/题材白名单排除通道（整词精确匹配，最长优先；后缀可省）：
    #     5 字以上行业名（如「非电力设备新能源」）不再受通用规则 {1,5} 限制，
    #     「非白酒」「剔除白酒板块」等省后缀/带后缀写法均可。整词无通配，
    #     「非常看好半导体板块」类日常句不会被误拆（"看"在 STOPWORDS 亦兜底）。
    _NEG_PREFIX = r"(?:非|剔除|排除|不要|去掉|不含|别选)"
    for _term in sorted(INDUSTRY_ALIASES, key=len, reverse=True):
        _pat = rf"{_NEG_PREFIX}\s*{re.escape(_term)}{_BOARD_NEG_SUFFIX}?"
        if re.search(_pat, working):
            if _term not in spec.exclude_concepts:
                spec.exclude_concepts.append(_term)
            working = re.sub(_pat, " ", working, count=1)
    for alias in sorted(BOARD_ALIASES, key=len, reverse=True):
        _m = re.search(rf"非\s*{re.escape(alias)}{_BOARD_NEG_SUFFIX}?", working)
        if _m:
            b = BOARD_ALIASES[alias]
            if b not in spec.exclude_boards:
                spec.exclude_boards.append(b)
            working = re.sub(rf"非\s*{re.escape(alias)}{_BOARD_NEG_SUFFIX}?", " ", working, count=1)

    def _neg_named_repl(_mm):
        _term = _mm.group(1)
        if _term and _term not in spec.exclude_concepts:
            spec.exclude_concepts.append(_term)
        return " "
    # 注意：此处用普通 raw 字符串 + 拼接，不能用 f-string——f-string 会把 {1,5} 当成
    # 元组表达式静默改成 "(1, 5)"，导致正则失效且不报错（已踩坑）。
    working = re.sub(r"非\s*([\u4e00-\u9fa5A-Za-z0-9]{1,5}?)" + _BOARD_NEG_SUFFIX, _neg_named_repl, working)
    _neg_pat = re.compile(r"(剔除|排除|不要|去掉|不含|别选)\s*([\u4e00-\u9fa5A-Za-z0-9]{1,6})", re.UNICODE)
    for _nm in _neg_pat.finditer(working):
        # 兜底通道同样剥掉尾部板块/行业等后缀：「剔除白酒板块」→ 排除"白酒"而非"白酒板块"
        # （白名单词已在 0a 处理，此处兜底非白名单词）；剥空（如「剔除板块」）只清文本不入排除。
        _target = re.sub(r"(?:板块|行业|概念|产业|股)$", "", _nm.group(2))
        _board = None
        for alias in sorted(BOARD_ALIASES, key=len, reverse=True):
            if _target.startswith(alias) or alias in _target:
                _board = BOARD_ALIASES[alias]
                break
        if _board is not None:
            if _board not in spec.exclude_boards:
                spec.exclude_boards.append(_board)
        elif _target and _target not in spec.exclude_concepts:
            spec.exclude_concepts.append(_target)
        working = working.replace(_nm.group(0), " ")

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

    # 4b) 行业/题材白名单正向通道：整词入 concepts 并剥离（含可选后缀），最长优先。
    #     修复 7 字以上行业名（如「电力设备新能源」）被 step5 的 2~6 字窗口漏掉的问题；
    #     剥离时连后缀一起吃掉，避免残留「板块」碎片污染 concepts；step5 末尾已有去重。
    for _term in sorted(INDUSTRY_ALIASES, key=len, reverse=True):
        _pat = rf"{re.escape(_term)}{_BOARD_NEG_SUFFIX}?"
        if re.search(_pat, working):
            if _term not in spec.concepts:
                spec.concepts.append(_term)
            working = re.sub(_pat, " ", working, count=1)

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
    # unparsed：仅当完全没有任何结构化理解（含排除）时才标记未理解
    if not (spec.boards or spec.filters or spec.sort or spec.concepts
            or spec.exclude_boards or spec.exclude_concepts):
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
        # 板块（正向）
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
        # 板块（排除）：命中排除板块 → 跳过（如"剔除创业板"）
        for b in spec.exclude_boards:
            prefixes = BOARD_CODE_PREFIX.get(b)
            if prefixes is None:
                continue
            code = str(rec.get("code", ""))
            if code.startswith(prefixes):
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
        # 概念（正向）
        if spec.concepts:
            rec_concepts = [str(c) for c in (rec.get("concepts") or [])]
            rec_name = str(rec.get("name", ""))
            hay = " ".join(rec_concepts) + " " + rec_name
            if not any(c in hay for c in spec.concepts):
                continue
        # 概念/名字（排除）：命中排除概念或名字片段 → 跳过（如"剔除ST"）
        if spec.exclude_concepts:
            rec_concepts = [str(c) for c in (rec.get("concepts") or [])]
            rec_name = str(rec.get("name", ""))
            hay = " ".join(rec_concepts) + " " + rec_name
            if any(c in hay for c in spec.exclude_concepts):
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


# ── 选股方案存档（2026-11-03：i问财方案保存/复用）────────────────────────────
# 边界说明：本模块红线是「只理解、不取数」；方案存档既非理解也非取数，是页面执行层
# 的轻量辅助（纯 JSON 读写、不触网）。**只存原始查询文本**——复用时重新 parse，
# spec 永远来自真实解析，绝不存旧解析结构（防 schema 漂移与陈旧条件）。
_QUERY_PRESETS_MAX = 50


def _query_presets_path() -> str:
    """选股方案存档路径（SS_DATA_DIR 隔离，与 nav_freq.json 同模式）。"""
    _data_dir = os.environ.get("SS_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    return os.path.join(_data_dir, "nl_presets.json")


def load_query_presets(limit: int = 20) -> list:
    """读取已保存的选股方案（新的在前）。文件缺失/损坏 → []（不臆造）。"""
    try:
        _path = _query_presets_path()
        if not os.path.exists(_path):
            return []
        with open(_path, "r", encoding="utf-8") as _f:
            _data = json.load(_f)
        if not isinstance(_data, list):
            return []
        _items = [it for it in _data
                  if isinstance(it, dict) and str(it.get("query", "")).strip()]
        return _items[:limit] if isinstance(limit, int) and limit > 0 else _items
    except Exception:  # noqa: BLE001 - 读取失败降级为空，不阻断选股主流程
        return []


def save_query_preset(query: str) -> bool:
    """保存一条选股方案（按查询文本去重，命中则移到最前；上限截断）。fail-safe。"""
    try:
        q = str(query or "").strip()
        if not q:
            return False
        _path = _query_presets_path()
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        _items = [it for it in load_query_presets(limit=0) if it.get("query") != q]
        _items.insert(0, {"query": q, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        from modules.atomic_io import atomic_json_dump
        atomic_json_dump(_items[:_QUERY_PRESETS_MAX], _path)
        return True
    except Exception:  # noqa: BLE001 - 保存失败如实返回 False，不臆造成功
        return False


def clear_query_presets() -> int:
    """清空全部选股方案，返回真实清除条数；文件缺失 0；失败 -1（诚实语义）。"""
    try:
        _path = _query_presets_path()
        if not os.path.exists(_path):
            return 0
        try:
            with open(_path, "r", encoding="utf-8") as _f:
                _old = json.load(_f)
            _n = len(_old) if isinstance(_old, list) else 0
        except Exception:  # noqa: BLE001
            _n = 0
        os.remove(_path)
        return _n
    except Exception:  # noqa: BLE001
        return -1
