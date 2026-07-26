"""
backend/broker/sim.py
---------------------
模拟账本券商（默认）。用 RealAccount / RealPosition 的 DB 记录撮合，
以传入的最新价立即全额成交。与前端 N_模拟交易 完全独立。
"""
from __future__ import annotations

from ..utils.timeutil import utc_now

from .base import BrokerAdapter, OrderResult


class SimulatedBroker(BrokerAdapter):
    name = "sim"
    is_live = False

    def __init__(self, account, db_session, quote_fn=None):
        """
        account: RealAccount ORM 实例
        db_session: SQLAlchemy session（调用方负责 commit）
        quote_fn: callable(code) -> float | None 最新价获取
        """
        self.account = account
        self.session = db_session
        self.quote_fn = quote_fn

    # ------------------------------------------------------------------
    def _latest_price(self, code: str) -> float | None:
        if self.quote_fn is None:
            return None
        try:
            p = self.quote_fn(code)
            return float(p) if p and float(p) > 0 else None
        except Exception:
            return None

    def place_order(self, code: str, side: str, quantity: int,
                    price: float | None = None) -> OrderResult:
        from ..models import RealPosition

        px = price if (price and price > 0) else self._latest_price(code)
        if not px or px <= 0:
            return OrderResult(ok=False, status="failed", message="无法获取最新价，撮合失败")
        quantity = int(quantity)
        if quantity <= 0 or quantity % 100 != 0:
            return OrderResult(ok=False, status="rejected", message="数量须为 100 的整数倍")

        amount = round(px * quantity, 2)
        pos = (self.session.query(RealPosition)
               .filter_by(user_id=self.account.user_id, stock_code=code)
               .first())

        if side == "buy":
            # cash 可能为 None（全新/迁移账户未初始化余额），统一按 0 处理，
            # 避免拒绝分支 f-string 用 None 触发 TypeError 让撮合异常崩溃。
            cash = self.account.cash or 0
            if cash < amount:
                return OrderResult(ok=False, status="rejected",
                                   message=f"可用资金不足（需 {amount:,.2f}，剩 {cash:,.2f}）")
            self.account.cash = round(cash - amount, 2)
            if pos is None:
                pos = RealPosition(user_id=self.account.user_id, stock_code=code,
                                   quantity=0, available=0, avg_cost=0.0)
                self.session.add(pos)
            total_cost = pos.avg_cost * pos.quantity + amount
            pos.quantity += quantity
            # T+1：当日买入不可卖（available 不加，次日由刷新逻辑补齐；简化为直接可用可改配置）
            pos.avg_cost = round(total_cost / pos.quantity, 4) if pos.quantity else 0.0
            pos.last_price = px
            pos.updated_at = utc_now()
        elif side == "sell":
            sellable = pos.quantity if pos else 0  # 模拟账本简化：全部持仓可卖
            if not pos or sellable < quantity:
                return OrderResult(ok=False, status="rejected",
                                   message=f"可卖数量不足（持有 {sellable}，欲卖 {quantity}）")
            pos.quantity -= quantity
            pos.available = max(0, pos.available - quantity)
            pos.last_price = px
            pos.updated_at = utc_now()
            self.account.cash = round(self.account.cash + amount, 2)
            if pos.quantity == 0:
                self.session.delete(pos)
        else:
            return OrderResult(ok=False, status="rejected", message=f"未知方向: {side}")

        return OrderResult(ok=True, status="filled", price=px, filled_qty=quantity,
                           broker_order_id=f"SIM-{utc_now().strftime('%Y%m%d%H%M%S%f')}",
                           message="模拟撮合成交")

    def health_check(self) -> dict:
        return {"ok": True, "message": "模拟账本就绪（不触达真实资金）"}
