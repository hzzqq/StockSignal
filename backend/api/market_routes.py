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

import sys
from pathlib import Path

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import ok, fail
from ..utils.params import parse_str_param, parse_limit_param, validate_stock_code

# 确保项目根（StockSignal）在 sys.path，便于 `from modules.fetcher import StockFetcher`
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.fetcher import StockFetcher  # noqa: E402

bp = Blueprint("market", __name__, url_prefix="/api")

# 合法复权参数集合：前复权(qfq)、后复权(hfq)、空字符串("") 或 None(默认透传)
_VALID_ADJUST = ("qfq", "hfq", "")


def _is_valid_adjust(a: "str | None") -> bool:
    """纯函数：校验复权参数。

    合法值：'qfq'、'hfq'、'' 或 None（默认）。其余一律视为非法。
    不依赖 Flask 上下文，可直接被离线单测导入调用。
    """
    return a is None or a in _VALID_ADJUST

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
    ticker = parse_str_param("ticker", max_len=16)
    if not validate_stock_code(ticker)[0]:
        return fail(message="参数无效", code="invalid_param", http_status=400)

    try:
        data = get_fetcher().get_realtime_quote(ticker)
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)

    if data is None:
        return fail(message="行情获取失败", code="quote_failed", http_status=502)
    return ok(data=data, message="success")


@bp.get("/quote/batch")
@jwt_required
def quote_batch():
    """
    GET /api/quote/batch?tickers=600519,000858,601088
    批量实时行情（最多 20 只，逗号分隔）。单只失败不回滚整体——返回
    {"quotes": {code: {quote} 或 {"error": "..."}}, "success_count": N, "failed_count": M}。
    供行情看板自选行情等「N 只并行」场景一次网络往返取数（替代前端逐只
    串行 /api/quote × N），并发取数走共享有界线程池 fetch_many（R90）。
    """
    raw = parse_str_param("tickers", max_len=512)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return fail(message="参数无效", code="invalid_param", http_status=400)
    if len(parts) > 20:
        return fail(message="一次最多查询 20 只", code="invalid_param", http_status=400)
    bad = [p for p in parts if not validate_stock_code(p)[0]]
    if bad:
        return fail(message=f"存在非法代码: {','.join(bad)}", code="invalid_param", http_status=400)

    # 去重保持顺序
    codes = list(dict.fromkeys(parts))

    def _one(code):
        try:
            d = get_fetcher().get_realtime_quote(code)
            return code, d
        except Exception:
            return code, None

    try:
        from modules.fetch_parallel import fetch_many
        res = fetch_many([(c, (lambda code=c: _one(code))) for c in codes])
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)

    quotes = {}
    success_count = 0
    for code in codes:
        item = res.get(code)
        if isinstance(item, tuple) and len(item) == 2:
            _, d = item
        else:
            d = None
        if d is not None:
            quotes[code] = d
            success_count += 1
        else:
            quotes[code] = {"error": "行情获取失败"}
    return ok(data={
        "quotes": quotes,
        "success_count": success_count,
        "failed_count": len(codes) - success_count,
    }, message="success")


@bp.get("/kline")
@jwt_required
def kline():
    """
    GET /api/kline?symbol=600519&start=2024-01-01&end=2026-07-09&period=daily&adjust=qfq&limit=60
    历史 K 线（日/周/月）。symbol 须为 6 位数字；period 默认 daily；其余参数透传。
    limit 可选：仅返回最近 N 根（如 limit=60 → tail(60)），供「最近 N 根」场景减少传输。
    """
    symbol = parse_str_param("symbol", max_len=16)
    if not validate_stock_code(symbol)[0]:
        return fail(message="参数无效", code="invalid_param", http_status=400)

    start = request.args.get("start") or "2024-01-01"
    end = request.args.get("end") or None
    adjust_raw = request.args.get("adjust")
    if not _is_valid_adjust(adjust_raw):
        return fail(message="不支持的复权参数", code="invalid_param", http_status=400)
    adjust = adjust_raw or "qfq"
    period = (request.args.get("period") or "daily").lower()
    if period not in ("daily", "weekly", "monthly"):
        return fail(message="参数无效", code="invalid_param", http_status=400)

    # R91：limit 截断（最近 N 根）。走 parse_limit_param（项目护栏：分页条数
    # 必须经该 helper，钳下界 1、防负数穿透）。default=None → 缺省/非法不截断。
    limit = parse_limit_param("limit", default=None, hi=200)

    try:
        df = get_fetcher().get_kline(symbol, start, end, period, adjust)
    except RuntimeError:
        # 全源 + 缓存均失败：fetcher 抛 RuntimeError（不返回空 DataFrame）
        return fail(message="无行情数据", code="no_kline_data", http_status=404)
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)

    # 兜底：极少数返回 None / 空 DataFrame 的情况，仍归为无行情数据
    if df is None or len(df) == 0:
        return fail(message="无行情数据", code="no_kline_data", http_status=404)
    if limit is not None:
        df = df.tail(limit)
    return ok(data=df.to_dict(orient="records"), message="success")


@bp.get("/intraday")
@jwt_required
def intraday():
    """
    GET /api/intraday?symbol=600519[&date=2026-07-24]
    个股分时数据（新浪分钟 K 线）。symbol 须为 6 位数字；date 可选（默认最近交易日）。
    返回 ok(data={"records": [...], "prev_close": float, "trade_date": str})。
    """
    symbol = parse_str_param("symbol", max_len=16)
    if not validate_stock_code(symbol)[0]:
        return fail(message="参数无效", code="invalid_param", http_status=400)
    trade_date = (request.args.get("date") or None)

    try:
        df, prev_close, target_date = get_fetcher().get_stock_intraday_sina(symbol, trade_date)
    except Exception:
        return fail(message="服务内部错误", code="internal_error", http_status=500)

    if df is None or len(df) == 0:
        return fail(message="无分时数据", code="no_intraday_data", http_status=404)
    return ok(data={
        "records": df.to_dict(orient="records"),
        "prev_close": prev_close,
        "trade_date": target_date,
    }, message="success")
