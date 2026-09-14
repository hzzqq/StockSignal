"""tests/test_public_numbers_consistency.py
==========================================
公开物料「规模数字」一致性守卫（2026-09-14）。

背景（本轮真实缺陷）：
    一次核对发现对外宣称的数字已大面积陈旧 **且互相矛盾**——

    | 位置 | 曾写 | 真实值 |
    |---|---|---|
    | README「功能页面」 | 41（同一文件另一处还写 **38 页**） | 55 |
    | README 测试文件数 | 248 | 287（tests/ 274 + backend/tests 13） |
    | README / promo ×2 「自动化测试」 | 2648 | 2976 |
    | `scripts/gen_portfolio_page.py` meta 描述 | 41 页 / **2608** 个测试 | 55 / 2976 |
    | 同上 · 正文导语 | 41 个功能页面 / 76 个端点 | 55 / **75** |
    | 同上 · 架构图 | 77 业务模块 | 92 |
    | 同上 · 广度图注 | 「15 年全市场广度历史（4094 交易日）」 | 4785 交易日（2007–2026） |

    最刺眼的是生成器**自己**声称「数字必须是真的」，却在同一文件里同时写死
    "2608" 与 "2,648" 两个互相矛盾的测试数 —— 典型的「改一处漏一处」。

    另外查实两个**独立**缺陷：
    ① 端点计数把 `backend/tests/test_security.py` 的测试专用路由 `/api/_test_boom`
       也算了进去 → 对外多报 1 个（76）；排除后 75，与 Flask `url_map` 完全一致。
    ② 作品集页与论文第 6.6 节都把 `thesis/ch6_eval/fig_history_trend.png` 说成
       「全市场广度历史」，而该文件实际由 `thesis/eval_ch6.py` 写成
       「评估数据累积趋势（每次运行 +1）」——**图注与图片完全不符**。
       仓库里此前根本没有生成广度历史图的脚本，现由
       `scripts/gen_breadth_history_fig.py` 从真实 CSV 产出
       `docs/assets/fig_breadth_history.png` 补上。

    既有的 `test_screenshot_no_fabrication.py` 只守住了 README 的**页面数**
    与测试数的**跨文档一致性**，管不住：①同一文档内的局部漏改（38 页）；
    ②生成器模板里的硬编码；③改页面数忘了改推广物料；④图注与图片不符。

本测试补五道闸门：
    A. 所有公开物料（含生成产物 docs/index.html）声明的**页面数**必须等于
       `pages/` 下真实页面数，且**互相一致**；
    B. 作品集生成器的 HTML 模板里**不得硬编码**任何规模数字
       （页数/端点数/测试数/模块数/年数/交易日数），一律走 `@占位符@`；
    C. 生成器 `render()` 必须把所有 `@占位符@` 替换干净 —— 防止
       「新增了占位符但忘了注册」，那会让页面上直接露出 `@FOO@` 字面量；
    D. 生成器的**端点计数**必须排除 backend/tests，并与独立复算结果一致；
    E. 广度历史图必须真实存在、被作品集页引用，且不得再引用那个「名不副实」的
       `fig_history_trend.png`（该文件是评估累积趋势图，不是广度图）。
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 需要保持一致的公开物料（docs/index.html 为生成产物，一并核对）
PUBLIC_DOCS = [
    "README.md",
    "docs/promo-final.md",
    "docs/promo-template.md",
    "docs/index.html",
]

GEN = os.path.join(ROOT, "scripts", "gen_portfolio_page.py")
BREADTH_GEN = os.path.join(ROOT, "scripts", "gen_breadth_history_fig.py")
BREADTH_FIG = os.path.join(ROOT, "docs", "assets", "fig_breadth_history.png")


def _src(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
        return f.read()


# ── A. 页面数：既真实又互相一致 ──────────────────────────────────────

# 只认「数字 + 页/页面」的规模声明，避免误伤「时间页」「翻页」等普通词。
_PAGE_PATTERNS = (
    r"(\d+)\s*个功能页面",
    r"(\d+)\s*个页面",
    r"(\d+)\s*页面",
    r"(\d+)\s*页",
)


def _actual_pages() -> int:
    return len([p for p in os.listdir(os.path.join(ROOT, "pages"))
                if p.endswith(".py") and not p.startswith("_")])


def _page_claims(text: str) -> set[int]:
    out: set[int] = set()
    for pat in _PAGE_PATTERNS:
        for m in re.findall(pat, text):
            out.add(int(m))
    return out


def test_public_docs_page_count_is_true_and_consistent():
    """所有公开物料的页面数都得等于真实页面数 —— 抓「改一处漏一处」。"""
    actual = _actual_pages()
    bad: dict[str, list[int]] = {}
    for rel in PUBLIC_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        claims = _page_claims(_src(rel))
        stale = sorted(v for v in claims if v != actual)
        if stale:
            bad[rel] = stale
    assert not bad, (
        f"公开物料的页面数与真实值（{actual}）不一致：{bad}；"
        f"历史缺陷：README 一处写 41、另一处写 38，推广物料还停在 41"
    )


def test_readme_page_count_matches_actual_pages():
    """保留既有断言的显式版本：README 的「N 个功能页面」必须等于真实页面数。"""
    text = _src("README.md")
    m = re.search(r"\*\*(\d+) 个功能页面\*\*", text)
    assert m, "README 未声明功能页面数"
    assert int(m.group(1)) == _actual_pages()


# ── B. 生成器模板不得硬编码规模数字 ─────────────────────────────────

# 模板里出现这些「数字 + 规模词」即视为硬编码违规（必须改写成 @占位符@）。
_BANNED_IN_TEMPLATE = (
    r"\d+\s*个?功能页面",
    r"\d+\s*个?页面",
    r"\d+\s*业务模块",
    r"\d+\s*(?:个)?(?:后端\s*)?REST\s*端点",
    r"\d+\s*(?:个)?自动化测试",
    r"\d+\s*个测试文件",
    r"\d+\s*项测试",
    r"\d+\s*个测试用例",
    r"\d+\s*(?:个)?交易日",   # 曾写死「4094 交易日」
    r"\d+\s*年",              # 曾写死「15 年」
)


def _template_strings() -> dict[str, str]:
    """取出生成器里 HTML / CSS 两个模块级字符串常量（模板正文）。"""
    with open(GEN, encoding="utf-8", errors="replace") as f:
        tree = ast.parse(f.read())
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            name = getattr(node.targets[0], "id", "")
            if name in ("HTML", "CSS"):
                out[name] = node.value.value
    assert out, "未取到生成器的 HTML/CSS 模板，守卫失效"
    return out


def test_portfolio_template_has_no_hardcoded_scale_numbers():
    """模板里不得写死规模数字 —— 必须走 @占位符@（本轮修掉 41/2608/76/77/4094/15 年）。"""
    offenders: list[str] = []
    for name, body in _template_strings().items():
        for pat in _BANNED_IN_TEMPLATE:
            for hit in re.findall(pat, body):
                offenders.append(f"{name}: {hit!r}")
    assert not offenders, (
        "生成器模板硬编码了规模数字，会随代码迭代静默过期：\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\n请改用 @PAGES@/@ROUTES@/@TESTS@/@MODULES@/@BREADTH_SPAN@ 等占位符"
    )


def test_portfolio_template_uses_placeholders_for_scale():
    """正向断言：关键占位符确实出现在模板里（防止有人「一删了之」）。"""
    html = _template_strings().get("HTML", "")
    for ph in ("@PAGES@", "@ROUTES@", "@TESTS@", "@MODULES@", "@TEST_FILES@",
               "@BREADTH_SPAN@", "@BREADTH@", "@BT_DAYS@"):
        assert ph in html, f"模板缺少占位符 {ph}"


# ── C. render() 必须把占位符替换干净 ────────────────────────────────

def _load_generator():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_gen_portfolio", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FAKE_STATS = {
    "pages": 55, "modules": 92, "routes": 75, "py_files": 577,
    "src_loc": 69022, "test_loc": 37590, "test_files": 288, "tests": 2986,
    "tests_exact": True, "guards": 33, "commits": 652, "days": 90,
    "first_day": "2026-01-01", "last_day": "2026-09-14",
    "breadth_days": 4785, "breadth_span": "2007\u20132026", "stocks": 5548,
    "bt": {"scored": 4092, "call": 3507, "hit": 1722, "acc": 49.1},
}


def test_render_replaces_every_placeholder():
    """render() 输出不得残留任何 @XXX@ 字面量（防「加了占位符忘了注册」）。"""
    mod = _load_generator()
    html = mod.render(dict(_FAKE_STATS))
    leftover = sorted(set(re.findall(r"@[A-Z_]{2,}@", html)))
    assert not leftover, (
        f"render() 输出残留未替换占位符 {leftover}——"
        f"新增占位符后必须同步登记进 render() 的 repl 字典"
    )


def test_render_injects_real_stats():
    """注入的数字确实落到页面上（防空渲染/静默吞掉）。"""
    mod = _load_generator()
    html = mod.render(dict(_FAKE_STATS))
    assert "55 个功能页面" in html, "页数未注入"
    assert "2,986" in html, "测试数未注入（应为千分位格式）"
    assert "92 业务模块" in html, "模块数未注入"


def test_render_injects_derived_breadth_and_backtest_labels():
    """广度区间/交易日数与回测三件套必须由数据推导注入（不得再写死）。"""
    mod = _load_generator()
    html = mod.render(dict(_FAKE_STATS))
    assert "2007\u20132026" in html, "广度区间标签未注入"
    assert "4,785" in html, "广度交易日数未注入"
    assert "4,092" in html, "可评分交易日数未注入"
    assert "@BREADTH_SPAN@" not in html and "@BT_DAYS@" not in html
    # 旧硬编码不得复活
    assert "4094" not in html and "15 年" not in html


# ── D. 端点计数必须排除 backend/tests ──────────────────────────────

_ROUTE_PAT = re.compile(r"@[A-Za-z_]+\.(route|get|post|put|delete|patch)\(")


def _route_decorator_count(include_tests: bool) -> int:
    """独立复算路由装饰器数（与生成器实现分离，避免同源自证）。"""
    n = 0
    backend = os.path.join(ROOT, "backend")
    for dirpath, _dirs, files in os.walk(backend):
        rel_parts = os.path.relpath(dirpath, ROOT).split(os.sep)
        if not include_tests and "tests" in rel_parts:
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8", errors="ignore") as f:
                    n += len(_ROUTE_PAT.findall(f.read()))
            except OSError:
                continue
    return n


def test_route_count_excludes_test_only_routes():
    """回归：端点计数必须排除 backend/tests 下的测试专用路由。

    曾把 `backend/tests/test_security.py` 的 `/api/_test_boom` 也算进去 → 多报 1 个（76）。
    真实生产端点 = 75，与 Flask `app.url_map`（非 static）逐条核对一致。
    """
    raw = _route_decorator_count(include_tests=True)
    prod = _route_decorator_count(include_tests=False)
    assert prod > 0, "未扫到任何路由装饰器，守卫失效"
    assert raw > prod, (
        "backend/tests 下应存在测试专用路由装饰器（本守卫据此防回归）；"
        "若测试路由已被移除，请同步复核本守卫的必要性"
    )
    actual = _load_generator()._count_routes()
    assert actual == prod, (
        f"生成器端点数 {actual} != 排除 tests 后的真实生产端点数 {prod}；"
        f"（未排除 tests 时会得到 {raw}）"
    )


# ── E. 广度历史图必须真实存在且被正确引用 ──────────────────────────

def test_breadth_figure_exists_and_is_not_a_stub():
    """广度历史图必须真实存在且不像空图/占位图。"""
    assert os.path.exists(BREADTH_GEN), "缺少广度图生成脚本 scripts/gen_breadth_history_fig.py"
    assert os.path.exists(BREADTH_FIG), (
        "缺少 docs/assets/fig_breadth_history.png（跑 scripts/gen_breadth_history_fig.py 生成）"
    )
    assert os.path.getsize(BREADTH_FIG) > 20_000, "广度历史图疑似空图/占位图"


def test_portfolio_no_longer_cites_mislabelled_eval_chart():
    """作品集页不得再引用 fig_history_trend.png（该文件实为「评估数据累积趋势」）。"""
    gen = _src("scripts/gen_portfolio_page.py")
    assert '"thesis/ch6_eval/fig_history_trend.png"' not in gen, (
        "CHARTS 又在引用 fig_history_trend.png —— 该文件由 thesis/eval_ch6.py 写成"
        "「评估数据累积趋势（每次运行 +1）」，不是全市场广度历史图"
    )
    assert "fig_breadth_history.png" in gen, "作品集页未引用真·广度历史图"
