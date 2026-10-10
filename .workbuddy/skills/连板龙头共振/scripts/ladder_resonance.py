#!/usr/bin/env python3
"""连板龙头共振 — 命令行入口。

读取 StockSignal 连板梯队历史（data/shepherd_ladder_history.json），跨日递推各档晋级率。
核心口径：首板→二板晋级率是接力意愿最纯粹的度量；综合晋级率优先取 2b，缺失时取可用档均值。
诚实红线：历史不足 10 天时 overall 仍返回，但 confidence="low" 且 actionable=False，不驱动决策。

用法：
  python ladder_resonance.py --auto
  python ladder_resonance.py --today '{"1": 45, "2": 12, "3": 3, "4": 1}'
  python ladder_resonance.py --summary
  python ladder_resonance.py --date 2026-09-30
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import ladder_engine as le  # type: ignore


def main() -> int:
    p = argparse.ArgumentParser(description="连板龙头共振：计算连板梯队晋级率")
    p.add_argument("--auto", action="store_true", help="自动读取 StockSignal 历史")
    p.add_argument("--today", type=str, help='传入今日梯队分布 JSON，如 {"1":45,"2":12,"3":3}')
    p.add_argument("--date", type=str, help="历史回填口径：只用到该日为止的数据（YYYY-MM-DD）")
    p.add_argument("--summary", action="store_true", help="输出数据边界与使用说明")
    args = p.parse_args()

    if args.summary:
        print(json.dumps({
            "name": "连板龙头共振",
            "data_source": "StockSignal data/shepherd_ladder_history.json（或 SS_LADDER_FILE）",
            "key_metric": "首板→二板晋级率（2b）",
            "actionable_threshold_days": le.MIN_PROMO_DAYS,
            "honesty": "历史不足 10 天或数据缺失时返回 confidence=low/none、actionable=False，不编造信号",
            "边界": "仅描述历史接力结构，不构成买卖建议",
        }, ensure_ascii=False, indent=2))
        return 0

    if args.today:
        try:
            dist = json.loads(args.today)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"--today JSON 解析失败：{e}"}, ensure_ascii=False))
            return 1
        result = le.evaluate(today_distribution=dist, as_of=args.date)
    elif args.auto or args.date:
        result = le.ladder_promotion_rates(as_of=args.date)
    else:
        p.print_help()
        return 0

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
