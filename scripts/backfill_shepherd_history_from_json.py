#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""shepherd_history 2007–2009 历史段回填（JSON → CSV，T-222）。

背景（T-221 披露 → 老板拍板「执行」）：
    运行真理源 ``data/shepherd_history.csv``（canonical）自 v1 恢复起仅覆盖
    2009-11-02 起；更早的 2007-01-05 ~ 2009-10-30 真实历史在
    ``data/shepherd_history.json``（4771 天，2007 起，规则 §四：与 CSV 冲突以 json 为准）。
    本脚本把 **CSV 缺失的日期** 从 JSON 并入 CSV（文本级合并，现有行逐字节不动）。

勘测实证（2026-10-06，NaN 感知复勘，勿凭记忆改动口径）：
    - 缺口段 687 天，仅 6 字段 100% 无缺失：up/down/flat_count、limit_up/limit_down、red_ratio；
    - 其余 10 列 **median_chg / avg_price / touch_down / zt_fail_count / hb_wave10 /
      connect_hl / connect_2b / fc_ratio / zt_fail_ratio / zt_prev_ret 历史上不存在**
      （None/NaN，非退化）→ 并入后留空，与 2026-09-09 前旧镜像 4786 行形态一致；
    - canonical 铁律「median_chg 完整」的适用范围 = >=2009-11-02（v1 恢复起点），
      守卫测试按此断言，未来日常增量刷新不破坏本守卫。

范围边界（诚实声明）：
    勘测另发现 **重叠段**（2009-11-02 起 4084 天）JSON 与 CSV 的广度字段口径不一致
    （JSON 全市场 vs CSV v1 稀疏样本）。按规则应以 json 为准重写，但那会改变历史
    温度序列与已钉论文回测口径 —— **超出本脚本职责，须老板单独拍板**，本脚本
    绝不触碰任何 CSV 已有日期的行。

用法：
    python scripts/backfill_shepherd_history_from_json.py            # dry-run（默认）
    python scripts/backfill_shepherd_history_from_json.py --apply    # 真正落盘
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

CSV_PATH = os.path.join(_ROOT, "data", "shepherd_history.csv")
JSON_PATH = os.path.join(_ROOT, "data", "shepherd_history.json")
MIRROR_PATH = os.path.join(_ROOT, "backups", "shepherd_history_restored.csv")

# CSV 列序（canonical header，勿改）
COLUMNS = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down",
           "red_ratio", "touch_down", "zt_fail_count", "hb_wave10", "median_chg",
           "avg_price", "connect_hl", "connect_2b", "fc_ratio", "zt_fail_ratio",
           "zt_prev_ret"]
# 勘测实证（NaN 感知复勘 2026-10-06）：缺口段仅这 6 字段 100% 无缺失；其余 10 列
# （含 connect_hl/zt_fail_ratio/zt_prev_ret 的 NaN）历史上不存在 → 留空（非退化）。
REQUIRED_NON_EMPTY = {"up_count", "down_count", "flat_count", "limit_up", "limit_down",
                      "red_ratio"}
EXPECTED_EMPTY = set(COLUMNS[1:]) - REQUIRED_NON_EMPTY


def _is_missing(v) -> bool:
    """None/空/NaN 都算缺失（NaN 感知——勘测初版曾把 NaN 误计为已填充）。"""
    if v is None or v == "":
        return True
    try:
        return isinstance(v, float) and math.isnan(v)
    except TypeError:
        return False


def _fmt(v) -> str:
    """JSON 值 → CSV 单元格（数值走 float 最短表示；None/NaN → 空串，同旧镜像惯例）。"""
    if _is_missing(v):
        return ""
    try:
        return str(float(v))
    except (TypeError, ValueError):
        return str(v)


def _read_csv_lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def build_merged_lines() -> tuple[list[str], dict]:
    """返回 (合并后的完整行列表含 header, 统计 dict)。纯计算，不落盘。"""
    lines = _read_csv_lines(CSV_PATH)
    header, data_lines = lines[0], lines[1:]
    assert header.split(",") == COLUMNS, f"CSV header 与预期不符: {header}"

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        recs = json.load(f)

    existing_dates = {ln.split(",", 1)[0] for ln in data_lines}
    new_recs = [r for r in recs if str(r.get("date"))[:10] not in existing_dates]

    # 诚实闸门 1：新行 6 个勘测实证干净字段必须齐；其余 10 列必须为空（历史形态）
    problems = []
    for r in new_recs:
        d = str(r.get("date"))[:10]
        for fld in REQUIRED_NON_EMPTY:
            if _is_missing(r.get(fld)):
                problems.append(f"{d}: 必需字段 {fld} 缺失")
        for fld in EXPECTED_EMPTY:
            if not _is_missing(r.get(fld)):
                problems.append(f"{d}: {fld} 非空，超出勘测口径（需人工复核）")
    if problems:
        raise SystemExit("诚实闸门拦截（JSON 质量与勘测不符，拒绝并入）:\n  " + "\n  ".join(problems[:10]))

    new_lines = []
    for r in sorted(new_recs, key=lambda r: str(r.get("date"))[:10]):
        vals = [_fmt(r.get(c)) for c in COLUMNS]
        new_lines.append(",".join(vals))

    if new_lines:
        new_dates = [ln.split(",", 1)[0] for ln in new_lines]
        old_min = min(ln.split(",", 1)[0] for ln in data_lines)
        # 诚实闸门 2：新段必须整体早于现有段（勘测：缺口段全部 <2009-11-02）
        assert max(new_dates) < old_min, \
            f"新段最大日期 {max(new_dates)} 不早于现有段最早 {old_min}，需人工复核"
        merged = [header, *new_lines, *data_lines]
    else:
        merged = list(lines)

    all_dates = [ln.split(",", 1)[0] for ln in merged[1:]]
    assert len(all_dates) == len(set(all_dates)), "合并后出现重复日期！"
    assert all_dates == sorted(all_dates), "合并后日期非严格升序！"

    stats = {"existing": len(data_lines), "new": len(new_lines), "total": len(merged) - 1,
             "new_range": f"{new_dates[0]}~{new_dates[-1]}" if new_dates else "-"}
    return merged, stats


def _atomic_write_text(path: str, lines: list[str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    merged, stats = build_merged_lines()
    print(f"[plan] 现有 {stats['existing']} 行不动；新并入 {stats['new']} 行（{stats['new_range']}）；"
          f"合计 {stats['total']} 行")
    print(f"[诚实口径] 新段除 6 广度字段外的 10 列（median_chg/avg_price/touch_down/"
          f"zt_fail_count/hb_wave10/connect_hl/connect_2b/fc_ratio/zt_fail_ratio/"
          f"zt_prev_ret）历史上不存在 → 留空（非退化）；"
          f">=2009-11-02 段 median_chg 完整铁律不受影响")
    if not apply:
        print("[dry-run] 未落盘。确认无误后加 --apply 执行。")
        return 0

    # .bak 兜底（数据退化可从 .bak 还原）
    bak = CSV_PATH + ".bak"
    if not os.path.exists(bak):
        with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
            content = f.read()
        with open(bak, "w", encoding="utf-8-sig", newline="") as f:
            f.write(content)
        print(f"[bak] 原始 CSV 已备份 → {bak}")

    _atomic_write_text(CSV_PATH, merged)
    _atomic_write_text(MIRROR_PATH, merged)
    print(f"[ok] 已写入 {CSV_PATH}")
    print(f"[ok] 持久镜像已同步 {MIRROR_PATH}")
    print("[回滚指引] data/ 不入 git：可从 .bak 还原 CSV；镜像回滚用 "
          "git checkout <prev> -- backups/shepherd_history_restored.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
