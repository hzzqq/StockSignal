"""结构化错误上报（纯工具，零业务耦合）。

集中收敛项目里散落的 `logger.warning(f"…{e}")` 写法，提供统一的
「模块名 + 上下文 + 异常信息」结构化记录，便于排查且不泄漏堆栈到前端。

设计原则（不破坏业务）：
- 仅依赖标准库 logging，不 import 任何业务模块；
- 不修改既有控制流，调用方拿到返回值后仍需自行决定 None / 兜底；
- 不上报原始 traceback 到响应体（安全基线）。
"""
import logging


def report_error(module, exc, context=None):
    """记录一次异常并返回安全的单行摘要。

    :param module: 调用方模块名（建议 ``__name__`` 或 ``"fetch_parallel"`` 这类短名）
    :param exc: 捕获到的异常实例
    :param context: 可选上下文（如 ``"single task"`` / ``"kline fetch"``），用于区分同类报错
    :returns: 单行安全摘要字符串（不含堆栈、不含敏感字段）
    """
    msg = f"[{module}] 处理异常"
    if context:
        msg += f" ({context})"
    msg += f": {exc}"
    logging.getLogger(module).warning(msg)
    return msg
