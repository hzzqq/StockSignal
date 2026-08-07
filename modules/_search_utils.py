"""搜索辅助纯函数（从 fetcher.py 拆出的叶子模块，R95）。

原 StockFetcher 的拼音/分词辅助方法均为无副作用纯函数，独立成模块便于：
  - 单测（无需构造 StockFetcher 实例 / 不触网）
  - 复用（search_ui / 自选股监控等可直接调用）
  - 减轻 fetcher.py god module 体积

StockFetcher._pinyin_initials 仍保留在 fetcher（依赖类级预热缓存），其余纯函数
下沉到此模块，fetcher 内对应方法改为委托，保持对外接口零变化。
"""
import logging

logger = logging.getLogger(__name__)


def pinyin_initials_static(name: str) -> str:
    """获取拼音首字母（纯函数，无副作用，用于缓存）。如 '招商银行' -> 'ZSYH'。"""
    try:
        import pypinyin
        return "".join([w[0][0] for w in pypinyin.pinyin(name, style=pypinyin.NORMAL)]).upper()
    except Exception as e:
        logger.warning(f"[search_utils] 处理异常: {e}")
        return ""


def pinyin_initials_variants(name: str) -> set:
    """获取股票名称的所有拼音首字母组合（处理多音字）。
    如 '长电科技' -> {'ZDKJ', 'CDKJ'}。
    """
    try:
        import pypinyin
        from itertools import product

        py_lists = pypinyin.pinyin(name, style=pypinyin.NORMAL, heteronym=True)
        variants = set()
        for combo in product(*py_lists):
            variants.add("".join([w[0].upper() for w in combo]))
        return variants
    except Exception as e:
        logger.warning(f"[search_utils] 处理异常: {e}")
        return set()


def pinyin_full(name: str) -> str:
    """获取股票名称的完整拼音（小写无空格）。如 '贵州茅台' -> 'guizhoumaotai'。"""
    try:
        import pypinyin
        return "".join([w[0] for w in pypinyin.pinyin(name, style=pypinyin.NORMAL)]).lower()
    except Exception as e:
        logger.warning(f"[search_utils] 处理异常: {e}")
        return name.lower()


def name_tokens(name: str) -> set:
    """将股票名称拆分为搜索用的中文分词 token。
    覆盖常见的简称模式：首字+尾字、中间词、2-gram、3-gram、单字、跳字简写。
    如 '招商银行' -> {'招商', '银行', '招', '商', '银', '行', '商银', '招商银', '商银行', '招行'}
    """
    tokens = set()
    tokens.add(name)  # 全称
    n = len(name)
    # 2-gram（如 "招商" "商银" "银行"）
    for i in range(n - 1):
        tokens.add(name[i:i + 2])
    # 3-gram（如 "招商银" "商银行"）
    for i in range(n - 2):
        tokens.add(name[i:i + 3])
    # 单字
    for ch in name:
        tokens.add(ch)
    # 首尾组合（简称常见形式：首字+尾字，如 "招行"）
    if n >= 2:
        tokens.add(name[0] + name[-1])
    if n >= 3:
        tokens.add(name[0] + name[2])  # 跳字简写
    return tokens
