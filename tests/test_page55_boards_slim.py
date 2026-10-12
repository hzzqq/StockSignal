"""
tests/test_page55_boards_slim.py
================================
T-269 守卫：55_P1量化信号页看多/看空榜——折叠（ss_fold_useful，标签带 Top1 摘要）
+ 名称列（本地股票库零网络映射，P1 代码尾 6 位归一）。T-259 同款范式防回潮。

mutation：去折叠 / 删名称列 → 对应用例变红。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "55_P1量化信号.py"


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_boards_folded_with_summary():
    """契约1：双榜收进 ss_fold_useful，标签带 Top1 摘要（折叠后仍有信息量）。"""
    src = _src()
    assert 'ss_fold_useful("📈 看多榜"' in src, "看多榜未折叠"
    assert 'ss_fold_useful("📉 看空榜"' in src, "看空榜未折叠"
    assert "_top1_summary" in src, "Top1 摘要函数缺失"
    # fold 在对应 _board_html 渲染之前（包裹语义）
    i_fold = src.index('ss_fold_useful("📈 看多榜"')
    i_render = src.index("_board_html(long_rows", i_fold)
    assert i_fold < i_render


def test_board_html_has_name_column():
    """契约2：榜单表格必须含名称列 + 尾 6 位归一映射（零网络）。"""
    src = _src()
    assert "<th>名称</th>" in src, "名称列表头缺失"
    assert "_code_to_name" in src, "本地股票库名称映射缺失"
    assert 'str(sym)[-6:].zfill(6)' in src, "P1 代码尾 6 位归一缺失"


def test_page_ast_valid():
    """页面可被 AST 解析（防静默语法损坏）。"""
    ast.parse(_src())
