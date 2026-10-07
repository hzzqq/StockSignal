# -*- coding: utf-8 -*-
"""tests/test_shepherd_history_backfill.py — T-222 历史段回填守卫。

锁定契约（T-222：JSON 2007–2009 段并入 CSV，现有行逐字节不动）：
- CSV 起点 = 2007-01-05（缺口段已并入）；
- 日期严格升序且唯一；
- canonical 铁律「median_chg 完整」适用于 >=2009-11-02（v1 恢复起点）——
  未来日常增量刷新只会在尾部加行，不得破坏本守卫；
- <2009-11-02 段 median_chg 如实留空（历史形态，非退化，勿「补齐」）；
- 持久镜像 backups/shepherd_history_restored.csv 与 CSV 内容一致。

注意：**不钉总行数**（日常 refresh_shepherd_history_recent 会尾部增量）。
数据文件较大，模块级只读一次。
"""
from __future__ import annotations

import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(_ROOT, "data", "shepherd_history.csv")
MIRROR_PATH = os.path.join(_ROOT, "backups", "shepherd_history_restored.csv")
V1_START = "2009-11-02"  # v1 恢复起点（median_chg 完整铁律的适用边界）


def _load_lines(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        lines = f.read().splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


@pytest.fixture(scope="module")
def csv_data():
    lines = _load_lines(CSV_PATH)
    header = lines[0].split(",")
    mi = header.index("median_chg")
    rows = [(ln.split(",", 1)[0], ln.split(","), ln) for ln in lines[1:]]
    return header, mi, rows


def test_history_starts_at_2007(csv_data):
    """缺口段已并入：起点必须是 2007-01-05（JSON 真值首日）。"""
    _header, _mi, rows = csv_data
    assert rows[0][0] == "2007-01-05"
    # 首行与 JSON 真值一致（6 广度字段；其余列如实留空）
    first = rows[0][1]
    assert first[1] == "932.0" and first[2] == "118.0" and first[6].startswith("88.76")
    assert all(x == "" for x in first[7:]), f"2007 首行后 10 列应留空: {first[7:]}"


def test_dates_unique_and_ascending(csv_data):
    _header, _mi, rows = csv_data
    dates = [r[0] for r in rows]
    assert dates == sorted(dates), "日期非严格升序"
    assert len(dates) == len(set(dates)), "存在重复日期"


def test_median_chg_complete_from_v1_start(csv_data):
    """canonical 铁律：>=2009-11-02 段 median_chg 100% 完整（防数据退化）。"""
    _header, mi, rows = csv_data
    old_seg = [r for r in rows if r[0] >= V1_START]
    assert old_seg, ">=2009-11-02 段为空？数据文件异常"
    missing = [d for d, cells, _ln in old_seg if cells[mi].strip() == ""]
    assert not missing, f"median_chg 完整铁律被破坏 {len(missing)} 行，如 {missing[:5]}"


def test_pre_v1_segment_honestly_empty_median_chg(csv_data):
    """<2009-11-02 段 median_chg 历史上不存在 → 如实留空。

    守「不臆造」：该段数据源本就无此列，若未来出现非空值说明有人编造/混入
    异口径数据，必须人工复核（勿顺手「补齐」旧段）。
    """
    _header, mi, rows = csv_data
    new_seg = [r for r in rows if r[0] < V1_START]
    assert new_seg, "2007 段为空？回填被回退"
    filled = [d for d, cells, _ln in new_seg if cells[mi].strip() != ""]
    assert not filled, f"<2009-11-02 段 median_chg 应留空，但 {len(filled)} 行有值，如 {filled[:5]}"


def test_mirror_synced_with_csv():
    """持久镜像必须与运行真理源一致（T-221/T-222 两次同步的契约）。"""
    assert _load_lines(CSV_PATH) == _load_lines(MIRROR_PATH), \
        "backups/shepherd_history_restored.csv 与 data/shepherd_history.csv 不一致"


def test_overlap_segment_keeps_sparse_era_values(csv_data):
    """重叠段维持 CSV 稀疏口径（老板 2026-10-07 拍板「按选项 A 维持现状」，DECISIONS 同日备案）。

    背景：JSON（全市场口径）与 CSV（v1 稀疏样本口径）在重叠段 4084 天上广度字段
    全量不一致（如 2009-11-02 up_count：JSON=1363 vs CSV=2.0）。规则 §四「冲突以
    json 为准」**不适用于本文件的重叠段**——老板已明确拒绝按 JSON 重写（那会改变
    历史温度序列与已钉论文回测口径 49.1%/4094）。本守卫钉住稀疏签名：若变红，说明
    有人重写了重叠段——须先取得老板对该口径变更的明确批准，勿静默「统一口径」。
    """
    _header, _mi, rows = csv_data
    by_date = {d: cells for d, cells, _ln in rows}
    row = by_date.get("2009-11-02")
    assert row is not None, "2009-11-02 行缺失"
    assert row[1] == "2.0", \
        f"重叠段稀疏口径签名漂移：2009-11-02 up_count={row[1]!r}（期望 2.0）。" \
        "重叠段属老板拍板「维持现状」区（2026-10-07），重写需另行批准"
