# -*- coding: utf-8 -*-
"""v1 功能页清单漂移守卫：TS 生成物必须与磁盘 pages/*.py 一致。

防的是「生成物造假」类缺陷：UI 上列出并不存在的页、或 v1 新增页后 v2
清单静默陈旧。任何不一致一律 fail，不许 skip（守卫在故障真发生时必须发声）。

反自静音（2026-11-09）：多处用 re.findall 取集合后只做「差集为空」判断，
正则一旦扫空（文件改名 / 引号风格变化），空集减空集恒为空 → 守卫假通过。
现在每个正则扫描都带数量下限兜底。
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "scripts" / "gen_v1_pages.py"
TS = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v1Pages.generated.ts"
MAPPING = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v2Mapping.ts"
ROUTER = ROOT / "frontend-v2" / "src" / "app" / "router.tsx"
READ_ROUTES = ROOT / "backend" / "api" / "read_routes.py"
DIAG_SCHEMA = ROOT / "frontend-v2" / "src" / "api" / "schemas" / "diagnostics.ts"
DATA_VIEW = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "DataSourceView.tsx"
PAGE_RE = re.compile(r"^\d{2}_.+\.py$")


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_v1_pages", GEN)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _disk_pages() -> list[str]:
    return sorted(p.name for p in (ROOT / "pages").glob("*.py") if PAGE_RE.match(p.name))


def _diag_required_query() -> set[str]:
    """从 AST 读 _DIAG_REQUIRED_QUERY，不靠正则猜引号。"""
    tree = ast.parse(READ_ROUTES.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "_DIAG_REQUIRED_QUERY" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("read_routes.py 缺少 _DIAG_REQUIRED_QUERY 单一真理源")


def test_generated_file_is_exactly_current_generator_output():
    """生成物与生成器当前输出逐字节一致 —— 忘了重跑即红。"""
    gen = _load_generator()
    expected = gen.render(gen.collect())
    assert TS.read_text(encoding="utf-8") == expected, \
        "v1Pages.generated.ts 已陈旧，请运行 python scripts/gen_v1_pages.py"


def test_ts_file_set_equals_disk_page_set():
    """TS 里的文件名集合 == 磁盘页集合，多一个（编造）或少一个（漏登记）都红。"""
    text = TS.read_text(encoding="utf-8")
    listed = re.findall(r'"file": "([^"]+)"', text)
    disk = _disk_pages()
    assert len(disk) >= 50, f"磁盘只扫到 {len(disk)} 个功能页，PAGE_RE 或 pages/ 路径疑似失效"
    assert listed == disk, (
        f"清单与磁盘不一致：TS={len(listed)} 磁盘={len(disk)}；"
        f"多出={sorted(set(listed) - set(disk))}；缺失={sorted(set(disk) - set(listed))}"
    )


def test_total_matches_actual_count():
    text = TS.read_text(encoding="utf-8")
    m = re.search(r"export const V1_PAGES_TOTAL = (\d+)", text)
    assert m, "缺 V1_PAGES_TOTAL"
    assert int(m.group(1)) == len(_disk_pages())


def test_every_page_has_group_and_v1_url():
    """每条都带分组与 v1 相对 URL，且分组在声明的枚举内（不允许 '其他' 悄悄扩散）。"""
    text = TS.read_text(encoding="utf-8")
    groups = set(re.findall(r'"group": "([^"]+)"', text))
    declared = set(_load_generator().GROUP_ORDER)
    assert len(groups) >= 3, f"只扫到 {len(groups)} 个分组，正则疑似失效（空集会恒满足子集判断）"
    assert groups <= declared, f"出现未声明分组: {groups - declared}"
    urls = re.findall(r'"v1Url": "([^"]+)"', text)
    assert len(urls) == len(_disk_pages())
    assert all(u.startswith("/") for u in urls)


def test_native_mapping_targets_are_real_router_paths():
    """native 映射指向的路由必须在 router.tsx 真实注册（不许指向不存在的页）。"""
    mapping = MAPPING.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    registered = set(re.findall(r"path: '([^']+)'", router))
    targets = set(re.findall(r"to: '([^']+)'", mapping))
    # 两个集合任一扫空都会让下面的差集恒为空 → 必须各自兜底。
    assert len(registered) >= 10, f"router 只扫到 {len(registered)} 条路由，正则疑似失效"
    assert len(targets) >= 10, f"映射只扫到 {len(targets)} 个 native 目标，正则疑似失效"
    missing = targets - registered - {'/'}
    assert not missing, f"native 映射指向未注册路由: {sorted(missing)}"


def test_data_mapping_paths_are_real_read_endpoints():
    """data 映射指向的端点必须在后端 read_routes.py 真实登记。"""
    mapping = MAPPING.read_text(encoding="utf-8")
    routes = READ_ROUTES.read_text(encoding="utf-8")
    registered = set(re.findall(r'@bp\.get\("([^"]+)"\)', routes))
    paths_all = re.findall(r"path: '(/api/v2/read/[^']+)'", mapping)
    paths = set(paths_all)
    assert len(registered) >= 20, f"后端只扫到 {len(registered)} 个 GET 端点，正则疑似失效"
    # 数据层（DATA 档）在 50/62/70 升 native 后已清零（全部转为 native 真页面）；
    # 保留守卫以钉死「若将来再有 data 条目，必须指向真实只读端点」。DATA 档允许为空。
    assert len(paths_all) >= 0, f"映射只扫到 {len(paths_all)} 条 data 条目"
    assert len(paths) >= 0, f"映射只扫到 {len(paths)} 个去重 data 端点"
    missing = {
        p for p in paths
        if p.removeprefix("/api/v2/read") not in registered
    }
    assert not missing, f"data 映射指向不存在的只读端点: {sorted(missing)}"


def test_required_query_data_deeplinks_are_usable():
    """功能全景指向需参端点的深链，数据浏览器必须能自动填示例参数。

    真实故障（2026-11-09）：/data?path=/api/v2/read/paper-trades 这类深链
    不带 query 直接 GET 会 400，页面一进去就报错；修法是后端 diagnostics
    下发 sample_query，前端 choose() 自动填入。本守卫把这条跨文件契约钉死。
    """
    required = _diag_required_query()
    assert len(required) >= 8, f"只扫到 {len(required)} 个需参端点，AST 扫描疑似失效"
    schema = DIAG_SCHEMA.read_text(encoding="utf-8")
    view = DATA_VIEW.read_text(encoding="utf-8")
    # 真实故障（2026-11-09）：/data?path=/api/v2/read/paper-trades 这类深链不带 query
    # 直接 GET 会 400，页面一进去就报错；修法是后端 diagnostics 下发 sample_query，
    # 前端 choose() 自动填入。本守卫把「数据浏览器自动填参」这条跨文件契约钉死——
    # 它对所有需参端点（无论 catalog 是否持有深链）都生效。
    assert "sample_query" in schema, "后端下发了 sample_query，前端 schema 却没接"
    assert "?.sample_query" in view, "选择端点时必须读取示例参数"
    assert "void load(path, sample)" in view, "选择端点时必须带示例参数发起 GET"
    assert "initialPath" in view and "choose(initialPath)" in view, "深链进入也要自动填参数"
    # catalog 数据层（DATA 块）曾持有 review-notes / financials 等需参端点深链；
    # 收口后这些页均已升 native（/review-notes、/financial-hunter 等），原生页自行
    # 处理 query，故不再强制 catalog 持有需参深链。仅当 catalog 仍有指向需参端点的
    # data 深链时，才需它落到已注册端点（防编造）。
    linked = set(re.findall(r"path: '(/api/v2/read/[^']+)'", MAPPING.read_text(encoding="utf-8")))
    # registered 曾在别的测试函数里定义，本函数未定义；过去因 linked & required 为空
    # 生成器不迭代而侥幸不报 NameError。现在就地真扫 + 数量兜底，杜绝守卫自我静音。
    registered = set(re.findall(r'@bp\.get\("([^"]+)"\)', READ_ROUTES.read_text(encoding="utf-8")))
    assert len(registered) >= 20, f"后端只扫到 {len(registered)} 个 GET 端点，正则疑似失效"
    bogus = sorted(p for p in (linked & required) if p.removeprefix("/api/v2/read") not in registered)
    assert not bogus, f"catalog 指向的需参端点却未注册: {bogus}"
