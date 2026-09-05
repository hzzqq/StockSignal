"""个股财报片段的纯函数助手（无 streamlit 依赖，可单测）。

抽离自 pages/20_个股分析.py 的 _fr_* 函数，独立成模块以便单元测试覆盖，
避免"仅凭 import 不崩"的伪绿测试。本模块零业务依赖，只引用 modules.colors。
"""
from __future__ import annotations

import pandas as pd

from modules.colors import UP_COLOR, DOWN_COLOR, HOLD_COLOR

# 业绩同比着色：红=同比增长为正（改善）/ 绿=为负（下滑），
# 与 16页 财报日历、A股红涨绿跌语义一致（业绩改善=红）。
# 注意：20页价格域是「绿涨红跌」例外（RED 变量实为绿），
# 但业绩域明确走 A股默认「红涨绿跌」，故直接用 UP_COLOR/DOWN_COLOR，
# 不复用会被绿涨例外污染的 RED/GREEN 变量。
_PERF_UP = UP_COLOR    # 红
_PERF_DOWN = DOWN_COLOR  # 绿
_PERF_FLAT = HOLD_COLOR  # 中性


def fr_fmt(v):
    """数值格式化：None/NaN→—；大数转 亿/万；其余保留 2 位。"""
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        fv = float(v)
        if abs(fv) >= 1e8:
            return f"{fv / 1e8:.2f}亿"
        if abs(fv) >= 1e4:
            return f"{fv / 1e4:.2f}万"
        return f"{fv:.2f}"
    except (TypeError, ValueError):
        return str(v) if v is not None else "—"


def fr_filter_by_code(df, code: str):
    """在任意财报 DataFrame 中按 6 位代码过滤出该股行（列名自适应）。

    依次尝试 代码 / 股票代码 / 证券代码 / code 列；找不到代码列或过滤异常时返回 None。
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        return None
    code = str(code).zfill(6)
    _col = None
    for cand in ("代码", "股票代码", "证券代码", "code"):
        if cand in df.columns:
            _col = cand
            break
    if _col is None:
        return None
    try:
        _s = df[_col].astype(str).str.strip().str.zfill(6)
        return df[_s == code]
    except Exception:
        return None


def fr_color_yoy(v):
    """业绩同比着色：>0 红(改善) / <0 绿(下滑)，与 16页 财报日历一致（红=好）。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return _PERF_FLAT, "—"
    if v > 0:
        return _PERF_UP, f"+{v:.2f}%"
    if v < 0:
        return _PERF_DOWN, f"{v:.2f}%"
    return _PERF_FLAT, "0.00%"


# 新浪三表中应保留为原样的非数值/标识列（不参加金额单位换算）
_NON_NUMERIC_COLS = (
    "报告日", "数据源", "是否审计", "公告日期", "币种", "类型", "更新日期",
)


def fr_format_financial_df(df):
    """财务三表（新浪宽表：行=报告期，列=科目）数值格式化：大数转 亿/万。

    仅对数值列做单位换算；报告日/数据源/公告日期等标识列原样保留。
    返回新 DataFrame，不修改入参。
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        return df
    out = df.copy()
    for c in out.columns:
        if c in _NON_NUMERIC_COLS:
            continue
        try:
            num = pd.to_numeric(out[c], errors="coerce")

            def _fmt(x):
                if pd.isna(x):
                    return "—"
                if abs(x) >= 1e8:
                    return f"{x / 1e8:.2f}亿"
                if abs(x) >= 1e4:
                    return f"{x / 1e4:.2f}万"
                return f"{x:.2f}"

            out[c] = num.apply(_fmt)
        except Exception:
            # 转换失败（罕见）保持原列
            pass
    return out
