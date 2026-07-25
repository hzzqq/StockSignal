"""
backend/broker/live.py
----------------------
真实券商适配器（QMT / easytrader）。懒加载第三方依赖：
- QMTBroker: 依赖 xtquant（迅投 QMT mini 投研端），broker_config 需 {"qmt_path": "...", "account_id": "..."}
- EasytraderBroker: 依赖 easytrader，broker_config 需 {"use": "ths|htzq|...", "exe_path"/"user"/"password" 等}

⚠️ 这些适配器 place_order 会触达真实资金。上层（executor）已保证：
   仅当 RealAccount.live_mode=True 且 broker_type 匹配时才会构造它们。
依赖未安装时抛 BrokerUnavailable，由上层落 failed 订单并提示用户。
"""
from __future__ import annotations

from .base import BrokerAdapter, BrokerUnavailable, OrderResult


class QMTBroker(BrokerAdapter):
    """迅投 QMT（xtquant）通道。"""
    name = "qmt"
    is_live = True

    def __init__(self, config: dict):
        self.config = config or {}
        try:
            from xtquant import xttrader  # noqa: F401
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
        except ImportError as e:
            raise BrokerUnavailable(
                "未安装 xtquant（QMT）依赖，无法真实下单。请在服务器安装 QMT mini 投研端并 pip 安装 xtquant。"
            ) from e
        path = self.config.get("qmt_path") or ""
        acc = self.config.get("account_id") or ""
        if not path or not acc:
            raise BrokerUnavailable("QMT 配置缺失：需要 qmt_path 与 account_id。")
        import random
        self._trader = XtQuantTrader(path, random.randint(100000, 999999))
        self._trader.start()
        if self._trader.connect() != 0:
            raise BrokerUnavailable("QMT 连接失败：请确认 mini 投研端已启动并登录。")
        self._account = StockAccount(acc)
        if self._trader.subscribe(self._account) != 0:
            raise BrokerUnavailable("QMT 账户订阅失败：请检查 account_id。")

    @staticmethod
    def _xt_code(code: str) -> str:
        code = str(code).zfill(6)
        if code.startswith(("6", "9", "5")):
            return f"{code}.SH"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return f"{code}.SZ"

    def place_order(self, code, side, quantity, price=None) -> OrderResult:
        from xtquant import xtconstant
        order_type = xtconstant.STOCK_BUY if side == "buy" else xtconstant.STOCK_SELL
        price_type = xtconstant.FIX_PRICE if (price and price > 0) else xtconstant.LATEST_PRICE
        oid = self._trader.order_stock(
            self._account, self._xt_code(code), order_type, int(quantity),
            price_type, float(price or 0), "StockSignal", "conditional")
        if oid < 0:
            return OrderResult(ok=False, status="failed", message=f"QMT 下单失败（返回 {oid}）")
        return OrderResult(ok=True, status="submitted", price=float(price or 0),
                           filled_qty=0, broker_order_id=str(oid),
                           message="已提交 QMT 委托（成交以券商回报为准）")

    def health_check(self) -> dict:
        return {"ok": True, "message": "QMT 通道已连接（真实资金，谨慎操作）"}


class EasytraderBroker(BrokerAdapter):
    """easytrader 通道（同花顺/券商客户端自动化）。"""
    name = "easytrader"
    is_live = True

    def __init__(self, config: dict):
        self.config = config or {}
        try:
            import easytrader
        except ImportError as e:
            raise BrokerUnavailable(
                "未安装 easytrader 依赖，无法真实下单。请先 pip install easytrader 并配置客户端。"
            ) from e
        use = self.config.get("use") or "universal_client"
        try:
            self._user = easytrader.use(use)
            exe = self.config.get("exe_path")
            if exe:
                self._user.connect(exe)
            elif self.config.get("prepare_file"):
                self._user.prepare(self.config["prepare_file"])
            else:
                raise BrokerUnavailable("easytrader 配置缺失：需要 exe_path 或 prepare_file。")
        except BrokerUnavailable:
            raise
        except Exception as e:
            raise BrokerUnavailable(f"easytrader 连接失败：{e}") from e

    def place_order(self, code, side, quantity, price=None) -> OrderResult:
        try:
            if side == "buy":
                if price and price > 0:
                    r = self._user.buy(code, price=float(price), amount=int(quantity))
                else:
                    r = self._user.market_buy(code, amount=int(quantity))
            else:
                if price and price > 0:
                    r = self._user.sell(code, price=float(price), amount=int(quantity))
                else:
                    r = self._user.market_sell(code, amount=int(quantity))
            oid = ""
            if isinstance(r, dict):
                oid = str(r.get("entrust_no") or r.get("order_id") or "")
            elif isinstance(r, list) and r and isinstance(r[0], dict):
                oid = str(r[0].get("entrust_no") or r[0].get("order_id") or "")
            return OrderResult(ok=True, status="submitted", price=float(price or 0),
                               filled_qty=0, broker_order_id=oid or None,
                               message="已提交 easytrader 委托（成交以券商回报为准）")
        except Exception as e:
            return OrderResult(ok=False, status="failed", message=f"easytrader 下单异常：{e}")

    def health_check(self) -> dict:
        try:
            self._user.balance
            return {"ok": True, "message": "easytrader 通道已连接（真实资金，谨慎操作）"}
        except Exception as e:
            return {"ok": False, "message": f"easytrader 通道异常：{e}"}
