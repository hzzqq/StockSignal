# -*- coding: utf-8 -*-
"""
tests/test_freshness_cross_language.py — 前后端鲜度阈值跨语言一致性守卫（P1）。

背景（2026-11-28 新方向审计 3-P1）：
  modules/decision.py 是 4/8 天阈值的单一真理源（后端封顶 60%/40% 与告警文案共用）；
  frontend-v2/src/lib/freshness.ts 因纯前端无法 import Python，持有一份镜像常量。
  此前前端测试只用常量自身做相对边界断言、后端 test_recommend_guard.py:106 只锁后端，
  任一侧漂移（如 4→5 / 8→10）两套测试仍全绿，F1-F4 建立的「前后端口径一致」会静默破裂。

本守卫从 TS 源文件正则抽字面量，断言与 Python 真理源逐字相等。改阈值必须同时改两侧，
否则本测试红灯——把「一次性人工对齐」升级为机器约束。
"""
from __future__ import annotations

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRESHNESS_TS = os.path.join(
    PROJECT_ROOT, "frontend-v2", "src", "lib", "freshness.ts"
)


def _ts_literal(name: str) -> int:
    """从 freshness.ts 抽 `export const NAME = <int>` 的字面量；缺失/非字面量即 fail。"""
    with open(FRESHNESS_TS, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"export\s+const\s+%s\s*=\s*(\d+)\b" % re.escape(name), text)
    assert m, f"freshness.ts 未找到 `export const {name} = <int>;`（可能改名或非字面量，需人工核对）"
    return int(m.group(1))


def test_freshness_thresholds_match_truth_source():
    """TS 镜像常量必须与 modules/decision 的单一真理源逐字相等。"""
    from modules.decision import FRESH_STALE_DAYS, FRESH_WARN_DAYS

    assert (_ts_literal("FRESH_WARN_DAYS"), _ts_literal("FRESH_STALE_DAYS")) == (
        FRESH_WARN_DAYS,
        FRESH_STALE_DAYS,
    ), "前后端鲜度阈值漂移：freshness.ts 与 modules/decision.py 必须同步修改"


def test_truth_source_values_unchanged():
    """真理源本身仍是 4/8（防止两侧一起被改成错误值而交叉守卫仍绿）。"""
    from modules.decision import FRESH_STALE_DAYS, FRESH_WARN_DAYS

    assert (FRESH_WARN_DAYS, FRESH_STALE_DAYS) == (4, 8)
