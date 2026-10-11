"""fetcher_core — fetcher.py 的纯函数拆分包（Tier1.1，安全法）。

首轮 pilot：迁入 ``_safe_json_loads``（缓存读取容错，无 StockFetcher 依赖）。
原 ``fetcher.py`` 通过 ``from modules.fetcher_core import _safe_json_loads`` re-export，
行为零变化；后续批次按同范式逐个迁入纯函数（URL 构建 / 缓存键归一化 / 日期工具等）。

设计红线（Tier1.1）：
- 本包**绝不 import ``modules.fetcher``**，避免循环依赖；
- 迁入函数必须保持签名与返回语义一致，且仅依赖标准库 + 本包内定义；
- ``fetcher.py`` 一律 re-export，不得再本地定义（由 AST 守卫锁死）。
"""
import json
import logging

logger = logging.getLogger(__name__)


def _safe_json_loads(s, default=None):
    """安全解析 JSON：损坏/空/非字符串一律返回 default，绝不抛异常。

    用于缓存读取路径的容错——缓存数据可能因磁盘写半截、版本变更而损坏，
    直接 json.loads 会抛 JSONDecodeError 炸到调用方；此处降级为 default，
    让上层走缓存未命中/空结果分支，而不是崩溃。
    """
    if not s or not isinstance(s, str):
        return default
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning(f"[fetcher] 缓存 JSON 解析失败，降级返回默认: {type(s).__name__}")
        return default
