"""
tests/test_xc_ux_enhance_guard.py — T-310 星辰AI 对话体验增强接线守卫（离线，不 import 页面模块）

钉住三项 additive 增强，防回潮（每项对应一个 mutation 注入点，删除接线 → 对应断言变红）：
1. 满意度反馈：assistant 分支渲染 👍/👎 并写入 m["feedback"] + _persist_feedback 落库；
   欢迎语（chips 标记）不展示；发给 AI 的上下文只取 role+content（反馈不泄漏进 prompt）。
2. 对话导出：标题栏 st.download_button（mime=text/markdown），空对话 disabled + 诚实提示；
   _export_markdown 超长载荷显式截断标注（诚实语义），导出携带反馈标注。
3. 自动滚底：scroll_nav.xc_autoscroll_js（MutationObserver + 近底守卫 + __xcMO 防叠加），
   widgets extra_js 单次注入链并入。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "53_星辰AI.py"
SNAV = ROOT / "modules" / "scroll_nav.py"
WGT = ROOT / "modules" / "widgets.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_feedback_wiring():
    src = _src(PAGE)
    assert 'key=f"xc_fb_up_{idx}"' in src, "缺少 👍 反馈按钮"
    assert 'key=f"xc_fb_down_{idx}"' in src, "缺少 👎 反馈按钮"
    assert 'm["feedback"] = "up"' in src and 'm["feedback"] = "down"' in src, \
        "反馈未写入消息字典（落库链断裂）"
    assert "_persist_feedback()" in src, "反馈未触发落库"
    assert 'st.session_state.pop("xc_messages_sig", None)' in src, \
        "落库前未清签名去重标记（重试链断裂）"
    assert 'if not m.get("chips"):' in src, "欢迎语缺少反馈排除守卫"
    # AI 上下文只取 role+content（反馈不泄漏进 prompt）
    assert '"role": mm.get("role"), "content": mm.get("content", "")' in src and \
        '"role": mm.get("role"), "content": str(mm.get("content", ""))' in src, \
        "AI 上下文构造被改动（须只取 role+content）"


def test_export_wiring():
    src = _src(PAGE)
    assert "def _export_markdown" in src, "缺少导出渲染函数"
    assert "st.download_button" in src, "缺少导出按钮"
    assert 'mime="text/markdown"' in src, "导出类型必须为 markdown"
    assert "disabled=not _real_msgs" in src, "空对话导出缺少禁用守卫"
    assert "暂无可导出的对话内容" in src, "空对话缺少诚实提示"
    assert "载荷超长已截断" in src, "超长载荷缺少显式截断标注（诚实语义）"
    assert "用户反馈" in src, "导出未携带满意度反馈标注"
    assert 'not m.get("chips")' in src, "欢迎语不得进入导出内容"


def test_autoscroll_wiring():
    js_mod = _src(SNAV)
    assert "def xc_autoscroll_js" in js_mod, "缺少自动滚底 JS 生成函数"
    assert "MutationObserver" in js_mod, "滚底观察器缺失"
    assert "nearBottom" in js_mod and "450" in js_mod, \
        "缺少近底守卫（用户上翻阅读时不得劫持滚动位置）"
    assert "__xcMO" in js_mod and "disconnect" in js_mod, "缺少观察器防叠加机制"
    wsrc = _src(WGT)
    assert "xc_autoscroll_js()" in wsrc, \
        "注入链未并入自动滚底（extra_js 单次通道约束）"


def test_sources_parse():
    """三文件 AST 可解析（防止半成品落盘）。"""
    for p in (PAGE, SNAV, WGT):
        ast.parse(_src(p), filename=str(p))
