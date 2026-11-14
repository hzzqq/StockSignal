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

本测试补七道闸门：
    A. 所有公开物料（含生成产物 docs/index.html）声明的**页面数**必须等于
       `pages/` 下真实页面数，且**互相一致**；
    B. 作品集生成器的 HTML 模板里**不得硬编码**任何规模数字
       （页数/端点数/测试数/模块数/年数/交易日数），一律走 `@占位符@`；
    C. 生成器 `render()` 必须把所有 `@占位符@` 替换干净 —— 防止
       「新增了占位符但忘了注册」，那会让页面上直接露出 `@FOO@` 字面量；
    D. 生成器的**端点计数**必须排除 backend/tests，并与独立复算结果一致；
    E. 广度历史图必须真实存在、被作品集页引用，且不得再引用那个「名不副实」的
       `fig_history_trend.png`（该文件是评估累积趋势图，不是广度图）；
    F. 生成物 docs/index.html 的端点/页面/Python 文件数 == 生成器实测；
    G. 所有公开物料的**测试数 / 测试文件数** == 生成器实测（pytest collect）、
       用例数与文件数口径同源、且不再写死天生会漂移的 Git 提交次数。
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
    # 发布物料（对外真正发出的文案）——曾不在清单内，数字长期停在 38 页（2026-09-15 修复）
    "docs/publish-kit/01-掘金-juejin.md",
    "docs/publish-kit/02-知乎-zhihu.md",
    "docs/publish-kit/03-V2EX.md",
    "docs/publish-kit/04-朋友圈.md",
]

GEN = os.path.join(ROOT, "scripts", "gen_portfolio_page.py")
BREADTH_GEN = os.path.join(ROOT, "scripts", "gen_breadth_history_fig.py")
BREADTH_FIG = os.path.join(ROOT, "docs", "assets", "fig_breadth_history.png")


def _src(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
        return f.read()


def _body(rel: str) -> str:
    """去掉 HTML 注释后的正文：注释里写旧数字不能当「已声明」喂饱守卫。"""
    return re.sub(r"<!--.*?-->", "", _src(rel), flags=re.S)


# 明确豁免：该物料是短贴，本来就不声明规模数字。新增物料若同样无声明，
# 必须先在此登记理由，否则守卫会报「正文没有页面数声明」。
_NO_PAGE_CLAIM_OK = {"docs/publish-kit/02-知乎-zhihu.md"}


# ── A. 页面数：既真实又互相一致 ──────────────────────────────────────

# 只认「数字 + 页/页面」的规模声明，避免误伤「时间页」「翻页」等普通词。
# ⚠️ 必须包含「个功能页」（无「面」）——发布物料里长期写的是「63 个功能页」，
#    漏掉该变体会让物料数字完全逃逸守卫（真实缺陷 2026-09-15 发现）。
_PAGE_PATTERNS = (
    r"(\d+)\s*个功能页面",
    r"(\d+)\s*个功能页(?!面)",
    r"(\d+)\s*个页面",
    r"(\d+)\s*页面",
    r"(\d+)\s*页(?!面)",
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
    """所有公开物料的页面数都得等于真实页面数 —— 抓「改一处漏一处」。

    反自静音（2026-11-09）：文件缺失曾 continue 静默跳过；页面数声明只看全文
    子串（注释里的旧数字也算）。现改为缺失即红、剥注释后正文必须声明。
    """
    actual = _actual_pages()
    missing = [rel for rel in PUBLIC_DOCS if not os.path.exists(os.path.join(ROOT, rel))]
    assert not missing, f"公开物料缺失，守卫不得静默跳过：{missing}"
    bad: dict[str, list[int]] = {}
    for rel in PUBLIC_DOCS:
        claims = _page_claims(_body(rel))
        if not claims and rel not in _NO_PAGE_CLAIM_OK:
            bad[rel] = [-1]
            continue
        stale = sorted(v for v in claims if v != actual)
        if stale:
            bad[rel] = stale
    assert not bad, (
        f"公开物料的页面数与真实值（{actual}）不一致：{bad}（-1=正文无声明）；"
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
    r"\d+\s*个?功能页(?!面)",   # 「个功能页」变体同样属于规模声明
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
               "@BREADTH_SPAN@", "@BREADTH@", "@BT_DAYS@", "@V2_ROUTES@"):
        assert ph in html, f"模板缺少占位符 {ph}"


# ── C. render() 必须把占位符替换干净 ────────────────────────────────

def _load_generator():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_gen_portfolio", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FAKE_STATS = {
    "pages": 55, "modules": 92, "routes": 75, "v2_routes": 58, "py_files": 577,
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


def _charts() -> list[tuple]:
    """从 AST 读 CHARTS 真值，不接受注释里的同款字符串。"""
    tree = ast.parse(_src("scripts/gen_portfolio_page.py"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "CHARTS":
            return ast.literal_eval(node.value)
    raise AssertionError("未找到 CHARTS 清单")


def test_portfolio_no_longer_cites_mislabelled_eval_chart():
    """作品集页不得再引用 fig_history_trend.png（该文件实为「评估数据累积趋势」）。

    反自静音：旧版用全文 `in gen` 判断「引用了真·广度历史图」，
    只在注释里写 fig_breadth_history.png 就能喂饱；现在从 AST 读 CHARTS。
    """
    charts = _charts()
    assert charts, "未找到 CHARTS 清单"
    paths = [rel for rel, *_ in charts]
    assert "thesis/ch6_eval/fig_history_trend.png" not in paths, (
        "CHARTS 又在引用 fig_history_trend.png —— 该文件由 thesis/eval_ch6.py 写成"
        "「评估数据累积趋势（每次运行 +1）」，不是全市场广度历史图"
    )
    assert any("fig_breadth_history.png" in p for p in paths), "CHARTS 未引用真·广度历史图"


def test_portfolio_charts_refer_to_existing_files():
    """T-204：CHARTS 每条引用的图片必须真实存在。

    render() 经 _data_uri 取图，文件缺失时**静默 continue**——路径失效（如 thesis
   重组搬目录）会让作品集页静默丢图、且无任何红。本守卫把「静默丢图」变「响亮失败」：
    2026-10-04 thesis 重组后 CHARTS 三条仍指 thesis/ch6_eval/*（实已移
    thesis/素材/ch6_eval/*），即为此类。
    """
    tree = ast.parse(_src("scripts/gen_portfolio_page.py"))
    charts = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "CHARTS"):
            charts = ast.literal_eval(node.value)
    assert charts, "未找到 CHARTS 清单"
    missing = [rel for rel, *_ in charts
               if not os.path.exists(os.path.join(ROOT, rel))]
    assert not missing, f"作品集 CHARTS 引用了不存在的图：{missing}（路径失效会被静默丢图）"


# ── F. 生成物 docs/index.html 必须与生成器统计一致 ───────────────────

def test_portfolio_generated_html_numbers_match_generator():
    """生成物里的规模数字必须来自生成器当前统计，端点数陈旧即红。

    真实故障（2026-11-09）：后端 REST 端点已增至 122，docs/index.html 仍写 92，
    而守卫只校验「模板不硬编码」「render() 替换干净」，从没校验过生成物本身。
    """
    gen = _load_generator()
    stats = gen.collect(fast=True)  # 不跑 pytest 收集：这里只校验可静态复算的规模数字
    html = _src("docs/index.html")
    assert not re.search(r"@[A-Z_]+@", html), "生成物里露出未替换的 @占位符@"

    route_claims = set(re.findall(r"(\d+)\s*个 REST 端点", html))
    assert route_claims, "生成物里没有「N 个 REST 端点」声明，守卫失效"
    assert route_claims == {str(stats["routes"])}, (
        f"生成物端点声明 {route_claims} != 生成器实测 {stats['routes']}；"
        "请重跑 python scripts/gen_portfolio_page.py"
    )
    stat = re.search(r'<div class="n">(\d+)</div><div class="l">后端 REST 端点', html)
    assert stat and int(stat.group(1)) == stats["routes"], "统计卡片的端点数与后端不一致"

    assert set(_page_claims(html)) == {stats["pages"]}, "生成物页面数与真实 pages/ 不一致"
    py_claims = set(re.findall(r"(\d+) 个 Python 文件", html))
    assert py_claims == {str(stats["py_files"])}, (
        f"生成物 Python 文件数 {py_claims} != 生成器实测 {stats['py_files']}"
    )
    assert stats["py_files"] < 2000, "py_files 仍疑似把虚拟环境/生成物算进自研源码"


def test_v2_route_count_reflected_in_generated_html():
    """作品集页必须如实体现 V2 React 生产前端的路由数（@V2_ROUTES@ 已由生成器注入）。

    V2 是 2026-11 起唯一新增方向，公开物料不得仍只讲 Streamlit 而把 V2 藏起来。
    """
    gen = _load_generator()
    stats = gen.collect(fast=True)
    html = _src("docs/index.html")
    assert not re.search(r"@[A-Z_]+@", html), "生成物里露出未替换的 @占位符@"
    # 统计卡片：V2 生产前端路由
    stat = re.search(r'<div class="n">(\d+)</div><div class="l">V2 生产前端路由', html)
    assert stat and int(stat.group(1)) == stats["v2_routes"], (
        f"生成物 V2 路由卡片 {stat.group(1) if stat else '缺失'} != 生成器实测 {stats['v2_routes']}"
    )
    # 导语里也必须带出 V2 路由数
    assert f"{stats['v2_routes']} 个路由" in html, "导语未带出 V2 路由数"


def test_generator_walk_excludes_third_party_dirs():
    """_walk 统计自研源码时不得深入 .venv / node_modules / .git 等目录。

    真实故障：旧 _walk(".") 把 .venv 的 12728 个第三方 .py 算进 py_files，
    公开物料写着「10220 个 Python 文件」，严重虚高。
    """
    gen = _load_generator()
    paths = gen._walk(".")
    assert len(paths) >= 200, f"只扫到 {len(paths)} 个 .py，_walk 疑似失效"
    bad = [p for p in paths if any(
        s in os.path.relpath(p, ROOT).replace("\\", "/").split("/")
        for s in (".venv", "node_modules", ".git", "site-packages", "artifacts", "backups")
    )]
    assert not bad, f"_walk 把第三方/生成物目录算进了自研源码：{bad[:5]}"
    assert len(paths) < 2000, f"_walk 仍统计到 {len(paths)} 个 .py，排除规则疑似回退"


# ── G. 测试规模数字 == 生成器实测；提交数不写死（2026-11-09） ────────
_TEST_CLAIM_PATTERNS = (
    r"(?<![\d,])(\d[\d,]*)\s*(?:个)?(?:自动化)?测试(?:用例)?(?!文件)",
    r"(?<![\d,])(\d[\d,]*)\s*个?用例",
    r"(?<![\d,])(\d[\d,]*)\s*项测试",
    r"测试\s*(\d[\d,]*)\s*passed",
    r"Tests-(\d[\d,]*)%20passed",
)


def _test_claims(text: str) -> set[int]:
    """抽出物料正文里的测试规模声明（支持千分位、badge、passed 等样式）。"""
    out: set[int] = set()
    for pat in _TEST_CLAIM_PATTERNS:
        for m in re.findall(pat, text):
            out.add(int(m.replace(",", "")))
    return out


def test_test_claim_scanner_catches_real_styles():
    """反例自测：扫描器能抓到各种真实写法，且不会把陈旧值当合格。"""
    samples = [
        "5086 个自动化测试", "5,418 个自动化测试用例",
        "测试 5422 passed", "Tests-5422%20passed",
        "5422 项测试", "5,422 个用例", "5422 个测试兜底",
    ]
    for s in samples:
        assert _test_claims(s), f"扫描器漏掉声明样式 {s!r}"
    assert 5086 in _test_claims("5086 个自动化测试")
    assert 5418 in _test_claims("5,418 个自动化测试用例")
    assert not _test_claims("74 页离线冒烟（整批不卡死）"), "误把非规模数字当测试数"
    assert not _test_claims("70,194 行测试代码"), "误把测试代码行数当用例数"


def test_public_test_count_equals_generator_truth():
    """所有公开物料的测试数必须等于生成器 AST 实测（测试函数数），漂移即红。

    口径变更（2026-11-09 收口）：对外「测试数」改用 ``_ast_test_count()`` 统计的
    测试函数数——环境无关、确定性、零依赖，彻底消除 pytest 收集因可选依赖
    （fastapi/live）缺失导致的跨环境漂移（本地 5432 / CI 5437 互相矛盾，违反
    「诚实口径」红线）。公开物料不得再引用 pytest 参数化展开数。

    真实故障（2026-11-09）：README / promo / publish-kit 写 5086、
    docs/index.html 写 5,418、生成器实测 5,422 —— 三套数字互相矛盾，
    而 F 段只锁了端点/页面/py_files，从没锁过测试数本身。
    """
    gen = _load_generator()
    stats = gen.collect(fast=True)  # 测试数 == _ast_test_count()，不依赖 pytest 收集环境
    expected = stats["tests"]
    assert expected >= 1000, f"只统计到 {expected} 个测试函数，扫描疑似失效"
    bad: dict[str, list[int]] = {}
    for rel in PUBLIC_DOCS:
        claims = _test_claims(_body(rel))
        if not claims:
            bad[rel] = [-1]
            continue
        wrong = sorted(v for v in claims if v != expected)
        if wrong:
            bad[rel] = wrong
    assert not bad, (
        f"公开物料测试数与生成器实测 {expected} 不一致：{bad}（-1=无声明）；"
        "请重跑 python scripts/gen_portfolio_page.py 并同步所有物料"
    )


def test_public_test_file_count_equals_generator_truth():
    """测试文件数同样不得写死；口径与用例数同源（含 modules/tests）。"""
    gen = _load_generator()
    expected = gen.collect(fast=True)["test_files"]
    assert expected >= 100, f"只统计到 {expected} 个测试文件，扫描疑似失效"
    for rel in PUBLIC_DOCS:
        claims = {int(m) for m in re.findall(r"(\d+)\s*个测试文件", _body(rel))}
        stale = sorted(v for v in claims if v != expected)
        assert not stale, f"{rel} 的测试文件数 {stale} != 生成器实测 {expected}"


def test_generator_test_scopes_are_consistent():
    """用例数（pytest）与文件数（_all_test_paths）必须覆盖同样三处目录。

    历史缺陷：collect() 的 test_files / test_loc 漏了 modules/tests，
    而 _pytest_count() 含该目录，导致同一份物料里两个数字口径不一致。
    """
    gen = _load_generator()
    paths = gen._all_test_paths()
    assert len(paths) >= 400, f"只扫到 {len(paths)} 个测试文件，扫描疑似失效"
    prefixes = {os.path.relpath(p, ROOT).replace("\\", "/").split("/")[0]
                for p in paths}
    assert prefixes == {"tests", "backend", "modules"}, (
        f"测试文件清单覆盖目录异常：{prefixes}；应与 _pytest_count 的三处目录一致"
    )
    tree = ast.parse(_src("scripts/gen_portfolio_page.py"))
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "_pytest_count"), None)
    assert fn is not None, "未找到 _pytest_count，守卫失效"
    dirs = {n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for d in ("tests", "backend/tests", "modules/tests"):
        assert d in dirs, f"_pytest_count 未覆盖 {d}，用例数与文件数口径将不一致"
    stats = gen.collect(fast=True)
    assert stats["test_files"] == len([p for p in paths
                                       if os.path.basename(p).startswith("test")])


def test_public_docs_do_not_hardcode_commit_count():
    """提交数天生滞后于生成它的 commit（@COMMITS@ 自指漂移），不得写死。

    生成物里的 `git rev-list --count HEAD` 永远算的是「生成前」的 HEAD，
    下一次提交又漂移一次；改成定性表述才能一次性消除。
    """
    for rel in PUBLIC_DOCS:
        body = _body(rel)
        assert not re.search(r"\d+\s*次提交", body), f"{rel} 又写死了提交次数"
        assert not re.search(r'<div class="n">\d+</div><div class="l">Git 提交', body), (
            f"{rel} 的 Git 提交卡片又写回具体数字"
        )
    assert "@COMMITS@" not in _template_strings().get("HTML", ""), (
        "模板又用回 @COMMITS@ 占位符，自指漂移会复发"
    )
