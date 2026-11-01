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
from modules.ui_kit import xc_bento_kpi

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


def _kpi_band() -> None:
    """B 类页五段式 pilot：header → KPI 带。

    本页是静态交付物展示页（2026-09-11 圆桌报告），可上卡的真实数据只有
    报告文本自身的结构化字段——全部用正则从报告 MD 提取，每张卡独立
    try/except：解析失败/文件缺失就跳过该卡，整带无卡则不渲染。
    绝不为凑卡编造或新拉不可靠数据（诚实红线）。
    """
    md = _read_text(_MD_PATH)
    if md is None:
        return  # 报告正文缺失时页面主区已有 error 提示，KPI 带诚实留空

    cards = []

    # 卡 1：数据日期（报告头部「数据日期：**…**」字段）
    try:
        m = re.search(r"数据日期：\*\*([^*]+)\*\*", md)
        if m:
            cards.append({
                "label": "数据日期",
                "value": m.group(1).strip(),
                "meta": "westock-mcp 实时行情快照（收盘）",
            })
    # ui_audit_exempt: except-pass 卡1 正则提取失败=报告缺字段，按设计跳过该卡（诚实留空，非真实错误）
    except Exception:  # noqa: BLE001
        pass

    # 卡 2：市场涨占比（报告市场快照表「涨占比 **11%**」）
    try:
        m = re.search(r"涨占比 \*\*(\d+)%\*\*", md)
        if m:
            cards.append({
                "label": "市场涨占比",
                "value": f"{m.group(1)}%",
                "meta": "广度温度官口径（报告快照值）",
            })
    # ui_audit_exempt: except-pass 卡2 正则提取失败=报告缺字段，按设计跳过该卡（诚实留空，非真实错误）
    except Exception:  # noqa: BLE001
        pass

    # 卡 3：参与视角数（报告结构：广度温度官/指数结构师/主线猎手/资金行为师/仓位司令 + 逆向视角）
    try:
        n_views = len(re.findall(r"^### [①②③④⑤]", md, flags=re.M)) + (
            1 if "逆向视角" in md else 0
        )
        if n_views:
            cards.append({
                "label": "参与视角",
                "value": str(n_views),
                "meta": "广度 / 结构 / 主线 / 资金 / 仓位 / 逆向",
            })
    # ui_audit_exempt: except-pass 卡3 正则提取失败=报告结构缺视角标题，按设计跳过该卡（诚实留空，非真实错误）
    except Exception:  # noqa: BLE001
        pass

    # 卡 4：显式缺席维度（报告诚实声明：宏观 PMI、北向资金——凡缺均标注）
    try:
        missing = [name for name in ("宏观 PMI", "北向资金") if name in md]
        if missing:
            cards.append({
                "label": "显式缺席维度",
                "value": str(len(missing)),
                "meta": "、".join(missing) + "（凡缺均显式标注）",
            })
    # ui_audit_exempt: except-pass 卡4 正则提取失败=报告缺缺席声明，按设计跳过该卡（诚实留空，非真实错误）
    except Exception:  # noqa: BLE001
        pass

    if cards:
        xc_bento_kpi(cards, template="1fr 1fr 1fr 1fr")


def _extract_html_fragment(html: str) -> str:
    """抽取 <style> 与 <body> 内文，拼成一个可直接嵌入 Streamlit markdown 的片段。

    避免把整份 <html><head><body> 直接塞进 markdown（会导致嵌套文档结构失效）。
    """
    styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S | re.I))
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.S | re.I)
    body_inner = body_match.group(1) if body_match else html
    return f"<style>{styles}</style>\n{body_inner}"


# ── 主区渲染 ──
_kpi_band()  # B 类页五段式 pilot：KPI 带置于 header 之后、主视区之前

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
                # ui_audit_exempt: unsafe-allow-html 静态交付物 HTML（deliverables/ 本地报告文件，非用户输入）原样嵌入
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

# ── 方法学与来源注脚（B 类页五段式 pilot：收尾一段）──
st.markdown("---")
st.caption(
    "口径与来源：本页为 2026-09-11 收盘投研圆桌交付物的静态站内展示（MD / HTML 双格式，"
    "原文见 deliverables/stock-partner/2026-09-11/）。数据源=westock-mcp 实时行情快照"
    "（涨跌分布 / 指数快照 / 行业资金）；凡缺维度（宏观 PMI、北向资金）在报告内显式标注。"
    "快照数据非实时行情，结论为当日研判存档，非投资建议。"
)
