"""T-367 星辰AI研究卡守卫：研究流程勾选条 + 2列模块网格 + 每卡复制。

- 顶部「研究流程」三阶段（数据调研→多维度论证→结论裁定）按真实 steps/answer 勾选；
- 每个分析步骤渲染为 2 列网格轻量卡（图标/工具名/结论/数据时点），每卡带📋复制；
- 引用溯源保留。
"""
import pathlib

PAGE = pathlib.Path(__file__).resolve().parents[1] / "pages" / "53_星辰AI.py"
SRC = PAGE.read_text(encoding="utf-8")


def test_flow_checkmarks_present():
    # 流程勾选条结构与三阶段文案
    assert "xc-flow" in SRC
    assert "xc-flow-label" in SRC
    assert '"数据调研"' in SRC
    assert '"多维度论证"' in SRC
    assert '"结论裁定"' in SRC
    # 勾选态按真实信号：有步骤→调研完成；步骤>=2→论证完成；有效回答→裁定完成
    assert "_stage_done" in SRC
    assert "_n_steps >= 2" in SRC


def test_module_grid_and_per_card_copy():
    # 2 列网格模块卡
    assert "xc-mod-h" in SRC
    assert "xc-mod-card" in SRC
    assert "st.columns(2)" in SRC
    # 每卡可复制（复用 xc_copy_block）
    assert "xc_copy_block(_copy_txt)" in SRC
    # 样式定义存在
    assert ".xc-flow-stage" in SRC
    assert ".xc-mod-reason" in SRC


def test_citations_preserved():
    # 引用溯源保留（参考图#3 的「引用」操作）
    assert "引用溯源" in SRC
