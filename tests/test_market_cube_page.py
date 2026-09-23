# -*- coding: utf-8 -*-
"""tests/test_market_cube_page.py — 17_市场魔方 整页替换守卫（T-147 批6）。

spec：``.workbuddy/specs/t146_market_cube_contract.md``（微信小程序「市场魔方助手」全球 tab 复刻）。

锁四条不变量：
1. 24 个全球产业卡清单完整在页面源码中（防漏卡）；
2. unavailable 诚实降级语义存在（数据缺失显性标注，绝不编造——铁律五，防回退）；
3. 「立体魔方」遗留实现（3D 散点魔方）已整体移除（老板 2026-09-19：原来的就不用了）；
4. 页面骨架与视觉纪律：render_standard_page 保留、零原生 st.error/warning/info、零硬编码浅色底。
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "pages" / "17_市场魔方.py"

INDUSTRIES = [
    "AI算力", "CPO", "半导体", "存储", "数据中心", "云计算",
    "商业航天", "卫星", "机器人", "自动驾驶", "核电", "电网",
    "军工", "新能源", "光伏", "锂电池", "石油", "天然气",
    "铜", "黄金", "银行金融", "生物医药", "消费", "稀土",
]

_LEGACY_3D = ("_cube_fig", "_load_cube", "_bento", "_composite", "Scatter3d")


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def _tree():
    return ast.parse(_src())


def test_market_cube_industries_complete():
    """24 产业卡必须齐全（照小程序「全球产业数据」逐卡复刻）。"""
    src = _src()
    missing = [n for n in INDUSTRIES if n not in src]
    assert not missing, f"全球产业数据缺卡: {missing}"


def test_market_cube_honest_unavailable_semantics():
    """诚实降级：unavailable 语义必须存在（数据源缺失显性标注，不回退编造）。"""
    src = _src()
    assert src.count('status') >= 1 and "unavailable" in src, (
        "市场魔方页缺少 unavailable 诚实降级语义（铁律五：取数不足必须显性标注）"
    )


def test_market_cube_legacy_3d_removed():
    """立体魔方遗留实现必须整体移除（老板 2026-09-19 指示「原来的就不用了」）。"""
    src = _src()
    leftover = [k for k in _LEGACY_3D if k in src]
    assert not leftover, f"立体魔方遗留代码未清除: {leftover}"


def test_market_cube_skeleton_and_hygiene():
    """页面骨架保留 + 视觉纪律（xc 盒、无浅色硬编码底）。"""
    src = _src()
    assert "render_standard_page" in src, "页面必须保留 render_standard_page 统一骨架"
    tree = _tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("error", "warning", "info", "success") \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "st":
            raise AssertionError(f"L{node.lineno}: 原生 st.{node.func.attr} 应走 ui_kit xc 盒")
    for hexbg in ("#fde8e6", "#e8f9ef"):
        assert hexbg not in src.lower(), f"硬编码浅色底 {hexbg} 禁止复活"


def test_market_cube_four_tabs_implemented():
    """批7：日韩/有色/AI/设置 四 tab 必须实装（占位符「素材待补」应移除）。"""
    src = _src()
    assert "素材待补" not in src, "四 tab 已按截图实装，占位符应移除"
    required = ("KOSPI", "KOSDAQ", "日经225", "越南胡志明", "孟买SENSEX",   # 日韩
                "LME铜", "LME铝", "LME锌", "LME镍", "LME锡",               # 有色
                "DRAM", "光模块", "算力租赁", "人民币/日元",                # AI/汇率
                "免责声明")                                                # 设置
    missing = [k for k in required if k not in src]
    assert not missing, f"四 tab 内容缺失: {missing}"


def test_market_cube_market_semantics_tokens():
    """涨跌语义必须走 ui_kit token/A股语义（红涨绿跌 + ▲▼ 双编码组件，不硬编码散色）。"""
    src = _src()
    assert ("UP_COLOR" in src or "delta_dir" in src or "ss-up" in src), (
        "市场魔方页涨跌着色必须走 colors.UP_COLOR / xc 卡 delta_dir / --ss-up token（红涨绿跌单源）"
    )
