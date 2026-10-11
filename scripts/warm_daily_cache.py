#!/usr/bin/env python
"""日线缓存预热 CLI（T-250，缓存加固 B 的脚本入口）。

用法：
    python scripts/warm_daily_cache.py                # 预热候选池 400 只（引擎同参）
    python scripts/warm_daily_cache.py --limit 200    # 缩小宇宙
    python scripts/warm_daily_cache.py --dry-run      # 只打印计划，不拉取
    python scripts/warm_daily_cache.py --timeout 600  # 收紧硬超时

诚实语义见 modules/cache_warmer.py；调度挂载见 backend/recommend_scheduler.py
（15:30 后荐股生成前置调用，SS_CACHE_WARM=0 可关）。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.cache_warmer import _engine_params, warm_universe  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="日线缓存预热（荐股引擎同参）")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=900.0,
                    help="整体硬超时秒（cache.db 即检查点，重跑续传）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    start, end, adjust = _engine_params()
    print(f"[warm] 计划：候选池 {args.limit} 只 | start={start} end={end} adjust={adjust}"
          f"（与荐股引擎逐字节同参，保证 cache_key 命中）")
    if args.dry_run:
        print("[warm] --dry-run：不拉取，仅打印计划。")
        return 0

    def progress(done, total):
        if done % 50 == 0 or done == total:
            print(f"[warm] {done}/{total}", flush=True)

    res = warm_universe(limit=args.limit, max_workers=args.workers,
                        timeout=args.timeout, progress=progress)
    print(f"[warm] 结果：warmed={res['warmed']} failed={res['failed']} "
          f"total={res['total']} {res['elapsed_s']}s"
          f"{' | ' + res['reason'] if res.get('reason') else ''}")
    if res["failed_codes"]:
        print(f"[warm] 失败明细（诚实计数）: {res['failed_codes'][:20]}"
              f"{'...' if len(res['failed_codes']) > 20 else ''}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
