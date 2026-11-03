# -*- coding: utf-8 -*-
"""tests/test_fetcher_cache_key_identity.py

T-247 Tier3 · T-250 批注遗留项：缓存键单一真源守卫。

锁四条不变量：
1. _build_cache_key 逐字节等价于既存 9 种 cache_key f-string（行为零变化）；
2. fetcher_* + _market_data_io + stock_research.py 内禁止新写 cache_key = f"..."；
3. 调用方 import 的是 fetcher_core 真身（AST 防本地 def 回潮）；
4. _build_cache_key 对未知 key_type / 缺必需 params 诚实 ValueError。
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COREFUNC = ROOT / "modules" / "fetcher_core" / "__init__.py"
FETCHER = ROOT / "modules" / "fetcher.py"


# ───────────────────── 1. 行为等价：9 种类型逐字节匹配 ─────────────────────

def test_build_cache_key_daily_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("daily", symbol="600519", start="2024-01-01", end="2024-12-31", adjust="qfq") \
        == "daily_600519_2024-01-01_2024-12-31_qfq"


def test_build_cache_key_daily_prefix_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("daily_prefix", symbol="000001") == "daily_000001"


def test_build_cache_key_kline_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("kline", period="weekly", symbol="000858",
                             start="2023-01-01", end="2023-12-31", adjust="none") \
        == "kline_weekly_000858_2023-01-01_2023-12-31_none"


def test_build_cache_key_rt_quote_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("rt_quote", ticker="600519") == "rt_quote_600519"


def test_build_cache_key_index_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("index", symbol="000300", start="2024-01-01", end="2024-12-31") \
        == "index_000300_2024-01-01_2024-12-31"


def test_build_cache_key_macro_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("macro", indicator="pmi_mfg") == "macro_pmi_mfg"


def test_build_cache_key_commodity_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("commodity", name="煤炭") == "commodity_煤炭"


def test_build_cache_key_name_only_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("name_only", code="600519") == "_name_only_cache_600519"


def test_build_cache_key_static_identity():
    from modules.fetcher_core import _build_cache_key
    assert _build_cache_key("static", value="sector_list_v3") == "sector_list_v3"


# ───────────────────── 2. 诚实降级 ─────────────────────

def test_build_cache_key_unknown_type_raises():
    from modules.fetcher_core import _build_cache_key
    try:
        _build_cache_key("oops", symbol="x")
    except ValueError as e:
        assert "oops" in str(e)
    else:
        raise AssertionError("未知 key_type 应 raise ValueError，实际吞了")


def test_build_cache_key_missing_param_raises():
    from modules.fetcher_core import _build_cache_key
    try:
        _build_cache_key("daily", symbol="600519", start="2024-01-01")
    except ValueError as e:
        assert "adjust" in str(e)
    else:
        raise AssertionError("缺必需 params 应 raise ValueError，实际吞了")


# ───────────────────── 3. AST：禁止 cache_key = f"..." 回潮 ─────────────────────

_GUARDED_FILES = [
    "fetcher_kline.py", "fetcher_realtime.py", "fetcher_search.py",
    "_market_data_io.py", "stock_research.py",
]
_RESIDUAL_RE = re.compile(r'cache_key\s*=\s*f"')


def test_no_residual_cache_key_fstring():
    """fetcher 相关模块不得再出现 cache_key = f"..." 硬编码（已全部迁 _build_cache_key）。"""
    offenders = []
    for fname in _GUARDED_FILES:
        p = ROOT / "modules" / fname
        src = p.read_text(encoding="utf-8")
        hits = list(_RESIDUAL_RE.finditer(src))
        for h in hits:
            lineno = src[:h.start()].count("\n") + 1
            offenders.append(f"{fname}:{lineno}: cache_key = f\"... 残留")
    assert not offenders, \
        "fetcher 相关模块残留 cache_key = f\" 硬编码（应改用 _build_cache_key）：\n  " + "\n  ".join(offenders)


# ───────────────────── 4. AST：_build_cache_key 真身锁在 fetcher_core ─────────────────────

def test_build_cache_key_no_local_def_in_fetcher_modules():
    """fetcher_* + _market_data_io + stock_research.py 不得本地 def _build_cache_key。"""
    offenders = []
    for fname in _GUARDED_FILES:
        p = ROOT / "modules" / fname
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_cache_key":
                offenders.append(f"{fname}:{node.lineno}: 本地 def _build_cache_key（真身必须是 fetcher_core 函数）")
    assert not offenders, \
        "_build_cache_key 真身回潮本地 def:\n  " + "\n  ".join(offenders)


def test_build_cache_key_imported_from_core():
    """fetcher.py 必须从 fetcher_core import _build_cache_key（同 Tier1.1 重导出范式）。"""
    src = FETCHER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "modules.fetcher_core":
            for alias in node.names:
                if alias.name == "_build_cache_key":
                    found = True
                    break
    assert found, "fetcher.py 应 re-export _build_cache_key from fetcher_core（调用方零改动）"
