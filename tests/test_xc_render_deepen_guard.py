"""
tests/test_xc_render_deepen_guard.py — T-312 星辰AI 回答溯源与渲染深化守卫（离线，不 import 页面模块）

钉住三项交付契约，防回退（mutation 目标，破坏任一接线 → 对应断言变红）：
1. markdown 渲染：回答内表格（xc-tbl）/行内代码（xc-code）/ [S#] 徽标（仅 cite_badges=True 开启）
   —— 行为级测试：从页面 AST 抽取 _inline/_md_to_html 沙箱执行，真实输入断真实输出；
2. 研究卡引用溯源：回答 [S#] 徽标化 + 引用区 st.popover 点击展开明细（key 含消息 idx 防多卡撞 key）；
3. 任务级失败一键重试：_poll_ai_task error/timeout 终态分支回溯最近用户提问挂 retry_prompt，
   render_message 渲染「重试本次提问」按钮并复用 _xc_pending 提交通道（fragment 级 rerun）。
"""
import ast
import html
import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "pages" / "53_星辰AI.py"


def _page_src() -> str:
    return PAGE.read_text(encoding="utf-8")


def _fn(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到模块级函数 {name}")


def _load_md_to_html():
    """从页面 AST 抽取 _inline/_md_to_html 在沙箱命名空间执行（仅依赖 re/html，无 Streamlit）。"""
    tree = ast.parse(_page_src(), filename=str(PAGE))
    ns: dict = {"re": re, "html": html}
    for name in ("_inline", "_md_to_html"):
        node = _fn(tree, name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<xc_md>", "exec"), ns)
    return ns["_md_to_html"]


# ─────────────────────────────────────────────────────────
# 契约 1：markdown 表格 / 行内代码 / [S#] 徽标（行为级）
# ─────────────────────────────────────────────────────────
def test_md_table_rendered_with_header_and_body():
    md = _load_md_to_html()
    out = md(
        "前置说明\n\n| 名称 | 代码 |\n| --- | --- |\n"
        "| 太极实业 | 600667 |\n| 中芯国际 | 688981 |\n\n后记"
    )
    assert "<table class='xc-tbl'>" in out, "markdown 表格未渲染为 xc-tbl（T-312 契约1 回退）"
    assert "<thead><tr><th>名称</th><th>代码</th></tr></thead>" in out
    assert "<td>太极实业</td>" in out and "<td>600667</td>" in out
    assert "<td>中芯国际</td>" in out
    assert "---" not in out, "分隔行 |---| 被当作数据行渲染"
    assert "前置说明" in out and "后记" in out, "表格前后段落丢失"


def test_md_table_alignment_separator_dropped():
    md = _load_md_to_html()
    out = md("| A | B |\n| :---: | ---: |\n| 1 | 2 |")
    assert ":---" not in out and "---:" not in out, "对齐分隔行未丢弃"


def test_md_table_xss_escaped_and_inline_code():
    md = _load_md_to_html()
    out = md("| 指标 | 值 |\n| --- | --- |\n| `<b>x</b>` | <script>alert(1)</script> |")
    assert "<code class='xc-code'>&lt;b&gt;x&lt;/b&gt;</code>" in out, "行内代码未渲染/未转义"
    assert "<script>" not in out, "表格单元格 HTML 未转义（XSS）"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_cite_badges_only_when_enabled():
    md = _load_md_to_html()
    plain = md("要点一 [S1] 要点二")
    assert "xc-cite" not in plain and "[S1]" in plain, \
        "普通回答默认不得渲染引用徽标（cite_badges 默认关闭）"
    badges = md("要点一 [S1] 要点二", cite_badges=True)
    assert '<span class="xc-cite" title="研究步骤 S1 · 详见下方引用溯源">S1</span>' in badges, \
        "cite_badges=True 未渲染 [S#] 徽标（研究卡溯源契约回退）"


def test_inline_code_protected_from_bold_italic():
    md = _load_md_to_html()
    out = md("值 `a*b**c` 与 **加粗**")
    assert "<code class='xc-code'>a*b**c</code>" in out, "行内代码内容被粗/斜体正则污染"
    assert "<b>加粗</b>" in out, "既有粗体渲染回退"
    assert "<i>" not in out


def test_code_block_list_quote_regression():
    md = _load_md_to_html()
    out = md("```python\nprint('hi')\n```\n\n- 项目 **加粗**\n1. 有序\n> 引用")
    assert "<pre class='xc-pre'>print('hi')</pre>" in out, "代码块渲染回退"
    assert "<li>项目 <b>加粗</b></li>" in out, "无序列表渲染回退"
    assert "<li>有序</li>" in out and "<ol>" in out, "有序列表渲染回退"
    assert "xc-quote" in out and "引用" in out, "引用块渲染回退"


# ─────────────────────────────────────────────────────────
# 契约 2：研究卡 [S#] 徽标 + 引用溯源 popover 点击展开
# ─────────────────────────────────────────────────────────
def test_research_card_citations_popover_and_badges():
    tree = ast.parse(_page_src(), filename=str(PAGE))
    fn = _fn(tree, "render_research_card")
    src = ast.get_source_segment(_page_src(), fn) or ""
    assert "cite_badges=True" in src, "研究卡回答未开启 [S#] 徽标（_md_to_html cite_badges=True）"
    has_popover = any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "popover"
        for n in ast.walk(fn)
    )
    assert has_popover, "引用溯源必须用 st.popover 点击展开明细（T-312 契约2 回退为静态列表）"
    assert "xc_cite_{idx}" in src, "popover key 未含消息 idx（多张研究卡同页渲染会撞 key）"
    assert "数据时点" in src, "popover 明细缺数据时点（诚实溯源语义缺失）"
    assert "use_container_width" not in src, "Streamlit API 卫生：禁 use_container_width"


# ─────────────────────────────────────────────────────────
# 契约 3：任务级失败一键重试接线
# ─────────────────────────────────────────────────────────
def test_task_failure_attaches_retry_prompt():
    tree = ast.parse(_page_src(), filename=str(PAGE))
    fn = _fn(tree, "_poll_ai_task")
    src = ast.get_source_segment(_page_src(), fn) or ""
    assert src.count('"retry_prompt"') >= 2, \
        "error/timeout 终态分支须都挂 retry_prompt（T-312 契约3：仅接一条 = 残缺接线）"
    assert 'reversed(st.session_state["xc_messages"])' in src, \
        "未回溯消息列表取最近用户提问"
    assert 'mm.get("role") == "user"' in src, "回溯未限定 user 角色（会把 AI 自己的回答当提问重发）"


def test_render_message_retry_button_wiring():
    tree = ast.parse(_page_src(), filename=str(PAGE))
    fn = _fn(tree, "render_message")
    src = ast.get_source_segment(_page_src(), fn) or ""
    assert "retry_prompt" in src, "render_message 未消费 retry_prompt"
    assert "xc_retry_msg_" in src, "重试按钮 key 缺失（撞 key 风险）"
    assert '"_xc_pending"' in src, "重试未复用 _xc_pending 提交通道（禁止新增通道）"
    assert 'st.rerun(scope="fragment")' in src, "重试必须 fragment 级 rerun（禁整页 rerun）"
    assert "use_container_width" not in src, "Streamlit API 卫生：禁 use_container_width"
