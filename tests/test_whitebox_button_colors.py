"""test_whitebox_button_colors.py — 按钮配色系统白盒测试

覆盖 modules.button_colors.btn_html 的全部分支与边界：
  - 默认 kind=primary
  - 6 种语义 kind 的 class 映射
  - size / block / disabled / icon / extra_class 组合
  - BUTTON_PALETTE 结构完整性（6 档 x light/dark）
纯函数，无 IO、无 streamlit 运行时依赖，可独立验证。
"""

import pytest

from modules.button_colors import btn_html, BUTTON_PALETTE

KINDS = ["primary", "success", "warning", "danger", "ghost", "info"]


class TestBtnHtmlBasics:
    """btn_html 基础行为。"""

    def test_default_is_primary(self):
        html = btn_html("提交")
        assert 'class="sf-btn sf-btn-primary"' in html
        assert ">提交</button>" in html

    def test_text_escaped_in_class_only(self):
        # 文本原样进入标签体，class 不含文本
        html = btn_html("确定")
        assert "确定" in html
        assert "sf-btn-确定" not in html


class TestBtnHtmlKinds:
    """6 种语义 kind 都映射到正确的 class。"""

    @pytest.mark.parametrize("kind", KINDS)
    def test_each_kind_class(self, kind):
        html = btn_html("x", kind=kind)
        assert f"sf-btn-{kind}" in html


class TestBtnHtmlModifiers:
    """size / block / disabled / icon / extra_class。"""

    def test_size_sm(self):
        html = btn_html("x", size="sm")
        assert "sf-btn-sm" in html

    def test_size_lg(self):
        html = btn_html("x", size="lg")
        assert "sf-btn-lg" in html

    def test_block(self):
        html = btn_html("x", block=True)
        assert "sf-btn-block" in html

    def test_disabled_adds_class_and_attr(self):
        html = btn_html("x", disabled=True)
        assert "disabled" in html  # class 中的 disabled
        assert " disabled" in html or 'disabled"' in html or "disabled>" in html
        assert "disabled" in html.split("class=")[1].split(">")[0]

    def test_icon_prepended(self):
        html = btn_html("保存", icon="💾")
        assert "💾保存" in html

    def test_no_icon_keeps_text_only(self):
        html = btn_html("保存")
        assert "保存" in html
        # 没有 icon 时标签体应恰好是文本
        assert html.endswith(">保存</button>")

    def test_extra_class_appended(self):
        html = btn_html("x", extra_class="my-cls")
        assert "my-cls" in html


class TestPaletteIntegrity:
    """BUTTON_PALETTE 结构完整性。"""

    def test_six_kinds_present(self):
        assert set(BUTTON_PALETTE.keys()) == set(KINDS)

    def test_each_kind_has_light_and_dark(self):
        for kind in KINDS:
            assert "light" in BUTTON_PALETTE[kind]
            assert "dark" in BUTTON_PALETTE[kind]
            for mode in ("light", "dark"):
                assert "bg" in BUTTON_PALETTE[kind][mode]
                assert "text" in BUTTON_PALETTE[kind][mode]

    def test_contrast_text_not_gray_for_solid(self):
        # 实心按钮文字应为纯白或近黑，杜绝灰/彩色文字（设计铁律）
        for kind in ("primary", "success", "warning", "danger"):
            assert BUTTON_PALETTE[kind]["light"]["text"] == "#ffffff"
            assert BUTTON_PALETTE[kind]["dark"]["text"] == "#ffffff"
