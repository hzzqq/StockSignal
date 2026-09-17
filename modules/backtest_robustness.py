"""modules/backtest_robustness.py — 回测稳健性（H5）。

把「参数挑出来的漂亮曲线」升级为「有稳健性证据的曲线」。四个纯计算能力：

1. ``walk_forward_windows``：把区间切成「滚动/扩张窗口」的样本内 + 样本外段，
   在训练段选参数、在测试段验证 —— 回答"这套参数是真规律还是记住了历史"。
2. ``overfit_assessment`` / ``summarize_walk_forward``：样本内外收益落差 → 过拟合判定。
3. ``param_sensitivity_matrix``：参数网格结果透视成矩阵 + 「参数高原占比」，
   高原宽 = 稳健，尖峰窄 = 过拟合风险。
4. ``ic_decay``：因子 IC 随 horizon 的衰减曲线（复用 ``factor_analysis``）。

红线（诚实口径）：
- 所有函数**纯计算、不触网**，数据由调用方注入；
- 样本不足 / 缺样本外结果 / 网格为空时，返回带 ``status`` 的**显式不可用**语义，
  **绝不编造**稳健结论、绝不把缺失当 0；
- 任何异常都兜底为安全默认值，不向上抛（回测页 fragment 不能被它拖崩）。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable

__all__ = [
    "walk_forward_windows",
    "overfit_assessment",
    "summarize_walk_forward",
    "param_sensitivity_matrix",
    "ic_decay",
]


def _to_date(x: Any) -> _dt.date:
    """把 str/date/datetime 统一成 ``datetime.date``。"""
    if isinstance(x, _dt.datetime):
        return x.date()
    if isinstance(x, _dt.date):
        return x
    return _dt.date.fromisoformat(str(x)[:10])


def walk_forward_windows(start: Any, end: Any, n_splits: int = 3,
                         min_train_days: int = 60, min_test_days: int = 5) -> list[dict]:
    """扩张窗口 walk-forward 切分：训练段从 ``start`` 起不断加长，测试段紧随其后。

    返回 ``[{fold, train_start, train_end, test_start, test_end, train_days, test_days}]``。
    区间过短（切不出合法窗口）时返回 ``[]`` —— 调用方据此诚实提示"样本不足以做稳健性检验"。
    """
    try:
        s, e = _to_date(start), _to_date(end)
    except Exception:  # noqa: BLE001
        return []
    if e <= s or int(n_splits) < 1:
        return []
    total = (e - s).days
    if total < (min_train_days + min_test_days):
        return []
    step = total / (int(n_splits) + 1)
    out: list[dict] = []
    for i in range(1, int(n_splits) + 1):
        tr_end = s + _dt.timedelta(days=round(step * i))
        te_start = tr_end
        te_end = (s + _dt.timedelta(days=round(step * (i + 1)))) if i < int(n_splits) else e
        if (tr_end - s).days < min_train_days:
            continue
        if (te_end - te_start).days < min_test_days:
            continue
        out.append({
            "fold": i,
            "train_start": s.isoformat(), "train_end": tr_end.isoformat(),
            "test_start": te_start.isoformat(), "test_end": te_end.isoformat(),
            "train_days": (tr_end - s).days, "test_days": (te_end - te_start).days,
        })
    return out


def overfit_assessment(is_return_pct: Any, oos_return_pct: Any,
                       tolerance: float = 0.5) -> dict:
    """样本内(IS) vs 样本外(OOS)收益落差 → 过拟合判定。

    ``tolerance``：允许的收益衰减比例（默认 0.5 = 样本外衰减不超过 50%）。
    语义（诚实）：样本不足时 ``status="unavailable"``，不做任何"看起来还行"的粉饰。
    """
    if is_return_pct is None or oos_return_pct is None:
        return {"status": "unavailable",
                "reason": "样本内/外收益缺失（回测未产生交易或数据不足）"}
    try:
        is_r, oos_r = float(is_return_pct), float(oos_return_pct)
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": "收益非数值"}
    if is_r <= 0:
        return {"status": "no_edge", "is": round(is_r, 2), "oos": round(oos_r, 2),
                "verdict": "no_edge",
                "note": "样本内本身不盈利，谈不上过拟合——先解决策略在训练段就无效的问题。"}
    decay = 1.0 - oos_r / is_r
    if oos_r >= is_r:
        verdict, note = "robust", "样本外不降反升，参数迁移性良好。"
    elif decay <= tolerance:
        verdict, note = "acceptable", (
            f"样本外收益衰减 {decay * 100:.0f}%，在容忍阈值（{tolerance * 100:.0f}%）内。")
    else:
        verdict, note = "overfit_risk", (
            f"样本外收益衰减 {decay * 100:.0f}%，超过容忍阈值（{tolerance * 100:.0f}%），存在过拟合风险。")
    return {"status": "ok", "is": round(is_r, 2), "oos": round(oos_r, 2),
            "decay_pct": round(decay * 100, 1), "verdict": verdict, "note": note}


def summarize_walk_forward(folds: Iterable[dict] | None) -> dict:
    """聚合各 fold 的 IS/OOS 收益 → 稳健性总评。

    ``folds`` 每项至少含 ``is_return_pct`` / ``oos_return_pct``。全空 → ``unavailable``。
    """
    folds = list(folds or [])
    valid = [f for f in folds
             if isinstance(f, dict)
             and f.get("is_return_pct") is not None
             and f.get("oos_return_pct") is not None]
    if not valid:
        return {"status": "unavailable", "n_folds": len(folds),
                "note": "没有可用于稳健性评估的样本外结果（回测未产生交易或数据不足）。"}
    n = len(valid)
    mean_is = sum(float(f["is_return_pct"]) for f in valid) / n
    mean_oos = sum(float(f["oos_return_pct"]) for f in valid) / n
    win = sum(1 for f in valid if float(f["oos_return_pct"]) > 0) / n
    return {
        "status": "ok", "n_folds": n,
        "mean_is": round(mean_is, 2), "mean_oos": round(mean_oos, 2),
        "oos_win_rate": round(win * 100, 1),
        "assessment": overfit_assessment(mean_is, mean_oos),
    }


def param_sensitivity_matrix(runs: Iterable[dict] | None, x_key: str, y_key: str,
                             value_key: str = "total_return",
                             within: float = 0.3) -> dict:
    """把参数网格结果透视成矩阵 + 「参数高原占比」。

    ``runs`` 每项形如 ``{"params": {...}, "total_return": 12.3, ...}``（``run_param_scan``
    的返回）。``plateau_ratio`` = 收益落在「最优值 ×(1-within)」以内的格子占比：
    越高说明存在"参数高原"（稳健），越低说明是"参数尖峰"（过拟合风险）。

    空网格返回空矩阵（``plateau_ratio=None``），不臆造。
    """
    rows = [r for r in (runs or [])
            if isinstance(r, dict) and "error" not in r and isinstance(r.get("params"), dict)]
    if not rows:
        return {"x_labels": [], "y_labels": [], "values": [],
                "best": None, "plateau_ratio": None, "n_cells": 0}

    def _val(r: dict):
        if value_key == "total_return":
            return r.get("total_return")
        summary = r.get("summary")
        if isinstance(summary, dict):
            return summary.get(value_key)
        return r.get(value_key)

    xs = sorted({r["params"].get(x_key) for r in rows}, key=lambda v: (v is None, v))
    ys = sorted({r["params"].get(y_key) for r in rows}, key=lambda v: (v is None, v))
    grid: dict = {}
    best = None
    for r in rows:
        x, y, v = r["params"].get(x_key), r["params"].get(y_key), _val(r)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        grid[(x, y)] = v
        if best is None or v > best[0]:
            best = (v, x, y)
    values = [[grid.get((x, y)) for x in xs] for y in ys]
    flat = [v for row in values for v in row if v is not None]
    plateau = None
    if best and best[0] > 0 and flat:
        thr = best[0] * (1.0 - within)
        plateau = round(sum(1 for v in flat if v >= thr) / len(flat) * 100, 1)
    return {
        "x_labels": xs, "y_labels": ys, "values": values,
        "best": {"value": round(best[0], 2), "x": best[1], "y": best[2]} if best else None,
        "plateau_ratio": plateau, "n_cells": len(flat),
    }


def ic_decay(factor_panel, ret_panel, horizons: Iterable[int] = (1, 3, 5, 10)) -> list[dict]:
    """因子 IC 随 horizon 的衰减：``[{horizon, ic_mean, ir, n}]``。

    复用 ``modules.factor_analysis``。面板缺失/依赖不可用时返回 ``[]``（诚实不出结论）。
    """
    try:
        from modules.factor_analysis import ic_series, ic_summary
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for h in horizons:
        try:
            sm = ic_summary(ic_series(factor_panel, ret_panel, forward=int(h)))
            ic_mean = sm.get("ic_mean")
            ir = sm.get("ir")
            out.append({
                "horizon": int(h),
                "ic_mean": None if ic_mean != ic_mean else round(float(ic_mean), 4),
                "ir": None if ir != ir else round(float(ir), 4),
                "n": int(sm.get("n") or 0),
            })
        except Exception:  # noqa: BLE001
            out.append({"horizon": int(h), "ic_mean": None, "ir": None, "n": 0})
    return out
