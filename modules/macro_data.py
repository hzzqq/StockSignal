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
        return None


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


def _parse_usdcny(df):
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
    {"key": "usd_cny", "name": "美元兑人民币(USD/CNY)", "fn": "fx_pair_quote",
     "unit": "", "freq": "实时", "source": "外汇交易中心", "region": "全球",
     "parse": _parse_usdcny,
     "desc": "人民币汇率；人民币升值利好人民币资产"},
    {"key": "dxy", "name": "美元指数 DXY", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "ICE / 东方财富", "region": "全球",
     "args": ("美元指数",), "value_hint": ["最新价", "收盘", "close"],
     "desc": "美元强弱；>103 强美元压制新兴市场与商品"},

    # ----------------------------- 全球：股市情绪传导 -----------------------------
    {"key": "us_sp500", "name": "标普500指数", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "东方财富", "region": "全球",
     "args": ("标普500",), "value_hint": ["最新价", "收盘", "close"],
     "desc": "美股大盘基准，外部风险偏好风向标"},
    {"key": "us_nasdaq", "name": "纳斯达克指数", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "东方财富", "region": "全球",
     "args": ("纳斯达克",), "value_hint": ["最新价", "收盘", "close"],
     "desc": "美股科技风向标，成长股估值锚"},
    {"key": "hsi", "name": "恒生指数", "fn": "index_global_hist_em",
     "unit": "点", "freq": "日", "source": "东方财富", "region": "全球",
     "args": ("恒生指数",), "value_hint": ["最新价", "收盘", "close"],
     "desc": "港股情绪，A 股外部传导最直接的窗口"},
]

_SPEC = {m["key"]: m for m in MACRO_INDICATORS}


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


def fetch_indicator(key: str) -> dict | None:
    """取单个宏观指标的最新值与前值。取不到返回 ``None``（不臆造）。"""
    spec = _SPEC.get(key)
    if not spec:
        return None
    try:
        import akshare as ak

        fn = getattr(ak, spec["fn"], None)
        if fn is None:
            return None
        args = tuple(spec.get("args", ()))
        df = fn(*args)

        # 特殊解析（美债 / 汇率）：返回 {"value","prev","date"}
        if spec.get("parse") is not None:
            parsed = spec["parse"](df)
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
                "date": parsed["date"],
            }

        if df is None or getattr(df, "empty", True):
            return None
        date_col = _pick_date_col(df, spec.get("date_hint"))
        val_col = _pick_value_col(df, spec["value_hint"])
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
            "date": str(last[date_col])[:10],
        }
    except Exception as e:  # noqa: BLE001
        logger.info(f"[macro_data] 指标 {key} 取数失败: {e}")
        return None


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

    if not sub:
        return None
    score = round(sum(sub.values()) / len(sub))
    return {
        "score": score,
        "sub": {k: round(v, 1) for k, v in sub.items()},
        "parts": {k: (vv["value"] if vv else None) for k, vv in parts.items()},
    }


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
        return f"{chg}{v:.1f} 位于荣枯线{'上方' if v >= 50 else '下方'}（{state}），{level}。"
    if key == "cpi":
        tone = "通胀压力抬头" if v >= 3 else ("温和通胀" if v >= 1 else "偏弱，关注通缩压力")
        return f"{chg}{v:.2f}%，{tone}。CPI 走高通常压制货币宽松预期。"
    if key == "ppi":
        tone = "上游景气较好" if v >= 0 else "上游仍处通缩，工业品价格承压"
        return f"{chg}{v:.2f}%，{tone}。PPI 回升通常对应周期股盈利改善。"
    if key == "gdp":
        return f"{chg}{v:.2f}%，增速{'高于' if v >= 5 else '低于'} 5% 参考位。"
    if key == "m2":
        faster = prev is not None and v > float(prev)
        return f"{chg}{v:.2f}%，货币供应同比{'加快' if faster else '放缓或持平'}，影响流动性预期。"
    if key == "lpr":
        return f"{chg}{v:.2f}%，1 年期 LPR；下调通常利好估值与风险偏好。"

    # ---- 全球指标 ----
    if key == "us_ism_pmi":
        state = "扩张" if v >= 50 else "收缩"
        return f"{chg}美国 ISM 制造业 PMI {v:.1f}，位于荣枯线{'上方' if v >= 50 else '下方'}（{state}）。"
    if key == "us_cpi":
        tone = "通胀偏高，美联储偏鹰" if v >= 3 else ("温和通胀" if v >= 1 else "通胀偏低，宽松空间较大")
        return f"{chg}{v:.2f}%，{tone}。"
    if key == "us_ppi":
        return f"{chg}{v:.2f}%，美国工业品价格；PPI 走高抬升全球成本与通胀预期。"
    if key == "us_nonfarm":
        healthy = v >= 150
        return f"{chg}{v:.0f} 千人；{'就业稳健（>15万）' if healthy else '就业偏弱（<15万）'}。"
    if key == "us_gdp":
        return f"{chg}{v:.2f}%，美国 GDP 增速{'强于' if v >= 2 else '弱于'} 2% 参考位。"
    if key == "us_unemployment":
        tone = "就业强劲" if v <= 4 else ("就业正常" if v <= 5 else "就业承压")
        return f"{chg}{v:.2f}%，{tone}。"
    if key == "us_treasury_10y":
        tone = "收益率偏高，全球流动性收紧" if v >= 4 else ("中性区间" if v >= 3 else "收益率偏低，宽松环境")
        return f"{chg}{v:.2f}%，美债 10Y 是全球资产定价锚；{tone}。"
    if key == "usd_cny":
        if prev is not None:
            d = v - float(prev)
            cheap = "人民币升值" if d < 0 else ("人民币贬值" if d > 0 else "汇率持平")
            return f"{chg}1 美元兑 {v:.4f} 元人民币；{cheap}，影响人民币资产估值。"
        return f"1 美元兑 {v:.4f} 元人民币（实时价，无前期对照）。"
    if key == "dxy":
        tone = "强美元，压制新兴市场与商品" if v >= 103 else ("弱美元，利好风险资产" if v <= 100 else "美元中性")
        return f"{chg}{v:.2f} 点，{tone}。"
    if key in ("us_sp500", "us_nasdaq", "hsi"):
        if prev is not None:
            d = v - float(prev)
            updown = "上行" if d > 0 else ("下行" if d < 0 else "持平")
            return f"{chg}最新 {v:,.0f} 点，较前期{updown}（美股/港股外部情绪传导 A 股）。"
        return f"最新 {v:,.0f} 点（暂无前期对照）。"
    return f"{chg}最新值 {v}。"
