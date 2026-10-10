#!/usr/bin/env python3
"""shepherd-next-day-edge 命令行入口。

给定当日市场广度数据（涨跌家数、跌停/触及跌停家数等），调用情绪极值信号层判断
「次日行情方向」。诚实红线：只有「极端恐慌（跌停占比达历史前 10%）→ 次日反弹」这一条
有 walk-forward 统计依据（296 天，次日红盘 62.5% vs 基准 49.8%，z=+4.36），
其余日子一律弃权（abstain=True），绝不硬猜方向。

用法：
  python next_day_edge.py --today '{"up_count":...,"down_count":...,"limit_down":...}'
  python next_day_edge.py --auto            # 从 StockSignal 当日快照自动取数
  python next_day_edge.py --summary         # 输出校准证据链
  STOCKSIGNAL_ROOT=/path/to/StockSignal python next_day_edge.py --auto
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# StockSignal 仓库默认位置（单一真理源：优先用仓库里的 modules.sentiment_edge）
DEFAULT_ROOT = "E:/project/ks/StockSignal"


def _load_engine():
    """优先加载 StockSignal 权威模块；否则回退到本 skill 自带引擎。返回 (engine, live)。"""
    root = os.environ.get("STOCKSIGNAL_ROOT", DEFAULT_ROOT)
    if root and os.path.isdir(os.path.join(root, "modules")):
        sys.path.insert(0, root)
        try:
            import modules.sentiment_edge as se  # type: ignore
            return se, True
        except Exception:
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", "lib"))
    import edge_engine as ee  # type: ignore
    return ee, False


def _auto_fetch(engine) -> dict | None:
    """从 StockSignal 当日快照 / 最新 snapshots 取广度字段；取不到返回 None。"""
    root = os.environ.get("STOCKSIGNAL_ROOT", DEFAULT_ROOT)
    cands = [os.path.join(root, "data", "daily_snapshot.json")]
    snap_dir = os.path.join(root, "data", "snapshots")
    if os.path.isdir(snap_dir):
        files = sorted(glob.glob(os.path.join(snap_dir, "*.json")))
        if files:
            cands.append(files[-1])
    keys = ("up_count", "down_count", "flat_count", "limit_down",
            "touch_down", "limit_up", "hb_wave10")
    for c in cands:
        if not os.path.exists(c):
            continue
        try:
            d = json.load(open(c, encoding="utf-8"))
        except Exception:
            continue
        breadth = {k: d[k] for k in keys if k in d}
        ind = d.get("indicators") or {}
        for k in keys:
            if k in ind and k not in breadth:
                breadth[k] = ind[k]
        if breadth:
            return breadth
    return None


def main():
    ap = argparse.ArgumentParser(description="牧羊人情绪 → 次日行情判断")
    ap.add_argument("--today", help="JSON dict：up_count/down_count/flat_count/limit_down/touch_down/limit_up/hb_wave10")
    ap.add_argument("--auto", action="store_true", help="从 StockSignal 当日快照自动取数")
    ap.add_argument("--summary", action="store_true", help="输出校准证据链摘要而非判断")
    ap.add_argument("--root", help="StockSignal 仓库根目录（覆盖 STOCKSIGNAL_ROOT）")
    args = ap.parse_args()

    if args.root:
        os.environ["STOCKSIGNAL_ROOT"] = args.root

    engine, live = _load_engine()
    tag = "live:modules.sentiment_edge" if live else "bundled:edge_engine"

    if args.summary:
        out = engine.calibration_summary()
        out["_engine"] = tag
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    today = None
    if args.today:
        try:
            today = json.loads(args.today)
        except Exception as e:
            print(json.dumps({"available": False, "abstain": True, "error": f"--today 不是合法 JSON: {e}"},
                            ensure_ascii=False, indent=2))
            return
    elif not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                today = json.loads(raw)
            except Exception:
                pass
    if today is None and args.auto:
        today = _auto_fetch(engine)

    if today is None:
        print(json.dumps({"available": False, "abstain": True,
                          "statement": "未提供当日数据。请用 --today '{\"limit_down\":...,\"up_count\":...,\"down_count\":...}' 或 --auto。",
                          "_engine": tag}, ensure_ascii=False, indent=2))
        return

    res = engine.panic_reversal(today)
    res["_engine"] = tag
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
