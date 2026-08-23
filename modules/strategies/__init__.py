"""可插拔策略包。

让回测策略从 Backtester 的硬编码 if/elif 中解耦：
- 每个策略是一个 BaseStrategy 子类，实现 generate_signals(df) -> list[int]
- 模块导入时自动注册到 STRATEGY_REGISTRY
- 用户可把自己的策略 .py 丢进本目录（实现 BaseStrategy 并调用 register），
  无需改动 Backtester 或页面代码即可被回测引擎选用

设计约束（保证可移植性）：
- 策略类必须只依赖 DataFrame 的标准列（见 BaseStrategy.DF_COLUMNS），
  不引用 Backtester 实例方法，以便独立 pickle / 跨进程传输。
- generate_signals 返回与 df 等长的信号列表：1=买入, -1=卖出, 0=持有。
"""

from .base import BaseStrategy
from .registry import (
    STRATEGY_REGISTRY,
    register,
    get_strategy,
    list_strategies,
    list_strategy_names,
)

# 导入内置策略，触发注册
from .multi_factor import MultiFactorStrategy
from .dual_trend import DualTrendStrategy
from .ma_cross import MaCrossStrategy
from .event_driven import EventDrivenStrategy

__all__ = [
    "BaseStrategy",
    "STRATEGY_REGISTRY",
    "register",
    "get_strategy",
    "list_strategies",
    "list_strategy_names",
    "MultiFactorStrategy",
    "DualTrendStrategy",
    "MaCrossStrategy",
    "EventDrivenStrategy",
]
