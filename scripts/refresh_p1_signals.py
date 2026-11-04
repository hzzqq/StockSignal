#!/usr/bin/env python
"""P1 信号单向同步（StockSignal 侧自托管副本维护）。

用法：
    python -m scripts.refresh_p1_signals            # 同步（幂等）
    python -m scripts.refresh_p1_signals --check    # 只报告不写盘（dry-run）

源目录发现走 modules.p1_signal.discover_source_dirs()（单一真理源，本脚本不抄绝对路径）。
写入目标默认 data/p1_signals/（相对仓库根计算）。

退出码：
    0  同步完成或无需同步
    1  发生写入错误
    2  全部候选结构无效 → 拒绝写入（保留既有副本）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.p1_sync import default_target_dir, sync_once  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P1 信号单向同步到 StockSignal 自托管副本")
    ap.add_argument("--check", action="store_true",
                    help="只报告计划，不写盘（dry-run）")
    ap.add_argument("--source", action="append", default=None,
                    help="覆盖源目录（可多次指定）；默认走 discover_source_dirs()")
    ap.add_argument("--target", default=None,
                    help="覆盖目标目录；默认 data/p1_signals/")
    args = ap.parse_args(argv)

    target = Path(args.target) if args.target else default_target_dir()
    srcs = args.source if args.source else None

    result = sync_once(source_dirs=srcs, target_dir=target, dry_run=bool(args.check))
    plan = result.get("plan", {})
    items = plan.get("items", [])

    print(f"目标目录：{plan.get('target_dir')}")
    print(f"候选文件：{plan.get('n_candidates')}　（源目录：{srcs or 'discover_source_dirs() 自动发现'}）")
    print("-" * 78)
    if not items:
        print("（无候选——检查 P1 是否已导出 signal_*.json，或设置 P1_SIGNAL_DIR / P1_SIGNAL_FALLBACK_DIR）")
    for it in items:
        print(f"  {str(it.get('model_key')):<22} {str(it.get('action')):<13} "
              f"latest_date={it.get('latest_date') or '—'}  {it.get('reason')}")
        if it.get("source"):
            print(f"      源：{it['source']}")
        print(f"      目标：{it.get('target')}")
    print("-" * 78)
    if result.get("errors"):
        for e in result["errors"]:
            print(f"  ⚠️ {e}")
    if args.check:
        print(f"[check 模式] 未写盘；计划中需复制 {sum(1 for i in items if i.get('action') == 'copy')} 个")
    else:
        print(f"已写入 {len(result.get('written') or [])} 个文件")
        for w in result.get("written") or []:
            print(f"  ✅ {w}")
    for s in result.get("skipped") or []:
        print(f"  ⏭️  {s}")

    if result.get("errors") and not result.get("written_any"):
        return 1
    if plan.get("all_invalid"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
