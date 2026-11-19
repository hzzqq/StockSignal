# -*- coding: utf-8 -*-
"""政策原文抓取 CLI。

用法：
    python -m scripts.refresh_policies [--detail] [--limit N] [--check]

--check 只探测（抓列表打印标题+日期），不写库。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import policy_fetch as pf  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="政策原文抓取与入库")
    ap.add_argument("--detail", action="store_true", help="同时抓详情页正文（增加请求数）")
    ap.add_argument("--limit", type=int, default=40, help="每条源最多取多少条（默认 40）")
    ap.add_argument("--check", action="store_true", help="只探测不写库，打印抓到的标题+日期")
    args = ap.parse_args(argv)

    if args.check:
        items, source, basis = pf.fetch_available(args.limit)
        print(json.dumps({
            "check": True,
            "source": source,
            "basis": basis,
            "count": len(items),
            "items": [
                {
                    "title": it.get("title"),
                    "publish_date": it.get("publish_date"),
                    "source": it.get("source"),
                    "source_url": it.get("source_url"),
                    "doc_number": it.get("doc_number"),
                }
                for it in items
            ],
        }, ensure_ascii=False, indent=2))
        return 0 if items else 2

    result = pf.refresh_policies(include_detail=args.detail, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result.get("written") or not result.get("failed")) else 2


if __name__ == "__main__":
    sys.exit(main())
