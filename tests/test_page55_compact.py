"""
tests/test_page55_compact.py
============================
T-277 第一批组件紧凑化守卫（55 页试点）：刷新钮图标化 / 说明收进 ❓ 悬浮。
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = (_ROOT / "pages" / "55_P1量化信号.py").read_text(encoding="utf-8")


def test_refresh_button_icon_only():
    """刷新钮只剩图标 + help 悬浮提示（去掉满宽方框与「刷新」两字）。"""
    assert 'st.button("🔄"' in _SRC, "刷新钮应仅保留 🔄 图标"
    assert 'width="stretch"' not in _SRC.split("p1_refresh")[0].split("st.button")[-1], \
        "刷新钮不应满宽"
    assert "刷新信号\"" not in _SRC, "「刷新信号」文字应移入 help"


def test_help_tooltip_carries_full_text():
    """原按钮文字语义不丢：help 悬浮提示承载刷新说明。"""
    assert "help=\"刷新信号：清除缓存并重新读取信号文件" in _SRC


def test_intro_collapsed_into_hover_badge():
    """接入说明 + 口径必读收进 ❓ 悬浮标注（ss_hover_preview），内容全保留。"""
    assert "ss_hover_preview(" in _SRC, "说明未收进悬浮标注"
    assert "口径必读" in _SRC and "接入说明" in _SRC, "说明内容被删（诚实语义回退）"
    assert "xc_warn_box(\n    \"⚠️ 阅读前必读" not in _SRC, "巨型警示卡未拆除"


# ────── T-277 第二批：全站刷新钮图标化守卫（白名单：回填/重试功能钮） ──────
import re

_PAGES = (_ROOT / "pages").glob("*.py")
_WHITELIST = ("回填", "重试")  # 功能钮/错误路径钮保留文字（需明示）


def test_site_wide_no_wide_refresh_text_buttons():
    """全站 pages/ 无满宽 🔄 文字钮（白名单外）——回潮即红并列出位置。"""
    leftover = []
    for p in _PAGES:
        t = p.read_text(encoding="utf-8")
        for m in re.finditer(
                r"st\.button\(\s*(['\"])🔄 ([^'\"]*)\1[^)]*width=[\"']stretch", t):
            label = m.group(2)
            if not any(w in label for w in _WHITELIST):
                leftover.append(f"{p.name}: 🔄 {label}")
    assert not leftover, "满宽 🔄 文字钮回潮:\n" + "\n".join(leftover)


def test_hover_pages_wired():
    """54/55 两试点页的 hover 标注接线不回退。"""
    s54 = (_ROOT / "pages" / "54_今日决策面板.py").read_text(encoding="utf-8")
    assert "ss_hover_preview(\"ℹ️ 怎么用\"" in s54, "54 页怎么用悬浮标注被删"
    assert "ss_hover_preview(\"ℹ️ 口径与用法\"" in _SRC, "55 页口径悬浮标注被删"
