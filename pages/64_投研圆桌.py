"""
页面 64：投研圆桌 · 大盘主线 + 情绪研判

把 2026-09-11 收盘的投研圆桌交付物（多视角：广度温度官 / 指数结构师 /
主线猎手 / 资金行为师 / 仓位司令 + 逆向视角）在站内呈现，作为左侧导航
「💬 社区与 AI → 投研圆桌」的落地页。

- 默认渲染 Markdown 报告正文（轻量、离线安全）；
- 可选「仪表盘预览」嵌入自包含 HTML 仪表盘（提取 <style> + <body> 内文）；
- 提供 MD / HTML 下载入口。
所有文件读取包 try/except 降级，离线 / 文件缺失均不抛未捕获异常。
"""
import logging
import re
from pathlib import Path

import streamlit as st

from modules.page_utils import render_standard_page

logger = logging.getLogger(__name__)

# 交付物相对仓库根目录解析（pages/64_*.py -> 仓根 = parent.parent）
_ROOT = Path(__file__).resolve().parent.parent
_REPORT_DIR = _ROOT / "deliverables" / "stock-partner" / "2026-09-11"
_MD_PATH = _REPORT_DIR / "大盘主线与情绪研判_投研圆桌.md"
_HTML_PATH = _REPORT_DIR / "大盘主线与情绪研判_投研圆桌.html"

dark = render_standard_page(
    title="投研圆桌 · 大盘主线 + 情绪研判", icon="📋",
    caption="多视角圆桌（广度温度官 / 指数结构师 / 主线猎手 / 资金行为师 / 仓位司令 + 逆向视角），"
            "数据日期 2026-09-11 收盘，数据源 westock-mcp 实时行情。"
            "凡缺维度（宏观 PMI、北向资金）均显式标注，无编造。",
)

# ── 侧栏：内容模式 ──
_mode = st.sidebar.radio(
    "内容模式",
    options=["报告正文 (Markdown)", "仪表盘预览 (HTML)"],
    index=0,
)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as _e:  # noqa: BLE001
        logger.warning("[64] 读取失败 %s: %s", path, _e)
        return None


def _extract_html_fragment(html: str) -> str:
    """抽取 <style> 与 <body> 内文，拼成一个可直接嵌入 Streamlit markdown 的片段。

    避免把整份 <html><head><body> 直接塞进 markdown（会导致嵌套文档结构失效）。
    """
    styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S | re.I))
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.S | re.I)
    body_inner = body_match.group(1) if body_match else html
    return f"<style>{styles}</style>\n{body_inner}"


# ── 主区渲染 ──
try:
    if _mode.startswith("报告正文"):
        md = _read_text(_MD_PATH)
        if md is None:
            st.error("⚠️ 未找到报告正文（MD）。请确认交付物 "
                     "`deliverables/stock-partner/2026-09-11/` 存在。")
        else:
            st.markdown(md, unsafe_allow_html=False)

    else:  # 仪表盘预览 (HTML)
        html = _read_text(_HTML_PATH)
        if html is None:
            st.error("⚠️ 未找到仪表盘 HTML。请确认交付物 "
                     "`deliverables/stock-partner/2026-09-11/` 存在。")
        else:
            try:
                fragment = _extract_html_fragment(html)
                st.markdown(fragment, unsafe_allow_html=True)
            except Exception as _e:  # noqa: BLE001
                logger.warning("[64] HTML 嵌入失败，回退 MD: %s", _e)
                md = _read_text(_MD_PATH)
                if md:
                    st.warning("仪表盘渲染失败，已回退到报告正文。")
                    st.markdown(md, unsafe_allow_html=False)
                else:
                    st.error("仪表盘与正文均不可用。")
except Exception as _e:  # noqa: BLE001
    logger.exception("[64] 渲染异常")
    st.error(f"页面渲染异常：{_e}")

# ── 下载入口（始终可用）──
st.divider()
c1, c2 = st.columns(2)
with c1:
    md = _read_text(_MD_PATH)
    if md is not None:
        st.download_button("⬇️ 下载报告 (Markdown)", md,
                           file_name="大盘主线与情绪研判_投研圆桌.md",
                           mime="text/markdown")
with c2:
    html = _read_text(_HTML_PATH)
    if html is not None:
        st.download_button("⬇️ 下载仪表盘 (HTML)", html,
                           file_name="大盘主线与情绪研判_投研圆桌.html",
                           mime="text/html")
