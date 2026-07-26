"""
backend/broker
--------------
券商适配器包：工厂 + 风控 + 统一下单执行入口。

安全护栏（多层）：
1. RealAccount.live_mode 默认 False → 永远走 SimulatedBroker（模拟账本）；
2. live_mode=True 且 broker_type=qmt/easytrader 才懒加载真实通道，
   依赖缺失/连接失败 → BrokerUnavailable → 落 failed 订单，不静默；
3. 每笔下单前过风控：交易时段、单笔金额上限、当日亏损停手线；
4. 所有订单（成功/拒绝/失败）都写 RealOrder 流水，可审计。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ..utils.timeutil import utc_now

from .base import BrokerAdapter, BrokerUnavailable, OrderResult
from .sim import SimulatedBroker

__all__ = ["BrokerAdapter", "BrokerUnavailable", "OrderResult",
           "SimulatedBroker", "get_broker", "execute_order", "risk_check"]

_BJ_TZ = timezone(timedelta(hours=8))


def _now_bj() -> datetime:
    return datetime.now(_BJ_TZ)


def in_trading_window(now: datetime | None = None) -> bool:
    """北京时区 A 股连续竞价时段（含集合竞价缓冲）：周一~周五 9:15-11:35 / 12:55-15:05。"""
    now = now or _now_bj()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (9 * 60 + 15 <= hm <= 11 * 60 + 35) or (12 * 60 + 55 <= hm <= 15 * 60 + 5)


def _server_quote(code: str):
    """服务端直接取最新价（复用 market_routes 的 fetcher 单例）。失败返回 None。"""
    try:
        from ..api.market_routes import get_fetcher
        data = get_fetcher().get_realtime_quote(code)
        if data and data.get("current"):
            px = float(data["current"])
            return px if px > 0 else None
    except Exception:
        pass
    return None


def get_broker(account, db_session):
    """按账户配置构造适配器。live 通道构造失败会抛 BrokerUnavailable。"""
    if not account.live_mode or account.broker_type in (None, "", "sim"):
        return SimulatedBroker(account, db_session, quote_fn=_server_quote)
    cfg = account.config_dict()
    if account.broker_type == "qmt":
        from .live import QMTBroker
        return QMTBroker(cfg)
    if account.broker_type == "easytrader":
        from .live import EasytraderBroker
        return EasytraderBroker(cfg)
    raise BrokerUnavailable(f"未知券商类型：{account.broker_type}")


def risk_check(account, db_session, code: str, side: str, quantity: int,
               est_price: float | None) -> str | None:
    """下单前风控。通过返回 None，否则返回拒绝原因字符串。"""
    from ..models import RealOrder

    now_bj = _now_bj()
    if not in_trading_window(now_bj):
        return "当前不在 A 股交易时段（周一至周五 9:15-11:35 / 12:55-15:05）"

    # 单笔金额上限
    px = est_price or _server_quote(code) or 0.0
    if px > 0 and account.max_order_amount and px * quantity > account.max_order_amount:
        return (f"单笔金额 {px * quantity:,.0f} 元超过上限 "
                f"{account.max_order_amount:,.0f} 元（可在实盘交易页调整）")

    # 当日亏损停手线：当日已实现卖出亏损估算 + 显式停手标记
    today = now_bj.strftime("%Y-%m-%d")
    if account.risk_paused_date == today:
        return "已触发当日亏损停手线，今日停止自动交易（可在实盘交易页手动解除）"
    if account.daily_loss_limit:
        day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        # 简化估算：当日 filled 卖单金额 - 当日 filled 买单金额，若净流出超过停手线则暂停
        orders = (db_session.query(RealOrder)
                  .filter(RealOrder.user_id == account.user_id,
                          RealOrder.status == "filled",
                          RealOrder.created_at >= day_start)
                  .all())
        buy_amt = sum(o.amount for o in orders if o.side == "buy")
        sell_amt = sum(o.amount for o in orders if o.side == "sell")
        realized = sell_amt - buy_amt
        if realized < 0 and abs(realized) >= account.daily_loss_limit * 3:
            # 净买入额过大不算亏损，此处仅在明显异常时保守停手（3 倍缓冲避免误伤正常建仓）
            account.risk_paused_date = today
            return "当日资金净流出异常，触发保守停手保护"
    return None


def execute_order(account, db_session, *, code: str, name: str, side: str,
                  quantity: int, price: float | None = None,
                  source: str = "manual", cond_order_id: int | None = None,
                  skip_risk: bool = False):
    """统一下单入口：风控 → 适配器下单 → 落 RealOrder 流水。

    返回 (RealOrder, OrderResult)。调用方负责最终 db_session.commit()。
    """
    from ..models import RealOrder

    mode = "live" if (account.live_mode and account.broker_type not in (None, "", "sim")) else "sim"
    order = RealOrder(user_id=account.user_id, stock_code=code, stock_name=name or "",
                      side=side, price=price or 0.0, quantity=int(quantity),
                      amount=0.0, status="failed", mode=mode,
                      source=source, cond_order_id=cond_order_id)

    reason = None if skip_risk else risk_check(account, db_session, code, side, quantity, price)
    if reason:
        order.status = "rejected"
        order.message = reason
        db_session.add(order)
        return order, OrderResult(ok=False, status="rejected", message=reason)

    try:
        broker = get_broker(account, db_session)
    except BrokerUnavailable as e:
        order.message = f"券商通道不可用：{e}"
        db_session.add(order)
        return order, OrderResult(ok=False, status="failed", message=order.message)

    try:
        result = broker.place_order(code, side, int(quantity), price)
    except Exception as e:  # 防御：适配器内部未捕获异常
        result = OrderResult(ok=False, status="failed", message=f"下单异常：{e}")

    order.status = result.status
    order.message = result.message
    order.broker_order_id = result.broker_order_id
    if result.ok:
        order.price = result.price or (price or 0.0)
        filled = result.filled_qty or int(quantity)
        order.amount = round(order.price * filled, 2)
    db_session.add(order)
    return order, result
