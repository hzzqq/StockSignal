"""刷新事件因子多头池：优先从 P1-QuantFactor 实时信号导出，缺则保留离线快照。

用法：
    python scripts/refresh_event_pool.py
    P1_PROJECT_DIR=/path/to/P1-QuantFactor python scripts/refresh_event_pool.py

说明：
    - 仅当 P1 已运行阶段6导出（data/P1/processed/signals/signal_*.json 存在且有效）
      时才覆盖 data/event_pool_brief.json；
    - 离线环境通常无该产物，此时优雅降级、保留既有离线快照，属预期行为。
环境变量：
    P1_PROJECT_DIR  指向 P1-QuantFactor 根目录（缺省用同机默认布局）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.shepherd_ladder import refresh_event_pool_from_p1  # noqa: E402


def main() -> int:
    st = refresh_event_pool_from_p1()
    if st["refreshed"]:
        print(f"✅ 已从 P1 实时刷新事件池：{st['date']} · {st['count']} 只 · {st['source']}")
        if st.get("stale"):
            print("⚠️ 注意：P1 信号 latest_date 已超过30天，时效性存疑。")
        return 0
    print("ℹ️ 未使用 P1 实时信号（" + (st.get("reason") or "未知") + "）：" + (st.get("note") or ""))
    print("   当前保留 data/event_pool_brief.json 离线快照不变。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
