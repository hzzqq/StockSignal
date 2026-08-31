"""数据落盘隔离回归：确保测试绝不写穿真实 data/。

conftest 在 pytest 启动时把 SS_DATA_DIR 指到临时目录，
本文件锁住这一行为 —— 一旦隔离失效，record_ladder_snapshot / save_snapshot
就会把 stub 假数据写进真实 data/shepherd_ladder_history.json，
污染 15:30 自动化读取的梯队历史与晋级率回测。
"""
import json
import os

from modules import shepherd_ladder as sl
from modules import decision as dc


def _real_ladder_history() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(root, "..", "data", "shepherd_ladder_history.json"))


def test_ss_data_dir_isolated():
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    assert sl.LADDER_FILE != _real_ladder_history(), "LADDER_FILE 仍指向真实 data/"
    assert dc.DATA_DIR != os.path.dirname(_real_ladder_history()), "decision.DATA_DIR 仍指向真实 data/"


def test_record_ladder_goes_to_tmp_not_real():
    real = _real_ladder_history()
    before = {}
    if os.path.exists(real):
        try:
            before = json.load(open(real, encoding="utf-8"))
        except Exception:
            before = {}

    ok = sl.record_ladder_snapshot("2099-12-31", [(1, 7), (2, 2)], 2, 9)
    assert ok is True

    # 真实文件里绝不能出现这条测试数据
    if os.path.exists(real):
        try:
            after = json.load(open(real, encoding="utf-8"))
        except Exception:
            after = {}
        assert "2099-12-31" not in after, "测试写穿到了真实 data/shepherd_ladder_history.json！"

    # 临时目录里应有
    tmp = sl.load_history()
    assert "2099-12-31" in tmp


def test_save_snapshot_goes_to_tmp_not_real():
    real_dir = os.path.dirname(_real_ladder_history())
    snap = dc.build_snapshot(
        "2099-12-31",
        {"up_count": 3000, "limit_up": 80},
        60.0,
        {"cycle": {"name": "修复确认"}, "score": 65, "bias": "偏多", "confidence": "中"},
        {"overall": 50.0},
    )
    assert dc.save_snapshot(snap) is True

    real_snap = os.path.abspath(os.path.join(real_dir, "daily_snapshot.json"))
    if os.path.exists(real_snap):
        try:
            data = json.load(open(real_snap, encoding="utf-8"))
        except Exception:
            data = {}
        assert data.get("date") != "2099-12-31", "测试快照写穿到了真实 data/daily_snapshot.json！"

    assert dc.load_snapshot() is not None
    assert dc.load_snapshot()["date"] == "2099-12-31"
