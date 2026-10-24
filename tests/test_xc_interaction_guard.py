"""
tests/test_xc_interaction_guard.py — T-315 星辰AI 交互补齐守卫

四项交付（对应 mutation 注入点）：
1. 停止生成：worker.cancel（pending/running → CANCELLED，终态不可取消，不存在返 None）
   + _run_task 结果写入不得覆盖取消态 + DELETE /api/tasks/<id> + 前端停止按钮；
2. 复制回答：气泡内 <textarea> 承载原文 + .xc-copy 按钮 + scroll_nav 事件委托 JS
   经 extra_js 单次注入（项目铁律：JS 只能走该通道）；
3. 重新生成：对已有 assistant 回答重新提问（xc_regen_*，复用 _xc_pending，无新通道）；
4. 消息时间戳：user/assistant 消息写入 ts 并渲染为可读时间。

说明：worker.cancel 用 __new__ 构造实例做行为级测试（不启动线程池、不落盘）。
"""
import ast
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "53_星辰AI.py"
WORKER = ROOT / "backend" / "tasks" / "worker.py"
ROUTES = ROOT / "backend" / "api" / "task_routes.py"
BGT = ROOT / "modules" / "background_tasks.py"
SNAV = ROOT / "modules" / "scroll_nav.py"
WGT = ROOT / "modules" / "widgets.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── 1. 停止生成 ────────────────────────────────────────────────
def test_worker_cancel_marks_cancelled():
    from backend.tasks.worker import Task, TaskStatus, TaskWorker

    w = TaskWorker.__new__(TaskWorker)          # 不启动线程池
    w._lock = threading.Lock()
    w._persist = lambda: None                   # 不落盘
    t = Task("t1", "ai_consult", {}, time.time())
    w._tasks = {"t1": t}

    assert w.cancel("t1") is True, "pending 任务必须可取消"
    assert t.status is TaskStatus.CANCELLED
    assert w.cancel("t1") is False, "已终态任务不得再次取消（避免状态回退）"
    assert w.cancel("missing") is None, "不存在的任务返回 None（与 False 区分）"


def test_cancel_terminal_untouchable():
    from backend.tasks.worker import Task, TaskStatus, TaskWorker

    w = TaskWorker.__new__(TaskWorker)
    w._lock = threading.Lock()
    w._persist = lambda: None
    for st in (TaskStatus.SUCCESS, TaskStatus.ERROR):
        t = Task("t2", "ai_consult", {}, time.time())
        t.status = st
        w._tasks = {"t2": t}
        assert w.cancel("t2") is False, f"{st} 是终态，不得被取消"
        assert t.status is st


def test_run_task_respects_cancelled():
    """结果写入必须尊重取消态：已取消的任务不得被回填为 success/error。"""
    src = _src(WORKER)
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_run_task"), None)
    assert fn is not None, "未找到 _run_task"
    seg = ast.get_source_segment(src, fn) or ""
    # 三处：排队期（RUNNING 之前）+ success 写入前 + error 写入前
    assert seg.count("TaskStatus.CANCELLED") >= 3, (
        "_run_task 必须在排队期、success、error 三处都检查取消态"
        "（漏一处：取消后被覆盖回 success/error）"
    )


def test_cancel_endpoint_exists():
    src = _src(ROUTES)
    assert "@bp.delete" in src, "缺少取消端点（DELETE /api/tasks/<id>）"
    assert "cancel" in src, "取消端点未接 worker.cancel"


def test_client_has_cancel_task():
    src = _src(BGT)
    assert "def cancel_task" in src, "客户端缺少 cancel_task"
    assert "/api/tasks/" in src and "requests.delete" in src, "cancel_task 必须用 DELETE 调任务端点"


def test_page_has_stop_button():
    src = _src(PAGE)
    assert "xc_stop" in src, "缺少停止生成按钮 key"
    assert "cancel_task" in src, "停止按钮未调客户端 cancel_task"


# ── 2. 复制回答 ────────────────────────────────────────────────
def test_page_copy_button_and_source():
    src = _src(PAGE)
    assert "xc-copy-src" in src, "缺少承载原文的 textarea（属性无法安全承载多行 markdown）"
    assert 'class="xc-copy"' in src, "缺少复制按钮"
    assert "xc_copy_block" in src, "复制按钮应统一由辅助函数生成（避免每条消息重复拼 HTML）"


def test_scroll_nav_copy_js_injected():
    snav = _src(SNAV)
    assert "def xc_interaction_js" in snav, "缺少复制事件委托 JS 生成函数"
    assert "xcCopyBound" in snav, "缺少重复绑定守卫（rerun 会重复注入）"
    assert "clipboard.writeText" in snav, "缺少剪贴板写入"
    assert "execCommand('copy')" in snav, "缺少剪贴板不可用时的降级路径（具体调用，非仅注释提及）"
    wgt = _src(WGT)
    assert "xc_interaction_js()" in wgt, "复制 JS 未并入 extra_js 单次注入链"
    # T-315 拼接边界：两段 IIFE 直接字符串拼接时，缺分号会变成 })()(function(){…（误当函数调用，
    # 实测导致复制绑定整段不执行）；本段必须前置分号，滚底段必须后置分号。
    assert '";(function(){"' in snav, "复制 JS 缺少前置分号（与上一段 IIFE 拼接会失效）"
    assert '"})();"' in snav, "自动滚底 JS 缺少结尾分号（后续 IIFE 会被误解析为函数调用）"


# ── 3. 重新生成 ────────────────────────────────────────────────
def test_page_regenerate_button():
    src = _src(PAGE)
    assert "xc_regen_" in src, "缺少重新生成按钮 key"
    assert '"_xc_pending"' in src, "重新生成必须复用 _xc_pending 通道（禁止新增提交通道）"


# ── 4. 消息时间戳 ──────────────────────────────────────────────
def test_message_timestamp_written_and_rendered():
    src = _src(PAGE)
    assert '"ts": time.time()' in src, "消息写入时未记录 ts"
    assert "_fmt_ts" in src, "缺少时间格式化函数"
    assert "xc-ts" in src, "时间戳未渲染到消息头"


def test_extra_js_segments_use_parent_scope():
    """T-315 阻塞级缺陷守卫：extra_js 各段运行在组件 iframe，必须用 P（父窗口）作用域。

    历史缺陷：drawer_js 用裸 window/document → 在 iframe 内建抽屉并可能因
    document.body 为 null 抛错，被外层 try 吞掉后**阻断其后所有 extra_js**
    （自动滚底、复制回答全部静默失效）。
    """
    drawer = (ROOT / "modules" / "drawer.py").read_text(encoding="utf-8")
    seg = drawer[drawer.index("def drawer_js"):]
    assert "P.document.body.appendChild" in seg, "抽屉未挂到父文档（用户看不到）"
    assert "P.__ssDrawer" in seg, "抽屉句柄未挂父窗口（业务侧 window.parent.__ssDrawer 会取不到）"
    # 反向：裸 window/document 不得作为抽屉 DOM 宿主
    assert "document.body.appendChild" not in seg.replace("P.document.body.appendChild", ""), \
        "仍在 iframe 内建 DOM（缺陷回潮）"
    assert "if (!P.__ssDrawer)" in seg, "未做幂等判定（rerun 会重复创建抽屉）"
    # 自隔离：本段必须自包 try，避免异常阻断后续 extra_js
    assert "catch (eD)" in seg, "缺少自隔离 try（异常会再次阻断后续注入）"


def test_sources_parse():
    for p in (PAGE, WORKER, ROUTES, BGT, SNAV, WGT):
        ast.parse(_src(p), filename=str(p))
