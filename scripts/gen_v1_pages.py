# -*- coding: utf-8 -*-
"""
生成 frontend-v2 的「v1 功能页」清单（单一真理源 = 磁盘 pages/*.py）。

为什么需要生成器：v2 的功能全景页必须展示 v1 全部功能，但手抄 74 个文件名
迟早与磁盘漂移，且容易把不存在的页写进 UI（生成物造假红线）。此脚本实时扫描
pages/ 目录，按编号区间分组，产出 TS 常量；配套
tests/test_v1_pages_catalog.py 会把 TS 里的文件名与磁盘逐项比对，漂移即红。

用法：python scripts/gen_v1_pages.py
产出：frontend-v2/src/features/catalog/v1Pages.generated.ts（勿手改）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "pages"
OUT = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v1Pages.generated.ts"

_PAGE_RE = re.compile(r"^(\d{2})_(.+)\.py$")

# 编号区间 → v1 功能分组（与 modules/widgets._NAV_GROUPS 的语义大类一致）
GROUP_RULES = (
    (10, 19, "行情与板块"),
    (20, 29, "个股研究"),
    (30, 39, "量化选股与回测"),
    (40, 49, "持仓与交易"),
    (50, 69, "市场情绪与广度"),
    (70, 79, "进阶分析"),
    (80, 89, "数据与工具"),
    (90, 99, "系统与账户"),
)
GROUP_ORDER = [g[2] for g in GROUP_RULES] + ["其他"]


def group_of(num: int) -> str:
    for lo, hi, label in GROUP_RULES:
        if lo <= num <= hi:
            return label
    return "其他"


def collect() -> list[dict]:
    rows = []
    for path in sorted(PAGES_DIR.glob("*.py")):
        m = _PAGE_RE.match(path.name)
        if not m:
            continue
        num, name = int(m.group(1)), m.group(2)
        rows.append({
            "file": path.name,
            "num": num,
            "name": name,
            "group": group_of(num),
            "v1Url": "/" + path.stem,
        })
    return rows


def render(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, indent=2)
    groups = json.dumps(GROUP_ORDER, ensure_ascii=False, indent=2)
    return (
        "// 自动生成，勿手改。来源：scripts/gen_v1_pages.py 实时扫描 pages/*.py。\n"
        "// 漂移守卫：tests/test_v1_pages_catalog.py（TS 文件名集合必须等于磁盘）。\n"
        "// 诚实口径：这里只登记真实存在的 v1 页面文件，不表示 v2 已实现等价功能；\n"
        "// 逐页的 v2 落地状态见同目录 v2Mapping.ts。\n"
        "export interface V1Page {\n"
        "  file: string\n"
        "  num: number\n"
        "  name: string\n"
        "  group: string\n"
        "  v1Url: string\n"
        "}\n\n"
        f"export const V1_PAGES: readonly V1Page[] = {payload}\n\n"
        f"export const V1_PAGE_GROUPS: readonly string[] = {groups}\n\n"
        f"export const V1_PAGES_TOTAL = {len(rows)}\n"
    )


def main() -> None:
    rows = collect()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows), encoding="utf-8")
    print(f"GEN_V1_PAGES_OK total={len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
