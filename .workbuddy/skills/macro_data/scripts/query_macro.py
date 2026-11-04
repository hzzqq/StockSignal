#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI for the macro_data skill.

Invokes StockSignal's ``modules.macro_data`` with honest semantics:
unavailable indicators return None, never fabricated.
"""
import argparse
import json
import os
import sys

DEFAULT_ROOT = os.environ.get("STOCKSIGNAL_ROOT", r"E:/project/ks/StockSignal")


def _load():
    root = DEFAULT_ROOT
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import modules.macro_data as md  # noqa: F401
        return md
    except Exception as e:  # noqa: BLE001
        print(json.dumps({
            "available": False,
            "error": f"无法加载 StockSignal 仓库: {e}",
            "hint": "设置环境变量 STOCKSIGNAL_ROOT 指向 StockSignal 仓库根目录",
        }, ensure_ascii=False))
        sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="宏观指标查询（诚实口径）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("indicator", help="单个指标")
    p1.add_argument("key")

    p2 = sub.add_parser("region", help="按区域取（国内/全球）")
    p2.add_argument("region", choices=["国内", "全球"])

    sub.add_parser("all", help="全部指标")
    sub.add_parser("regime", help="全球宏观风险偏好评分")

    args = ap.parse_args()
    md = _load()

    if args.cmd == "indicator":
        out = md.fetch_indicator(args.key)
    elif args.cmd == "region":
        out = md.fetch_by_region(args.region)
    elif args.cmd == "all":
        out = md.fetch_all()
    else:
        out = md.global_regime_score()

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
