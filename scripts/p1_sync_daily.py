#!/usr/bin/env python
"""P1 信号同步日常化 CLI（与守护线程同一套判定，避免双口径）。

用法：
  python scripts/p1_sync_daily.py                 # 跑一轮（同步 + 体检 + 落档）
  python scripts/p1_sync_daily.py --status        # 只看健康，不跑同步
  python scripts/p1_sync_daily.py --dry-run       # 只算计划，不写副本也不写快照
  python scripts/p1_sync_daily.py --loop --interval 60   # 前台常驻（调试用）
  python scripts/p1_sync_daily.py --json          # 机器可读输出

退出码（供计划任务/巡检脚本判定）：
  0 = 本轮 ok / 健康 ok；1 = warn（有红项但未失效）；2 = dead（无副本/全部结构不合格）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.p1_sync_health import (  # noqa: E402
    DEFAULT_INTERVAL_MINUTES,
    assess_p1_sync_health,
    run_sync_cycle,
    status_path,
)

_EXIT_BY_STATUS = {"ok": 0, "warn": 1, "dead": 2}


def _fmt_health(h: dict) -> str:
    lines = [f"P1 自托管副本健康：{h.get('status')} — {h.get('message')}",
             f"目录：{h.get('signal_dir')}",
             f"最新数据日：{h.get('latest') or '—'}（滞后 {h.get('age_days')} 天）",
             f"模型：{', '.join(h.get('models') or []) or '（无）'}"]
    for r in h.get("rows") or []:
        flags = ("结构✅" if r.get("structural_ok") else "结构❌") + \
                ("新鲜✅" if r.get("freshness_ok") else "新鲜⚠️")
        errs = f" | {'; '.join(r.get('errors') or [])}" if r.get("errors") else ""
        lines.append(f"  - {r.get('file')}（{r.get('model_key')}）{flags}"
                     f" latest={r.get('latest_date') or '—'}{errs}")
    if h.get("last_run_at"):
        lines.append(f"上次运行：{h.get('last_run_at')}（ok={h.get('last_run_ok')}）")
    return "\n".join(lines)


def _fmt_cycle(s: dict) -> str:
    h = s.get("health") or {}
    counts = s.get("counts") or {}
    lines = [f"本轮：{'ok' if s.get('ok') else 'FAIL'}（mode={s.get('mode')}，"
             f"written={len(s.get('written') or [])}）",
             f"计划：copy={counts.get('copy', 0)} unchanged={counts.get('unchanged', 0)} "
             f"target_newer={counts.get('target_newer', 0)} skip={counts.get('skip', 0)}"
             f"{'（全部候选无效，拒绝写入）' if s.get('all_invalid') else ''}",
             f"健康：{h.get('status')} — {h.get('message')}"]
    for e in s.get("errors") or []:
        lines.append(f"错误：{e}")
    if s.get("dry_run"):
        lines.append("dry-run：未写副本、未写状态快照")
    else:
        lines.append(f"状态快照：{status_path(s.get('target_dir'))}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P1 信号同步日常化（同步 + 体检 + 状态快照）")
    ap.add_argument("--status", action="store_true", help="只打印健康，不跑同步")
    ap.add_argument("--loop", action="store_true", help="前台常驻循环")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MINUTES,
                    help=f"循环间隔分钟（默认 {DEFAULT_INTERVAL_MINUTES}）")
    ap.add_argument("--dry-run", action="store_true", help="只算计划，不写盘")
    ap.add_argument("--source", action="append", default=None, help="源目录（可多次）")
    ap.add_argument("--target", default=None, help="目标目录（默认 data/p1_signals）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.status:
        h = assess_p1_sync_health(target_dir=args.target)
        print(json.dumps(h, ensure_ascii=False, indent=2) if args.json else _fmt_health(h))
        return _EXIT_BY_STATUS.get(str(h.get("status")), 1)

    if args.loop:
        while True:
            snap = run_sync_cycle(source_dirs=args.source, target_dir=args.target,
                                  dry_run=args.dry_run, mode="loop",
                                  interval_minutes=args.interval)
            print(json.dumps(snap, ensure_ascii=False, indent=2) if args.json else _fmt_cycle(snap))
            time.sleep(max(5, args.interval) * 60)

    snap = run_sync_cycle(source_dirs=args.source, target_dir=args.target,
                          dry_run=args.dry_run, mode="once")
    print(json.dumps(snap, ensure_ascii=False, indent=2) if args.json else _fmt_cycle(snap))
    if not snap.get("ok"):
        return 2
    return _EXIT_BY_STATUS.get(str((snap.get("health") or {}).get("status")), 1)


if __name__ == "__main__":
    raise SystemExit(main())
