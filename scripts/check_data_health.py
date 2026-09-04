#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""决策数据健康巡检 CLI（自找缺口 S9）。

打印全部决策相关数据源的真实数据截止日与新鲜度；存在 stale 源时以非零退出码结束，
方便 CI / 定时任务在「数据陈旧」时告警或触发刷新。

用法：
    python scripts/check_data_health.py            # 打印看板；存在 stale 源时 exit 1（CI 门禁用）
    python scripts/check_data_health.py --no-fail   # 纯报告，无论多陈旧都 exit 0

不触网、只读本地文件。
"""
from __future__ import annotations

import os
import sys

# 允许以 `python scripts/check_data_health.py` 直接运行（脚本目录不在包路径上）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.data_health import assess_all_sources, health_rows


def _main() -> int:
    no_fail = "--no-fail" in sys.argv[1:]
    fr = assess_all_sources()
    print("=" * 56)
    print("决策数据健康看板")
    print("=" * 56)
    _icon = {"ok": "🟢", "warn": "🟡", "stale": "🔴", "unknown": "⚪"}
    for r in health_rows():
        d = r["as_of"] or "未知"
        lag = f"滞后 {r['lag_days']} 天" if isinstance(r["lag_days"], int) else "无日期"
        print(f"  {_icon.get(r['status'], '⚪')} {r['name']:<8} 截至 {d:<12} {lag}")
    print("-" * 56)
    print(f"  整体状态：{fr['status']}"
          + (f"（最大滞后 {fr['max_lag_days']} 天）" if fr.get("max_lag_days") is not None else ""))
    if fr["status"] == "stale":
        print("⚠️ 存在陈旧数据源，决策建议需谨慎 / 刷新后参考。")
        return 0 if no_fail else 1
    if fr["status"] == "warn":
        print("🟡 部分数据源偏旧，建议关注。")
    elif fr["status"] == "unknown":
        print("⚪ 部分数据源无日期，新鲜度未知。")
    else:
        print("🟢 全部决策数据源新鲜。")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
