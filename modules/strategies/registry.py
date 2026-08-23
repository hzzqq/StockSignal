"""策略注册表。

全局单例字典 STRATEGY_REGISTRY：{name: strategy_class}。
模块导入即注册，Backtester 与页面只通过这里取策略，不再硬编码。
"""

from typing import Dict, List, Type

from .base import BaseStrategy


# 全局注册表：策略 name -> 策略类
STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def register(strategy_cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
    """装饰器 / 函数式注册一个策略类。

    用法：
        @register
        class MyStrategy(BaseStrategy):
            ...
    或：
        class MyStrategy(BaseStrategy): ...
        register(MyStrategy)
    """
    name = getattr(strategy_cls, "name", None)
    if not name:
        raise ValueError(f"策略类 {strategy_cls.__name__} 必须定义 name 属性")
    if name in STRATEGY_REGISTRY and STRATEGY_REGISTRY[name] is not strategy_cls:
        # 允许同模块重复注册覆盖，但给出告警
        import logging
        logging.getLogger("strategies").warning(
            f"策略名 '{name}' 被 {strategy_cls.__name__} 覆盖（原: {STRATEGY_REGISTRY[name].__name__}）"
        )
    STRATEGY_REGISTRY[name] = strategy_cls
    return strategy_cls


def get_strategy(name: str) -> Type[BaseStrategy]:
    """按 name 取策略类；不存在抛清晰错误。"""
    if name not in STRATEGY_REGISTRY:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise KeyError(f"未注册的策略: '{name}'。可用: {available}")
    return STRATEGY_REGISTRY[name]


def list_strategies() -> List[dict]:
    """返回所有策略的元信息列表（name/display_name/description）。"""
    out = []
    for name, cls in STRATEGY_REGISTRY.items():
        out.append({
            "name": name,
            "display_name": getattr(cls, "display_name", name),
            "description": getattr(cls, "description", ""),
        })
    return out


def list_strategy_names() -> List[str]:
    """返回所有已注册策略 name（供页面 selectbox options）。"""
    return sorted(STRATEGY_REGISTRY.keys())
