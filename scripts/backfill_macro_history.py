# -*- coding: utf-8 -*-
"""宏观指标历史回填脚本（一次性 / 增量皆可）。

用途
----
把 akshare 各宏观接口返回的**全历史序列**写入 ``data/macro_history.db``
（表结构见 ``modules/macro_store.py``），使宏观分可回放、可复现。

为什么需要
----------
改库前宏观指标完全不落盘（每次现取现用），导致：
1. 宏观页首屏 3~8 秒（22 个指标串行网络往返）；
2. 事件因子的宏观分无法复现（今天跑和上个月跑结果不同），历史回测不可归因。

回填的必要性
------------
``modules/macro_data.py`` 里多数指标的 ``parse`` 只提取**最新值 + 前值**
（无法给出历史）；但底层 akshare 接口本身返回**全历史**（实测：
forex_hist_em 4217 行自 2010、index_global_hist_em 10467 行自 1986、
macro_china_pmi 226 行自 2008）。本脚本绕过 parse，直接从原始 df 抽
（日期, 值, 前值）三元组入库。

诚实红线
--------
- 日期归一化失败 / 值取不到 → **跳过该行**，不写脏数据。
- 原始 df 排序方向不一（PMI 倒序、指数正序）→ 统一按日期**升序**处理，
  并据排序位置算 prev（前一行 = 前一期）。
- 取不到任何有效点 → 该指标写入 0 条，如实报告，**不编造**。

用法
----
    python -m scripts.backfill_macro_history            # 全部指标
    python -m scripts.backfill_macro_history pmi usd_cnh # 指定指标
    python -m scripts.backfill_macro_history --dry-run   # 只看会写多少，不落库
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import warnings
from datetime import date

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import macro_store  # noqa: E402
from modules.macro_data import MACRO_INDICATORS, _SPEC  # noqa: E402
from modules.macro_data import (  # noqa: E402
    _pick_date_col as _md_pick_date_col,
    _pick_value_col as _md_pick_value_col,
    _normalize_macro_date as _md_normalize_date,
)


# ── 日期归一化 ──────────────────────────────────────────────────────────────

_CN_MONTH = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
_CN_QUARTER = re.compile(r"(\d{4})\s*年\s*第\s*([1-4一二三四])\s*季度")


def normalize_date(raw) -> str | None:
    """归一化日期 —— 复用生产实现 ``modules.macro_data._normalize_macro_date``
    （单一真理源：生产与回填必须用同一套日期口径，否则入库数据与在线取数对不上）。

    支持形态：
      - ``2026-11-06`` / ``2026/11/06``（date / str / Timestamp）
      - ``2026年10月份``（中国月度宏观接口）
      - ``2026年第1季度``（中国 GDP 季度接口）→ 归一到该季度首月 1 日
      - ``2026-11``（仅年月）
    """
    return _md_normalize_date(raw)


def _to_float(v):
    """宽松数值转换：None / NaN / 非法 → None（绝不补 0）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


# ── 原始 df → (date, value, prev) 三元组 ────────────────────────────────────


def extract_points(spec: dict) -> list[dict]:
    """从原始 df / Series 抽出历史观测点列表（升序）。

    复用 registry 的 ``value_hint``（各指标的真实数值列名，如美官方指标是
    「今值」而非「close」——不复用会挑错列，回填出错误口径的数据）。
    对倒序数据（PMI 等中国月度接口）自动反向。
    """
    import akshare as ak

    # 专用抽取器：口径特殊（需日期参数 + 指定列 + 单位换算），逐个显式实现
    special = _SPECIAL_EXTRACTORS.get(spec.get("key"))
    if special is not None:
        return special(spec)

    fn_name = spec.get("fn")
    args = tuple(spec.get("args", ()))
    fn = getattr(ak, fn_name, None)
    if fn is None:
        return []
    raw = fn(*args)
    if raw is None or getattr(raw, "empty", True):
        return []

    # 少数接口（macro_bank_usa_interest_rate）返回 pandas.Series：索引=日期，值=数值
    if isinstance(raw, pd.Series):
        items = list(raw.items())
        rows = []
        for idx, v in items:
            d = normalize_date(idx)
            val = _to_float(v)
            if d is None or val is None:
                continue
            rows.append({"date": d, "value": val})
        return _finalize(rows)

    df = raw
    # 复用生产的列选择器（单一真理源）：生产用的是**包含匹配**
    # （如 gdp 的 hint '同比增长' 命中 '国内生产总值-同比增长'），
    # 这里若自己重造精确匹配会挑错列 → 回填出错误口径的数据。
    date_col = _pick_date_col(df, spec.get("date_hint"))
    hints = list(spec.get("value_hint") or []) + ["今值", "现值"]
    val_col = _pick_value_col(df, hints)
    if date_col is None or val_col is None:
        return []

    rows = []
    for _, r in df.iterrows():
        d = normalize_date(r[date_col])
        v = _to_float(r[val_col])
        if d is None or v is None:
            continue
        rows.append({"date": d, "value": v})
    return _finalize(rows)


def _extract_usd_cny(spec: dict) -> list[dict]:
    """usd_cny 专用：中行外汇牌价（新浪）→ 央行中间价。

    与生产口径（``modules/macro_data._parse_usd_cny_boc``）一致：
    - 需带 start_date / end_date 参数（否则只返回默认区间）；
    - 取「央行中间价」列（**不是**中行汇买价/钞买价）；
    - 牌价按「每 100 美元」计价 → 需 ÷100（与生产 parse 同口径，不得省略，
      否则入库值会是真实值的 100 倍）。
    """
    import akshare as ak

    fn = getattr(ak, "currency_boc_sina", None)
    if fn is None:
        return []
    try:
        df = fn(start_date="19900101", end_date=date.today().strftime("%Y%m%d"))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"currency_boc_sina 取数失败: {e}") from e
    if df is None or getattr(df, "empty", True):
        return []
    date_col = next((c for c in df.columns if "日期" in str(c)), None)
    mid_col = next((c for c in df.columns if "央行中间价" in str(c)), None)
    if date_col is None or mid_col is None:
        return []
    rows = []
    for _, r in df.iterrows():
        d = normalize_date(r[date_col])
        v = _to_float(r[mid_col])
        if d is None or v is None:
            continue
        # 与生产 parse 同口径：>100 说明是「每 100 美元」牌价 → ÷100
        if v > 100:
            v = v / 100
        rows.append({"date": d, "value": round(v, 6)})
    return _finalize(rows)


def _extract_bond_10y(cn: bool):
    """美债 / 中债 10Y 收益率历史（bond_zh_us_rate 宽表 → 指定期限列）。

    与生产口径（``modules/macro_data._parse_us_treasury_10y`` /
    ``_parse_cn_treasury_10y``）一致：宽表里有几十个期限列，**必须按
    「美国国债收益率10年」/「中国国债收益率10年」精确挑列**，
    走通用列选择会挑到「美国GDP年增率」等无关列 → 回填出错误口径的数据。
    """
    import akshare as ak

    fn = getattr(ak, "bond_zh_us_rate", None)
    if fn is None:
        return []
    target = "中国国债收益率10年" if cn else "美国国债收益率10年"
    try:
        df = fn(start_date="19900101")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"bond_zh_us_rate 取数失败: {e}") from e
    if df is None or getattr(df, "empty", True):
        return []
    date_col = next((c for c in df.columns
                     if "SOLAR_DATE" in str(c) or "日期" in str(c)), None)
    val_col = next((c for c in df.columns if target in str(c)), None)
    if date_col is None or val_col is None:
        return []
    rows = []
    for _, r in df.iterrows():
        d = normalize_date(r[date_col])
        v = _to_float(r[val_col])
        if d is None or v is None:
            continue
        rows.append({"date": d, "value": v})
    return _finalize(rows)


def _extract_bond_2y(spec: dict) -> list[dict]:
    """美债 2Y 收益率历史（宽表 → 「美国国债收益率2年」列）。"""
    import akshare as ak

    fn = getattr(ak, "bond_zh_us_rate", None)
    if fn is None:
        return []
    try:
        df = fn(start_date="19900101")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"bond_zh_us_rate 取数失败: {e}") from e
    if df is None or getattr(df, "empty", True):
        return []
    date_col = next((c for c in df.columns
                     if "SOLAR_DATE" in str(c) or "日期" in str(c)), None)
    val_col = next((c for c in df.columns if "美国国债收益率2年" in str(c)), None)
    if date_col is None or val_col is None:
        return []
    rows = []
    for _, r in df.iterrows():
        d = normalize_date(r[date_col])
        v = _to_float(r[val_col])
        if d is None or v is None:
            continue
        rows.append({"date": d, "value": v})
    return _finalize(rows)


# 专用抽取器注册表（口径特殊，逐个显式实现，不走通用路径）
_SPECIAL_EXTRACTORS = {
    "usd_cny": _extract_usd_cny,
    "us_treasury_10y": lambda spec: _extract_bond_10y(cn=False),
    "us_treasury_2y": _extract_bond_2y,
    "cn_treasury_10y": lambda spec: _extract_bond_10y(cn=True),
}


def _finalize(rows: list[dict]) -> list[dict]:
    """统一升序 + 计算 prev（前一期）。首行无前值 → None（不编造）。"""
    if not rows:
        return []
    rows.sort(key=lambda x: x["date"])
    for i, r in enumerate(rows):
        r["prev"] = rows[i - 1]["value"] if i > 0 else None
    return rows


def _pick_date_col(df, hints=None):
    """挑日期列 —— 复用生产实现（单一真理源，含 '季度'/'TRADE_DATE' 等候选）。

    生产 ``modules/macro_data._pick_date_col`` 用**包含匹配**：
    ``any(k in str(c) for k in (hints or base))``。自造精确匹配会漏列。
    """
    return _md_pick_date_col(df, hints)


def _pick_value_col(df, hints):
    """挑数值列 —— 复用生产实现（单一真理源，含 '同比增长' 等模糊命中）。

    生产 ``modules/macro_data._pick_value_col`` 用**包含匹配**：
    ``if h in str(c)``。自造精确匹配会让 gdp 挑错列（绝对值列）→ 口径错误。
    """
    return _md_pick_value_col(df, hints)


# ── 主流程 ──────────────────────────────────────────────────────────────────


def backfill(keys: list[str], dry_run: bool = False) -> dict:
    """回填指定指标。返回统计 dict。"""
    stats = {}
    for key in keys:
        spec = _SPEC.get(key)
        if not spec:
            stats[key] = {"ok": False, "reason": "指标不在注册表"}
            continue
        try:
            points = extract_points(spec)
        except Exception as e:  # noqa: BLE001 - 单指标失败不影响其余
            stats[key] = {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:120]}"}
            continue
        if not points:
            stats[key] = {"ok": False, "reason": "原始接口未取到有效历史点"}
            continue
        if dry_run:
            stats[key] = {
                "ok": True,
                "dry_run": True,
                "points": len(points),
                "from": points[0]["date"],
                "to": points[-1]["date"],
            }
            continue
        n = macro_store.write_macro_series(key, points, source=spec.get("source", ""))
        stats[key] = {
            "ok": True,
            "written": n,
            "from": points[0]["date"],
            "to": points[-1]["date"],
        }
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="宏观指标历史回填")
    ap.add_argument("keys", nargs="*", help="指标 key（留空 = 全部）")
    ap.add_argument("--dry-run", action="store_true", help="只报告将写入的数据量，不落库")
    args = ap.parse_args()

    macro_store.init_macro_db()

    keys = args.keys or [m["key"] for m in MACRO_INDICATORS]
    print(f"[backfill] 目标指标 {len(keys)} 个{'（dry-run）' if args.dry_run else ''}")
    stats = backfill(keys, dry_run=args.dry_run)

    ok = sum(1 for s in stats.values() if s.get("ok"))
    for key, s in stats.items():
        if s.get("ok"):
            tail = f"{s.get('written', s.get('points'))} 点 {s['from']}~{s['to']}"
            print(f"  [OK]   {key:16} {tail}")
        else:
            print(f"  [FAIL] {key:16} {s.get('reason')}")
    print(f"[backfill] 成功 {ok}/{len(keys)}")
    return 0 if ok == len(keys) else 1


if __name__ == "__main__":
    raise SystemExit(main())
