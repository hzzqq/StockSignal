"""pages/86_网页作品集.py — 网页渲染作品集（MVP）。

对标 ai-demo 的「AI 生成交互式前端作品合集」模式：
  - 作品静态文件放 ``webapps/<作品目录>/``（收录规则见 webapps/README.md，追加式）；
  - 由本地 Flask 静态托管：``GET {API_BASE}/webapps/<dir>/<file>``；
  - 本页扫描 ``webapps/*/meta.json`` 生成 Bento 卡片网格。

诚实红线（本页三条，均写死不得删）：
  1. 扫描不到任何作品 / Flask 未启动 → xc_info_banner 诚实降级提示，
     **绝不渲染假 iframe、假数据**。
  2. 页面显著标注：作品为「本地静态交互页面，数据为示意/演示，非实时行情」。
  3. iframe 嵌入 vs st.markdown 的本质区别（页内注释说明）：
     st.markdown 会剥掉 <script>（安全沙箱），而 st.components.v1.html 的
     iframe 允许完整 JS 运行——作品依赖 canvas 动画/拖拽交互，必须走后者。
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from modules.page_utils import render_standard_page
from modules.session import API_BASE
from modules.ui_kit import xc_content_card, xc_info_banner

# webapps 目录：基于仓库根解析的绝对路径（与 backend/app.py 的静态路由同源）
WEBAPPS_DIR = Path(__file__).resolve().parent.parent / "webapps"


def _scan_webapps() -> list[dict]:
    """扫描 webapps/*/meta.json，返回合法作品元数据列表（按目录名排序）。

    防御性约束：meta.json 由仓库内文件提供，但仍按不可信输入处理——
    entry 必须是相对路径且不含 ``..``（防索引页拼出穿越 URL）；字段缺失/
    JSON 损坏的作品直接跳过（不渲染半残卡片）。
    """
    works: list[dict] = []
    if not WEBAPPS_DIR.is_dir():
        return works
    for meta_path in sorted(WEBAPPS_DIR.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 损坏的 meta 跳过，不让单个坏文件炸整页
            continue
        if not isinstance(meta, dict):
            continue
        title, desc, entry = meta.get("title"), meta.get("desc"), meta.get("entry")
        if not (isinstance(title, str) and title.strip()):
            continue
        if not (isinstance(entry, str) and entry.strip()):
            continue
        if ".." in entry or entry.startswith(("/", "\\")):  # 防穿越 URL
            continue
        works.append(
            {
                "dir": meta_path.parent.name,
                "title": title.strip(),
                "desc": str(desc or "").strip(),
                "entry": entry.strip(),
                "version": str(meta.get("version", "—")),
                "added": str(meta.get("added", "—")),
            }
        )
    return works


def _work_url(work: dict) -> str:
    """作品在 Flask 静态托管下的 URL（API_BASE 单源复用 modules.session，不硬编码端口）。"""
    return f"{API_BASE}/webapps/{work['dir']}/{work['entry']}"


def _dir_label(work: dict) -> str:
    """卡片上展示的目录标注（相对仓库根）。"""
    return f"webapps/{work['dir']}"


def _render_work_card(work: dict, col) -> None:
    """在给定列里渲染一张作品卡：信息 + 两个动作（新窗口打开 / 页内嵌入）。"""
    url = _work_url(work)
    with col:
        xc_content_card(
            title=f"{work['title']}（v{work['version']}）",
            body=work["desc"] or "（无简介）",
            icon="🎨",
        )
        st.caption(f"目录 `{_dir_label(work)}` · 收录 {work['added']}")
        # 动作 ①：新窗口打开 —— 直达 Flask 静态托管地址，体验最完整
        # （width="stretch" 是项目守卫要求的等价写法，禁用废弃的 use_container_width）
        st.link_button("🚀 新窗口打开", url, width="stretch")
        # 动作 ②：页内嵌入开关 —— 勾选后展开 iframe
        embed = st.toggle("🔍 页内嵌入", key=f"embed_{work['dir']}")
        if embed:
            # ── 本质区别说明（诚实红线 #3）──────────────────────────────
            # st.markdown 渲染 HTML 时会剥掉 <script>（Streamlit 安全沙箱），
            # canvas 动画/拖拽等交互全部失效；st.components.v1.html 是真正的
            # iframe，允许完整 JS 运行，故作品嵌入必须走它。
            iframe_html = (
                f'<iframe src="{url}" '
                'style="width:100%;height:720px;border:0;border-radius:12px"></iframe>'
            )
            components.html(iframe_html, height=740)


def main() -> None:
    render_standard_page(title="网页作品集", icon="🎨", layout="wide")

    # 诚实红线 #2：显著标注数据性质
    xc_info_banner(
        "以下作品均为本地静态交互页面，数据为示意/演示，非实时行情，不构成投资建议。",
        kind="warning",
        icon="⚠️",
    )

    works = _scan_webapps()

    # 诚实红线 #1：扫不到任何作品 → 诚实降级，绝不渲染假 iframe/假数据
    if not works:
        xc_info_banner(
            f"暂无已收录作品（未在 {WEBAPPS_DIR} 下扫到任何 meta.json）。"
            f"作品托管在本地 Flask（默认 {API_BASE}），请先启动后端，"
            "并确认 webapps/<作品目录>/meta.json 存在（收录规则见 webapps/README.md）。",
            kind="danger",
            icon="🛑",
        )
        return

    st.markdown(f"**已收录作品（{len(works)} 个）** · 收录规则：追加式，新作品只能加在末位")

    # Bento 风格卡片网格：两列排布；最后一个落单时保持左列对齐
    for i in range(0, len(works), 2):
        row = works[i : i + 2]
        cols = st.columns(2)
        for col, work in zip(cols, row):
            _render_work_card(work, col)


main()
