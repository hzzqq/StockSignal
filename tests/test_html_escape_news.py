"""
tests/test_html_escape_news.py
==============================
回归：外部数据（新闻标题 / 股吧用户名·正文·头像）拼进
``st.markdown(..., unsafe_allow_html=True)`` 前必须转义。

背景（cycle 33 修复的真实缺陷）：
- ``pages/2_个股分析.py`` 把新闻标题原样拼进 HTML 表格与风险/催化提示条，
  标题里若含 ``<script>`` / 未闭合标签 → 页面标签泄露、排版错乱、可执行脚本；
- ``pages/D_股吧.py`` 把用户名、评论正文、头像 URL 原样拼进 HTML，
  其中头像位于 ``src="…"`` 属性内，未转义可直接从属性逃逸注入事件处理器。

本文件只测纯函数 + 源码级断言，不启 Streamlit，跑得快且不依赖网络。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from modules.format_helpers import safe_html_text

ROOT = Path(__file__).resolve().parents[1]

XSS_PAYLOAD = '<script>alert("x")</script>'


class TestSafeHtmlText:
    def test_escapes_script_tag(self):
        out = safe_html_text(XSS_PAYLOAD)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_escapes_quotes_for_attribute_context(self):
        # 头像 URL 场景：必须堵死 `" onerror="` 这类属性逃逸
        out = safe_html_text('x" onerror="alert(1)')
        assert '"' not in out
        assert "&quot;" in out

    def test_escapes_ampersand_and_angle(self):
        assert safe_html_text("a & b < c > d") == "a &amp; b &lt; c &gt; d"

    def test_none_returns_default_not_literal_none(self):
        assert safe_html_text(None) == ""
        assert safe_html_text(None, "—") == "—"

    def test_empty_string_returns_default(self):
        assert safe_html_text("", "?") == "?"
        assert safe_html_text("   ") == "   "  # 纯空格不算空，原样保留

    def test_non_string_is_stringified_then_escaped(self):
        assert safe_html_text(123) == "123"
        assert safe_html_text(1.5) == "1.5"

    def test_plain_text_unchanged(self):
        assert safe_html_text("贵州茅台业绩超预期") == "贵州茅台业绩超预期"

    def test_idempotent_enough_for_double_call(self):
        # 二次转义会变成 &amp;lt;，说明调用方不应重复转义；这里锁定行为可预期
        once = safe_html_text("<b>")
        assert safe_html_text(once) == "&amp;lt;b&amp;gt;"


class TestPagesUseEscaping:
    """源码级回归：防止后来者把转义调用改回裸拼接。"""

    def _src(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_stock_page_imports_and_escapes_news_title(self):
        src = self._src("pages/2_个股分析.py")
        assert "safe_html_text" in src, "个股分析页应导入 safe_html_text"
        # 新闻表格行 / 风险 / 催化提示条：标题必须走转义（单引号写法，≥2 处）
        assert src.count("safe_html_text(r.get('title')") >= 2, "标题未走 safe_html_text 转义"

    def test_stock_page_has_no_raw_title_in_html(self):
        src = self._src("pages/2_个股分析.py")
        # 裸 {r.get('title')} 直接插值到 f-string HTML 里应当已被消灭
        assert not re.search(r"\{r\.get\('title'\)\s*or\s*'—'\}", src)

    def test_forum_page_escapes_user_content(self):
        src = self._src("pages/D_股吧.py")
        assert "safe_html_text" in src, "股吧页应导入 safe_html_text"
        # 头像 src 属性
        assert 'src="{safe_html_text(avatar_data_url)}"' in src
        # 评论正文与用户名
        assert "safe_html_text(c.get('content'))" in src
        assert "safe_html_text(c.get('username'), '?')" in src

    def test_forum_page_has_no_raw_comment_content(self):
        src = self._src("pages/D_股吧.py")
        assert "{c.get('content', '')}" not in src
        assert '<img src="{avatar_data_url}"' not in src

    def test_quantagent_page_escapes_llm_text(self):
        # cycle 34：QuantAgent 投研页把 LLM 生成文本（结论/理由/辩论发言）原样拼进
        # unsafe_allow_html=True 的卡片，含 < 的研报（如 "PE <20"）会被浏览器吞掉，
        # 理论上也存在注入风险，必须转义
        src = self._src("pages/Q_QuantAgent投研.py")
        assert "safe_html_text" in src, "QuantAgent 页应导入 safe_html_text"
        assert "safe_html_text(l.get('message'))" in src
        assert "safe_html_text(c.get('verdict'), '-')" in src
        assert "safe_html_text(c.get('rationale'))" in src
        assert "safe_html_text(st_.get('text'))" in src
        assert "safe_html_text(st_.get('name'))" in src
        # 执行轨迹（markdown 渲染）也需转义动态字段
        assert "safe_html_text(t.get('log'))" in src
        # 实时日志流函数已自带转义，不应被回退
        assert "_html.escape(str(e.get('message', '')))" in src



@pytest.mark.parametrize(
    "payload",
    [
        XSS_PAYLOAD,
        '<img src=x onerror=alert(1)>',
        '<a href="javascript:alert(1)">click</a>',
        "</td></tr><tr><td>injected",
        "<b>未闭合",
    ],
)
def test_common_payloads_fully_neutralized(payload):
    out = safe_html_text(payload)
    # 转义后不应残留任何可被浏览器解析的标签起始
    assert "<" not in out and ">" not in out
