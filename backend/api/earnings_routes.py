"""GET /api/v2/read/earnings-hunter —— 业绩预告信号扫描端点（后端化 v1 页面 77 财报猎手）。

数据源：``modules.fundflow.get_earnings_forecast(period)``（东财 stock_yjyg_em，
best-effort，30 分钟 TTL 缓存）；信号分级：``modules.financial_hunter`` 启发式文本映射。

红线：
  * 不编造预告行、不补 0：数据源为空或取数异常时 available=false + 真实原因，
    单个数据集失败不阻断整体响应；
  * period / min_pct / signals 严格校验，非法 -> 422 validation_error；
  * 响应里 NaN/NaT 一律转 None（JSON 中不允许出现 NaN 字面量）。
"""
from __future__ import annotations

import pandas as pd
from flask import Blueprint, request

from modules.financial_hunter import SIGNAL_ORDER, annotate, scan
from modules.fundflow import get_earnings_forecast

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok

bp = Blueprint("earnings_hunter", __name__, url_prefix="/api/v2")

_PERIODS = ["20260630", "20260331", "20251231", "20250930", "20250630"]
_PERIODS_TXT = "/".join(_PERIODS)
_EMPTY_REASON = "该报告期暂无业绩预告数据（可能未到披露期或接口暂不可用）"
_PCT_MIN, _PCT_MAX = -200.0, 200.0
_MAX_ROWS = 100


def _nan_to_none(v):
    """递归把 NaN/NaT/pd.NA 转 None，保证 JSON 里不出现 NaN 字面量。"""
    if isinstance(v, dict):
        return {k: _nan_to_none(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_nan_to_none(x) for x in v]
    if v is None:
        return None
    try:
        if bool(pd.isna(v)):
            return None
    except (TypeError, ValueError):
        pass  # 非标量（如嵌套容器被 pandas 拒绝）原样透传，交给 ok() 兜底
    return v


@bp.get("/read/earnings-hunter")
@jwt_required
def earnings_hunter():
    """业绩预告信号扫描。

    query: period?（报告期，须在白名单内，缺省 20260630）,
           min_pct?（-200~200 的数值，按业绩变动幅度过滤）,
           signals?（逗号分隔，取值 ⊆ 利好/偏多/中性/偏空/利空）
    返回: {available, reason, rows, n_total, n_scanned, signal_counts}
          available=false 时仅含 available/reason/rows。
    """
    # ---- period 白名单（区分「未提供」与「显式空值」）----
    period = request.args.get("period")
    if period is None:
        period = _PERIODS[0]
    if period not in _PERIODS:
        return fail(message=f"period 须为 {_PERIODS_TXT} 之一",
                    code="validation_error", http_status=422)

    # ---- min_pct：可选 float，-200..200（NaN/inf 在范围判断中被拒）----
    min_pct = None
    raw_min = request.args.get("min_pct")
    if raw_min is not None and raw_min.strip() != "":
        try:
            min_pct = float(raw_min)
        except (TypeError, ValueError):
            return fail(message="min_pct 须为 -200~200 的数值",
                        code="validation_error", http_status=422)
        if not (_PCT_MIN <= min_pct <= _PCT_MAX):
            return fail(message="min_pct 须为 -200~200 的数值",
                        code="validation_error", http_status=422)

    # ---- signals：逗号分隔，取值 ⊆ SIGNAL_ORDER ----
    signals = None
    raw_sig = request.args.get("signals")
    if raw_sig is not None and raw_sig.strip() != "":
        items = [s.strip() for s in raw_sig.split(",")]
        if any(not s for s in items) or any(s not in SIGNAL_ORDER for s in items):
            return fail(message="signals 须为逗号分隔的信号级别，取值限："
                                + "/".join(SIGNAL_ORDER),
                        code="validation_error", http_status=422)
        signals = items

    # ---- 取数（best-effort，失败不阻断）----
    try:
        raw = get_earnings_forecast(period)
    except Exception as e:  # noqa: BLE001 - 单个数据源失败诚实降级，不编造数据
        reason = f"业绩预告获取失败: {type(e).__name__}: {e}"[:180]
        return ok(data={"available": False, "reason": reason, "rows": []},
                  message="earnings-hunter")

    if raw is None or len(raw) == 0:
        return ok(data={"available": False, "reason": _EMPTY_REASON, "rows": []},
                  message="earnings-hunter")

    # ---- 分级 + 筛选 ----
    anno = annotate(raw)
    vc = anno["_signal"].value_counts()
    signal_counts = {s: int(vc.get(s, 0)) for s in SIGNAL_ORDER}  # 全档都给，0 也给

    hits = scan(raw, min_pct=min_pct, signals=signals)
    rows = [_nan_to_none(rec) for rec in hits.head(_MAX_ROWS).to_dict("records")]

    return ok(data={
        "available": True,
        "reason": None,
        "rows": rows,
        "n_total": int(len(hits)),
        "n_scanned": int(len(anno)),
        "signal_counts": signal_counts,
    }, message="earnings-hunter")
