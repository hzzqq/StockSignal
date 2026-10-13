# -*- coding: utf-8 -*-
"""
scripts/bench_cache_layers.py — 缓存层有效性实证（T-273A，离线负载模拟）。

目的：T-272① 铺好四层观测后，用受控负载量化「四道缓存闸门各自拦了什么」，
产出 reports/cache_layer_eval.json 供毕设「缓存层有效性实证」小节引用。

诚实边界（写进 JSON meta 与文档，绝不冒充生产数据）：
- 本脚本为**模拟负载**：请求序列由固定 seed 生成，非真实用户流量；
- 数据源全程 stub（_fetch_level 替换），**零网络**、离线可复现；
- 数据落盘走 SS_DATA_DIR 隔离目录，不碰真实 data/。

三个场景：
  1. l0_l1     —— 200 请求页面式负载（重复交互/轮询/冷启动混合）→ L0/L1 命中率；
                    另含「L0 重启模拟」子场景（清空内存层）→ L1 命中率；
  2. l5_fallback —— 四源全败（模拟网络断），预填 L1 → L5 陈旧兜底命中/拒绝分布；
  3. swr       —— market_drivers 过期缓存并发穿透 → SWR 立即返回/单飞去重/阻塞节省。

用法：
    python scripts/bench_cache_layers.py               # 默认 seed=20261013, n=200
    python scripts/bench_cache_layers.py --seed 42 --requests 500
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# SS_DATA_DIR 必须在 import fetcher/market_cache 之前生效（测试隔离同款机制）
_BENCH_DATA = Path(os.environ.get("SS_BENCH_DATA_DIR", "E:/tmp/bench_cache_data"))
os.environ["SS_DATA_DIR"] = str(_BENCH_DATA)
_BENCH_DATA.mkdir(parents=True, exist_ok=True)

import pandas as pd  # noqa: E402

import modules.fetcher as fm  # noqa: E402
import modules.market_drivers as md  # noqa: E402
from modules._feed_io import get_cache_metrics  # noqa: E402

REPORT = ROOT / "reports" / "cache_layer_eval.json"


def _snap_cache_metrics() -> dict:
    return {k: dict(v) for k, v in get_cache_metrics().items()}


def _metrics_diff(before: dict, after: dict) -> dict:
    out = {}
    for layer, m in after.items():
        b = before.get(layer, {"hits": 0, "misses": 0})
        out[layer] = {
            "hits": m["hits"] - b.get("hits", 0),
            "misses": m["misses"] - b.get("misses", 0),
        }
        out[layer]["calls"] = out[layer]["hits"] + out[layer]["misses"]
        out[layer]["hit_rate"] = (round(out[layer]["hits"] / out[layer]["calls"], 4)
                                  if out[layer]["calls"] else None)
    return out


def _fake_daily(code: str, days: int = 260) -> pd.DataFrame:
    """确定性合成行情（零网络）：date/open/close/high/low/volume。"""
    idx = pd.date_range(end="2026-10-12", periods=120, freq="D")
    base = 10.0 + (sum(ord(c) for c in code) % 90) / 10.0
    close = base + pd.Series(range(len(idx)), index=idx) * 0.01
    return pd.DataFrame({
        "date": idx.strftime("%Y-%m-%d"), "open": base, "close": close,
        "high": close + 0.1, "low": close - 0.1, "volume": 1000,
    })


class _SourceStub:
    """_fetch_level 替换桩：mode=ok 返回合成行情；mode=fail 四源全败。"""

    def __init__(self):
        self.mode = "ok"
        self.calls = 0
        self._orig = fm.StockFetcher._fetch_level

    def install(self, fetcher: "fm.StockFetcher"):
        stub = self

        def _patched(self, level, symbol, start, end, adjust):
            stub.calls += 1
            if stub.mode == "fail":
                return None, f"{level}: stub 模拟网络不可用"
            return _fake_daily(symbol), None

        fetcher.__class__._fetch_level = _patched

    def restore(self):
        fm.StockFetcher._fetch_level = self._orig


def scenario_l0_l1(n_requests: int, seed: int) -> dict:
    """场景 1：页面式负载 → L0/L1 命中率（含 L0 重启模拟子场景）。"""
    rng = random.Random(seed)
    hot_pool = [f"6000{i:02d}" for i in range(5)]      # 重复交互标的
    mid_pool = [f"0001{i:02d}" for i in range(20)]     # 轮询标的
    cold_pool = [f"300{i:03d}" for i in range(50)]     # 冷启动标的

    fetcher = fm.StockFetcher()
    stub = _SourceStub()
    stub.install(fetcher)
    fm._L0_CACHE.clear()  # 场景隔离：清空进程内存层
    try:
        before = _snap_cache_metrics()
        t0 = time.time()
        for _ in range(n_requests):
            r = rng.random()
            if r < 0.60:                       # 60% 重复交互（热池）
                sym = rng.choice(hot_pool)
            elif r < 0.90:                     # 30% 轮询（中池）
                sym = rng.choice(mid_pool)
            else:                              # 10% 冷启动
                sym = rng.choice(cold_pool)
            try:
                fetcher.get_daily(sym, start="2026-07-01", end="2026-10-12")
            except RuntimeError:
                pass                           # 失败如实计入场景 2，本场景 stub 全成功
        elapsed = round(time.time() - t0, 2)
        diff = _metrics_diff(before, _snap_cache_metrics())
        src_calls = stub.calls  # 竞速源调用总数 = L0 miss 数 × 4 源并行（stub 层计数）

        # 子场景：L0 重启模拟（清空内存层，等价进程重启）→ L1 命中率
        fm._L0_CACHE.clear()
        before2 = _snap_cache_metrics()
        for sym in (hot_pool + mid_pool):
            fetcher.get_daily(sym, start="2026-07-01", end="2026-10-12")
        diff2 = _metrics_diff(before2, _snap_cache_metrics())
    finally:
        stub.restore()
        fm._L0_CACHE.clear()

    return {
        "config": {"n_requests": n_requests, "seed": seed,
                   "mix": "repeat 60% / rotate 30% / cold 10%",
                   "pools": {"hot": 5, "mid": 20, "cold": 50}},
        "results": {
            "source_calls": src_calls,
            "source_calls_note": "stub 层计数 = L0 未命中数 × 四源并行竞速（每次 miss 4 个 level 调用）",
            "elapsed_s": elapsed,
            "layers": diff,
            "source_request_count": diff.get("L0", {}).get("calls", 0),
            "restart_sim": {
                "note": "清空 L0（等价进程重启）后重放 25 个已落盘标的 → L1 命中率",
                "layers": diff2,
            },
        },
    }


def scenario_l5_fallback() -> dict:
    """场景 2：四源全败 → L5 陈旧兜底命中/拒绝分布（诚实语义验证）。"""
    fetcher = fm.StockFetcher()
    stub = _SourceStub()
    stub.install(fetcher)
    stub.mode = "fail"
    fm._L0_CACHE.clear()
    # 预填 3 个标的的 L1（此前网络正常时落盘的「昨天的真数据」）
    cached_syms = ["600100", "600200", "600300"]
    conn = fetcher._get_conn()
    for sym in cached_syms:
        fetcher._write_cache(conn, "daily_cache",
                             f"daily_{sym}_2026-07-01_2026-10-12_qfq",
                             _fake_daily(sym))
    conn.close()

    ok_fb, no_fb = [], []
    try:
        for sym in cached_syms + ["999901", "999902", "999903"]:  # 后三个无缓存
            try:
                df = fetcher.get_daily(sym, start="2026-07-01", end="2026-10-12")
                if df is not None and len(df):
                    ok_fb.append(sym)
            except RuntimeError:
                no_fb.append(sym)
    finally:
        stub.restore()
        fm._L0_CACHE.clear()

    return {
        "config": {"cached_syms": cached_syms, "uncached_syms": 3,
                   "source_mode": "all_fail"},
        "results": {
            "fallback_hit": ok_fb, "fallback_miss": no_fb,
            "hit_count": len(ok_fb), "miss_count": len(no_fb),
            "note": "命中=拿陈旧数据（as_of 标注必带）；拒绝=宁可诚实失败不喂碎片",
        },
    }


def scenario_swr(concurrency: int = 16, fn_cost_s: float = 0.3) -> dict:
    """场景 3：market_drivers 过期缓存并发穿透 → SWR 收益量化。"""
    key = f"drivers_bench_{fn_cost_s}"
    with md._CACHE_LOCK:
        md._CACHE[key] = (time.time() - 700, ("old_df", {"old": True}))  # 过期 100s
    build_calls = {"n": 0}
    lock = threading.Lock()

    def _build():
        with lock:
            build_calls["n"] += 1
        time.sleep(fn_cost_s)  # 模拟网络取数耗时（生产实测 30-60s，此处缩小）
        return ("new_df", {"new": True})

    barrier = threading.Barrier(concurrency)
    results = {"stale_now": 0, "fresh_after": 0, "elapsed": []}

    def _user2(idx: int):
        barrier.wait()
        t0 = time.time()
        val, swr = md._cached_swr(md._CACHE_TTL, key, _build)
        dt = round(time.time() - t0, 3)
        with lock:
            results["elapsed"].append(dt)
            if swr is not None:
                results["stale_now"] += 1
            elif val == ("new_df", {"new": True}):
                results["fresh_after"] += 1

    threads = [threading.Thread(target=_user2, args=(i,)) for i in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 等后台刷新完成
    for _ in range(200):
        if key not in md._SWR_INFLIGHT:
            break
        time.sleep(0.05)
    with md._CACHE_LOCK:
        md._CACHE.pop(key, None)

    elapsed = sorted(results["elapsed"])
    n = len(elapsed)
    return {
        "config": {"concurrency": concurrency, "fn_cost_s": fn_cost_s,
                   "note": "fn 模拟耗时（生产同路径实测 30-60s），按比例外推阻塞节省"},
        "results": {
            "users": n,
            "got_stale_immediately": results["stale_now"],
            "got_fresh": results["fresh_after"],
            "build_executions": build_calls["n"],
            "singleflight_dedup_pct": round((1 - build_calls["n"] / max(n, 1)) * 100, 1),
            "p50_elapsed_s": elapsed[n // 2] if n else None,
            "max_elapsed_s": elapsed[-1] if n else None,
            "sync_equivalent_max_s": round(fn_cost_s, 2),
            "blocking_saved_note": "SWR 下全部用户亚秒返回旧值；同步语义下最后完成者需等完整 fn 耗时",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="缓存层有效性实证（离线模拟）")
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--requests", type=int, default=200)
    args = ap.parse_args()

    print(f"[bench] SS_DATA_DIR={_BENCH_DATA} seed={args.seed} requests={args.requests}")
    # Run 隔离（可复现承诺）：清空 bench 数据目录——L1 SQLite 是跨 run 持久的，
    # 不清空则上一轮残留会污染命中率（实测：残留使重启模拟从 24/25 变 25/25）
    shutil.rmtree(_BENCH_DATA, ignore_errors=True)
    _BENCH_DATA.mkdir(parents=True, exist_ok=True)
    s1 = scenario_l0_l1(args.requests, args.seed)
    print(f"[bench] 场景1 L0/L1 完成: L0 hit_rate={s1['results']['layers'].get('L0', {}).get('hit_rate')}")
    s2 = scenario_l5_fallback()
    print(f"[bench] 场景2 L5 兜底完成: hit={s2['results']['hit_count']} miss={s2['results']['miss_count']}")
    s3 = scenario_swr()
    print(f"[bench] 场景3 SWR 完成: 立即返回={s3['results']['got_stale_immediately']}/{s3['results']['users']}, "
          f"build 执行 {s3['results']['build_executions']} 次（单飞去重 {s3['results']['singleflight_dedup_pct']}%）")

    payload = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "seed": args.seed, "n_requests": args.requests,
            "data_dir": str(_BENCH_DATA),
            "honesty_note": "模拟负载（固定 seed 生成请求序列），非生产流量；数据源 stub 零网络，离线可复现",
            "code_version": "T-273A @ 7fe27f1+",
        },
        "scenarios": {"l0_l1": s1, "l5_fallback": s2, "swr": s3},
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[bench] 报告已写入 {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
