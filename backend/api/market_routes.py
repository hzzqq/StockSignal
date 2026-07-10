"""
backend/api/market_routes.py
----------------------------
行情接入接口：/api/quote、/api/kline。

消费数据层 modules.fetcher.StockFetcher（契约见 modules/FETCHER_CONTRACT.md）：
- get_realtime_quote(ticker) -> dict | None
- get_daily(symbol, start, end, adjust) -> pd.DataFrame（全源失败抛 RuntimeError，见 FETCHER_CONTRACT.md §1.1）

硬约束（与 FETCHER_CONTRACT.md §3 一致）：
- 统一走 utils.response.ok/fail，禁止直接 return dict/str。
- 错误文案统一中文："行情获取失败"(quote 为 None) / "无行情数据"(kline 全源失败)
  / "参数无效"(ticker/symbol 非 6 位) / "服务内部错误"(异常)。
- 保留 JWT 鉴权（与现有受保护接口一致）。
- 复用进程内 StockFetcher 单例，避免每次请求重复建连。
- 入参校验：ticker/symbol 必须是 6 位数字，否则 response.fail("参数无效")。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import ok, fail

# 确保项目根（StockSignal）在 sys.path，便于 `from modules.fetcher import StockFetcher`
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.fetcher import StockFetcher  # noqa: E402

bp = Blueprint("market", __name__, url_prefix="/api")

_TICKER_RE = re.compile(r"^\d{6}$")

# 进程内单例：首次请求时惰性创建（建连/预热只做一次）
_fetcher = None


def get_fetcher() -> "StockFetcher":
    """返回进程内 StockFetcher 单例。"""
    global _fetcher
    if _fetcher is None:
        _fetcher = StockFetcher()
    return _fetcher


@bp.get("/quote")
@jwt_required
def quote():
    """
    GET /api/quote?ticker=600519
    实时五档行情。ticker 须为 6 位数字。
    """
    ticker = (request.args.get("ticker") or "").strip()
    if not _TICKER_RE.match(ticker):
        return fail(message="参数无效", code="invalid_param", http_status=400)

    try:
        data = get_fetcher().get_realtime_quote(ticker)
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)

    if data is None:
        return fail(message="行情获取失败", code="quote_failed", http_status=502)
    return ok(data=data, message="success")


@bp.get("/kline")
@jwt_required
def kline():
    """
    GET /api/kline?symbol=600519&start=2024-01-01&end=2026-07-09&adjust=qfq
    历史日线（DataFrame）。symbol 须为 6 位数字；start/end/adjust 透传。
    """
    symbol = (request.args.get("symbol") or "").strip()
    if not _TICKER_RE.match(symbol):
        return fail(message="参数无效", code="invalid_param", http_status=400)

    start = request.args.get("start") or "2024-01-01"
    end = request.args.get("end") or None
    adjust = request.args.get("adjust") or "qfq"

    try:
        df = get_fetcher().get_daily(symbol, start, end, adjust)
    except RuntimeError:
        # 全源 + 缓存均失败：fetcher 抛 RuntimeError（不返回空 DataFrame）
        return fail(message="无行情数据", code="no_kline_data", http_status=404)
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)

    # 兜底：极少数返回 None / 空 DataFrame 的情况，仍归为无行情数据
    if df is None or len(df) == 0:
        return fail(message="无行情数据", code="no_kline_data", http_status=404)
    return ok(data=df.to_dict(orient="records"), message="success")
