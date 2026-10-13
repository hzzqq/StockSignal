"""
tests/test_ui_theme_finpro.py
=============================
T-276：「金融终端 Pro」风格守卫——preset 结构 / 红涨绿跌语义不反转 /
风格选择器显示同步修复防回潮。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.ui_theme import STYLE_PRESETS  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]


def test_finpro_registered():
    """finpro 已注册且为 dark 模式（第 7 套风格）。"""
    assert "finpro" in STYLE_PRESETS, "finpro preset 缺失（T-276 产物被删）"
    p = STYLE_PRESETS["finpro"]
    assert p["mode"] == "dark"
    assert "金融终端 Pro" in p["label"]


def test_finpro_core_vars_present():
    """七变量齐备：底/卡/主色/文字/边框（金融终端深蓝体系）。"""
    v = STYLE_PRESETS["finpro"]["vars"]
    for var in ("--bg:#0a1020", "--card:#0f1726", "--acc1:#2f81f7",
                "--txt:#e6edf3", "--border:#1f2937"):
        assert var in v, f"核心变量缺失: {var}"


def test_semantic_colors_not_overridden():
    """红线：finpro 不得覆盖红涨绿跌语义色（--ss-up/--ss-down/--buy/--sell）。"""
    v = STYLE_PRESETS["finpro"]["vars"]
    for banned in ("--ss-up:", "--ss-down:", "--buy:", "--sell:"):
        assert banned not in v, f"finpro 覆盖了语义色 {banned}（A股红涨绿跌铁律）"
    # extra 特征层同样不得改语义色
    extra = STYLE_PRESETS["finpro"]["extra"]
    for banned in ("--ss-up:", "--ss-down:", "--buy:", "--sell:"):
        assert banned not in extra, f"finpro extra 覆盖了语义色 {banned}"


def test_finpro_native_expander_dark_override():
    """T-282 防回潮：expander 必须 DOM 级深色覆盖（三层）。

    Streamlit 1.58 的 expander 背景由 emotion 在 JS 侧按 config 主题计算
    （darkenedBgMix15/25），不引用 CSS 变量——token 映射无效。不覆盖 DOM
    则深蓝页面出现浅色「白横条」（2026-10-13 浏览器实测 finpro 每日荐股页）。
    """
    extra = STYLE_PRESETS["finpro"]["extra"]
    for needed in ('[data-testid="stExpander"] details',
                   '[data-testid="stExpander"] summary',
                   '[data-testid="stExpanderDetails"]'):
        assert needed in extra, \
            f"finpro extra 缺少 {needed} 深色覆盖——expander 将回退浅色底（白横条缺陷）"


def test_style_switcher_key_sync_fix():
    """style_switcher 的 key 携带当前风格（prefs 切换后显示同步，T-276 修复防回潮）。"""
    src = (_ROOT / "modules" / "ui_theme.py").read_text(encoding="utf-8")
    assert "ui_style_select_{" in src, \
        "style_switcher 的 selectbox key 回退为固定值——prefs 切换后显示将与实际风格脱节"
