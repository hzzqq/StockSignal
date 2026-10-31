# -*- coding: utf-8 -*-
"""tests/test_bento_standards.py — Bento 推广标准守卫（G4/G5，ui-ds 设计系统 Phase1 §4.2）。

G4 Bento 模板白名单：pages 中 xc_bento_grid/xc_bento_kpi 的 template= 传参
  必须命中 6 个标准预设（防任意 fr 值泛滥出 68 种布局）。第 5/6 项是
  54_今日决策面板现网存量（Phase3 评审事实#1：Phase1 原案 4 预设不含它们，
  上线即红，故扩为 6；其中 '1.3fr 1fr 1fr 1fr' 在 54 L855 的多行调用里，
  单行 grep 不可见，由本守卫 AST 扫描首次捕获——守卫即文档）。不传
  template= 走 ui_kit 默认自适应预设，视为合法。

G5 自绘卡禁令（两级）：
  1. 废弃/反模式类字面量硬禁：``class="ss-stat"``/``ss-info``/``ss-hero``/
     ``ss-chart``/``xc-sector-card``/``xc-sector-grid``——HTML 构建器已全部
     路由 xc（_stat_tile_html→_xc_card_html 等），pages 零现存量（P0 前实测），
     纯防新增。
  2. 未知类登记制：pages 手写 class= 的 token 必须命中 ``_KNOWN_PAGE_CLASSES``
     登记表（= P0 时点全量清点快照）。新 class 上线前必须：优先改走 ui_kit
     工厂；确需自绘则在此登记（与 Phase2 §4.3 widget key 登记同文化）。
     f-string 内嵌表达式（含 ``{``/``}`` 的 token）跳过。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"

# ── G4：Bento 模板 6 预设（第 5/6 项为 54 页现网存量，Phase3 评审事实 #1）──────
BENTO_TEMPLATE_WHITELIST = {
    "1.6fr 1fr 1fr",                # 1 大 2 小
    "1fr 1fr 1fr 1fr",              # 四等宽
    "1.2fr 1fr 1fr 1fr",            # 54 决策面板现网（回测周期分组 KPI 带，L802）
    "1.3fr 1fr 1fr 1fr",            # 54 决策面板现网（预测记录 KPI 带，L855 多行调用）
    "2fr 1fr",                      # 图表 + 侧栏
    "repeat(auto-fit,minmax(220px,1fr))",  # 默认自适应（ui_kit 签名默认值）
}

_BENTO_FACTORIES = {"xc_bento_grid", "xc_bento_kpi"}


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", t)


def _page_sources():
    for p in sorted(PAGES.rglob("*.py")):
        try:
            yield p, p.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue


def test_bento_templates_within_whitelist():
    """G4：xc_bento_grid/xc_bento_kpi 的 template 实参 ∈ 5 预设（可静态验证）。"""
    offenders = []
    for p, src in _page_sources():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if name not in _BENTO_FACTORIES:
                continue
            for kw in node.keywords:
                if kw.arg != "template":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    if _norm(kw.value.value) not in {_norm(t) for t in BENTO_TEMPLATE_WHITELIST}:
                        offenders.append(
                            f"{p.relative_to(ROOT)}:{node.lineno} template={kw.value.value!r}")
                else:
                    offenders.append(
                        f"{p.relative_to(ROOT)}:{node.lineno} template 非字符串常量（守卫无法验证，"
                        f"请用白名单预设或登记新预设）")
    assert not offenders, (
        "Bento template 超出 5 预设白名单（防布局泛滥；确需新预设请人审后登记）:\n  "
        + "\n  ".join(offenders)
    )


# ── G5-1：废弃/反模式类字面量（零现存量，纯防新增）────────────────────────
_BANNED_CLASS_TOKENS = frozenset({
    "ss-stat", "ss-info", "ss-hero", "ss-chart",
    "xc-sector-card", "xc-sector-grid",
})


def test_pages_no_deprecated_card_literals():
    for p, src in _page_sources():
        toks = {t for m in re.findall(r'class="([^"]+)"', src) for t in m.split()}
        hit = sorted(toks & _BANNED_CLASS_TOKENS)
        assert not hit, f"{p.relative_to(ROOT)} 出现废弃/反模式类字面量 {hit}（应改走 ui_kit 工厂）"


# ── G5-2：未知类登记制（快照 = P0 时点 pages 全量清点）────────────────────
_KNOWN_PAGE_CLASSES = frozenset({
    # 通用/旧组件残留（存量极少，渐进收敛不强删）
    "card", "compare-wrap", "dot", "label", "value",
    # 登录/落地页族（lg-*，与 ui_theme --ss-login-* 配套）
    "lg-ai", "lg-ai-clue", "lg-brand-name", "lg-brand-sub", "lg-breadth",
    "lg-card", "lg-card-h", "lg-card-meta", "lg-desk", "lg-desk-brand",
    "lg-desk-desc", "lg-down", "lg-footer", "lg-form", "lg-gauge",
    "lg-gauge-bar", "lg-gauge-val", "lg-grad", "lg-idx", "lg-idx-chg",
    "lg-idx-name", "lg-idx-val", "lg-logo", "lg-quick", "lg-tag", "lg-title",
    "lg-up",
    # 问答/对比/白名单等页面局部组件
    "qa-badge", "qa-bar", "qa-card", "qa-icon", "qa-name", "qa-row",
    "sf-card", "sf-card-subtitle", "sf-card-title", "sf-metric-card",
    "sf-page-link", "wl-op", "wl-table",
    # 星辰 AI 会话族（53 页，xc-* 局部组件）
    "xc-av", "xc-badge", "xc-banner", "xc-bubble", "xc-cite", "xc-col",
    "xc-copy", "xc-copy-src", "xc-copy-wrap", "xc-flow", "xc-flow-label",
    "xc-flow-stage", "xc-intent", "xc-kv", "xc-kv-grid", "xc-mod-card",
    "xc-mod-h", "xc-mod-reason", "xc-mod-top", "xc-msg", "xc-name",
    "xc-role", "xc-role-tool", "xc-role-user", "xc-sug-label",
    "xc-tool-card", "xc-tool-err", "xc-tool-tbl", "xc-ts", "xc-typing",
    "xc-user", "xc-user-av", "xc-user-bubble", "xc-who",
})

_TOKEN_HAS_EXPR = re.compile(r"[{}]")


def test_pages_no_unknown_markup_classes():
    """G5-2：pages 手写 class token 必须命中登记表（防自绘卡泛滥）。

    新增步骤：① 优先改走 ui_kit 工厂（xc_content_card/xc_kpi_grid/xc_info_banner…）；
    ② 确需自绘 → 本文件 _KNOWN_PAGE_CLASSES 登记（一行）。
    """
    offenders = []
    for p, src in _page_sources():
        for m in re.findall(r'class="([^"]+)"', src):
            for tok in m.split():
                if _TOKEN_HAS_EXPR.search(tok):
                    continue  # f-string 内嵌表达式，静态不可判
                if tok not in _KNOWN_PAGE_CLASSES and tok not in _BANNED_CLASS_TOKENS:
                    offenders.append(f"{p.relative_to(ROOT)}: class {tok!r}")
    assert not offenders, (
        "pages 出现未登记的自绘 class（Phase1 §4.2 G5 / Phase2 登记制）:\n  "
        + "\n  ".join(offenders)
    )
