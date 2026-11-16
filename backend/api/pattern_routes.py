"""POST /api/v2/pattern-scan —— 形态扫描端点（后端化 v1 高级形态识别算法）。

红线：
  * 不在本文件内直接 import akshare —— K 线取数一律走已有服务层 get_fetcher()（V8 native 崩溃红线）；
  * codes / window_days 严格校验，非法 -> 422 validation_error；
  * 单股取数或扫描失败 -> 该股 available=false + reason，不中断整批、不补零、不伪造形态。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok

bp = Blueprint("pattern", __name__, url_prefix="/api/v2")

_CODE_RE = re.compile(r"^\d{6}$")
_DEFAULT_WINDOW = 250


def _load_klines(code: str, window_days: int) -> list[dict]:
    """用已有服务层取日线，转成 scan_patterns 需要的 dict 列表。

    取数异常 / 空数据一律抛异常，由端点按「单股失败」处理（available=false + reason）。
    """
    from ..api.market_routes import get_fetcher

    start = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    df = get_fetcher().get_kline(code, start, None, "daily", "qfq")
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        raise RuntimeError("K线数据为空")
    cols = [c for c in ("date", "open", "high", "low", "close", "ma5", "ma20") if c in df.columns]
    return df[cols].to_dict("records")


@bp.post("/pattern-scan")
@jwt_required
def pattern_scan():
    """批量形态扫描。

    body: {"codes": str[1..50]（去空后按 6 位数字校验）,
           "window_days"?: int 1..5000（缺省 250）}
    返回: {"results": [{"code", "available", "patterns", "reason", "n_bars"}, ...],
           "n_scanned": int, "available": bool}
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return fail(message="body 必须是 JSON 对象", code="validation_error", http_status=422)

    raw_codes = body.get("codes")
    if not isinstance(raw_codes, list):
        return fail(message="codes 必须是数组", code="validation_error", http_status=422)

    codes = []
    for c in raw_codes:
        if c is None:
            continue
        s = str(c).strip()
        if s:
            codes.append(s)
    if not (1 <= len(codes) <= 50):
        return fail(message="codes 去空后须为 1~50 项", code="validation_error", http_status=422)
    if any(not _CODE_RE.fullmatch(c) for c in codes):
        return fail(message="codes 须为 6 位数字股票代码", code="validation_error", http_status=422)

    window_days = body.get("window_days", _DEFAULT_WINDOW)
    if (isinstance(window_days, bool) or not isinstance(window_days, int)
            or not (1 <= window_days <= 5000)):
        return fail(message="window_days 须为 1~5000 的整数",
                    code="validation_error", http_status=422)

    from modules.pattern_scan import scan_patterns

    results = []
    for code in codes:
        try:
            scan = scan_patterns(_load_klines(code, window_days))
        except Exception as e:  # noqa: BLE001 - 单股失败不中断整批
            scan = {
                "available": False,
                "patterns": [],
                "reason": f"K线获取失败: {type(e).__name__}",
                "n_bars": 0,
            }
        item = {"code": code}
        item.update(scan)
        results.append(item)

    return ok(data={
        "results": results,
        "n_scanned": len(results),
        "available": any(bool(r["available"]) for r in results),
    }, message="pattern-scan")
