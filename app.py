"""
StockSignal 主入口
A股事件驱动投资分析平台
"""

import streamlit as st

st.set_page_config(
    page_title="StockSignal · A股事件驱动投资分析平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 StockSignal · A股事件驱动投资分析平台")
st.markdown("---")

# 侧边栏
with st.sidebar:
    st.header("导航")
    st.markdown("""
    **功能页面：**
    - 📈 行情看板 — K线、均线、成交量
    - 🔔 事件追踪 — 信号评分、事件时间轴
    - ⚙️ 策略回测 — 事件驱动 / 均线交叉
    - 💰 仓位管理 — 持仓盈亏、Excel导出
    """)

    st.markdown("---")
    st.caption("软件工程实训课程设计")
    st.caption("作者：hzz")

# 首页概览
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="行情看板", value="📈", help="交互式K线、行业热力图")
with col2:
    st.metric(label="事件追踪", value="🔔", help="三类信号综合评分")
with col3:
    st.metric(label="策略回测", value="⚙️", help="收益曲线、夏普比率")
with col4:
    st.metric(label="仓位管理", value="💰", help="盈亏统计、Excel导出")

st.markdown("---")

st.header("项目简介")
st.markdown("""
StockSignal 是一款面向个人投资者的 **A股事件驱动分析工具**，通过整合三类核心催化信号：

| 类型 | 说明 | 示例 |
|------|------|------|
| **产业事件** | 政策发布、行业并购、产能变化 | 光伏装机补贴、半导体设备禁令 |
| **价格信号** | 大宗商品、上游原材料价格变动 | MLCC 涨价、煤炭港口价格 |
| **宏观数据** | PMI、CPI、社融等关键宏观指标 | PMI 超预期 → 顺周期主线 |

帮助用户**快速识别行情主线**、**可视化行业轮动**、**回测事件驱动策略**。
""")

st.markdown("---")
st.info("👈 请在左侧侧边栏选择功能页面开始使用，或在顶部导航栏选择对应页面。")
