#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI for the event_factor skill.

Invokes StockSignal's ``modules.event_factor`` with honest semantics:
if data is unavailable, prints ``available=False`` and the reason — never fabricates.
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
        import modules.event_factor as ef  # noqa: F401
        return ef
    except Exception as e:  # noqa: BLE001
        print(json.dumps({
            "available": False,
            "error": f"无法加载 StockSignal 仓库: {e}",
            "hint": "设置环境变量 STOCKSIGNAL_ROOT 指向 StockSignal 仓库根目录",
        }, ensure_ascii=False))
        sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="事件因子查询（诚实口径）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("symbol", help="查询单个标的事件因子")
    p1.add_argument("symbol")
    p1.add_argument("--model", default="ev")
    p1.add_argument("--voice-user", default=None,
                     help="启用第五源：仅读取该登录用户自己的语音事件（隐私闸门）")
    p1.add_argument("--include-macro", action="store_true",
                     help="附加全球宏观上下文（联网取真实数据，不参与评分）")

    p2 = sub.add_parser("longlist", help="事件驱动看多榜")
    p2.add_argument("--top-n", type=int, default=20)
    p2.add_argument("--model", default="ev")

    args = ap.parse_args()
    ef = _load()

    if args.cmd == "symbol":
        out = ef.get_event_factor(
            args.symbol, model=args.model,
            voice_user=args.voice_user,
            include_macro=args.include_macro,
        )
    else:
        out = ef.event_driven_long_list(top_n=args.top_n, model=args.model)

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
