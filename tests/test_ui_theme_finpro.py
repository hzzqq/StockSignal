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


def test_style_switcher_key_sync_fix():
    """style_switcher 的 key 携带当前风格（prefs 切换后显示同步，T-276 修复防回潮）。"""
    src = (_ROOT / "modules" / "ui_theme.py").read_text(encoding="utf-8")
    assert "ui_style_select_{" in src, \
        "style_switcher 的 selectbox key 回退为固定值——prefs 切换后显示将与实际风格脱节"
