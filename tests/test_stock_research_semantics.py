# -*- coding: utf-8 -*-
"""守卫：个股研究实现体的方向语义 + KPI 契约（M1 修订版，2026-11-04）。

⚠️ 本仓有两套并行配色语义，禁止一刀切「统一成红涨绿跌」：
  · 报告体 / 个股页价格域：--doc-up 绿涨、--doc-down 红跌（历史参考文档约定），
    modules.colors.RED == "#009e60" 实为绿色；tests/test_colors.py:41-42 硬断言锁死。
  · 交易屏 / 全站 A 股：--ss-up/--ss-down 红涨绿跌，UP_COLOR == "#ff4d4f"。
本守卫只锁「方向文字/形状」与「KPI 显式 delta_dir」，**不反转 --doc-* 色值**，
并反向锁住该例外不被后人误删。彩色 🟢/🔴 是同形圆点，对红绿色觉缺陷退化成逐字
阅读，故方向改用 ▲/▼/— 形状 + 方向词双通道（颜色由 delta_dir 提供）。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "modules" / "stock_research.py"


def _tree():
    return ast.parse(SRC.read_text(encoding="utf-8"))


def _source():
    return SRC.read_text(encoding="utf-8")


def _calls(tree, name):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name]


def _metric_calls(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "metric"]


def _kpi_cards(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            ks = {k.value for k in n.keys
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "label" in ks and "value" in ks:
                yield n


def test_no_colored_dot_signal():
    """强弱信号灯不得退回 🟢/🔴 同形彩色圆点。"""
    s = _source()
    for bad in ("🟢", "🔴"):
        assert bad not in s, f"stock_research.py 仍含 {bad} 彩色圆点（方向应走 ▲/▼/—）"


def test_direction_shape_channel_present():
    """方向词必须与 ▲/▼/— 形状配对，且不得回退到反了的彩色语义。"""
    s = _source()
    for good in ("▲ 强势", "▼ 偏弱", "— 中性", "▲ 整体偏多", "▼ 整体偏空", "— 多空平衡"):
        assert good in s, f"缺少方向形状配对: {good}"
    for bad in ("🟢 强势", "🔴 偏弱", "🟢 整体偏多", "🔴 整体偏空"):
        assert bad not in s, f"回退到语义反转文案: {bad}"


def test_no_metric_or_sf_card_calls():
    tree = _tree()
    assert not _metric_calls(tree), "实现体仍有 st.metric（终态应为 xc_kpi_grid/stat_tile）"
    assert not _calls(tree, "sf_card"), "实现体仍有 sf_card（应迁 xc_section_header）"
    assert not _calls(tree, "sf_metric"), "实现体仍有 sf_metric（已收敛到 xc card 视觉）"


def test_all_kpi_cards_declare_delta_dir():
    """18 张卡 + 2 处瓦片全部显式 delta_dir；且渲染调用真实存在（防空转）。"""
    tree = _tree()
    cards = list(_kpi_cards(tree))
    assert len(cards) >= 18, f"KPI 卡数量异常（{len(cards)}），守卫口径需复核"
    missing = [n.lineno for n in cards
               if "delta_dir" not in {k.value for k in n.keys
                                      if isinstance(k, ast.Constant) and isinstance(k.value, str)}]
    assert not missing, f"第 {missing} 行 KPI 卡缺显式 delta_dir"
    tiles = _calls(tree, "stat_tile")
    assert len(tiles) == 2, f"stat_tile 应为 2 处，实际 {len(tiles)}"
    assert all(any(k.arg == "delta_dir" for k in n.keywords) for n in tiles), \
        "stat_tile 缺显式 delta_dir"
    assert len(_calls(tree, "xc_kpi_grid")) >= 4, "KPI 网格渲染调用缺失"


def test_doc_green_up_exception_preserved():
    """反向锁：报告体「绿涨红跌」历史例外不得被误改成「红涨绿跌」。

    Phase1 视觉成员曾把 20 页 docstring 判为过时错误并提议反转，实为误判：
    该页价格域确实走 --doc-up 绿涨。改文案会让文档与真实渲染相反。
    """
    doc = (ROOT / "pages" / "20_个股分析.py").read_text(encoding="utf-8")
    assert "绿涨红跌" in doc, "20 页 docstring 绿涨红跌例外说明被误删"
    colors = (ROOT / "modules" / "colors.py").read_text(encoding="utf-8")
    assert 'RED = "#009e60"' in colors and 'GREEN = "#dc2626"' in colors, \
        "报告体色值常量被反转（会撞 test_colors.py 硬断言）"
    theme = (ROOT / "modules" / "ui_theme.py").read_text(encoding="utf-8")
    assert "--doc-up:#009e60" in theme and "--doc-down:#dc2626" in theme, \
        "报告体 CSS 令牌被反转"


def test_mutation_semantics_guard_not_vacuous():
    """mutation 自验：本文件的 AST 判定必须能真的检出违规，防「零样本恒真」假绿。"""
    good = ('xc_kpi_grid([{"label": "甲", "value": "1", "delta_dir": "flat"}])\n'
            'stat_tile("乙", "2", delta_dir="flat")\n')
    t = ast.parse(good)
    assert len(list(_kpi_cards(t))) == 1 and len(_calls(t, "stat_tile")) == 1
    bad = ('xc_kpi_grid([{"label": "甲", "value": "1"}])\n'
           'st.metric("乙", "2", delta_color="off")\n')
    t2 = ast.parse(bad)
    c = list(_kpi_cards(t2))
    assert c and "delta_dir" not in {k.value for k in c[0].keys
                                     if isinstance(k, ast.Constant)}, "卡缺 delta_dir 未被检出"
    assert _metric_calls(t2), "st.metric 未被检出——守卫假绿"
