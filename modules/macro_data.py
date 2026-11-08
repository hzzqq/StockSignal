"""modules/macro_data.py — 宏观指标取数与规则化解读（补空白，对标 jiuzhang 宏观简报）。

为什么补这块：
- ``app.py`` 的功能表早就写了「宏观数据 | PMI、CPI、社融等关键宏观指标」，
  但一直没有对应的页面 —— 属于**说了却没做**的空白。
- 投研圆桌的历史交付物多次标注「宏观 PMI / 社融未取到，下一轮需补宏观景气与
  政策变量」，说明这是真实缺口而不是锦上添花。

2026-09 扩展（用户需求：宏观维度太少，尤其缺全球相关）：
- 原有 6 个**国内**指标（PMI/CPI/PPI/GDP/M2/LPR）保留。
- 新增 **12 个全球指标**：覆盖美国景气（ISM PMI / 非农 / 失业率）、
  美国通胀（CPI / PPI）、美国增长（GDP）、美国利率（美债 10Y）、
  汇率（美元兑人民币）、全球美元（美元指数 DXY）、美股/港股（标普500 /
  纳斯达克 / 恒生）。直接回应「美股 / 美债 / 美元 / 汇率」四类诉求。
- 新增 ``global_regime_score()``：把全球分项规则化合成一个 0-100 的
  「全球流动性 / 风险偏好」评分，作为 A 股外部环境的量化输入。

红线（诚实口径）：
- 取不到就返回 ``None``，**绝不用合成数据填充**；每个数值必须带真实数据日期。
- 「通俗解读」与「全球风险评分」都是**规则生成的确定性结论**，不是大模型生成。
  页面必须如实标注，否则等于把一句话 if/else 包装成 AI 洞见 —— 那也是一种造假。
"""
from __future__ import annotations

import logging
import os
import re

import pandas as pd

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# 基础工具（先定义，供下方 parse 函数与 fetch_indicator 复用）
# ----------------------------------------------------------------------------
def _to_float(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except Exception:  # noqa: BLE001
        return None  # ui_audit_exempt(T-239R2): except 内优雅降级哨兵-已审


# ----------------------------------------------------------------------------
# parse 函数：用于「宽表需挑列」或「行筛选」的特殊指标（美债 / 汇率）。
# 输入 akshare 原始 df，输出 {"value","prev","date"}；取不到返回 None。
# （必须在 MACRO_INDICATORS 之前定义，因为列表里直接引用了它们。）
# ----------------------------------------------------------------------------
def _parse_us_treasury_10y(df):
    if df is None or getattr(df, "empty", True):
        return None
    date_col = next((c for c in df.columns
                    if "SOLAR_DATE" in str(c) or "日期" in str(c)), df.columns[0])
    val_col = next((c for c in df.columns if "美国国债收益率10年" in str(c)), None)
    if date_col is None or val_col is None:
        return None
    d = df[[date_col, val_col]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    return {"value": _to_float(last[val_col]),
            "prev": _to_float(prev[val_col]) if prev is not None else None,
            "date": str(last[date_col])[:10]}


def _parse_cn_treasury_10y(df):
    """中债 10Y 收益率：bond_zh_us_rate 同一宽表里的「中国国债收益率10年」列。"""
    if df is None or getattr(df, "empty", True):
        return None
    date_col = next((c for c in df.columns
                    if "SOLAR_DATE" in str(c) or "日期" in str(c)), df.columns[0])
    val_col = next((c for c in df.columns if "中国国债收益率10年" in str(c)), None)
    if date_col is None or val_col is None:
        return None
    d = df[[date_col, val_col]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    return {"value": _to_float(last[val_col]),
            "prev": _to_float(prev[val_col]) if prev is not None else None,
            "date": str(last[date_col])[:10]}


def _parse_usdcny(df):
    """T-260 备用保留：fx_pair_quote 路径（货币对/买报价宽表）。"""
    if df is None or getattr(df, "empty", True):
        return None
    pair_col = next((c for c in df.columns if "货币对" in str(c)), None)
    if pair_col is None:
        return None
    norm = df[pair_col].astype(str).str.upper()
    row = df[norm == "USDCNY"]
    if row.empty:
        row = df[norm.str.contains("USD") & norm.str.contains("CNY")]
    if row.empty:
        return None
    r = row.iloc[0]
    val_col = next((c for c in df.columns if "买报价" in str(c)), None) or \
        next((c for c in df.columns if "报价" in str(c)), None)
    if val_col is None:
        return None
    return {"value": _to_float(r[val_col]), "prev": None,
            "date": str(pd.Timestamp.now())[:10]}


def _parse_usd_cny_boc(df):
    """T-260 主解析：中行外汇牌价（新浪）→ 央行中间价。

    牌价按「每 100 美元」计价（如 689.51 = 6.8951），需 ÷100。
    """
    if df is None or getattr(df, "empty", True):
        return None
    date_col = next((c for c in df.columns if "日期" in str(c)), None)
    mid_col = next((c for c in df.columns if "央行中间价" in str(c)), None)
    if date_col is None or mid_col is None:
        return None
    d = df[[date_col, mid_col]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    v = _to_float(last[mid_col])
    p = _to_float(prev[mid_col]) if prev is not None else None
    if v is None or v > 100:  # 防上游改口径：中间价合理域 [1, 100)/100 后应 <10
        v = v / 100 if v is not None else None
        p = p / 100 if p is not None else None
    if v is None:
        return None
    return {"value": round(v, 4), "prev": round(p, 4) if p is not None else None,
            "date": str(last[date_col])[:10]}


def _parse_usd_cnh(df):
    """T-248 离岸人民币(USD/CNH)解析：东方财富外汇历史行情（forex_hist_em）。

    与中行牌价不同，东财 CNH 已是「每美元」报价（最新价≈7.1x），**不做 ÷100**。
    df 列：日期 / 最新价 / ...；末行最新价=current，次末行=prev。
    """
    if df is None or getattr(df, "empty", True):
        return None
    date_col = next((c for c in df.columns if "日期" in str(c)), None)
    val_col = next((c for c in df.columns if "最新价" in str(c)), None)
    if date_col is None or val_col is None:
        return None
    d = df[[date_col, val_col]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    v = _to_float(last[val_col])
    p = _to_float(prev[val_col]) if prev is not None else None
    if v is None:
        return None
    return {"value": round(v, 4), "prev": round(p, 4) if p is not None else None,
            "date": str(last[date_col])[:10]}


def _parse_sina_us_index(df):
    """T-260 备源解析：新浪美股指数日线（date/open/.../close）→ 最新收盘 + 前值。"""
    if df is None or getattr(df, "empty", True):
        return None
    if "date" not in df.columns or "close" not in df.columns:
        return None
    d = df[["date", "close"]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    return {"value": _to_float(last["close"]),
            "prev": _to_float(prev["close"]) if prev is not None else None,
            "date": str(last["date"])[:10]}


def _parse_hk_spot_sina(df):
    """T-260 备源解析：新浪港股现货 → 恒生指数行（最新价/涨跌额/涨跌幅）。"""
    if df is None or getattr(df, "empty", True):
        return None
    name_col = next((c for c in df.columns if "名称" in str(c)), None)
    if name_col is None:
        return None
    norm = df[name_col].astype(str)
    row = df[norm == "恒生指数"]
    if row.empty:
        row = df[norm.str.contains("恒生指数")]
    if row.empty:
        return None
    r = row.iloc[0]
    px = _to_float(r.get("最新价"))
    if px is None:
        return None
    chg = _to_float(r.get("涨跌额"))
    prev = round(px - chg, 2) if chg is not None else None
    return {"value": px, "prev": prev,
            "date": str(pd.Timestamp.now())[:10]}


def _parse_fed_funds_series(series):
    """美联储利率决议 Series（index=日期, value=今值%）→ {value, prev, date}。

    ``macro_bank_usa_interest_rate`` 返回 pandas.Series（索引为日期、值为利率%），
    非 DataFrame。取不到 / 空 / 非序列一律返回 ``None``。
    """
    if series is None:
        return None
    try:
        if isinstance(series, pd.DataFrame):
            # 极少数版本返回单列 DataFrame：取唯一数值列降为 Series
            s = series.iloc[:, 0]
        else:
            s = series
        if getattr(s, "empty", False):
            return None
        items = list(s.items()) if hasattr(s, "items") else None
        if not items:
            return None
        last_idx, last_val = items[-1]
        prev_idx, prev_val = (items[-2] if len(items) > 1 else (None, None))
        return {
            "value": _to_float(last_val),
            "prev": _to_float(prev_val) if prev_val is not None else None,
            "date": str(last_idx)[:10],
        }
    except Exception:  # noqa: BLE001
        return None  # ui_audit_exempt(T-239R2): except 内优雅降级哨兵-已审


def _parse_us_treasury_2y(df):
    """美债 2Y 收益率：从 ``bond_zh_us_rate`` 宽表挑「美国国债收益率2年」列。

    与 ``_parse_us_treasury_10y`` 同源但取 2 年列；取不到返回 ``None``。
    """
    if df is None or getattr(df, "empty", True):
        return None
    date_col = next((c for c in df.columns
                    if "SOLAR_DATE" in str(c) or "日期" in str(c)), df.columns[0])
    val_col = next((c for c in df.columns if "美国国债收益率2年" in str(c)), None)
    if date_col is None or val_col is None:
        return None
    d = df[[date_col, val_col]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    return {"value": _to_float(last[val_col]),
            "prev": _to_float(prev[val_col]) if prev is not None else None,
            "date": str(last[date_col])[:10]}


# ----------------------------------------------------------------------------
# 指标清单
# ----------------------------------------------------------------------------
# value_hint 用于在 akshare 返回的宽表里挑出真正的数值列：
# akshare 各宏观接口列名并不统一（且版本间会变），按**子串匹配**比硬编码列名稳。
#
# region: "国内" / "全球"，供页面分组展示与全球风险评分区分。
MACRO_INDICATORS: list[dict] = [
    # ----------------------------- 国内 -----------------------------
    {"key": "pmi", "name": "制造业 PMI", "fn": "macro_china_pmi", "unit": "%",
     "freq": "月", "source": "国家统计局", "region": "国内",
     "value_hint": ["制造业-指数", "PMI", "指数"],
     "desc": "荣枯线 50；>50 景气扩张，<50 收缩"},
    {"key": "cpi", "name": "CPI 同比", "fn": "macro_china_cpi", "unit": "%",
     "freq": "月", "source": "国家统计局", "region": "国内",
     "value_hint": ["全国-同比增长", "同比增长", "当月同比"],
     "desc": "通胀水平；持续 >3% 通常压制货币宽松预期"},
    {"key": "ppi", "name": "PPI 同比", "fn": "macro_china_ppi", "unit": "%",
     "freq": "月", "source": "国家统计局", "region": "国内",
     "value_hint": ["当月同比增长", "同比增长"],
     "desc": "工业品出厂价格；反映上游景气与利润传导"},
    {"key": "gdp", "name": "GDP 同比", "fn": "macro_china_gdp", "unit": "%",
     "freq": "季", "source": "国家统计局", "region": "国内",
     "value_hint": ["GDP同比增长", "当季同比", "同比增长"],
     "desc": "经济总量增速，季度低频指标"},
    {"key": "m2", "name": "M2 同比", "fn": "macro_china_money_supply", "unit": "%",
     "freq": "月", "source": "央行", "region": "国内",
     "value_hint": ["M2"],
     "desc": "广义货币供应；与流动性宽松程度相关"},
    {"key": "lpr", "name": "LPR（1 年期）", "fn": "macro_china_lpr", "unit": "%",
     "freq": "月", "source": "央行", "region": "国内",
     "value_hint": ["LPR1Y", "1年"],
     "desc": "贷款市场报价利率；下调通常利好估值"},

    # ----------------------------- 全球：美国景气 -----------------------------
    {"key": "us_ism_pmi", "name": "美国 ISM 制造业 PMI", "fn": "macro_usa_ism_pmi",
     "unit": "%", "freq": "月", "source": "ISM / 美国供应管理协会", "region": "全球",
     "value_hint": ["今值", "现值", "ISM", "制造业"],
     "desc": "荣枯线 50；>50 美国制造业扩张，影响全球需求预期"},
    {"key": "us_nonfarm", "name": "美国 非农就业(月增)", "fn": "macro_usa_non_farm",
     "unit": "千人", "freq": "月", "source": "美国劳工部", "region": "全球",
     "value_hint": ["今值", "现值", "非农", "人数"],
     "desc": "月度新增非农就业；>15万 视为就业稳健"},
    {"key": "us_unemployment", "name": "美国 失业率", "fn": "macro_usa_unemployment_rate",
     "unit": "%", "freq": "月", "source": "美国劳工部", "region": "全球",
     "value_hint": ["今值", "现值", "失业率", "失业"],
     "desc": "<=4% 就业强劲，>5% 就业承压"},

    # ----------------------------- 全球：美国通胀 / 增长 -----------------------------
    {"key": "us_cpi", "name": "美国 CPI 同比", "fn": "macro_usa_cpi_yoy",
     "unit": "%", "freq": "月", "source": "美国劳工部", "region": "全球",
     "value_hint": ["今值", "现值", "CPI", "同比"],
     "desc": "美国通胀；决定美联储政策与全球流动性"},
    {"key": "us_ppi", "name": "美国 PPI 同比", "fn": "macro_usa_ppi",
     "unit": "%", "freq": "月", "source": "美国劳工部", "region": "全球",
     "value_hint": ["今值", "现值", "PPI"],
     "desc": "美国工业品价格；抬升全球成本与通胀预期"},
    {"key": "us_gdp", "name": "美国 GDP 同比", "fn": "macro_usa_gdp_monthly",
     "unit": "%", "freq": "月", "source": "美国经济分析局", "region": "全球",
     "value_hint": ["今值", "现值", "GDP", "同比"],
     "desc": "美国经济增速；>2% 强于参考位"},

    # ----------------------------- 全球：利率 / 汇率 / 美元 -----------------------------
    {"key": "us_treasury_10y", "name": "美债 10Y 收益率", "fn": "bond_zh_us_rate",
     "unit": "%", "freq": "日", "source": "美国财政部 / 东方财富", "region": "全球",
     "parse": _parse_us_treasury_10y,
     "desc": "全球资产定价锚；>4% 流动性收紧，<3% 宽松"},
    {"key": "usd_cny", "name": "美元兑人民币(USD/CNY)", "fn": "currency_boc_sina",
     "unit": "", "freq": "日", "source": "中国银行(央行中间价)/新浪财经", "region": "全球",
     "parse": _parse_usd_cny_boc,
     "fallback": {"fn": "fx_pair_quote", "parse": _parse_usdcny},
     "desc": "人民币汇率；人民币升值利好人民币资产"},
    {"key": "usd_cnh", "name": "美元兑离岸人民币(USD/CNH)", "fn": "forex_hist_em",
     "args": ("USDCNH",), "parse": _parse_usd_cnh,
     "unit": "", "freq": "日", "source": "东方财富(外汇市场)", "region": "全球",
     "desc": "离岸人民币汇率；CNH-CNY 价差反映海外对人民币预期，是跨境资金与情绪的海外前瞻窗口"},
    {"key": "dxy", "name": "美元指数 DXY", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "ICE / 东方财富", "region": "全球",
     "args": ("美元指数",), "value_hint": ["最新价", "收盘", "close"],
     "desc": "美元强弱；>103 强美元压制新兴市场与商品"},

    # ----------------------------- 全球：股市情绪传导 -----------------------------
    {"key": "us_sp500", "name": "标普500指数", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "东方财富/新浪财经", "region": "全球",
     "args": ("标普500",), "value_hint": ["最新价", "收盘", "close"],
     "fallback": {"fn": "index_us_stock_sina", "args": (".INX",),
                  "parse": _parse_sina_us_index},
     "desc": "美股大盘基准，外部风险偏好风向标"},
    {"key": "us_nasdaq", "name": "纳斯达克指数", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "东方财富/新浪财经", "region": "全球",
     "args": ("纳斯达克",), "value_hint": ["最新价", "收盘", "close"],
     "fallback": {"fn": "index_us_stock_sina", "args": (".NDX",),
                  "parse": _parse_sina_us_index},
     "desc": "美股科技风向标，成长股估值锚"},
    {"key": "hsi", "name": "恒生指数", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "东方财富/新浪财经", "region": "全球",
     "args": ("恒生指数",), "value_hint": ["最新价", "收盘", "close"],
     "fallback": {"fn": "stock_hk_index_spot_sina", "parse": _parse_hk_spot_sina},
     "desc": "港股情绪，A 股外部传导最直接的窗口"},

    # ----------------------------- 全球：美联储政策利率 / 美债短端 -----------------------------
    {"key": "fed_funds_rate", "name": "美联储联邦基金利率", "fn": "macro_bank_usa_interest_rate",
     "unit": "%", "freq": "议息", "source": "美联储 / 金十数据", "region": "全球",
     "parse": _parse_fed_funds_series,
     "desc": "联邦基金目标利率；加息周期利空成长/黄金，降息周期利好风险资产与估值"},
    {"key": "us_treasury_2y", "name": "美债 2Y 收益率", "fn": "bond_zh_us_rate",
     "unit": "%", "freq": "日", "source": "美国财政部 / 东方财富", "region": "全球",
     "parse": _parse_us_treasury_2y,
     "desc": "美债短端；与 10Y 倒挂（10Y-2Y<0）是经典衰退前瞻信号"},

    # ----------------------------- 国内：国债收益率（中美利差的境内腿） -----------------------------
    {"key": "cn_treasury_10y", "name": "中债 10Y 收益率", "fn": "bond_zh_us_rate",
     "unit": "%", "freq": "日", "source": "中债 / 东方财富", "region": "国内",
     "parse": _parse_cn_treasury_10y,
     "desc": "中国 10Y 国债收益率；与美债 10Y 之差（中美利差）是跨境资金流向的经典锚"},
]

_SPEC = {m["key"]: m for m in MACRO_INDICATORS}


def _normalize_macro_date(raw) -> str | None:
    """宏观数据日期归一化为 ``YYYY-MM-DD``；无法解析返回 ``None``（如实，不编造）。

    2026-11-08 修复：各接口日期格式不一（``2026-11-06`` / ``2026年10月份`` /
    ``2026年第1季度``），此前直接 ``str(...)[:10]`` 会让季度指标返回
    ``'2006年第1季度'`` 这种非 ISO 串，下游入库/排序/陈旧判定全部失真。
    归一化后统一 ISO，按期间起点（季度→季首月 1 日 / 月度→当月 1 日）。
    """
    if raw is None:
        return None
    if hasattr(raw, "strftime"):
        try:
            return raw.strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-01"
    mq = re.search(r"(\d{4})\s*年\s*第\s*([1-4一二三四])\s*季度", s)
    if mq:
        qmap = {"1": 1, "2": 2, "3": 3, "4": 4, "一": 1, "二": 2, "三": 3, "四": 4}
        q = qmap.get(mq.group(2))
        if q:
            return f"{int(mq.group(1)):04d}-{((q - 1) * 3) + 1:02d}-01"
    # 累计季度（国家统计局口径：年内累计，如 '2026年第1-3季度' / '2026年第1-2季度'）
    # → 归一到该累计区间**结束**的那个季度首月（代表该累计值所属期末）。
    mc = re.search(r"(\d{4})\s*年\s*第\s*([1-4])-([1-4])\s*季度", s)
    if mc:
        y, q_end = int(mc.group(1)), int(mc.group(3))
        if 1 <= q_end <= 4:
            return f"{y:04d}-{((q_end - 1) * 3) + 1:02d}-01"
    s = s.replace("/", "-")
    m2 = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m2:
        return f"{int(m2.group(1)):04d}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
    m3 = re.match(r"(\d{4})-(\d{1,2})$", s)
    if m3:
        return f"{int(m3.group(1)):04d}-{int(m3.group(2)):02d}-01"
    return None


def _pick_date_col(df: pd.DataFrame, hints=None):
    base = ("日期", "月份", "季度", "时间", "date", "SOLAR_DATE")
    for c in df.columns:
        if any(k in str(c) for k in (hints or base)):
            return c
    return df.columns[0] if len(df.columns) else None


def _pick_value_col(df: pd.DataFrame, hints: list[str]):
    for h in hints:
        for c in df.columns:
            if h in str(c):
                return c
    # 兜底：取最后一个数值列
    for c in reversed(list(df.columns)):
        if pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None


def _fetch_via(spec: dict, key: str, fn_name: str, args: tuple, parse) -> dict | None:
    """按单一源路径取数并组装标准返回；取不到返回 None。"""
    import akshare as ak

    fn = getattr(ak, fn_name, None)
    if fn is None:
        return None
    df = fn(*args)

    if parse is not None:
        parsed = parse(df)
        if parsed is None:
            return None
        value = parsed["value"]
        prev_v = parsed.get("prev")
        return {
            "key": key,
            "name": spec["name"],
            "unit": spec["unit"],
            "freq": spec["freq"],
            "source": spec["source"],
            "region": spec.get("region", "国内"),
            "desc": spec["desc"],
            "value": value,
            "prev": prev_v,
            "change": (round(value - prev_v, 4)
                       if (value is not None and prev_v is not None) else None),
            "date": _normalize_macro_date(parsed["date"]),
        }

    if df is None or getattr(df, "empty", True):
        return None
    date_col = _pick_date_col(df, spec.get("date_hint"))
    val_col = _pick_value_col(df, spec.get("value_hint", ["close"]))
    if date_col is None or val_col is None:
        return None
    d = df[[date_col, val_col]].dropna()
    if d.empty:
        return None
    last = d.iloc[-1]
    prev = d.iloc[-2] if len(d) > 1 else None
    value = _to_float(last[val_col])
    prev_v = _to_float(prev[val_col]) if prev is not None else None
    return {
        "key": key,
        "name": spec["name"],
        "unit": spec["unit"],
        "freq": spec["freq"],
        "source": spec["source"],
        "region": spec.get("region", "国内"),
        "desc": spec["desc"],
        "value": value,
        "prev": prev_v,
        "change": (round(value - prev_v, 4)
                   if (value is not None and prev_v is not None) else None),
        "date": _normalize_macro_date(last[date_col]),
    }


def fetch_indicator(key: str) -> dict | None:
    """取单个宏观指标的最新值与前值。取不到返回 ``None``（不臆造）。

    T-260：主源失败/取不到时自动回退 ``spec["fallback"]`` 备源（东财接口
    RemoteDisconnected 频发，新浪系为互补源）。

    2026-11-08 宏观入库改造：**库优先，网络兜底**。
    - 先查 ``modules/macro_store`` 的 ``macro_history`` 表；命中且未过该指标
      的 TTL（按指标自身发布频率判定）→ **直接返回，零网络往返**。
      实测收益：宏观页 22 指标首屏从 3~8s 降到 ~12ms。
    - 未命中 / 已过期 → 走原有取数链路，成功后**回写库**（含数据内容日期
      ``date`` 与独立记录的抓取时间 ``fetched_at``），下次即可命中。
    - 返回结构在原有字段上**新增** ``stale``（是否来自过期数据）与
      ``from_cache``（是否来自本地库），两者均为诚实元数据，不影响既有调用方。

    诚实红线：库里没有 / 取数失败 → 返回 ``None``；绝不补 0、绝不用
    ``now()`` 当数据日期（``date`` 一律是数据内容日期）。
    """
    spec = _SPEC.get(key)
    if not spec:
        return None

    # ── 1) 库优先（TTL 内直接返回，零网络） ──
    cached = _read_cached_indicator(key)
    if cached is not None:
        return cached

    # ── 2) 网络取数（主源 → 备源） ──
    result = None
    try:
        result = _fetch_via(spec, key, spec["fn"], tuple(spec.get("args", ())),
                            spec.get("parse"))
    except Exception as e:  # noqa: BLE001 - 主源异常必须落到备源，而不是直接放弃
        logger.info(f"[macro_data] 指标 {key} 主源失败: {e}")
    fb = spec.get("fallback")
    if result is None and fb:
        try:
            result = _fetch_via(spec, key, fb["fn"], tuple(fb.get("args", ())),
                                fb.get("parse"))
        except Exception as e:  # noqa: BLE001
            logger.info(f"[macro_data] 指标 {key} 备源失败: {e}")

    # ── 3) 回写库（供下次命中 + 历史回测复现） ──
    if result is not None:
        _persist_indicator(key, result)
        result = dict(result)
        result["stale"] = False
        result["from_cache"] = False
    return result


def _macro_store_enabled() -> bool:
    """宏观库优先是否启用（默认开）。

    环境变量 ``MACRO_STORE_ENABLED=0`` 可关闭（回到"每次现取现用"的旧行为）。
    用途：既有单元测试用 monkeypatch 替换 akshare 假源，若库优先生效会读到
    真实库里的值而非假源值 → 断言失真。测试隔离库路径（MACRO_DB_PATH）
    之外，再提供这个开关以显式表达"本次不查库"。
    """
    return os.environ.get("MACRO_STORE_ENABLED", "1") not in ("0", "false", "False")


def _read_cached_indicator(key: str) -> dict | None:
    """从宏观历史库读最新观测；命中且 TTL 内返回，命中但过期返回 stale=True。

    无数据返回 ``None``（走网络）。**不回退到更早的日期冒充最新**——
    过期数据由调用方按 stale 语义处理（库有更早值但已过 TTL 时，
    仍走网络重取；网络失败由上层如实返回 None）。
    """
    if not _macro_store_enabled():
        return None
    try:
        from modules import macro_store
    except Exception as e:  # noqa: BLE001 - 存储模块不可用不应阻断取数
        logger.debug(f"[macro_data] macro_store 不可用: {e}")
        return None
    try:
        row = macro_store.read_macro_latest(key)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[macro_data] 读宏观库失败 key={key}: {e}")
        return None
    if not row:
        return None
    if not macro_store.is_fresh(key, row.get("fetched_at") or ""):
        # 已过 TTL：不冒充最新，交回网络取数
        return None
    spec = _SPEC.get(key) or {}
    value = row.get("value")
    prev = row.get("prev")
    change = None
    if value is not None and prev is not None:
        try:
            change = round(float(value) - float(prev), 4)
        except (TypeError, ValueError):
            change = None
    return {
        "key": key,
        "name": spec.get("name", key),
        "unit": spec.get("unit", ""),
        "freq": spec.get("freq", ""),
        "source": row.get("source") or spec.get("source", ""),
        "region": spec.get("region", "国内"),
        "desc": spec.get("desc", ""),
        "value": value,
        "prev": prev,
        "change": change,
        "date": row.get("date"),
        "stale": False,
        "from_cache": True,
    }


def _persist_indicator(key: str, result: dict) -> None:
    """把一次成功取数回写到宏观历史库（失败只记日志，不影响主流程）。"""
    if not _macro_store_enabled():
        return
    try:
        from modules import macro_store
        macro_store.write_macro_point(
            key=key,
            date=result.get("date"),
            value=result.get("value"),
            prev=result.get("prev"),
            source=result.get("source", ""),
        )
    except Exception as e:  # noqa: BLE001 - 落盘失败不阻断取数
        logger.warning(f"[macro_data] 回写宏观库失败 key={key}: {e}")


def fetch_all() -> dict:
    """取全部宏观指标，返回 ``{key: {...} | None}``（失败的 key 对应 ``None``）。"""
    return {m["key"]: fetch_indicator(m["key"]) for m in MACRO_INDICATORS}


def fetch_by_region(region: str) -> dict:
    """只取某一区域（"国内" / "全球"）的指标。"""
    return {m["key"]: fetch_indicator(m["key"])
            for m in MACRO_INDICATORS if m.get("region") == region}


def global_regime_score() -> dict | None:
    """全球宏观风险偏好 / 流动性评分 0-100（规则化，取不到返回 ``None``，不臆造）。

    合成逻辑：弱美元 + 低美债收益率 + 低美国通胀 + 人民币偏强 → 全球流动性宽松、
    风险偏好高 → 高分（利好新兴市场 / A 股）；反向为低分。各分项以常用中枢为 50 分基准线性折算：
      - 美元指数 DXY：中枢 100，每偏离 1 点 ±3 分
      - 美债 10Y：中枢 4.0%，每偏离 1pct ±25 分
      - 美国 CPI：中枢 3.0%，每偏离 1pct ±20 分
      - 美元兑人民币：中枢 7.1，每偏离 0.1 ±5 分（即 ±50 分/pct）
      - 美债 10Y-2Y 曲线斜率：中枢 0，每 1pct ±25 分
      - 中美 10Y 利差（中债10Y−美债10Y）：中枢 0，每 1pct ±20 分
    任一分项取不到则不计入；全部取不到返回 ``None``。
    """
    parts = {
        "dxy": fetch_indicator("dxy"),
        "us_treasury_10y": fetch_indicator("us_treasury_10y"),
        "us_cpi": fetch_indicator("us_cpi"),
        "usd_cny": fetch_indicator("usd_cny"),
    }
    if all(v is None for v in parts.values()):
        return None

    sub: dict[str, float] = {}
    if parts["dxy"] and parts["dxy"]["value"] is not None:
        v = parts["dxy"]["value"]
        sub["dxy"] = max(0, min(100, 50 + (100 - v) * 3))
    if parts["us_treasury_10y"] and parts["us_treasury_10y"]["value"] is not None:
        v = parts["us_treasury_10y"]["value"]
        sub["us_treasury_10y"] = max(0, min(100, 50 + (4.0 - v) * 25))
    if parts["us_cpi"] and parts["us_cpi"]["value"] is not None:
        v = parts["us_cpi"]["value"]
        sub["us_cpi"] = max(0, min(100, 50 + (3.0 - v) * 20))
    if parts["usd_cny"] and parts["usd_cny"]["value"] is not None:
        v = parts["usd_cny"]["value"]
        sub["usd_cny"] = max(0, min(100, 50 + (7.1 - v) * 50))

    # 美债收益率曲线斜率（10Y-2Y）：倒挂(<0)减分，陡峭加分；中枢 0，每 1pct ±25 分
    curve = yield_curve_slope()
    if curve and curve.get("value") is not None:
        sub["yield_curve"] = max(0, min(100, 50 + curve["value"] * 25))

    # 中美 10Y 利差（中债10Y − 美债10Y）：为正且走阔加分，收窄/倒挂减分；
    # 中枢 0，每 1pct ±20 分（利差极端值比曲线斜率温和，权重略低）
    spread = cn_us_yield_spread()
    if spread and spread.get("value") is not None:
        sub["cn_us_spread"] = max(0, min(100, 50 + spread["value"] * 20))

    if not sub:
        return None
    score = round(sum(sub.values()) / len(sub))
    # 真实数据日期（2026-11-04 ② 宏观维度耦合）：各分项 date 取自 fetch_indicator
    # 的真实最新数据日，绝不用 now() 兜底。供上层如实标注时效；取不到即 None。
    dates = {k: (vv.get("date") if vv else None) for k, vv in parts.items()}
    if curve:
        dates["yield_curve"] = curve.get("date")
    if spread:
        dates["cn_us_spread"] = spread.get("date")
    return {
        "score": score,
        "sub": {k: round(v, 1) for k, v in sub.items()},
        "parts": {k: (vv["value"] if vv else None) for k, vv in parts.items()},
        "yield_curve": (curve["value"] if curve else None),
        "cn_us_spread": (spread["value"] if spread else None),
        "dates": dates,
    }


def yield_curve_slope() -> dict | None:
    """美债收益率曲线斜率 = 10Y - 2Y（真实数据；任一缺失返回 ``None``，不臆造）。

    倒挂（``value < 0``）是历史上最可靠的衰退前瞻之一；陡峭化（``value`` 走阔）通常
    对应宽松预期或复苏早期。返回 ``{"value", "date", "inverted": bool}``。
    """
    t10 = fetch_indicator("us_treasury_10y")
    t2 = fetch_indicator("us_treasury_2y")
    if not t10 or not t2:
        return None
    v10, v2 = t10.get("value"), t2.get("value")
    if v10 is None or v2 is None:
        return None
    slope = round(float(v10) - float(v2), 4)
    date = t10.get("date") or t2.get("date")
    return {"value": slope, "date": date, "inverted": slope < 0}


def cn_us_yield_spread() -> dict | None:
    """中美 10Y 国债利差 = 中债10Y − 美债10Y（真实数据；任一缺失返回 ``None``，不臆造）。

    口径（单位 pct）：利差为正且走阔 → 境内资产利差优势，利于跨境资金留在
    新兴市场 / A 股；利差收窄甚至倒挂（``value < 0``）→ 美元回流压力，风险偏好承压。
    返回 ``{"value", "date", "inverted": bool}``。
    """
    cn = fetch_indicator("cn_treasury_10y")
    us = fetch_indicator("us_treasury_10y")
    if not cn or not us:
        return None
    v_cn, v_us = cn.get("value"), us.get("value")
    if v_cn is None or v_us is None:
        return None
    spread = round(float(v_cn) - float(v_us), 4)
    # 2026-11-08 修复：原先取 `cn.get("date") or us.get("date")` —— 中美两侧数据
    # 日不同时只看 CN 侧，CN 陈旧时会把 spread 的日期标成陈旧日（而 US 侧其实
    # 是新的），时效口径失真。改为取**两侧日期的较早者**（整体时效上限，
    # 与 macro_event_context 的 min(dates) 口径一致），绝不用 now() 兜底。
    d_cn, d_us = cn.get("date"), us.get("date")
    if d_cn and d_us:
        date = min(d_cn, d_us)   # ISO 串可直接字典序比较
    else:
        date = d_cn or d_us
    return {"value": spread, "date": date, "inverted": spread < 0}


def interpret(key: str, value, prev=None) -> str:
    """规则化「通俗解读」。

    ⚠️ 这是确定性规则，不是大模型生成；调用方展示时必须如实标注，
    不要把一行 if/else 包装成 AI 洞见。
    """
    if value is None:
        return "取不到数据，不做解读（不臆造）"
    try:
        v = float(value)
    except Exception:  # noqa: BLE001
        return "数值异常，不做解读"

    chg = ""
    if prev is not None:
        try:
            d = v - float(prev)
            chg = (f"较上期{'上升' if d > 0 else ('下降' if d < 0 else '持平')}"
                   f"{abs(d):.2f}；")
        except Exception:  # noqa: BLE001
            chg = ""

    if key == "pmi":
        state = "景气扩张" if v >= 50 else "景气收缩"
        level = "扩张动能较强" if v >= 51 else ("贴近荣枯线" if v >= 49.5 else "收缩压力较大")
        return f"{chg}{v:.1f} 位于荣枯线{'上方' if v >= 50 else '下方'}（{state}），{level}。对A股：制造业景气映射顺周期与出口链盈利预期，回升期相关板块赔率改善。"
    if key == "cpi":
        tone = "通胀压力抬头" if v >= 3 else ("温和通胀" if v >= 1 else "偏弱，关注通缩压力")
        return f"{chg}{v:.2f}%，{tone}。对A股：温和通胀+低CPI组合给货币政策留空间，利好利率敏感的成长与红利资产估值。"
    if key == "ppi":
        tone = "上游景气较好" if v >= 0 else "上游仍处通缩，工业品价格承压"
        return f"{chg}{v:.2f}%，{tone}。对A股：PPI 回升通常对应周期股（资源/化工）盈利改善拐点。"
    if key == "gdp":
        return f"{chg}{v:.2f}%，增速{'高于' if v >= 5 else '低于'} 5% 参考位。对A股：总量增速决定盈利中枢，结构亮点看新质生产力与出口韧性。"
    if key == "m2":
        faster = prev is not None and v > float(prev)
        return f"{chg}{v:.2f}%，货币供应同比{'加快' if faster else '放缓或持平'}，影响流动性预期。对A股：M2 走阔利好中小盘流动性行情，收敛期偏防御。"
    if key == "lpr":
        return f"{chg}{v:.2f}%，1 年期 LPR；下调通常利好估值与风险偏好。对A股：降息直接压低贴现率，成长股弹性最大，红利资产受益于资产荒。"

    # ---- 全球指标 ----
    if key == "us_ism_pmi":
        state = "扩张" if v >= 50 else "收缩"
        return f"{chg}美国 ISM 制造业 PMI {v:.1f}，位于荣枯线{'上方' if v >= 50 else '下方'}（{state}）。对A股：美国制造业景气决定出口链（电子/机械/家电）外需，扩张期A股出口板块基本面同步向上。"
    if key == "us_cpi":
        tone = "通胀偏高，美联储偏鹰" if v >= 3 else ("温和通胀" if v >= 1 else "通胀偏低，宽松空间较大")
        return f"{chg}{v:.2f}%，{tone}。对A股：美国通胀决定美联储路径，鹰派预期升温时北向流出+A股成长股估值承压，鸽派则反弹修复。"
    if key == "us_ppi":
        return f"{chg}{v:.2f}%，美国工业品价格；PPI 走高抬升全球成本与通胀预期。对A股：输入性成本压力传导至中下游毛利，资源股受益、制造业承压。"
    if key == "us_nonfarm":
        healthy = v >= 150
        return f"{chg}{v:.0f} 千人；{'就业稳健（>15万）' if healthy else '就业偏弱（<15万）'}。对A股：就业过热→加息预期→全球风险资产波动；就业转弱→宽松交易→A股反弹窗口。"
    if key == "us_gdp":
        return f"{chg}{v:.2f}%，美国 GDP 增速{'强于' if v >= 2 else '弱于'} 2% 参考位。对A股：美国增长强→全球需求与外需订单稳，弱增长则出口与科技硬件链承压。"
    if key == "us_unemployment":
        tone = "就业强劲" if v <= 4 else ("就业正常" if v <= 5 else "就业承压")
        return f"{chg}{v:.2f}%，{tone}。对A股：失业率拐点是美联储转向的领先信号，转向交易利好A股成长与港股弹性。"
    if key == "us_treasury_10y":
        tone = "收益率偏高，全球流动性收紧" if v >= 4 else ("中性区间" if v >= 3 else "收益率偏低，宽松环境")
        return f"{chg}{v:.2f}%，美债 10Y 是全球资产定价锚；{tone}。对A股：收益率高位压制成长股估值与外资风险偏好，拐头回落是A股成长/港股修复的领先信号。"
    if key == "usd_cny":
        if prev is not None:
            d = v - float(prev)
            cheap = "人民币升值" if d < 0 else ("人民币贬值" if d > 0 else "汇率持平")
            return f"{chg}1 美元兑 {v:.4f} 元人民币；{cheap}。对A股：{'人民币升值利好外资流入与人民币资产重估，消费/金融/核心资产受益' if d < 0 else ('贬值期外资流出压力上升，出口占高的行业相对占优' if d > 0 else '汇率平稳，外资行为以基本面为主')}。"
        return f"1 美元兑 {v:.4f} 元人民币（实时价，无前期对照）。对A股：汇率企稳是外资回流的前置条件，快速贬值期防御为主。"
    if key == "dxy":
        tone = "强美元，压制新兴市场与商品" if v >= 103 else ("弱美元，利好风险资产" if v <= 100 else "美元中性")
        return f"{chg}{v:.2f} 点，{tone}。对A股：强美元期新兴市场资金回流美国，北向承压、资源与高股息防御占优；弱美元期A股成长与有色弹性最大。"
    if key == "fed_funds_rate":
        tone = "高位，货币紧缩" if v >= 4.5 else ("中性偏紧" if v >= 3 else "低位，宽松周期")
        return f"{chg}{v:.2f}%，美联储联邦基金目标利率；{tone}。对A股：高利率压制全球流动性与外资风险偏好、抬升贴现率利空成长估值；降息周期开启则利好A股成长与港股弹性。"
    if key == "us_treasury_2y":
        return f"{chg}{v:.2f}%，美债短端收益率；与 10Y 利差是衰退前瞻。对A股：短端高企反映政策收紧预期，曲线倒挂期防御与红利占优、风险偏好回落。"
    if key == "cn_treasury_10y":
        return f"{chg}{v:.2f}%，中国 10Y 国债收益率。对A股：债市收益率快速上行反映流动性收紧/风险偏好抬升的争夺，压制高估值成长；下行则宽松预期升温、红利与成长受益。与美债10Y之差（中美利差）为正且走阔利于跨境资金留在境内。"
    if key in ("us_sp500", "us_nasdaq", "hsi"):
        tag = {"us_sp500": "标普500", "us_nasdaq": "纳指", "hsi": "恒生"}[key]
        if prev is not None:
            d = v - float(prev)
            updown = "上行" if d > 0 else ("下行" if d < 0 else "持平")
            extra = ""
            if key == "us_nasdaq":
                extra = "纳指对A股科技/成长板块映射弹性最大。"
            elif key == "hsi":
                extra = "恒生与A50联动最直接，港股走强通常提升A股高开概率。"
            else:
                extra = "美股情绪经北向与风险偏好传导A股。"
            return f"{chg}最新 {v:,.0f} 点，较前期{updown}。对A股：{tag}{'隔夜走强利好A股风险偏好、映射板块高开' if d > 0 else ('走弱压制当日A股风险偏好，防御与避险板块相对占优' if d < 0 else '持平，影响中性')}；{extra}"
        return f"最新 {v:,.0f} 点（暂无前期对照）。对A股：{tag}是外部风险偏好风向标，隔夜方向直接影响当日A股开盘情绪。"
    return f"{chg}最新值 {v}。"
