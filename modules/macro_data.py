"""modules/macro_data.py — 宏观指标取数与规则化解读（补空白，对标 jiuzhang 宏观简报）。

为什么补这块：
- ``app.py`` 的功能表早就写了「宏观数据 | PMI、CPI、社融等关键宏观指标」，
  但一直没有对应的页面 —— 属于**说了却没做**的空白。
- 投研圆桌的历史交付物多次标注「宏观 PMI / 社融未取到，下一轮需补宏观景气与
  政策变量」，说明这是真实缺口而不是锦上添花。

红线（诚实口径）：
- 取不到就返回 ``None``，**绝不用合成数据填充**；每个数值必须带真实数据日期。
- 「通俗解读」是**规则生成的确定性结论**，不是大模型生成的。页面必须如实标注，
  否则等于把一句话 if/else 包装成 AI 洞见 —— 那也是一种造假。
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# value_hint 用于在 akshare 返回的宽表里挑出真正的数值列：
# akshare 各宏观接口列名并不统一（且版本间会变），按**子串匹配**比硬编码列名稳。
MACRO_INDICATORS: list[dict] = [
    {"key": "pmi", "name": "制造业 PMI", "fn": "macro_china_pmi", "unit": "%",
     "freq": "月", "source": "国家统计局",
     "value_hint": ["制造业-指数", "PMI", "指数"],
     "desc": "荣枯线 50；>50 景气扩张，<50 收缩"},
    {"key": "cpi", "name": "CPI 同比", "fn": "macro_china_cpi", "unit": "%",
     "freq": "月", "source": "国家统计局",
     "value_hint": ["全国-同比增长", "同比增长", "当月同比"],
     "desc": "通胀水平；持续 >3% 通常压制货币宽松预期"},
    {"key": "ppi", "name": "PPI 同比", "fn": "macro_china_ppi", "unit": "%",
     "freq": "月", "source": "国家统计局",
     "value_hint": ["当月同比增长", "同比增长"],
     "desc": "工业品出厂价格；反映上游景气与利润传导"},
    {"key": "gdp", "name": "GDP 同比", "fn": "macro_china_gdp", "unit": "%",
     "freq": "季", "source": "国家统计局",
     "value_hint": ["GDP同比增长", "当季同比", "同比增长"],
     "desc": "经济总量增速，季度低频指标"},
    {"key": "m2", "name": "M2 同比", "fn": "macro_china_money_supply", "unit": "%",
     "freq": "月", "source": "央行",
     "value_hint": ["M2"],
     "desc": "广义货币供应；与流动性宽松程度相关"},
    {"key": "lpr", "name": "LPR（1 年期）", "fn": "macro_china_lpr", "unit": "%",
     "freq": "月", "source": "央行",
     "value_hint": ["LPR1Y", "1年"],
     "desc": "贷款市场报价利率；下调通常利好估值"},
]

_SPEC = {m["key"]: m for m in MACRO_INDICATORS}


def _pick_date_col(df: pd.DataFrame):
    for c in df.columns:
        if any(k in str(c) for k in ("日期", "月份", "季度", "时间", "date")):
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


def _to_float(v):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(v)
    except Exception:  # noqa: BLE001
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
        df = fn()
        if df is None or getattr(df, "empty", True):
            return None
        date_col = _pick_date_col(df)
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
    return f"{chg}最新值 {v}。"
