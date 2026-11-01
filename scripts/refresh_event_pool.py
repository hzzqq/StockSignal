"""刷新事件因子多头池：优先从 P1-QuantFactor 实时信号导出，缺则保留离线快照。

用法：
    python scripts/refresh_event_pool.py                # dry-run（默认）
    python scripts/refresh_event_pool.py --apply        # 真正落盘
    P1_PROJECT_DIR=/path/to/P1 python scripts/refresh_event_pool.py --apply

说明：
    - 仅当 P1 已运行阶段6导出（data/P1/processed/signals/signal_*.json 存在且有效）
      时才覆盖 data/event_pool_brief.json；
    - 离线环境通常无该产物，此时优雅降级、保留既有离线快照，属预期行为。
环境变量：
    P1_PROJECT_DIR        指向 P1-QuantFactor 根目录；设置后**优先**使用
    P1_SIGNAL_DIR         直接指定信号目录（最高优先，见 modules.p1_signal）
    P1_SIGNAL_FALLBACK_DIR  P1 产出目录的覆盖口（默认 E:/project/sj/data/P1/processed/signals）
    均未设置时：按 modules.p1_signal.discover_source_dirs() 的候选顺序取**第一个真实存在**
    的目录（本仓 data/p1_signals 通常命中，故无 P1 仓也能刷新）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.shepherd_ladder import refresh_event_pool_from_p1  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true",
                    help="真正落盘（默认 dry-run 只打印不落盘）")
    args = ap.parse_args()

    st = refresh_event_pool_from_p1(dry_run=not args.apply)
    mode = "DRY-RUN" if not args.apply else "APPLY"
    if st["refreshed"]:
        dr_suffix = "（dry-run，未落盘）" if st.get("dry_run") else ""
        print(f"[{mode}] ✅ 已从 P1 实时刷新事件池{dr_suffix}："
              f"{st['date']} · {st['count']} 只 · {st['source']}")
        if st.get("stale"):
            print("   ⚠️ 注意：P1 信号 latest_date 已超过30天，时效性存疑。")
        return 0
    print(f"[{mode}] ℹ️ 未使用 P1 实时信号（{st.get('reason') or '未知'}）："
          f"{st.get('note') or ''}")
    print("   当前保留 data/event_pool_brief.json 离线快照不变。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
