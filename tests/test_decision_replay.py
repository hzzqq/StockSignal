"""
tests/test_decision_replay.py
-----------------------------
T-325 方向D「决策复盘回放器」契约守卫。

覆盖 AC：
- **AC-R1 只回放归档日**：无归档 → status=unavailable + reason（绝不拿重构值
  冒充「当日当时快照」）。
- **AC-R2 次日对照诚实**：严格 > date 的第一个交易日；末日/缺失 → None；
  稀疏段 up_count 缺失 → None 值（绝不默认 0）。
- **AC-R3 预测对账复用口径**：find_prediction 走 _load（含平盘日 hit=None 纠正）；
  未记录 → None（不编造）。
- **AC-R4 P1 诚实边界**：回放包必须携带「P1 历史未归档」标注。
- **AC-R5 UI 契约**：页面存在、@st.fragment、width 语义（禁 use_container_width）、
  _NAV_GROUPS 显式注册。

所有用例离线（tmp CSV / monkeypatch 归档与 PRED_PATH），不触网。
"""
from __future__ import annotations

import ast
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

import modules.decision_replay as dr  # noqa: E402
import modules.decision_track as dt  # noqa: E402


# ─────────────────────────── fixtures ───────────────────────────
def _d(days_ago: int) -> str:
    """时钟相对日期（防时间炸弹）。"""
    return (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


@pytest.fixture
def history_csv(tmp_path):
    """广度历史小样：含稀疏段 NaN 行（诚实语义用）。"""
    d0, d1, d2, d3, d4 = (_d(i) for i in (4, 3, 2, 1, 0))
    rows = [
        "date,up_count,down_count",
        f"{d0},1000,800",
        f"{d1},1100,700",
        f"{d2},,600",          # 稀疏段：up_count 缺失
        f"{d3},1200,650",
        f"{d4},900,950",
    ]
    p = tmp_path / "hist.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
    return str(p), {"m4": d0, "m3": d1, "m2": d2, "m1": d3, "m0": d4}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """一份真实结构的归档快照（键对齐 data/snapshots/2026-10-23.json）。"""
    snap = {
        "date": _d(1), "as_of": _d(1), "data_age_days": 0,
        "generated_at": f"{_d(1)} 18:00:00",
        "temperature": 61.5, "cycle": "复苏", "score": 63.0,
        "bias": "偏多", "confidence": "中", "promo_overall": 0.31,
        "ladder": {"2b": 0.25}, "position": {"pct": 55, "reasons": ["温度上行"]},
        "event_factor": {"available": True, "signal": "偏多", "date": _d(1)},
        "data_freshness": {"status": "ok"},
        "indicators": {}, "signals": {}, "scenario": {},
    }
    from modules import decision as dm
    arch_dir = tmp_path / "snapshots"
    arch_dir.mkdir()
    (arch_dir / f"{_d(1)}.json").write_text(
        json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(dm, "ARCHIVE_DIR", str(arch_dir))
    return snap


# ─────────────────────── AC-R2 次日对照 ───────────────────────
def test_next_trading_row_strictly_after(history_csv):
    path, d = history_csv
    r = dr.next_trading_row(d["m3"], path)
    assert r == {"date": d["m2"], "up_count": None, "down_count": 600}


def test_next_trading_row_sparse_nan_not_zero(history_csv):
    """稀疏段 up_count 缺失 → None（绝不默认 0，诚实语义）。"""
    path, d = history_csv
    r = dr.next_trading_row(d["m4"], path)
    assert r["date"] == d["m3"] and r["up_count"] == 1100
    r2 = dr.next_trading_row(d["m2"], path)   # 下一行是 m3（有值）
    assert r2["up_count"] == 1200
    # 直接取稀疏行本身：按列语义 None 已在 m2 行验证


def test_next_trading_row_last_day_none(history_csv):
    path, d = history_csv
    assert dr.next_trading_row(d["m0"], path) is None
    assert dr.next_trading_row(_d(-5), path) is None   # 未来日期 → None


def test_next_trading_row_same_day_not_counted(history_csv):
    """date 当日行不算（严格 >），返回下一交易日。"""
    path, d = history_csv
    r = dr.next_trading_row(d["m1"], path)
    assert r["date"] == d["m0"]


def test_next_trading_row_missing_file(tmp_path):
    assert dr.next_trading_row(_d(1), str(tmp_path / "nope.csv")) is None


# ─────────────────────── AC-R3 预测对账 ───────────────────────
def test_find_prediction_hit_and_flat_day_fix(tmp_path, monkeypatch):
    """命中 + 平盘日口径纠正透传（hit False→None，R7）。"""
    d = _d(2)
    p = tmp_path / "pred.json"
    p.write_text(json.dumps([
        {"date": _d(3), "bias": "偏空", "realized": 0.0, "hit": False},
        {"date": d, "bias": "偏多", "realized": 1.2, "hit": True},
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(dt, "PRED_PATH", str(p))
    r = dt.find_prediction(d)
    assert r["bias"] == "偏多" and r["hit"] is True
    flat = dt.find_prediction(_d(3))
    assert flat["hit"] is None          # 平盘日纠正口径生效
    assert dt.find_prediction(_d(30)) is None


def test_find_prediction_bad_json_none(tmp_path, monkeypatch):
    p = tmp_path / "bad.json"
    p.write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(dt, "PRED_PATH", str(p))
    assert dt.find_prediction(_d(1)) is None


# ─────────────────────── AC-R1/R4 回放包 ───────────────────────
def test_build_replay_unavailable_without_archive(tmp_path, monkeypatch):
    from modules import decision as dm
    monkeypatch.setattr(dm, "ARCHIVE_DIR", str(tmp_path / "empty"))
    rec = dr.build_replay(_d(1))
    assert rec["status"] == "unavailable"
    assert "无归档快照" in rec["reason"]
    assert "snapshot" not in rec        # 不携带任何冒充数据


def test_build_replay_ok_passthrough(archive, history_csv, tmp_path, monkeypatch):
    path, d = history_csv
    monkeypatch.setattr(dt, "PRED_PATH", str(tmp_path / "none.json"))
    rec = dr.build_replay(d["m1"], history_path=path)
    assert rec["status"] == "ok"
    assert rec["date"] == d["m1"]
    assert rec["snapshot"]["temperature"] == 61.5    # 原样透传
    assert rec["snapshot"]["position"]["pct"] == 55
    assert rec["next_day"]["date"] == d["m0"]        # 次日对照
    assert rec["prediction"] is None                 # 未记录 → None 不编造
    for token in ("P1", "未归档", "覆盖式导出"):
        assert token in rec["p1_note"]


def test_build_replay_prediction_exception_tolerant(archive, monkeypatch):
    """对账查询异常 → pred=None 留痕不崩（回放主链路不被打分链拖死）。"""
    def _boom(_d):
        raise RuntimeError("io down")
    monkeypatch.setattr(dt, "find_prediction", _boom)
    monkeypatch.setattr("modules.decision_track.find_prediction", _boom)
    rec = dr.build_replay(_d(1))
    assert rec["status"] == "ok" and rec["prediction"] is None


def test_list_replayable_dates_sorted(monkeypatch, tmp_path):
    from modules import decision as dm
    arch = tmp_path / "snaps"
    arch.mkdir()
    for dd in ("2026-09-02", "2026-08-31", "2026-09-01"):
        (arch / f"{dd}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(dm, "ARCHIVE_DIR", str(arch))
    dates = dr.list_replayable_dates()
    assert dates == sorted(dates) == ["2026-08-31", "2026-09-01", "2026-09-02"]


# ─────────────────────── AC-R5 UI 契约（AST 守卫） ───────────────────────
PAGE = os.path.join(PROJECT_ROOT, "pages", "97_决策回放.py")


def test_page_exists_with_fragment_and_width_semantics():
    assert os.path.exists(PAGE), "回放页必须存在"
    src = Path(PAGE).read_text(encoding="utf-8")
    assert "st.fragment" in src or "safe_fragment" in src, "必须用 fragment（禁整页 rerun）"
    assert "use_container_width" not in src, "禁用废弃参数 use_container_width"
    assert "rerun(" not in src, "禁整页 rerun（铁律 3）"


def test_unavailable_path_carries_no_fabricated_values(tmp_path, monkeypatch):
    """诚实语义底线：无归档路径不得携带任何冒充数据（snapshot/next_day 均缺席）。"""
    from modules import decision as dm
    monkeypatch.setattr(dm, "ARCHIVE_DIR", str(tmp_path / "empty_snaps"))
    rec = dr.build_replay("2000-01-01")
    assert rec["status"] == "unavailable"
    assert "snapshot" not in rec and "next_day" not in rec and "prediction" not in rec


def test_nav_groups_registers_replay_page():
    """_NAV_GROUPS 必须显式注册回放页（单一真理源，禁自动兜底）。"""
    src = Path(os.path.join(PROJECT_ROOT, "modules", "widgets.py")).read_text(encoding="utf-8")
    assert "pages/97_决策回放.py" in src
    tree = ast.parse(src)
    # 定位 _NAV_GROUPS 赋值并检查注册行在其字面量内
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "_NAV_GROUPS" for t in node.targets):
            seg = ast.get_source_segment(src, node)
            assert seg and "97_决策回放" in seg, "回放页必须注册在 _NAV_GROUPS 字面量内"
            return
    pytest.fail("未找到 _NAV_GROUPS 定义")
