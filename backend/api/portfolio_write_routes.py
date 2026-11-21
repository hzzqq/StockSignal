# -*- coding: utf-8 -*-
"""backend/api/portfolio_write_routes.py — 40/41/45 组合写操作（v1 PortfolioManager 同源）。

写向 GET /api/v2/read/portfolio 读取的**同一份本地模拟账本**（data/portfolio.csv
与 data/portfolio_trades.csv），复用 modules.portfolio.PortfolioManager 的
add_position / remove_position / sell_position，不另起一套口径、不复制写盘逻辑。

对齐 v1 modules/portfolio_views.py 的真实写语义：
  - 添加持仓：ticker / buy_date / buy_price / shares / note，名称和备注由调用方传入；
  - 删除持仓：按当前持仓表行号（与 /portfolio 返回顺序一致）删除，仅删记录不回滚卖出历史；
  - 记录卖出：按 ticker 校验可卖股数，写 portfolio_trades.csv，绝不改买入批次。

诚实边界：
  - 这是本地模拟/历史账本，全站共享，非实盘、非用户隔离；v2 页面如实标注；
  - 服务端不联网取行情/名称，名称和价格全部来自请求，缺名回退代码；
  - 失败（参数非法 / 可卖股数不足 / 行号越界）→ 422，不返回半写状态。

红线：本模块只写本地模拟 CSV，不触碰任何券商/真实交易端点。
"""
from __future__ import annotations

from datetime import datetime
import math

from flask import Blueprint

from ..auth.decorators import jwt_required
from ..utils.errors import NotFoundError, ValidationError
from ..utils.params import json_body
from ..utils.response import ok

bp = Blueprint("portfolio_write", __name__, url_prefix="/api/v2")

_NOTE = "本地模拟/历史账本（data/portfolio*.csv），全站共享，非实盘，不构成投资建议"


def _manager():
    from modules.portfolio import PortfolioManager
    return PortfolioManager()


def _ticker(raw) -> str:
    code = str(raw or "").strip()
    if len(code) != 6 or not code.isdigit():
        raise ValidationError("ticker 须为 6 位股票代码")
    return code


def _positive(raw, field: str, *, integer: bool = False):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 须为有效正数")  # noqa: B904
    if not math.isfinite(value) or value <= 0:
        raise ValidationError(f"{field} 须为有效正数")
    return int(value) if integer else value


def _date(raw, field: str) -> str:
    value = str(raw or "").strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"{field} 须为 YYYY-MM-DD 格式的真实日期")  # noqa: B904


def _text(raw, field: str, limit: int = 200) -> str:
    value = raw.strip() if isinstance(raw, str) else ""
    if len(value) > limit:
        raise ValidationError(f"{field} 不能超过 {limit} 个字符")
    return value


def _apply(fn, *args, **kwargs):
    """PortfolioManager 的业务 ValueError（可卖股数不足等）统一转 422。"""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise ValidationError(str(e)) from e


@bp.post("/portfolio/positions")
@jwt_required
def add_position():
    """POST /api/v2/portfolio/positions —— 添加一条模拟持仓（写 portfolio.csv）。"""
    body = json_body()
    ticker = _ticker(body.get("ticker"))
    buy_date = _date(body.get("buy_date"), "buy_date")
    price = _positive(body.get("buy_price"), "buy_price")
    shares = _positive(body.get("shares"), "shares", integer=True)
    name = _text(body.get("name"), "name", 60) or ticker
    note = _text(body.get("note"), "note")

    row = _apply(_manager().add_position,
                 ticker=ticker, name=name, buy_date=buy_date,
                 buy_price=price, shares=shares, note=note)
    return ok(data={"position": row, "note": _NOTE}, message="portfolio-position-added")


@bp.delete("/portfolio/positions/<int:index>")
@jwt_required
def delete_position(index: int):
    """DELETE /api/v2/portfolio/positions/<index> —— 按行号删除模拟持仓。"""
    if index < 0:
        raise ValidationError("index 须为非负整数")
    removed = _manager().remove_position(index)
    if removed is None:
        raise NotFoundError(f"持仓行号 {index} 不存在")
    return ok(data={"removed": removed, "note": _NOTE}, message="portfolio-position-deleted")


@bp.post("/portfolio/sell")
@jwt_required
def sell_position():
    """POST /api/v2/portfolio/sell —— 记录一笔模拟卖出（写 portfolio_trades.csv）。"""
    body = json_body()
    ticker = _ticker(body.get("ticker"))
    sell_date = _date(body.get("sell_date"), "sell_date")
    price = _positive(body.get("sell_price"), "sell_price")
    shares = _positive(body.get("sell_shares"), "sell_shares", integer=True)
    name = _text(body.get("name"), "name", 60) or ticker
    note = _text(body.get("note"), "note")

    row = _apply(_manager().sell_position,
                 ticker=ticker, sell_date=sell_date, sell_price=price,
                 sell_shares=shares, note=note, name=name)
    return ok(data={"trade": row, "note": _NOTE}, message="portfolio-sell-recorded")
