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


def fr_normalize_pct(v):
    """把「百分数 / 带 % 字符串 / None」归一为 float（百分数数值）；非法返回 None。"""
    if v is None:
        return None
    t = str(v).replace("%", "").replace(",", "").strip()
    if t in ("", "-", "None", "nan", "NaN"):
        return None
    try:
        return float(t)
    except (TypeError, ValueError):
        return None


def fr_fmt_pct(v):
    """百分数格式化：None/NaN → —；其余保留 2 位 + %。"""
    x = fr_normalize_pct(v)
    if x is None:
        return "—"
    return f"{x:.2f}%"


def fr_compute_margins(row) -> dict:
    """从单期业绩报表行计算 毛利率% / 净利率%（均为百分数）。

    - 毛利率%：取东财「销售毛利率」（重命名后列名 毛利率，本身已是百分数）。
    - 净利率%：= 净利润 / 营业总收入 × 100（两者原始单位为元）。
    任一缺失 / 非法返回对应 None（不造假、不补零）。
    """
    if row is None or getattr(row, "empty", True):
        return {"毛利率%": None, "净利率%": None}
    gm = fr_normalize_pct(row.get("毛利率"))
    net = None
    try:
        rev_f = float(row.get("营业总收入"))
        np_f = float(row.get("净利润"))
        if rev_f not in (None,) and rev_f != 0:
            net = np_f / rev_f * 100
    except (TypeError, ValueError):
        net = None
    return {"毛利率%": gm, "净利率%": net}


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


# ══════════════════════════════════════════════════════════════════════════
# 横向历史对比（v3 · 2026-09-13）
# ══════════════════════════════════════════════════════════════════════════
# 东财业绩报表（stock_yjbb_em）每个报告期只返回「该期全市场」一张表，
# 故「同一只股票的多个报告期」必须拉多个 period 再按代码过滤、纵向拼接。
# 下列函数把这一流程做成纯函数，便于单测（不发网络请求）。

# 报告期代码 → 人类可读标签（如 "20251231" → "2025年报"）。
# 覆盖 0331/0630/0930/1231 四种法定报告期。
_QUARTER_SUFFIX = {"0331": "一季报", "0630": "中报", "0930": "三季报", "1231": "年报"}


def fr_period_label(period: str) -> str:
    """把报告期代码转中文标签：'20251231' → '2025年报'；无法识别时原样返回。"""
    p = str(period).strip()
    if len(p) != 8 or not p.isdigit():
        return p
    year, mmdd = p[:4], p[4:]
    suffix = _QUARTER_SUFFIX.get(mmdd)
    return f"{year}{suffix}" if suffix else p


def fr_build_history(period_rows) -> "pd.DataFrame":
    """把「多个报告期 → 各期该股单行」的结果合并为横向历史对比表。

    参数 period_rows：可迭代的 (period, row) —— period 形如 '20251231'，
      row 为 ``fr_filter_by_code(...)`` 的产物（0 或 1 行 DataFrame），可为 None。

    返回列：报告期(period 代码) / 报告期标签 / 每股收益 / 营业总收入 / 营收同比% /
      净利润 / 净利润同比% / ROE%。按报告期升序（旧→新）排列。
    缺失期直接跳过（不补零，避免造假）；无任何有效数据时返回空 DataFrame。
    本函数不修改入参。
    """
    cols = ["报告期", "报告期标签", "每股收益", "营业总收入", "营收同比%", "净利润", "净利润同比%", "ROE%", "毛利率%", "净利率%"]
    recs = []
    for period, row in (period_rows or []):
        if row is None or getattr(row, "empty", True):
            continue
        try:
            r = row.iloc[0]
        except Exception:
            continue
        rec = {"报告期": str(period), "报告期标签": fr_period_label(period)}
        for c in ("每股收益", "营业总收入", "营收同比%", "净利润", "净利润同比%", "ROE%"):
            try:
                rec[c] = r.get(c)
            except Exception:
                rec[c] = None
        rec.update(fr_compute_margins(r))
        recs.append(rec)
    if not recs:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(recs, columns=cols)
    return out.sort_values("报告期").reset_index(drop=True)


# 横向历史对比表里，指标列 → 其同比列名的映射。
# ⚠️ 不能靠 f"{metric}同比%" 拼——东财把「营业总收入」的同比列命名为「营收同比%」（缩写）。
# 拼错会导致同比序列全为 None（静默丢数据），故在此显式登记。
_METRIC_YOY_COL = {
    "营业总收入": "营收同比%",
    "净利润": "净利润同比%",
    "每股收益": None,   # 东财业绩报表未提供 EPS 同比
    "ROE%": None,       # 同上
    "毛利率%": None,    # 毛利率无同列同比
    "净利率%": None,    # 净利率（=净利润/营收）无同列同比
}


def fr_yoy_column(metric: str):
    """返回 metric 对应的同比列名；无对应列时返回 None。"""
    return _METRIC_YOY_COL.get(str(metric), f"{metric}同比%")


def fr_history_metrics(df, metric: str = "净利润"):
    """从横向历史表抽取绘图所需的 (x标签列表, 数值列表, 同比列表)。

    - x：报告期标签（如 '2023年报'），按输入顺序
    - 数值：metric 列转 float（NaN → None，Plotly 自动断线，不补零）
    - 同比：metric 对应同比列（见 _METRIC_YOY_COL）转 float，缺失时为 None
    数据不足（<2 个点）时仍返回（调用方自行决定是否绘图），但任何异常都返回三个空列表。
    """
    if df is None or getattr(df, "empty", True) or metric not in df.columns:
        return [], [], []
    try:
        x = [str(v) for v in df["报告期标签"].tolist()]
        y = pd.to_numeric(df[metric], errors="coerce")
        y = [None if pd.isna(v) else float(v) for v in y.tolist()]
        yoy_col = fr_yoy_column(metric)
        if yoy_col and yoy_col in df.columns:
            yy = pd.to_numeric(df[yoy_col], errors="coerce")
            yoy = [None if pd.isna(v) else float(v) for v in yy.tolist()]
        else:
            yoy = [None] * len(x)
        return x, y, yoy
    except Exception:
        return [], [], []


def fr_expand_rows(df, metric: str = "净利润"):
    """生成「展开分析」明细行：[(报告期标签, 数值, 同比数值)]，最新期在前。

    与 ``fr_history_metrics`` 同源，仅排序方向相反（用户视角先看最新）。
    """
    x, y, yoy = fr_history_metrics(df, metric)
    rows = list(zip(x, y, yoy))
    return rows[::-1]
