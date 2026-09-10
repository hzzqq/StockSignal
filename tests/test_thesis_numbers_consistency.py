"""tests/test_thesis_numbers_consistency.py

论文回测数字 ↔ 实算结果 一致性守卫（2026-09-09 锐评 R8）。

为何存在
--------
R7 修正了「平盘日被当作下跌」的口径缺陷，命中率由 49.3%（1806/3667）变为
49.1%（1722/3507），但**论文正文、中英文摘要仍引用旧数字**——如果只改代码不改论文，
毕业论文就会出现「正文数字与实算结果不一致」的硬伤，且下次口径再变还会重演。

本测试把论文的关键实证数字**钉死在实算产物上**：
``reports/backtest_decision_closure.json``（由 ``scripts/backtest_decision_closure.py``
生成、随仓库提交）为唯一真理源，论文必须与之一致。

若回测数据或口径变化导致本测试失败，正确处理是**重跑回测并同步论文**，
而不是放宽断言。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

THESIS = os.path.join(ROOT, "thesis", "StockSignal_毕业论文_完整稿.md")
BT_JSON = os.path.join(ROOT, "reports", "backtest_decision_closure.json")


def _load():
    assert os.path.exists(BT_JSON), f"缺少回测产物：{BT_JSON}（先跑 scripts/backtest_decision_closure.py）"
    with open(BT_JSON, encoding="utf-8") as f:
        bt = json.load(f)
    with open(THESIS, encoding="utf-8") as f:
        thesis = f.read()
    return bt, thesis


def test_proposition_one_hit_rate_matches_backtest():
    """命题一的方向命中率必须与实算 JSON 逐字一致（含分式）。"""
    bt, thesis = _load()
    o = bt["overall"]
    expect = f"{o['dir_accuracy']}%（{o['hit']}/{o['call']}）"
    assert expect in thesis, f"论文未引用实算命中率 {expect}（可能仍是旧数字）"

    # 中英文摘要同样不得引用过期数字
    assert f"方向命中率 {o['dir_accuracy']}%" in thesis, "中文摘要命中率与实算不一致"
    assert f"direction hit rate {o['dir_accuracy']}%" in thesis, "英文摘要命中率与实算不一致"


def test_flat_days_disclosed_consistently():
    """平盘日数、口径说明必须与实算一致（含被排除的样本量）。"""
    bt, thesis = _load()
    flat = bt["meta"]["flat_days_excluded"]
    assert flat > 0, "实算应统计出平盘日"
    assert f"{flat} 个平盘日" in thesis, f"论文未披露平盘日数 {flat}"
    assert "无方向信息" in thesis, "论文缺少平盘日口径说明"
    assert bt["overall"]["dir_call_denominator"] == bt["overall"]["call"], (
        "回测产物的分母口径字段与 call 不一致"
    )


def test_table_6_3_position_numbers_match_backtest():
    """表 6-3 各周期的 n 与平均建议仓位必须与实算 by_stage_full_closure 逐行一致。"""
    bt, thesis = _load()
    rows = bt["by_stage_full_closure"]
    assert rows, "实算缺少 by_stage_full_closure"
    missing = []
    for r in rows:
        cell = f"| {r['cycle']} | {r['n']} | {r['avg_pct']} |"
        if cell not in thesis:
            missing.append(cell)
    assert not missing, "表 6-3 与实算不一致，缺行：" + "; ".join(missing)


def test_group_position_spread_matches_backtest():
    """四大分组的仓位价差（论文反复引用的 22.8pt）必须由实算推出。"""
    bt, thesis = _load()
    g = {r["group"]: r for r in bt["by_group_calibration"]}
    off, deff = g["进攻期"]["avg_pct"], g["防守期"]["avg_pct"]
    spread = round(float(off) - float(deff), 1)
    assert spread > 0, "进攻期仓位应高于防守期"
    assert f"{spread} 个百分点" in thesis or f"{spread}pt" in thesis, (
        f"论文未引用实算价差 {spread}pt（进攻 {off} / 防守 {deff}）"
    )


def test_no_stale_backtest_numbers_in_thesis():
    """反向守卫：整体命中率的位置不得出现与实算不符的百分比。"""
    bt, thesis = _load()
    acc = str(bt["overall"]["dir_accuracy"])
    # 命题一那段里的命中率必须是实算值
    m = re.search(r"全链路次日方向命中率 \*\*([\d.]+)%", thesis)
    assert m, "未定位到命题一命中率句子"
    assert m.group(1) == acc, f"命题一命中率 {m.group(1)}% ≠ 实算 {acc}%"
