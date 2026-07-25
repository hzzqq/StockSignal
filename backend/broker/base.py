"""
backend/broker/base.py
----------------------
券商适配器抽象基类 + 统一下单结果结构。

安全设计：
- 所有适配器实现 place_order()，返回 OrderResult；
- 真实券商适配器（QMT / easytrader）为懒加载：仅当账户 live_mode=True
  且 broker_type 指向它们时才 import 对应第三方库；
- 依赖缺失 / 连接失败时抛 BrokerUnavailable，由上层落一条 failed 订单，
  绝不静默吞错。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class BrokerUnavailable(Exception):
    """券商通道不可用（依赖未安装 / 连接失败 / 配置缺失）。"""


@dataclass
class OrderResult:
    ok: bool
    status: str = "filled"            # filled / rejected / submitted / failed
    price: float = 0.0                # 成交/委托价
    filled_qty: int = 0
    broker_order_id: str | None = None
    message: str = ""
    extra: dict = field(default_factory=dict)


class BrokerAdapter(ABC):
    """券商适配器统一接口。code 均为 6 位股票代码字符串。"""

    name = "base"
    is_live = False  # 是否触达真实资金

    @abstractmethod
    def place_order(self, code: str, side: str, quantity: int,
                    price: float | None = None) -> OrderResult:
        """下单。side: buy/sell；price=None 表示市价（按最新价撮合）。"""

    def health_check(self) -> dict:
        """通道健康检查，返回 {"ok": bool, "message": str}。"""
        return {"ok": True, "message": f"{self.name} ready"}
