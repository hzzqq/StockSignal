# -*- coding: utf-8 -*-
"""
tests/test_decision.py — 锁住「今日决策」单一真理源（modules/decision.py）

为什么测它：
    仓位推导被三处消费（决策面板 / 每日快照脚本 / 首页 banner），
    一旦规则漂移，三处会给出互相矛盾的建议，且首页是只读展示、最难发现错。
    这里把规则边界钉死，改 decision.py 必须同步改这里。

覆盖：
    · derive_position 加/减仓各项、clamp 边界、None 兜底、周期名带括号后缀
    · build_snapshot 组装（含 forecast/promo 为 None 的降级）
    · save/load 往返、归档副本、list_archive_dates、is_stale
"""
import json
import os
import time

import pytest

from modules import decision as dc


# ───────────────────────── derive_position ─────────────────────────
def test_neutral_baseline_no_adjustment():
    """温度 50 + 中性 + 未知周期 + 无晋级率 → 就是 50%，档位中性。"""
    pos = dc.derive_position(50, score=50, bias="中性", cycle_name="", overall_promo=None)
    assert pos["pct"] == 50
    assert pos["band"] == "中性"
    assert pos["color"] == "#f59e0b"
    # 无晋级率数据时不该产生任何调节理由（缺数据 ≠ 看空）
    assert not any("晋级率" in r for r in pos["reasons"])


def test_bullish_stack_adds_up():
    """偏多 +8、主升高潮 +5、晋级率≥60% +5 → 50 起步应到 68（偏多档）。"""
    pos = dc.derive_position(50, bias="偏多", cycle_name="主升高潮", overall_promo=65.0)
    assert pos["pct"] == 68
    assert pos["band"] == "偏多"
    assert pos["color"] == "#ee2a2a"


def test_bearish_stack_subtracts():
    """偏空 -8、退潮 -10、晋级率<20% -6 → 50 起步应到 26（偏空档）。"""
    pos = dc.derive_position(50, bias="偏空", cycle_name="退潮", overall_promo=10.0)
    assert pos["pct"] == 26
    assert pos["band"] == "偏空"
    assert pos["color"] == "#00d486"


def test_cycle_name_with_parenthesis_suffix_still_matches():
    """周期名可能带括号后缀（如「主升高潮（加速）」），必须取核心名匹配到调节值。"""
    plain = dc.derive_position(50, bias="中性", cycle_name="主升高潮", overall_promo=None)
    suffix = dc.derive_position(50, bias="中性", cycle_name="主升高潮（加速）", overall_promo=None)
    assert plain["pct"] == suffix["pct"] == 55


@pytest.mark.parametrize("promo,expected_delta", [
    (60.0, 5), (40.0, 0), (20.0, -3), (19.9, -6), (0.0, -6),
])
def test_promo_bands(promo, expected_delta):
    """晋级率四档边界：≥60 +5 / 40-60 0 / 20-40 -3 / <20 -6。"""
    pos = dc.derive_position(50, bias="中性", cycle_name="", overall_promo=promo)
    assert pos["pct"] == 50 + expected_delta


def test_clamp_upper_and_lower():
    """极端输入必须 clamp 在 5~95，不能给出 0% 或 100% 这种无法执行的建议。"""
    hi = dc.derive_position(200, bias="偏多", cycle_name="主升高潮", overall_promo=90.0)
    lo = dc.derive_position(-50, bias="偏空", cycle_name="退潮", overall_promo=0.0)
    assert hi["pct"] == 95 and hi["band"] == "激进"
    assert lo["pct"] == 5 and lo["band"] == "防御"


def test_none_inputs_fall_back_gracefully():
    """任何入参为 None 都兜底，不抛异常（脚本与首页都靠这个不崩）。"""
    pos = dc.derive_position(None, score=None, bias=None, cycle_name=None, overall_promo=None)
    assert pos["pct"] == 50  # 温度 None → 兜底 50，其余无调节


def test_band_thresholds():
    """档位分界点：80/60/40/20 必须落在正确的档。"""
    assert dc.derive_position(80, bias="中性", cycle_name="")["band"] == "激进"
    assert dc.derive_position(60, bias="中性", cycle_name="")["band"] == "偏多"
    assert dc.derive_position(40, bias="中性", cycle_name="")["band"] == "中性"
    assert dc.derive_position(20, bias="中性", cycle_name="")["band"] == "偏空"
    assert dc.derive_position(19, bias="中性", cycle_name="")["band"] == "防御"


# ───────────────────────── build_snapshot ─────────────────────────
def test_build_snapshot_assembles_all_fields():
    """快照要带齐首页 banner 需要的字段，缺一个首页就得回退到猜。"""
    fc = {"cycle": {"name": "修复确认"}, "score": 62, "bias": "偏多",
          "confidence": "中", "signals": ["a"], "scenario": ["b"]}
    snap = dc.build_snapshot("2026-08-31", {"up_count": 3000}, 58.0, fc, {"overall": 45.0})
    assert snap["date"] == "2026-08-31"
    assert snap["temperature"] == 58.0
    assert snap["cycle"] == "修复确认"
    assert snap["bias"] == "偏多"
    assert snap["promo_overall"] == 45.0
    assert snap["indicators"] == {"up_count": 3000}
    # 58 + 偏多8 + 修复确认3 + 晋级率45%(0) = 69
    assert snap["position"]["pct"] == 69


def test_build_snapshot_survives_none_sources():
    """forecast / promo 为 None 时必须降级出一份快照，而不是抛异常。"""
    snap = dc.build_snapshot("2026-08-31", {}, 50.0, None, None)
    assert snap["cycle"] == ""
    assert snap["promo_overall"] is None
    assert snap["position"]["pct"] == 50


# ───────────────────────── 落盘 / 读取 / 归档 ─────────────────────────
@pytest.fixture()
def snap_dir(tmp_path, monkeypatch):
    """把落盘路径重定向到 tmp_path，避免测试污染真实 data/。"""
    monkeypatch.setattr(dc, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dc, "SNAPSHOT_PATH", str(tmp_path / "daily_snapshot.json"))
    monkeypatch.setattr(dc, "ARCHIVE_DIR", str(tmp_path / "snapshots"))
    return tmp_path


def test_save_and_load_roundtrip(snap_dir):
    snap = dc.build_snapshot("2026-08-31", {"x": 1}, 60.0, {"cycle": {"name": "退潮"}}, {"overall": 30.0})
    assert dc.save_snapshot(snap) is True
    loaded = dc.load_snapshot()
    assert loaded["date"] == "2026-08-31"
    assert loaded["position"]["pct"] == snap["position"]["pct"]
    # 按日期过滤：对得上才返回
    assert dc.load_snapshot("2026-08-31") is not None
    assert dc.load_snapshot("2026-01-01") is None


def test_save_writes_archive_copy(snap_dir):
    """归档是复盘回测的数据源，写最新快照时必须同步落一份按日期的副本。"""
    dc.save_snapshot(dc.build_snapshot("2026-08-30", {}, 55.0, None, None))
    dc.save_snapshot(dc.build_snapshot("2026-08-31", {}, 60.0, None, None))
    assert os.path.exists(snap_dir / "snapshots" / "2026-08-30.json")
    assert os.path.exists(snap_dir / "snapshots" / "2026-08-31.json")
    assert dc.list_archive_dates() == ["2026-08-30", "2026-08-31"]
    assert dc.load_archive("2026-08-30")["temperature"] == 55.0


def test_save_rejects_snapshot_without_date(snap_dir):
    """缺 date 的快照拒绝落盘——否则会把历史文件按错误日期覆盖掉。"""
    assert dc.save_snapshot({"temperature": 50}) is False
    assert dc.load_snapshot() is None


def test_save_same_date_overwrites_not_accumulates(snap_dir):
    """同一天跑多次（定时任务重跑）必须幂等，只留最后一次。"""
    dc.save_snapshot(dc.build_snapshot("2026-08-31", {}, 50.0, None, None))
    dc.save_snapshot(dc.build_snapshot("2026-08-31", {}, 70.0, None, None))
    assert dc.load_snapshot()["temperature"] == 70.0
    assert len(dc.list_archive_dates()) == 1


def test_load_snapshot_missing_file_returns_none(snap_dir):
    """文件不存在返回 None（首页据此隐藏 banner），不抛 FileNotFoundError。"""
    assert dc.load_snapshot() is None


def test_is_stale(snap_dir):
    """过期判定：无文件 → 旧；刚写 → 新；mtime 拨回 2 天前 → 旧。"""
    assert dc.is_stale() is True
    dc.save_snapshot(dc.build_snapshot("2026-08-31", {}, 50.0, None, None))
    assert dc.is_stale() is False
    old = time.time() - 48 * 3600
    os.utime(dc.SNAPSHOT_PATH, (old, old))
    assert dc.is_stale() is True


def test_snapshot_json_is_utf8_readable(snap_dir):
    """落盘 JSON 必须 UTF-8 无转义，否则中文周期名在首页显示成 \\uXXXX。"""
    dc.save_snapshot(dc.build_snapshot("2026-08-31", {}, 50.0, {"cycle": {"name": "主升高潮"}}, None))
    raw = open(dc.SNAPSHOT_PATH, "r", encoding="utf-8").read()
    assert "主升高潮" in raw
    assert json.loads(raw)["cycle"] == "主升高潮"
