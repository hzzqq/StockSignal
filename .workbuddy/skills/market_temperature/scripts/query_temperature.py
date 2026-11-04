#!/usr/bin/env python
"""query_temperature.py — 查询 A 股市场情绪温度（0-100 + 五档 + 极端区 + 相似日）。

用法：
    python scripts/query_temperature.py
    python scripts/query_temperature.py --stock-signal-root E:/project/ks/StockSignal
    python scripts/query_temperature.py --today-json today_breadth.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

from temperature_engine import compute, load_today_json  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A 股市场情绪温度计查询")
    ap.add_argument("--stock-signal-root", default=None,
                    help="StockSignal 仓库根目录（默认自动发现）")
    ap.add_argument("--today-json", default=None,
                    help="本地当日广度 JSON 文件路径")
    ap.add_argument("--hist-days", type=int, default=2000,
                    help="历史分位回稳天数（默认 2000）")
    args = ap.parse_args(argv)

    today = None
    if args.today_json:
        try:
            today = load_today_json(args.today_json)
        except Exception as e:
            print(json.dumps({"available": False,
                              "reason": f"当日广度 JSON 读取失败：{e}"},
                             ensure_ascii=False, indent=2))
            return 2

    result = compute(today=today, hist_days=args.hist_days,
                     stock_signal_root=args.stock_signal_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
