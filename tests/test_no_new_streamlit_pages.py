# -*- coding: utf-8 -*-
"""技术栈红线守卫：禁止在 v1 Streamlit 侧新增功能页（2026-11-16 parity C 批）。

背景：技术栈红线写明「禁新增任何 Streamlit 页/功能，新 UI 一律 v2/React」。
此前这条只写在 MEMORY / 退役评估文档里，CI 无任何硬约束——任何人往 pages/
丢一个新 .py 都不会被测试发现，双前端维护成本会静默回升。

单一真理源：frontend-v2/src/features/catalog/v1Pages.generated.ts 的 V1_PAGES
是 74 页的冻结清单。本守卫双向真扫：
  1. 磁盘 pages/*.py 不许出现不在 V1_PAGES 的新页（红线：新增 Streamlit 页）；
  2. V1_PAGES 里的页也不许从磁盘消失（防止有人靠删清单绕过红线）。
第 3 条：每个 V1_PAGES 页必须在 v2Mapping.ts 有登记（status 任意档），
杜绝「加了页却不写映射」的静默漂移。

不联网、不依赖 Flask/DB，纯源文件真扫。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / "pages"
GENERATED_TS = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v1Pages.generated.ts"
MAPPING_TS = ROOT / "frontend-v2" / "src" / "features" / "catalog" / "v2Mapping.ts"

# 生成清单里的文件名：`'20_个股研究.py',` 或 `"20_个股研究.py",`
_PAGE_IN_TS = re.compile(r"['\"](\d+_[^'\"]+\.py)['\"]")
# 映射表 key：`'20_个股研究.py': {` 或 `"20_个股研究.py": {`
_MAPPED_KEY = re.compile(r"['\"](\d+_[^'\"]+\.py)['\"]\s*:\s*\{")


def _disk_pages() -> set[str]:
    assert PAGES_DIR.is_dir(), f"pages/ 目录缺失：{PAGES_DIR}"
    return {p.name for p in PAGES_DIR.glob("*.py") if p.is_file() and not p.name.startswith("__")}


def _generated_pages() -> set[str]:
    assert GENERATED_TS.is_file(), f"V1_PAGES 生成清单缺失：{GENERATED_TS}"
    return set(_PAGE_IN_TS.findall(GENERATED_TS.read_text(encoding="utf-8")))


def test_no_new_streamlit_page_beyond_frozen_v1_list():
    disk = _disk_pages()
    frozen = _generated_pages()
    assert len(frozen) >= 70, f"V1_PAGES 解析异常，仅 {len(frozen)} 页（源文件改格式？）"
    added = sorted(disk - frozen)
    assert not added, (
        f"技术栈红线：pages/ 发现 {len(added)} 个不在冻结清单 V1_PAGES 的新 Streamlit 页：{added}。"
        "禁止新增 v1 页；新 UI 一律走 frontend-v2/React。若确属迁移补登，"
        "先重跑生成脚本把该页并入 V1_PAGES 与 v2Mapping.ts，再提交。"
    )


def test_frozen_v1_pages_not_silently_deleted():
    disk = _disk_pages()
    frozen = _generated_pages()
    removed = sorted(frozen - disk)
    assert not removed, (
        f"V1_PAGES 冻结清单含 {len(removed)} 个磁盘上已不存在的页：{removed}。"
        "禁止靠删清单绕过红线；页面下线须同步改公开数字并走老板显式指令。"
    )


def test_every_v1_page_has_v2_mapping_entry():
    assert MAPPING_TS.is_file(), f"v2Mapping.ts 缺失：{MAPPING_TS}"
    mapped = set(_MAPPED_KEY.findall(MAPPING_TS.read_text(encoding="utf-8")))
    frozen = _generated_pages()
    unlisted = sorted(frozen - mapped)
    assert not unlisted, (
        f"v2Mapping.ts 漏登记 {len(unlisted)} 个 V1_PAGES 页：{unlisted}；"
        "状态可为 native / v1-pinned / v1-only 任一档，但必须有显式条目。"
    )
