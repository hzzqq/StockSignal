# -*- coding: utf-8 -*-
"""F821 未定义名守卫（2026-11-02 存量修复的回潮钉）。

背景：ruff --select F821 全仓扫出 132 处，分诊后确认 9 处为**真实未定义名**
（其余 123 处是 from __future__ import annotations 下的类型注解，运行期安全）。
这 9 处共同特征：都落在 try/except 或线程池任务里 → 异常被吞 → **静默失效**
（功能不工作但页面不崩），因此长期无测试变红。本文件逐个钉住。

判定方式：源码锚点 + 顺序断言（不用 ruff，避免测试依赖外部二进制）。
"""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── ① 星辰AI 咨询：poll_task / submit_task_with_error 必须有函数内导入 ──────
def test_widgets_ai_imports_background_tasks_in_function():
    src = _src("modules/_widgets_ai.py")
    assert "from modules.background_tasks import poll_task" in src, \
        "poll_task 未导入 → _poll_ai_consult_task 轮询必抛 NameError（被 try 吞掉，AI 咨询永远无结果）"
    assert "from modules.background_tasks import submit_task_with_error" in src, \
        "submit_task_with_error 未导入 → AI 咨询提交必抛 NameError"

    # 二者必须是函数内延迟导入（模块级导入会与 background_tasks 形成循环）
    tree = ast.parse(src)
    nested = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and node.module == "modules.background_tasks":
                for a in node.names:
                    nested.add(a.name)
    assert {"poll_task", "submit_task_with_error"} <= nested, \
        f"background_tasks 的导入应在函数内（避免循环导入），实际函数内导入={sorted(nested)}"


# ── ② 广度特征 as_of：mr 必须有定义 ─────────────────────────────────────
def test_breadth_features_defines_mr():
    src = _src("modules/breadth_features.py")
    assert re.search(r"import modules\.market_regime as mr", src), \
        "mr 未导入 → data_as_of 恒返回「未知」（诚实声明失效）"


# ── ③ 校准落盘：DATA_DIR 必须来自 decision_track 单一真理源 ───────────────
def test_calibration_uses_track_data_dir():
    src = _src("modules/calibration.py")
    assert "Path(_track.DATA_DIR)" in src, \
        "apply_patch 引用了未定义的 DATA_DIR → 补丁写回成功后误报失败（文件已改却返回 applied=False）"
    assert not re.search(r"Path\(DATA_DIR\)", src), "残留裸 DATA_DIR 引用"


# ── ④ 组合收益：异常分支引用的变量必须是函数参数 ─────────────────────────
def test_portfolio_views_exception_log_uses_ticker():
    src = _src("modules/portfolio_views.py")
    assert "组合收益净值计算 ticker={ticker}" in src, \
        "_fetch_position_series 的参数名是 ticker，异常分支引用 code 会抛 NameError 掩盖真实异常"


# ── ⑤ 指数迷你卡：配色常量必须在函数作用域内可解析 ───────────────────────
def test_widgets_index_mini_cards_imports_colors():
    src = _src("modules/widgets.py")
    assert "from modules.visualizer import DOWN_COLOR, UP_COLOR" in src, \
        "render_index_mini_cards 使用 UP_COLOR/DOWN_COLOR 但只在另一函数内导入 → 作用域取不到"


# ── ⑥ 行情看板：本地回退必须真实实现 ───────────────────────────────────
def test_wl_quote_local_is_defined():
    src = _src("pages/10_行情看板.py")
    assert re.search(r"^def _wl_quote_local\(", src, re.M), \
        "_wl_quote_local 被 fetch_many 任务引用却从未定义 → 本地逐只回退静默失效"
    tree = ast.parse(src)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_wl_quote_local" in defined


# ── ⑦ 事件追踪：不得残留死代码里的未定义名 ────────────────────────────────
def test_event_tracking_intraday_no_undefined_names():
    src = _src("pages/23_事件追踪.py")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_cached_intraday"), None)
    assert fn is not None
    undefined = {"_df", "_pc", "_dt"}
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert not (undefined & used), \
        f"_cached_intraday 仍在用未定义名 {sorted(undefined & used)} → 后端异常时抛 NameError"


# ── ⑧ 决策面板：pos 必须先定义后使用 ────────────────────────────────────
def test_decision_panel_pos_defined_before_use():
    src = _src("pages/54_今日决策面板.py")
    i_def = src.find("pos = derive_position(")
    i_use = src.find('position_pct=pos["pct"]')
    assert i_def != -1 and i_use != -1, "锚点缺失（derive_position 或 freshness 徽标）"
    assert i_def < i_use, \
        "position_pct=pos[\"pct\"] 位于 derive_position 之前 → 恒抛 NameError 被 except 吞掉，徽标永不渲染"


# ── ⑨ 通用扫描：ruff F821 只允许类型注解类白名单 ─────────────────────────
TYPE_ONLY = {"Dict", "List", "Any", "Optional", "Tuple", "Set", "Callable", "Sequence", "Mapping"}


def test_no_new_undefined_names_outside_type_annotations():
    """ruff F821 全仓扫描：非类型注解的未定义名必须为 0。

    类型名（Dict/List/...）在 `from __future__ import annotations` 下运行期不求值，
    属既有风格问题（另案清理），此处放行；其余一律 fail。
    ruff 不在环境时 skip（仅「环境不具备」允许 skip）。
    """
    import shutil
    import subprocess
    import sys

    ruff = shutil.which("ruff")
    if not ruff:
        try:
            import ruff  # noqa: F401
            ruff = sys.executable
            args = [sys.executable, "-m", "ruff"]
        except Exception:
            pytest.skip("ruff 未安装（环境不具备），跳过 F821 扫描")
    else:
        args = [ruff]

    proc = subprocess.run(
        args + ["check", "--select", "F821", "--output-format", "concise",
                "modules", "pages", "backend", "mcp_server", "scripts", "app.py"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    real = []
    for line in (proc.stdout or "").splitlines():
        m = re.search(r":(\d+):\d+: F821 Undefined name `([^`]+)`", line)
        if not m:
            continue
        if m.group(2) in TYPE_ONLY:
            continue
        real.append(line.strip())
    assert not real, "发现非注解类未定义名（会静默失效或崩溃）:\n" + "\n".join(real)
