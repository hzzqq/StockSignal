"""scripts/p1_signal_quality_report.py —— P1 信号数据质量巡检 CLI（方向 3）。

用法：
    python scripts/p1_signal_quality_report.py                 # 扫 data/p1_signals + 心跳，Markdown 报告
    python scripts/p1_signal_quality_report.py --json         # JSON 输出（供自动化消费）
    python scripts/p1_signal_quality_report.py --dir PATH     # 指定目录
    python scripts/p1_signal_quality_report.py --heartbeat PATH --no-heartbeat  # 心跳日志路径 / 跳过
    python scripts/p1_signal_quality_report.py --max-age ens=3 --max-age fusion=15  # 覆盖 SLA
    python scripts/p1_signal_quality_report.py --heartbeat-max-idle 4  # 心跳停更 SLA（自然日）

退出码：0 = 全绿（无红灯）；1 = 存在红灯（结构/新鲜度/心跳）。黄灯（ens↔baseline 对齐）不阻断。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import p1_signal_quality as q


def parse_max_age(pairs: list) -> dict:
    out = {}
    for kv in pairs or []:
        k, _, v = kv.partition("=")
        if not k or not v:
            raise SystemExit(f"--max-age 需 k=v 格式（如 ens=3），收到: {kv!r}")
        out[k.strip()] = int(v.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="P1 信号数据质量体检")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_dir = os.path.join(repo_root, "data", "p1_signals")
    default_hb = os.path.join(repo_root, "logs", "p1_push_heartbeat.log")
    ap.add_argument("--dir", default=default_dir, help="信号目录（默认 data/p1_signals）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--max-age", action="append", metavar="K=V", help="按模型覆盖 SLA 天数，可多次")
    ap.add_argument("--ens-min-jaccard", type=float, default=q.ENS_MIN_JACCARD, help="ens↔baseline 对齐阈值")
    ap.add_argument("--heartbeat", default=default_hb, help="推送链心跳日志路径（默认 logs/p1_push_heartbeat.log）")
    ap.add_argument("--no-heartbeat", action="store_true", help="跳过心跳体检")
    ap.add_argument("--heartbeat-max-idle", type=int, default=None, help="心跳停更 SLA（自然日）")
    args = ap.parse_args()

    summary = q.summarize(args.dir, max_age_by_model=parse_max_age(args.max_age),
                          ens_min_jaccard=args.ens_min_jaccard,
                          heartbeat_path=None if args.no_heartbeat else args.heartbeat,
                          heartbeat_max_idle_days=args.heartbeat_max_idle)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(q.render_report(summary))
    return 0 if summary["ok_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
