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


def _real_market_cache_db() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(root, "..", "data", "market_cache.db"))


def _real_news_db() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(root, "..", "data", "news.db"))


def test_market_cache_isolated():
    """market_cache._DB_PATH 必须跟随 SS_DATA_DIR，而非硬编码真实 data/。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    import modules.market_cache as mc
    assert mc._DB_PATH != _real_market_cache_db(), "market_cache._DB_PATH 仍指向真实 data/"
    assert mc._DB_PATH.startswith(os.environ["SS_DATA_DIR"]), \
        "market_cache 未隔离到临时目录（SS_DATA_DIR）"


def test_news_db_isolated():
    """NewsDatabase 默认路径必须跟随 SS_DATA_DIR，而非硬编码真实 data/news.db。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    from modules.news import NewsDatabase
    nd = NewsDatabase()  # 默认路径，应落到 SS_DATA_DIR
    assert nd.db_path != _real_news_db(), "NewsDatabase 默认仍指向真实 data/news.db"
    assert nd.db_path.startswith(os.environ["SS_DATA_DIR"]), \
        "NewsDatabase 未隔离到临时目录（SS_DATA_DIR）"


def test_market_drivers_cache_path_aligned():
    """market_drivers._read_last_cached_value 读的市场_cache.db 目录须与 market_cache 一致。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    import modules.market_cache as mc
    import modules.market_drivers as md
    expected_dir = os.path.dirname(mc._DB_PATH)
    _here = os.path.dirname(os.path.abspath(md.__file__))
    got_dir = os.environ.get("SS_DATA_DIR") or os.path.join(_here, "..", "data")
    assert os.path.abspath(got_dir) == os.path.abspath(expected_dir), \
        "market_drivers 缓存目录与 market_cache 不一致 → 测试会读穿真实 data/"


def test_fetcher_cache_db_isolated():
    """StockFetcher 默认缓存库须跟随 SS_DATA_DIR，而非硬编码真实 data/cache.db。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    from modules.fetcher import StockFetcher
    f = StockFetcher()
    real = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data", "cache.db"))
    assert os.path.abspath(f.db_path) != real, "fetcher 缓存库仍指向真实 data/cache.db"
    assert f.db_path.startswith(os.environ["SS_DATA_DIR"]), \
        "fetcher 缓存库未隔离到临时目录（SS_DATA_DIR）"


def test_shepherd_history_isolated():
    """shepherd 历史 CSV/JSON 须跟随 SS_DATA_DIR，而非硬编码真实 data/shepherd_history.*。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    import modules.shepherd as sh
    real = os.path.abspath(os.path.join(
        os.path.dirname(os.path.abspath(sh.__file__)), "..", "data", "shepherd_history.csv"))
    assert os.path.abspath(sh._HISTORY_FILE) != real, "shepherd 历史仍指向真实 data/shepherd_history.csv"
    assert sh._HISTORY_FILE.startswith(os.environ["SS_DATA_DIR"]), \
        "shepherd 历史未隔离到临时目录（SS_DATA_DIR）"


def test_session_avatar_dir_isolated():
    """session 头像目录须跟随 SS_DATA_DIR，而非硬编码真实 data/avatars。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    import modules.session as sess
    d = sess._avatar_dir()
    real = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(sess.__file__)), "data", "avatars"))
    assert os.path.abspath(d) != real, "session 头像目录仍指向真实 data/avatars"
    assert d.startswith(os.environ["SS_DATA_DIR"]), \
        "session 头像未隔离到临时目录（SS_DATA_DIR）"


def test_shepherd_note_dir_isolated():
    """shepherd_note 笔记目录须跟随 SS_DATA_DIR，而非硬编码真实 data/shepherd_notes.json。"""
    assert os.environ.get("SS_DATA_DIR"), "conftest 未启用数据隔离（SS_DATA_DIR 缺失）"
    import modules.shepherd_note as sn
    real = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(sn.__file__))), "data", "shepherd_notes.json"))
    assert os.path.abspath(sn.NOTE_FILE) != real, "shepherd_note 仍指向真实 data/shepherd_notes.json"
    assert sn.NOTE_DIR.startswith(os.environ["SS_DATA_DIR"]), \
        "shepherd_note 未隔离到临时目录（SS_DATA_DIR）"
