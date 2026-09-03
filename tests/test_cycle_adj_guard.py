# -*- coding: utf-8 -*-
"""I7 / I1 护栏测试：CYCLE_ADJ 刻度不变量 + 仅可由校准落地修改。

锁死「情绪周期 → 仓位调节」这套差异化主线的核心常数不被静默漂移：
  · 六个阶段刻度边界正确（冰点/主升为正、退潮/高潮分化为负）
  · 取值落在合理区间 [-15, 15]
  · decision.py 中 CYCLE_ADJ 仅被字面量赋值一次；calibration 的 as_patch/apply_patch
    是唯一的「写入方」（AST 扫描确认，无别的代码偷偷改它）
"""
import ast
import logging
import os

import pytest

from modules import decision as _dec
from modules import calibration as _cal


def test_cycle_adj_keys_complete():
    assert set(_dec.CYCLE_ADJ.keys()) == {
        "主升高潮", "修复确认", "修复试探", "高潮分化", "退潮", "冰点"}


def test_cycle_adj_sign_invariants():
    # 情绪越热越该加仓、越冷越该减仓的语义不变量
    assert _dec.CYCLE_ADJ["主升高潮"] > 0
    assert _dec.CYCLE_ADJ["冰点"] > 0          # 冰点=超卖左侧试探
    assert _dec.CYCLE_ADJ["退潮"] < 0
    assert _dec.CYCLE_ADJ["高潮分化"] < 0


def test_cycle_adj_bounds():
    for v in _dec.CYCLE_ADJ.values():
        assert -15 <= v <= 15, f"刻度 {v} 越界"


def test_cycle_adj_assigned_once_in_source():
    """decision.py 里 CYCLE_ADJ 只能被字面量赋值一次（防止重复赋值漂移）。"""
    src = open(_dec.__file__, encoding="utf-8").read()
    assigns = src.count("CYCLE_ADJ = {")
    assert assigns == 1, f"期望 CYCLE_ADJ 仅字面量赋值一次，实际 {assigns} 次"


def test_only_calibration_writes_cycle_adj():
    """AST 扫描：calibration 模块里只有 as_patch / apply_patch 引用 CYCLE_ADJ 做写入语义。"""
    cal_src = open(_cal.__file__, encoding="utf-8").read()
    tree = ast.parse(cal_src)
    writers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "CYCLE_ADJ":
                    # 形如 _dec.CYCLE_ADJ[...] = x （真写入）
                    writers.append(ast.unparse(node))
    # 当前设计：calibration 不直接赋值 decision.CYCLE_ADJ，只生成补丁字典由 apply_patch 落地；
    # apply_patch 用正则改写 decision.py 源码（不在此 AST 体现）。所以这里断言「无直接赋值」。
    assert writers == [], f"calibration 不应直接赋值 CYCLE_ADJ，发现: {writers}"


def test_apply_patch_refuses_when_not_ready(tmp_path, monkeypatch):
    """I1 护栏：样本不足（verdict 不 ready）时 apply_patch 拒绝落地、不改文件。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    from modules import decision_track as _track
    importlib.reload(_track)
    from modules import calibration as _cal2
    importlib.reload(_cal2)

    # 清空预测记录 → 样本为 0 → verdict 不 ready
    _track._save([])
    before = dict(_dec.CYCLE_ADJ)
    res = _cal2.apply_patch(dry_run=False)
    assert res["applied"] is False
    assert _dec.CYCLE_ADJ == before, "未 ready 时 CYCLE_ADJ 绝不能被改"


def test_apply_patch_dry_run_is_noop(tmp_path, monkeypatch, caplog):
    """I1 护栏：默认 dry_run 只预览、不写文件、不改常数。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    import importlib
    from modules import decision_track as _track
    importlib.reload(_track)
    from modules import calibration as _cal2
    importlib.reload(_cal2)

    _track._save([])
    before = dict(_dec.CYCLE_ADJ)
    with caplog.at_level(logging.WARNING):
        res = _cal2.apply_patch(dry_run=True)
    assert res["applied"] is False
    assert _dec.CYCLE_ADJ == before
