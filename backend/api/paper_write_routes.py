# -*- coding: utf-8 -*-
"""模拟账本写端点（供 V2 /paper 从只读壳升级）。

写向 GET /api/v2/read/paper-trades 读取的**同一文件**：路径不是本模块另起一套，
而是在请求时动态引用 read_routes._DATA_DIR / read_routes._safe_file，
因此 monkeypatch 读取侧的数据根即可同时覆盖读写两侧，天然同源。

对齐 v1 pages/42_模拟交易.py 的真实写语义：
  - 账本文件 data/paper_<user>.json，按用户隔离（用户取自 JWT 的 current_user）；
  - 成交记录 trades 元素形如
    {time, code, name, side, price, qty, amount}，side 取值为中文「买」「卖」；
  - 买入：扣现金、按加权均价更新/新建持仓、追加成交；
  - 卖出：加回现金、减持仓（清零则移除该标的）、追加成交；
  - 重置：恢复初始账本。

诚实边界（不伪造数据）：
  - 价格 / 名称由调用方随请求提供，本模块不联网取行情；
  - 净资产快照（equity）仍由 v1 页面基于实时行情生成，本模块不写假的净值点；
  - 按 id 删除只从成交记录中移除该条，不回滚现金与持仓——历史买入的均价依赖
    当时上下文，无法由单条记录反推，强行回滚会造出错误数据；需要整体复原请用重置端点。

红线：本模块只操作本地 JSON 账本，不涉及任何外部交易能力。
"""
from __future__ import annotations

import json
import math
from datetime import datetime

from flask import Blueprint, g

from . import read_routes
from ..auth.decorators import jwt_required
from ..utils.errors import NotFoundError, ValidationError
from ..utils.params import json_body, validate_stock_code
from ..utils.response import ok
from modules.atomic_io import atomic_json_dump

bp = Blueprint("paper_write", __name__, url_prefix="/api/v2")

INIT_CASH = 1000000.0
_SIDES = ("买", "卖")


def _current_user() -> str:
    """用户隔离：账本归属当前 JWT 用户，忽略调用方自报的用户名。"""
    user = getattr(g, "current_user", None)
    username = getattr(user, "username", "") if user is not None else ""
    if not read_routes._USER_RE.fullmatch(username):
        raise ValidationError("当前用户标识非法")
    return username


def _book_path(user: str):
    """复用读取侧的路径拼接与防穿越校验，确保读写指向同一文件。"""
    path = read_routes._safe_file(read_routes._DATA_DIR, f"paper_{user}.json")
    if path is None:
        raise ValidationError("非法路径")
    return path


def _new_book() -> dict:
    return {
        "init_cash": INIT_CASH,
        "cash": INIT_CASH,
        "positions": {},
        "trades": [],
        "equity": [],
    }


def _load_book(path):
    """读账本；文件缺失返回 None，由调用方决定建新账本还是诚实报不存在。"""
    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            book = json.load(f)
    except (json.JSONDecodeError, OSError):
        raise ValidationError("账本文件解析失败")  # noqa: B904
    if not isinstance(book, dict):
        raise ValidationError("账本文件格式非法")
    return book


def _ensure_shape(book: dict) -> dict:
    """对旧账本补默认字段，缺字段按 v1 初值处理，不覆盖已有数据。"""
    book.setdefault("init_cash", INIT_CASH)
    book.setdefault("cash", book["init_cash"])
    book.setdefault("positions", {})
    book.setdefault("trades", [])
    book.setdefault("equity", [])
    if not isinstance(book["positions"], dict):
        raise ValidationError("账本持仓字段格式非法")
    if not isinstance(book["trades"], list):
        raise ValidationError("账本成交字段格式非法")
    if not isinstance(book["equity"], list):
        raise ValidationError("账本净值字段格式非法")
    return book


def _next_trade_id(trades: list) -> int:
    max_id = 0
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        value = trade.get("id")
        if isinstance(value, int) and not isinstance(value, bool) and value > max_id:
            max_id = value
    return max_id + 1


def _paid_price(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("price 必须是正数")
    price = float(value)
    if not math.isfinite(price) or price <= 0:
        raise ValidationError("price 必须是有限正数")
    return price


def _share_count(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("qty 必须是 100 的整数倍且不小于 100")
    if value < 100 or value % 100 != 0:
        raise ValidationError("qty 必须是 100 的整数倍且不小于 100")
    return value


@bp.post("/paper-trades")
@jwt_required
def add_paper_trade():
    """新增一笔模拟成交并更新现金/持仓，写回当前用户的账本。

    body: {code, side: "买"|"卖", price: number, qty: int, name?: str}
    返回 data = 落盘的成交记录（含服务端生成的 id）。
    """
    user = _current_user()
    body = json_body()

    code_ok, code = validate_stock_code(body.get("code"))
    if not code_ok:
        raise ValidationError("code 必须是 6 位股票代码")

    side = body.get("side")
    if side not in _SIDES:
        raise ValidationError("side 只能是 买 或 卖")

    price = _paid_price(body.get("price"))
    qty = _share_count(body.get("qty"))
    raw_name = body.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    name = name or code

    path = _book_path(user)
    book = _ensure_shape(_load_book(path) or _new_book())
    positions = book["positions"]
    amount = round(price * qty, 2)

    if side == "买":
        if amount > book["cash"]:
            raise ValidationError("现金不足，无法完成模拟买入")
        book["cash"] = round(book["cash"] - amount, 2)
        pos = positions.get(code)
        if isinstance(pos, dict) and isinstance(pos.get("qty"), (int, float)) \
                and isinstance(pos.get("avg_cost"), (int, float)):
            total_qty = pos["qty"] + qty
            pos["avg_cost"] = (pos["avg_cost"] * pos["qty"] + amount) / total_qty
            pos["qty"] = total_qty
            if not pos.get("name"):
                pos["name"] = name
        else:
            positions[code] = {"name": name, "qty": qty, "avg_cost": price}
    else:
        pos = positions.get(code)
        if not isinstance(pos, dict) or not isinstance(pos.get("qty"), (int, float)) \
                or qty > pos["qty"]:
            raise ValidationError("持仓不足或尚未持有该标的")
        book["cash"] = round(book["cash"] + amount, 2)
        pos["qty"] = pos["qty"] - qty
        if pos["qty"] <= 0:
            del positions[code]

    trade = {
        "id": _next_trade_id(book["trades"]),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "code": code,
        "name": name,
        "side": side,
        "price": round(price, 2),
        "qty": qty,
        "amount": amount,
    }
    book["trades"].append(trade)
    atomic_json_dump(book, str(path))
    return ok(data=trade, message="模拟成交已记录")


@bp.delete("/paper-trades/<int:trade_id>")
@jwt_required
def delete_paper_trade(trade_id: int):
    """按 id 删除当前用户账本中的一条模拟成交记录。

    这是纯记录删除：不回滚现金与持仓（见模块 docstring 的诚实边界）。
    账本或该 id 不存在时返回 404 not_found，不静默成功。
    """
    user = _current_user()
    path = _book_path(user)
    book = _load_book(path)
    if book is None:
        raise NotFoundError("模拟账本不存在，无可删除的成交")
    trades = book.get("trades")
    if not isinstance(trades, list):
        raise NotFoundError("账本无有效成交记录")
    target = next(
        (t for t in trades if isinstance(t, dict) and t.get("id") == trade_id),
        None,
    )
    if target is None:
        raise NotFoundError(f"成交记录 {trade_id} 不存在")
    trades.remove(target)
    atomic_json_dump(book, str(path))
    return ok(
        data={"deleted_id": trade_id, "remaining": len(trades)},
        message="模拟成交记录已删除",
    )


@bp.post("/paper-trades/reset")
@jwt_required
def reset_paper_book():
    """重置当前用户的模拟账本（对齐 v1 的清空/恢复初始资金操作）。"""
    user = _current_user()
    path = _book_path(user)
    book = _new_book()
    atomic_json_dump(book, str(path))
    return ok(data=book, message="模拟账户已重置")
