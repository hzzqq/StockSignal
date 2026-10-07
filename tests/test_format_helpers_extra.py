"""format_helpers 新增 clamp / safe_delta 纯函数测试（无网依赖）。

来源：origin/polish-continue 分支（polish 29/30/30b）中**尚未合入 main** 的真缺口，
经勘测剔除两类「已在 main / 重复实现」后移植：
- technical compute_macd/compute_ema 已在 main（60055ba 自 backup-local 合入）；
- 分支的 to_percent_str 与 main 既有 format_pct 实现逐字节相同（均为百分比原值
  直格式化、不 ×100），属重复造轮子，已剔除（DRY）。
另补 analysis_engine NaN 安全契约守卫（防止回退为 int(round(nan)) 崩溃）。
"""
import ast
import os

import modules.format_helpers as FH

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────── clamp ─────────────────────────
def test_clamp_normal():
    assert FH.clamp(50, 0, 100) == 50
    assert FH.clamp(150, 0, 100) == 100
    assert FH.clamp(-5, 0, 100) == 0


def test_clamp_nan_none_fallback():
    """NaN / None -> 下界（保守）；±inf -> 对应边界。替代 max(lo, min(hi, x)) 的漏洞。"""
    assert FH.clamp(float("nan"), 0, 100) == 0
    assert FH.clamp(None, 0, 100) == 0
    assert FH.clamp("oops", 0, 100) == 0
    assert FH.clamp(float("inf"), 0, 100) == 100
    assert FH.clamp(float("-inf"), 0, 100) == 0


def test_naive_minmax_leaks_but_clamp_does_not():
    """复现原缺陷：旧写法 max(lo, min(hi, nan)) 会返回 100（错误），clamp 返回保守下界。"""
    naive = max(0, min(100, float("nan")))  # 旧写法
    assert naive == 100, "Python min/max 对 NaN 的行为（文档化旧缺陷）"
    assert FH.clamp(float("nan"), 0, 100) == 0


# ───────────────────────── safe_delta ─────────────────────────
def test_safe_delta_basic():
    assert FH.safe_delta(10, 3) == 7
    assert FH.safe_delta(3, 10) == -7


def test_safe_delta_none_nan():
    assert FH.safe_delta(None, 5) == 0.0
    assert FH.safe_delta(5, None) == 0.0
    assert FH.safe_delta(float("nan"), 5) == 0.0
    assert FH.safe_delta(5, float("inf")) == 0.0


def test_to_percent_str_not_added_duplicate():
    """防重复：main 的 format_pct 已覆盖「百分点原值直格式化」，不应再加同名异实现。"""
    assert not hasattr(FH, "to_percent_str"), \
        "to_percent_str 与 format_pct 实现重复（DRY），不应存在"
    assert FH.format_pct(12.34) == "12.34%"
    assert FH.format_pct(None) == "—"


# ─────────────── analysis_engine NaN 安全契约守卫 ───────────────
def test_analysis_engine_composite_uses_clamp_before_int():
    """防回退：composite 必须 clamp-before-int，否则 NaN 维度会让 int(round(nan)) 崩溃。"""
    src = open(os.path.join(_ROOT, "modules", "analysis_engine.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    imported = {
        alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        and n.module == "modules.format_helpers" for alias in n.names
    }
    assert "clamp" in imported and "to_float" in imported, \
        f"analysis_engine 必须从 format_helpers 导入 clamp/to_float，实际 {imported}"
    assert "int(round(clamp(" in src, "composite 必须 clamp 在 int(round) 之前（NaN 安全）"
    assert "composite = max(0, min(100, composite))" not in src, \
        "旧写法 max/min 钳制已回退（NaN 会先撞 int(round) 崩溃）"


def test_naive_int_round_nan_would_crash():
    """文档化被修复的崩溃：int(round(nan)) 抛 ValueError，clamp 后不再发生。"""
    import pytest
    with pytest.raises(ValueError):
        int(round(float("nan")))
    assert int(round(FH.clamp(float("nan"), 0, 100))) == 0

