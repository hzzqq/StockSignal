"""集中配色常量（单一来源，避免跨模块重复定义导致配色漂移）。

本模块零依赖（不 import streamlit / plotly / 任何业务模块），
可被前端页面、可视化模块与后端任务安全复用。

两组语义不同，请勿混淆：
1. RED / GREEN / AMBER —— 个股分析页「参考文档」约定为**绿涨红跌**
   （RED 实际为绿色、GREEN 实际为红色），名称保留历史语义，仅作固定色值。
2. UP_COLOR / DOWN_COLOR / HOLD_COLOR —— A 股默认**红涨绿跌**。
   想切回「绿涨红跌」：把 UP_COLOR / DOWN_COLOR 对调即可。
"""

# ---- 参考文档约定：绿涨红跌（个股分析页使用，名称保留历史语义）----
RED = "#009e60"      # 涨 / 利好 / 买入（文档绿）
GREEN = "#dc2626"    # 跌 / 利空 / 卖出（文档红）
AMBER = "#d97706"    # 中性 / 持有

# ---- A 股默认：红涨绿跌 ----
UP_COLOR = "#ff4d4f"    # 涨 · 红
DOWN_COLOR = "#00d486"  # 跌 · 绿
HOLD_COLOR = "#ffa502"  # 持有 / 中性


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """把 #rrggbb / #rgb 转成 rgba(r,g,b,a)，供 Plotly fillcolor 使用。

    统一入口：避免各模块手写 ``color + "22"`` 生成 8 位 hex
    （Plotly scatter 的 fillcolor 拒绝 8 位 hex，曾导致市场情绪页 9 个
    卡片全部 ValueError 崩溃）。任何需要半透明填充的地方都用本函数。
    """
    if not hex_color:
        return f"rgba(0,0,0,{alpha})"
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except (ValueError, IndexError):
        # 非法 hex（如 "not-a-color" / 长度不足）：安全兜底为透明黑，避免调用点 ValueError 崩溃
        return f"rgba(0,0,0,{alpha})"
    return f"rgba({r},{g},{b},{alpha})"


# 兼容旧调用点（部分模块曾用下划线前缀命名）
_hex_to_rgba = hex_to_rgba
