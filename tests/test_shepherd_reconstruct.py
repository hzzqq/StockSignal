# -*- coding: utf-8 -*-
"""牧羊人指标历史重构：_enrich_zt_from_cache 反推 zt_pool 指标的单元测试。

核心防护：回测历史上 zt_prev_ret / zt_fail_ratio / connect_hl 只来自近 ~30 天 zt_pool
接口（稀疏），导致 analyze_history 全期坍缩成「修复试探」。本模块从已落盘的 per-stock
缓存（含 limit_up/zt_fail_count/change_pct）反推这三个指标，覆盖全历史。

测试不联网：用合成缓存验证反推口径正确。
"""
import os
import tempfile

import pandas as pd
import pytest

from modules.shepherd_reconstruct import (
    _enrich_zt_from_cache, _board_limit_pct, _atomic_to_csv, _atomic_json_dump,
    _detect_limit, _aggregate_frames, _normalize_daily, _AGG_SPEC, reconstruct_breadth,
)


def _write_cache(cache_dir, name, rows):
    pd.DataFrame(rows).to_csv(os.path.join(cache_dir, f"{name}.csv"), index=False)


def _make_cache(cache_dir):
    # 股A：01-01/01-02 连板（limit_up 连续），01-03 炸板（触板未封）
    _write_cache(cache_dir, "A", [
        {"date": "2024-01-01", "up_count": 1, "down_count": 0, "flat_count": 0,
         "limit_up": 1, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 10.0, "close": 11},
        {"date": "2024-01-02", "up_count": 1, "down_count": 0, "flat_count": 0,
         "limit_up": 1, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 5.0, "close": 12},
        {"date": "2024-01-03", "up_count": 0, "down_count": 1, "flat_count": 0,
         "limit_up": 0, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 1, "hb_wave10": 0, "change_pct": -2.0, "close": 11},
    ])
    # 股B：01-02 炸板 2 只（这里用单股模拟炸板家数累加）
    _write_cache(cache_dir, "B", [
        {"date": "2024-01-01", "up_count": 0, "down_count": 0, "flat_count": 1,
         "limit_up": 0, "limit_down": 0, "touch_up": 0, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 1.0, "close": 10},
        {"date": "2024-01-02", "up_count": 0, "down_count": 0, "flat_count": 1,
         "limit_up": 0, "limit_down": 0, "touch_up": 1, "touch_down": 0,
         "zt_fail_count": 2, "hb_wave10": 0, "change_pct": 2.0, "close": 10},
        {"date": "2024-01-03", "up_count": 0, "down_count": 0, "flat_count": 1,
         "limit_up": 0, "limit_down": 0, "touch_up": 0, "touch_down": 0,
         "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 3.0, "close": 10},
    ])


def test_enrich_zt_fail_ratio():
    """炸板率 = Σ炸板 / (Σ涨停 + Σ炸板) × 100。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
        })
        out = _enrich_zt_from_cache(breadth, d)
        zfr = out["zt_fail_ratio"].tolist()
        assert zfr[0] == 0.0          # 01-01: 0/(1+0)
        assert abs(zfr[1] - 66.67) < 0.01   # 01-02: 2/(1+2)
        assert zfr[2] == 100.0        # 01-03: 1/(0+1)


def test_enrich_zt_prev_ret():
    """昨板溢价 = 昨日涨停股今日平均涨跌幅。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
        })
        out = _enrich_zt_from_cache(breadth, d)
        zpr = out["zt_prev_ret"].tolist()
        assert pd.isna(zpr[0])              # 首日前无「昨日涨停」
        assert abs(zpr[1] - 5.0) < 1e-6     # 01-01 涨停的 A，01-02 涨 5%
        assert abs(zpr[2] - (-2.0)) < 1e-6  # 01-02 涨停的 A，01-03 跌 -2%


def test_enrich_connect_hl():
    """最高连板数 = 逐股连板天数取最大。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
        })
        out = _enrich_zt_from_cache(breadth, d)
        chl = out["connect_hl"].tolist()
        assert chl[0] == 1   # A 单板
        assert chl[1] == 2   # A 两连板
        assert chl[2] == 0   # A 断板，无连板


def test_enrich_preserves_existing_zt_pool():
    """近期 zt_pool 已有真实值时不被反推值覆盖（仅 fillna）。"""
    with tempfile.TemporaryDirectory() as d:
        _make_cache(d)
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "limit_up": [1.0, 1.0, 0.0], "limit_down": [0.0, 0.0, 0.0],
            # 近期 zt_pool 真实值（如 01-02 真实炸板率 40%）
            "zt_fail_ratio": [None, 40.0, None],
            "zt_prev_ret": [None, 8.8, None],
            "connect_hl": [None, 7, None],
        })
        out = _enrich_zt_from_cache(breadth, d)
        # 01-02 保留真实值
        assert out["zt_fail_ratio"].iloc[1] == 40.0
        assert out["zt_prev_ret"].iloc[1] == 8.8
        assert out["connect_hl"].iloc[1] == 7
        # 01-01/01-03 由反推补齐
        assert out["zt_fail_ratio"].iloc[0] == 0.0
        assert out["connect_hl"].iloc[2] == 0


def test_enrich_empty_cache_is_noop():
    with tempfile.TemporaryDirectory() as d:
        breadth = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"]),
            "limit_up": [1.0], "limit_down": [0.0],
            "zt_fail_ratio": [None], "zt_prev_ret": [None], "connect_hl": [None],
        })
        out = _enrich_zt_from_cache(breadth, d)
        assert out["zt_fail_ratio"].isna().all()
        assert out["zt_prev_ret"].isna().all()


def test_board_limit_pct_bare_and_prefixed():
    # 带前缀（原口径）
    assert _board_limit_pct("sh600000") == 0.10   # 沪主板
    assert _board_limit_pct("sz000001") == 0.10   # 深主板
    assert _board_limit_pct("sh688981") == 0.20   # 科创板
    assert _board_limit_pct("sz300750") == 0.20   # 创业板
    assert _board_limit_pct("bj920001") == 0.30   # 北交所
    # 裸代码（修复前裸 688/300 被前缀逻辑漏掉 → 误判 10%）
    assert _board_limit_pct("600000") == 0.10     # 裸主板
    assert _board_limit_pct("688001") == 0.20     # 裸科创板
    assert _board_limit_pct("300750") == 0.20     # 裸创业板
    assert _board_limit_pct("830799") == 0.30     # 裸北交所 8 段
    assert _board_limit_pct("920002") == 0.30     # 裸北交所 920 段


def test_atomic_to_csv_no_tmp_lingering(tmp_path):
    """_atomic_to_csv 写完后临时文件须被 replace 掉，主文件可完整 reload。"""
    import os
    p = str(tmp_path / "cache" / "600000.csv")
    df = pd.DataFrame({"a": [1, 2, 3]})
    _atomic_to_csv(df, p)
    assert os.path.exists(p)
    assert not os.path.exists(p + ".tmp")
    assert list(pd.read_csv(p)["a"]) == [1, 2, 3]


def test_atomic_json_dump_no_tmp_lingering(tmp_path):
    """_atomic_json_dump 写完后临时文件须被 replace 掉，主文件可完整 load。"""
    import os
    p = str(tmp_path / "symbols.json")
    _atomic_json_dump(["600000", "000001"], p)
    assert os.path.exists(p)
    assert not os.path.exists(p + ".tmp")
    import json
    assert json.load(open(p, encoding="utf-8")) == ["600000", "000001"]


def _row(prev, close, high, low):
    return pd.Series({"prev_close": prev, "close": close, "high": high, "low": low})


def test_detect_limit_board_aware_cyb():
    """创业板 limit=20%：+20% 封板判涨停；+15% 不判涨停；盘中触板(high 到 20%)算 touch_up。
    锁死 R3 修复的二阶正确性：非主板须按真实幅度判定，否则涨停家数会虚高。
    """
    # 封死涨停：close=high=prev*1.20
    up_sealed = _row(10.0, 12.0, 12.0, 11.0)
    assert _detect_limit(up_sealed, 0.20) == (1, 0, 1, 0)
    # +15%（未到 20% 板）：不判涨停，也未触板（high 仅 15%）
    mid = _row(10.0, 11.5, 11.5, 11.0)
    assert _detect_limit(mid, 0.20) == (0, 0, 0, 0)
    # 盘中触涨停后回落：high 到 20% 但 close 仅 19%
    touched = _row(10.0, 11.9, 12.0, 11.5)
    assert _detect_limit(touched, 0.20) == (0, 0, 1, 0)


def test_detect_limit_board_aware_main_and_bse():
    """主板 limit=10% / 北交所 limit=30% 的触板判定同样正确。"""
    # 主板封死跌停：close=low=prev*0.90
    main_down = _row(10.0, 9.0, 9.5, 9.0)
    assert _detect_limit(main_down, 0.10) == (0, 1, 0, 1)
    # 北交所 +30% 封板
    bse_up = _row(10.0, 13.0, 13.0, 12.5)
    assert _detect_limit(bse_up, 0.30) == (1, 0, 1, 0)
    # 北交所 +20%（未到 30% 板）不判涨停
    bse_mid = _row(10.0, 12.0, 12.0, 11.0)
    assert _detect_limit(bse_mid, 0.30) == (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# R24 离线回归网：补全 _aggregate_frames / _normalize_daily / reconstruct_breadth
# 离线缓存主路径（之前仅覆盖了 _enrich_zt_from_cache / _board_limit_pct 等）。
# 目的：用合成数据锁死重构核心行为，不改网络即可抓出回归。
# ---------------------------------------------------------------------------

def test_aggregate_frames_sums_and_stats():
    """跨股横截面聚合：家数求和 + 中位数涨跌幅 + 均值股价 + 红盘率。"""
    f1 = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "up_count": [1, 0], "down_count": [0, 1], "flat_count": [0, 0],
        "limit_up": [1, 0], "limit_down": [0, 1], "touch_down": [0, 0],
        "zt_fail_count": [0, 1], "hb_wave10": [0, 1],
        "change_pct": [5.0, -3.0], "close": [12.0, 11.0],
    })
    f2 = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-03"],
        "up_count": [0, 1], "down_count": [1, 0], "flat_count": [0, 0],
        "limit_up": [0, 1], "limit_down": [1, 0], "touch_down": [0, 0],
        "zt_fail_count": [1, 0], "hb_wave10": [1, 0],
        "change_pct": [2.0, 4.0], "close": [10.0, 13.0],
    })
    out = _aggregate_frames([f1, f2])
    dates = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d").tolist()
    assert dates == ["2024-01-02", "2024-01-03"]
    r0 = out.iloc[0]  # 01-02：两股一涨一跌（互换）
    assert r0["up_count"] == 1 and r0["down_count"] == 1
    assert r0["limit_up"] == 1 and r0["limit_down"] == 1
    assert r0["zt_fail_count"] == 1 and r0["hb_wave10"] == 1
    # median(5.0, 2.0)=3.5 ; mean(12.0, 10.0)=11.0
    assert abs(r0["median_chg"] - 3.5) < 1e-6
    assert abs(r0["avg_price"] - 11.0) < 1e-6
    # 红盘率 = up/(up+down)*100 = 50
    assert abs(r0["red_ratio"] - 50.0) < 1e-6
    r1 = out.iloc[1]  # 01-03：一跌一涨
    assert r1["up_count"] == 1 and r1["down_count"] == 1
    assert abs(r1["median_chg"] - 0.5) < 1e-6   # median(-3.0, 4.0)
    assert abs(r1["avg_price"] - 12.0) < 1e-6   # mean(11.0, 13.0)


def test_aggregate_frames_empty_input():
    """空输入返回空 DataFrame，但列 schema 必须完整（防回归列结构崩坏）。"""
    out = _aggregate_frames([])
    assert out.empty
    expected_cols = ["date"] + list(_AGG_SPEC.keys()) + ["red_ratio"]
    for c in expected_cols:
        assert c in out.columns


def test_normalize_daily_prev_close_and_dropna():
    """新浪日线标准化：prev_close 取上一日 close；过滤缺 date/close 行；不足 2 行返回 None。"""
    raw = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "open": [10.0, 10.5, 11.0],
        "high": [10.5, 11.0, 11.5],
        "low": [9.8, 10.2, 10.8],
        "close": [10.2, 11.0, 11.3],
        "volume": [1000, 1100, 1200],
    })
    out = _normalize_daily(raw)
    assert out is not None
    # 首日 prev_close 为 NaN 被丢弃 → 剩 2 行
    assert len(out) == 2
    assert pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d").tolist() == \
        ["2024-01-02", "2024-01-03"]
    # prev_close 取上一日 close
    assert abs(out["prev_close"].iloc[0] - 10.2) < 1e-6
    assert abs(out["prev_close"].iloc[1] - 11.0) < 1e-6


def test_normalize_daily_invalid_returns_none():
    """非法输入（None / 单行）必须返回 None，不应抛异常或返回空壳。"""
    assert _normalize_daily(None) is None
    short = pd.DataFrame({"date": ["2024-01-01"], "close": [10.0]})
    assert _normalize_daily(short) is None


def test_reconstruct_breadth_reads_cache_offline(monkeypatch):
    """断点续跑主路径：缓存全命中时完全不联网，直接从缓存聚合出横截面。
    用 monkeypatch 把模块级 _CACHE_DIR 指到临时目录，避免污染真实 data/。
    """
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("modules.shepherd_reconstruct._CACHE_DIR", tmp)
    # 写两只「已聚合」缓存（与 _aggregate_cached 落盘 schema 一致）
    pd.DataFrame({
        "date": ["2024-03-01", "2024-03-02"],
        "up_count": [1, 0], "down_count": [0, 1], "flat_count": [0, 0],
        "limit_up": [1, 0], "limit_down": [0, 1], "touch_up": [1, 0], "touch_down": [0, 0],
        "zt_fail_count": [0, 1], "hb_wave10": [0, 1],
        "change_pct": [5.0, -3.0], "close": [12.0, 11.0],
    }).to_csv(os.path.join(tmp, "600000.csv"), index=False)
    pd.DataFrame({
        "date": ["2024-03-01", "2024-03-02"],
        "up_count": [0, 1], "down_count": [1, 0], "flat_count": [0, 0],
        "limit_up": [0, 1], "limit_down": [1, 0], "touch_up": [0, 1], "touch_down": [0, 0],
        "zt_fail_count": [1, 0], "hb_wave10": [1, 0],
        "change_pct": [2.0, 4.0], "close": [10.0, 13.0],
    }).to_csv(os.path.join(tmp, "000001.csv"), index=False)

    out = reconstruct_breadth("2024-03-01", "2024-03-02",
                              symbols=["600000", "000001"], use_cache=True)
    assert not out.empty
    # 两日，每日各 1 涨 1 跌
    assert len(out) == 2
    for _, r in out.iterrows():
        assert r["up_count"] == 1 and r["down_count"] == 1
        assert abs(r["red_ratio"] - 50.0) < 1e-6

# ---------------------------------------------------------------------------
# 2026-09-10 事故回归：缓存「截断 / 陈旧」双缺陷
#   ① 命中缓存直接 return 永不刷新 → 数据永久冻结在构建日；
#   ② 未命中时把「本次请求窗口」整份覆盖写盘 → 一次窄窗口运行把 17 年历史截成 6 行
#      （实测 3849/5548 只中招，data/shepherd_history.csv 家数低估 ~3 倍、跌停 ~10 倍）。
# 下列用例把「并集/合并」语义钉死，防止回退。
# ---------------------------------------------------------------------------

import pathlib  # noqa: E402

from modules.shepherd_reconstruct import (  # noqa: E402
    _aggregate_cached, _aggregate_worker, _merge_cache_frames, _SOCKET_TIMEOUT_SEC,
)


def _rows(dates, up=1, down=0):
    return [{"date": d, "up_count": up, "down_count": down, "flat_count": 0,
             "limit_up": 0, "limit_down": 0, "touch_up": 0, "touch_down": 0,
             "zt_fail_count": 0, "hb_wave10": 0, "change_pct": 0.0, "close": 10.0}
            for d in dates]


def test_merge_cache_frames_unions_and_prefers_new():
    """合并语义：旧缓存独有的日期保留，同日以新值覆盖。"""
    old = pd.DataFrame(_rows(["2024-01-01", "2024-01-02"]))
    new = pd.DataFrame(_rows(["2024-01-02", "2024-01-03"], up=9))
    out = _merge_cache_frames(old, new)
    assert out is not None
    assert len(out) == 3
    got = dict(zip(pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d"), out["up_count"]))
    assert got == {"2024-01-01": 1, "2024-01-02": 9, "2024-01-03": 9}
    assert pd.to_datetime(out["date"]).is_monotonic_increasing


def test_merge_cache_frames_none_inputs():
    """两端都可能为 None：全新取 new；拉取失败取 old；都空回 None。"""
    only_new = pd.DataFrame(_rows(["2024-01-01"]))
    assert len(_merge_cache_frames(None, only_new)) == 1
    assert len(_merge_cache_frames(only_new, None)) == 1
    assert _merge_cache_frames(None, None) is None
    assert _merge_cache_frames(pd.DataFrame(), pd.DataFrame()) is None


def test_narrow_window_refresh_does_not_truncate_history(monkeypatch):
    """★ 事故核心回归：窄窗口刷新后缓存必须是「旧历史 ∪ 新窗口」，而不是只剩窗口那两行。"""
    tmp = tempfile.mkdtemp()
    old_dates = ["2024-01-%02d" % d for d in range(1, 11)]
    _write_cache(tmp, "600000", _rows(old_dates))
    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock",
                        lambda sym, sd, ed: pd.DataFrame(_rows(["2024-01-11", "2024-01-12"])))

    out = _aggregate_cached("600000", "2007-01-01", "2024-01-12", tmp,
                            use_cache=True, refresh_days=5)
    assert out is not None and len(out) == 12, "返回的应是并集 12 行"
    on_disk = pd.read_csv(os.path.join(tmp, "600000.csv"))
    assert len(on_disk) == 12, "★ 落盘被截断：只剩 %d 行（旧实现只有 2 行）" % len(on_disk)
    assert pd.to_datetime(on_disk["date"]).min().strftime("%Y-%m-%d") == "2024-01-01"


def test_refresh_replaces_same_day_value(monkeypatch):
    """刷新窗口与旧缓存重叠时，同日必须取新值（否则无法修正当日错值）。"""
    tmp = tempfile.mkdtemp()
    _write_cache(tmp, "600000", _rows(["2024-01-01", "2024-01-02"], up=1))
    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock",
                        lambda sym, sd, ed: pd.DataFrame(_rows(["2024-01-02"], up=99)))

    out = _aggregate_cached("600000", "2024-01-01", "2024-01-02", tmp,
                            use_cache=True, refresh_days=5)
    got = dict(zip(pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d"), out["up_count"]))
    assert got["2024-01-02"] == 99 and got["2024-01-01"] == 1


def test_fetch_failure_preserves_existing_cache(monkeypatch):
    """拉取失败（返回 None）绝不能清空已有历史。"""
    tmp = tempfile.mkdtemp()
    _write_cache(tmp, "600000", _rows(["2024-01-01", "2024-01-02", "2024-01-03"]))
    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock",
                        lambda sym, sd, ed: None)

    out = _aggregate_cached("600000", "2024-01-04", "2024-01-05", tmp,
                            use_cache=True, refresh_days=5)
    assert out is not None and len(out) == 3
    assert len(pd.read_csv(os.path.join(tmp, "600000.csv"))) == 3


def test_cache_hit_fast_path_skips_fetch(monkeypatch):
    """refresh_days=0 且已有缓存 → 走快速路径，一次网络都不打。"""
    tmp = tempfile.mkdtemp()
    _write_cache(tmp, "600000", _rows(["2024-01-01"]))

    def _boom(*a, **k):
        raise AssertionError("快速路径不该触发拉取")

    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock", _boom)
    out = _aggregate_cached("600000", "2007-01-01", "2024-01-02", tmp,
                            use_cache=True, refresh_days=0)
    assert len(out) == 1


class _InlineExecutor:
    """把进程池换成同进程执行，便于用 monkeypatch 观察 worker 调用（spawn 子进程看不到 patch）。"""

    instances = []

    def __init__(self, max_workers=None):
        self.max_workers = max_workers
        self.shutdown_called_with = None
        _InlineExecutor.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def shutdown(self, wait=True, cancel_futures=False):
        # 生产代码走 `shutdown(wait=False, cancel_futures=True)` 防死锁，
        # 替身必须同样提供该接口，否则「替身与真实池不同构」会掩盖真实调用。
        self.shutdown_called_with = {"wait": wait, "cancel_futures": cancel_futures}

    def submit(self, fn, arg):
        class _F:
            def __init__(self, r):
                self._r = r

            def result(self, timeout=None):
                return self._r

            def done(self):
                return True

        return _F(fn(arg))


class _CfShim:
    ProcessPoolExecutor = _InlineExecutor

    class TimeoutError(Exception):
        pass

    @staticmethod
    def as_completed(futures, timeout=None):
        # 真实 as_completed 支持 timeout，生产代码现在会传总墙钟上限。
        return list(futures)


def _patch_inline_pool(monkeypatch):
    monkeypatch.setattr("modules.shepherd_reconstruct.cf", _CfShim)


def test_reconstruct_breadth_refresh_days_visits_cached_symbols(monkeypatch, tmp_path):
    """★ refresh_days>0 时，已缓存的标的也必须被刷新（否则数据永久冻结在构建日）。"""
    _write_cache(str(tmp_path), "600000", _rows(["2024-01-01"]))
    _write_cache(str(tmp_path), "000001", _rows(["2024-01-01"]))
    monkeypatch.setattr("modules.shepherd_reconstruct._CACHE_DIR", str(tmp_path))
    _patch_inline_pool(monkeypatch)

    calls = []

    def _fake(sym, sd, ed):
        calls.append(sym)
        return pd.DataFrame(_rows(["2024-01-02"]))

    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock", _fake)
    out = reconstruct_breadth("2024-01-01", "2024-01-02", symbols=["600000", "000001"],
                              use_cache=True, refresh_days=5)
    assert sorted(calls) == ["000001", "600000"], "已缓存标的被跳过，实得 %s" % calls
    assert not out.empty and len(out) == 2


def test_reconstruct_breadth_without_refresh_skips_cached_symbols(monkeypatch, tmp_path):
    """refresh_days=0 时保留断点续跑语义：已缓存标的不再拉取。"""
    _write_cache(str(tmp_path), "600000", _rows(["2024-01-01"]))
    monkeypatch.setattr("modules.shepherd_reconstruct._CACHE_DIR", str(tmp_path))
    _patch_inline_pool(monkeypatch)

    calls = []
    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock",
                        lambda sym, sd, ed: calls.append(sym) or pd.DataFrame(_rows(["2024-01-01"])))
    reconstruct_breadth("2024-01-01", "2024-01-02", symbols=["600000"],
                        use_cache=True, refresh_days=0)
    assert calls == []


def test_worker_sets_socket_timeout():
    """worker 必须自设 socket 超时，否则网络挂起时永久阻塞、进程池退出被吊死。"""
    import socket
    prev = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(None)
        _aggregate_worker(("600000", "2024-01-01", "2024-01-02", tempfile.mkdtemp(), True))
        assert socket.getdefaulttimeout() == _SOCKET_TIMEOUT_SEC
    finally:
        socket.setdefaulttimeout(prev)


def test_worker_accepts_legacy_5_tuple(monkeypatch):
    """兼容旧 5 元组签名（老脚本可能仍这么传）。"""
    seen = {}
    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_cached",
                        lambda sym, sd, ed, cd, uc, rd=0: seen.update(rd=rd) or pd.DataFrame())
    _aggregate_worker(("600000", "2024-01-01", "2024-01-02", tempfile.mkdtemp(), True))
    assert seen.get("rd") == 0


def test_aggregate_cached_writes_merged_frame_not_raw_window():
    """AST 不变量守卫：写盘对象必须是 _merge_cache_frames(...) 的结果，绝不能是原始窗口。"""
    import ast
    src = pathlib.Path("modules/shepherd_reconstruct.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "_aggregate_cached")

    merged_vars, written_args = set(), []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Name) and f.id == "_merge_cache_frames":
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        merged_vars.add(t.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "_atomic_to_csv" and node.args:
            written_args.append(node.args[0])
    assert merged_vars, "未找到 _merge_cache_frames 的赋值，合并语义可能已被移除"
    assert written_args, "未找到 _atomic_to_csv 调用"
    for a in written_args:
        assert isinstance(a, ast.Name) and a.id in merged_vars, \
            "写盘的不是合并结果（AST 节点 %s），存在截断历史的风险" % type(a).__name__
        assert a.id != "new", "写盘对象是原始新窗口 → 必然截断历史"


def test_reconstruct_breadth_exposes_refresh_days_param():
    """入口参数存在性守卫：CLI/脚本靠它做增量刷新，不能悄悄删掉。"""
    import inspect
    from modules.shepherd_reconstruct import build_shepherd_history
    for fn in (reconstruct_breadth, build_shepherd_history):
        assert "refresh_days" in inspect.signature(fn).parameters, fn.__name__


def test_reconstruct_breadth_never_shuts_down_with_wait_true(monkeypatch, tmp_path):
    """★ 死锁守卫：进程池必须以 shutdown(wait=False) 放手。

    旧写法是 `with ProcessPoolExecutor(...) as ex`，退出时走 `shutdown(wait=True)`；
    worker 一旦卡在**非 socket 阻塞**（V8 解码 / 代理连接不遵守超时），future 永不完成，
    as_completed 永久阻塞、with 退出又 wait=True —— 主进程**永不返回**。
    2026-09-10 实际踩过：26 分 44 秒零进度，正是老板明令禁止的「长时间易卡死」模式。
    """
    _InlineExecutor.instances.clear()
    _write_cache(str(tmp_path), "600000", _rows(["2024-01-01"]))
    monkeypatch.setattr("modules.shepherd_reconstruct._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("modules.shepherd_reconstruct._aggregate_one_stock",
                        lambda *a, **k: pd.DataFrame(_rows(["2024-01-02"])))
    _patch_inline_pool(monkeypatch)

    reconstruct_breadth("2024-01-01", "2024-01-02", max_workers=1,
                        symbols=["600000"], refresh_days=7)

    assert _InlineExecutor.instances, "未创建进程池"
    called = _InlineExecutor.instances[-1].shutdown_called_with
    assert called is not None, "进程池未显式 shutdown（退回 with 退出即 wait=True 的老坑）"
    assert called["wait"] is False, \
        "shutdown(wait=True) 会让卡死的 worker 永久吊死主进程"
    assert called["cancel_futures"] is True, \
        "未取消排队任务：卡死时剩余任务仍占着 worker 不放"


def test_reconstruct_breadth_caps_total_fetch_wall_clock(monkeypatch, tmp_path):
    """★ 总墙钟上限守卫：抓取阶段必须带 timeout 的 as_completed，不能无限等。

    仅靠 `fut.result(timeout=60)` 无效——它只对**已完成**的 future 计时。
    """
    import inspect
    src = inspect.getsource(reconstruct_breadth)
    assert "as_completed(futures, timeout=" in src, "抓取阶段缺少总墙钟上限"
    assert "_FETCH_TIMEOUT_SEC" in src, "上限未走可配置常量"


def test_reconstruct_breadth_filters_cache_to_window_before_concat(monkeypatch, tmp_path):
    """★ OOM 守卫：窄窗口请求必须先裁剪缓存再累积，不得物化全部历史。

    实测事故：缓存是「每只股票全史」（5548 只共 355 万行 / 200MB），旧实现无条件
    把全部行 read 进 frames 再 concat —— 只算近 27 天却物化 17 年全史，峰值内存 GB 级，
    进程被 OS 杀掉且**来不及打任何 traceback**（表现为抓取完成 5500/5548 后日志永久静默）。
    """
    from modules import shepherd_reconstruct as sr

    hist = ["2024-01-%02d" % d for d in range(1, 21)]          # 区间外（20 天）
    win = ["2025-06-01", "2025-06-02"]                        # 区间内（2 天）
    for sym in ("600000", "000001"):
        _write_cache(str(tmp_path), sym, _rows(hist + win))
    monkeypatch.setattr(sr, "_CACHE_DIR", str(tmp_path))

    seen = {}
    real_agg = sr._aggregate_frames

    def spy(frames):
        seen["rows"] = sum(len(f) for f in frames)
        seen["n_files"] = len(frames)
        return real_agg(frames)

    monkeypatch.setattr(sr, "_aggregate_frames", spy)
    out = sr.reconstruct_breadth("2025-06-01", "2025-06-02", max_workers=1,
                                 symbols=["600000", "000001"], use_cache=True,
                                 refresh_days=0)

    assert seen.get("n_files") == 2, "缓存文件未被全部纳入"
    assert seen["rows"] == 4, (
        "★ 进入聚合的行数是 %d，应为 4（2 只 × 窗口内 2 天）——"
        "说明区间外历史仍被读进内存，窄窗口刷新会重现 OOM" % seen["rows"])
    assert len(out) == 2 and out["up_count"].sum() == 4


def test_enrich_zt_from_cache_streak_seeded_by_preceding_history(tmp_path):
    """★ 连板数必须由全量历史递推，不能因为窗口裁剪被截断成 1 板。

    反推函数为了性能会按需裁剪日期，但**连板天数是跨日递推量**：
    若先裁剪再算 streak，窗口首日的 6 连板会被误读成 1 板（数据错但不报错）。
    """
    from modules.shepherd_reconstruct import _enrich_zt_from_cache

    rows = _rows(["2025-06-%02d" % d for d in range(1, 7)])
    for r in rows:
        r["limit_up"] = 1
    _write_cache(str(tmp_path), "600000", rows)

    breadth = pd.DataFrame({"date": [pd.Timestamp("2025-06-06")]})
    out = _enrich_zt_from_cache(breadth, str(tmp_path))
    got = int(out.loc[0, "connect_hl"])
    assert got == 6, "连板被截断成 %d 板（应为 6）——streak 必须在裁剪前算" % got


def test_enrich_zt_from_cache_never_fabricates_missing_dates(tmp_path):
    """缺数据不编造：分母为 0 的红盘/炸板比率给 None，而不是 0。"""
    from modules.shepherd_reconstruct import _enrich_zt_from_cache

    rows = _rows(["2025-06-02", "2025-06-03"])
    rows[0]["limit_up"] = 1
    rows[0]["zt_fail_count"] = 2
    _write_cache(str(tmp_path), "600000", rows)

    breadth = pd.DataFrame({"date": [pd.Timestamp("2025-06-03"),
                                     pd.Timestamp("2025-06-04")]})
    out = _enrich_zt_from_cache(breadth, str(tmp_path))
    assert pd.isna(out.loc[0, "zt_fail_ratio"]), "无涨停/炸板时不该编造 0"
    assert int(out.loc[0, "connect_hl"]) == 0
    assert pd.isna(out.loc[1, "zt_fail_ratio"]), "无该日数据时不该编造 0"


def test_enrich_zt_from_cache_is_bounded_by_needed_dates():
    """性能不变量守卫：必须先按 need 裁剪再聚合。

    旧实现对每个缓存文件做 4 次 Python 级 groupby().items() 迭代 ——
    5548 文件 × ~4800 日期 × 4 ≈ 1.06 亿次，单这一段要十几分钟，
    日志表现为「再也不动」，与死锁无法区分。必须保持按需裁剪 + 进度日志。
    """
    import inspect
    from modules.shepherd_reconstruct import _enrich_zt_from_cache
    src = inspect.getsource(_enrich_zt_from_cache)
    assert "isin(need)" in src, "缺少按需日期裁剪 → 会重现上亿次迭代的性能坑"
    assert "进度 %d/%d" in src, "缺少进度日志 → 长耗时无法与死锁区分"
