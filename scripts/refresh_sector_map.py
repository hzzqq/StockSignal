# -*- coding: utf-8 -*-
"""行业实体映射刷新 CLI（一期 90 个纯行业）。

用法（工作树根目录下）：
    python -m scripts.refresh_sector_map --check
    python -m scripts.refresh_sector_map --limit 2
    python -m scripts.refresh_sector_map --report
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import sector_map as sm  # noqa: E402
from modules import sector_map_fetch as fetcher  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="刷新全行业实体映射（一期 90 纯行业）")
    p.add_argument("--limit", type=int, default=90, help="最多处理多少个行业（硬上限 90）")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--resume", dest="resume", action="store_true", default=True,
                   help="只重抓 failed/stale/缺失行业（默认）")
    g.add_argument("--no-resume", dest="resume", action="store_false",
                   help="全部重抓")
    p.add_argument("--check", action="store_true",
                   help="只探测同花顺行业清单，不抓成分股、不写库")
    p.add_argument("--report", action="store_true", help="打印当前映射统计 JSON")
    args = p.parse_args(argv)

    if args.check:
        items = fetcher.fetch_industry_names()
        out = {
            "source": items[0].get("source", "none") if items else "none",
            "count": len(items),
            "sample": [str(i.get("name")) for i in items[:10]],
        }
    elif args.report:
        out = sm.sector_map_stats()
    else:
        out = fetcher.refresh_sector_map(limit=args.limit, resume=args.resume)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
