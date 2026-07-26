"""widgets 纯助手函数安全加固测试（无 Streamlit/网络依赖）。

覆盖（R1/R2/R5/R6）：
- 纯格式化助手在合法输入下行为不变（_hex_to_rgba 等返回预期串）。
- None/空输入安全降级（不抛异常）：_hex_to_rgba / STAR_AI_LOGO / _index_name_html。
- 从数据派生文本构建 HTML 时必须转义（防注入）：_index_name_html / _ai_md，
  恶意名称如 <script> 被转义而非原样输出。
"""
import modules.widgets as W


# ── 合法输入行为不变 ───────────────────────────────────────
def test_hex_to_rgba_valid():
    assert W._hex_to_rgba("#667eea", 0.5) == "rgba(102,126,234,0.5)"
    assert W._hex_to_rgba("#000000", 0.0) == "rgba(0,0,0,0.0)"


def test_star_ai_logo_valid():
    out = W.STAR_AI_LOGO(20)
    assert isinstance(out, str)
    assert out.startswith("<svg")
    assert 'width="20"' in out


# ── None/空安全降级（不抛异常）────────────────────────────
def test_hex_to_rgba_none_safe():
    assert W._hex_to_rgba(None, 0.5) == "rgba(0,0,0,0.5)"
    assert W._hex_to_rgba("", 0.5) == "rgba(0,0,0,0.5)"


def test_hex_to_rgba_invalid_safe():
    # 非法色字符串不应抛 ValueError，降级为透明黑
    assert W._hex_to_rgba("not-a-color", 0.3) == "rgba(0,0,0,0.3)"
    assert W._hex_to_rgba("zzz", 0.3) == "rgba(0,0,0,0.3)"


def test_star_ai_logo_none_safe():
    # None/非数值/非正数降级为 20，不抛异常
    assert W.STAR_AI_LOGO(None).startswith("<svg")
    assert W.STAR_AI_LOGO("abc").startswith("<svg")
    assert W.STAR_AI_LOGO(0).startswith("<svg")
    assert W.STAR_AI_LOGO(-5).startswith("<svg")


def test_index_name_html_none_safe():
    out = W._index_name_html(None, "#000", 17)
    assert isinstance(out, str)
    assert "—" in out
    # 空串同样安全降级
    assert "—" in W._index_name_html("", "#000", 17)


# ── 数据派生文本必须转义（防注入）────────────────────────
def test_index_name_html_escapes_script():
    evil = "<script>alert(1)</script>"
    out = W._index_name_html(evil, "#000", 17)
    assert "<script>" not in out          # 不允许原始标签
    assert "&lt;script&gt;" in out        # 必须被转义
    assert evil not in out


def test_index_name_html_normal_passthrough():
    out = W._index_name_html("上证指数", "#111827", 17)
    assert "上证指数" in out
    assert 'font-size:17px' in out


def test_ai_md_escapes_script():
    # _ai_md 是纯函数且已转义：恶意内容不应以原始标签出现
    evil = "<script>alert(1)</script>"
    out = W._ai_md(evil)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_ai_md_valid_markdown():
    # 合法 markdown 仍被正常转换
    assert "<b>粗体</b>" in W._ai_md("**粗体**")
    assert "<br>" in W._ai_md("第一行\n第二行")


# ── 既有隐式 None 修复不回归 ──────────────────────────────
def test_trend_label_invalid_returns_string():
    assert W._trend_label(0, 0, 0, 0, 0) == "—"
    out = W._trend_label(10.0, 10.02, 9.99, 10.0, 10.0)
    assert isinstance(out, str)
    assert out != "None"
