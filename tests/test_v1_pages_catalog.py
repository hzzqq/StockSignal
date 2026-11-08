# -*- coding: utf-8 -*-
"""v1 功能页清单漂移守卫：TS 生成物必须与磁盘 pages/*.py 一致。

防的是「生成物造假」类缺陷：UI 上列出并不存在的页、或 v1 新增页后 v2
清单静默陈旧。任何不一致一律 fail，不许 skip（守卫在故障真发生时必须发声）。
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "scripts" / "gen_v1_pages.py"
TS = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v1Pages.generated.ts"
MAPPING = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v2Mapping.ts"
ROUTER = ROOT / "frontend-v2" / "src" / "app" / "router.tsx"
PAGE_RE = re.compile(r"^\d{2}_.+\.py$")


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_v1_pages", GEN)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _disk_pages() -> list[str]:
    return sorted(p.name for p in (ROOT / "pages").glob("*.py") if PAGE_RE.match(p.name))


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
    missing = targets - registered - {'/'}
    assert not missing, f"native 映射指向未注册路由: {sorted(missing)}"


def test_data_mapping_paths_are_real_read_endpoints():
    """data 映射指向的端点必须在后端 read_routes.py 真实登记。"""
    mapping = MAPPING.read_text(encoding="utf-8")
    routes = (ROOT / "backend" / "api" / "read_routes.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'@bp\.get\("([^"]+)"\)', routes))
    paths = set(re.findall(r"path: '(/api/v2/read/[^']+)'", mapping))
    missing = {
        p for p in paths
        if p.removeprefix("/api/v2/read") not in registered
    }
    assert not missing, f"data 映射指向不存在的只读端点: {sorted(missing)}"
