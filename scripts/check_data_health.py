#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""决策数据健康巡检 CLI（自找缺口 S9）。

打印全部决策相关数据源的真实数据截止日与新鲜度；存在 stale 源时以非零退出码结束，
方便 CI / 定时任务在「数据陈旧」时告警或触发刷新。

用法：
    python scripts/check_data_health.py            # 打印看板；存在 stale 源时 exit 1（CI 门禁用）
    python scripts/check_data_health.py --no-fail   # 纯报告，无论多陈旧都 exit 0
    python scripts/check_data_health.py --refresh   # 列出陈旧源的刷新命令（去重，不执行）
    python scripts/check_data_health.py --refresh --exec   # 尝试执行刷新命令（有网才真成功）

守卫的最后一环：--refresh 让闭环从「只暴露滞后」进化到「陈旧可一键刷新」。
注意：本仓所有刷新路径都依赖联网 / 跨仓（沙箱无网会失败），--exec 会如实报
「刷新失败（可能无网络）」，绝不伪造成功。
"""
from __future__ import annotations

import os
import subprocess
import sys

# 允许以 `python scripts/check_data_health.py` 直接运行（脚本目录不在包路径上）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from modules.data_health import assess_all_sources, build_refresh_plan, health_rows

_REFRESH_TIMEOUT = 600  # 单条刷新命令超时（秒）


def _print_board() -> dict:
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
    return fr


def _print_refresh_plan(plan: list[dict]) -> None:
    if not plan:
        print("🟢 无陈旧源，无需刷新。")
        return
    print("📋 陈旧源刷新计划（去重命令）：")
    for i, p in enumerate(plan, 1):
        _tag = "🌐 联网" if p["mode"] == "live" else "🔗 跨仓"
        print(f"  [{i}] ({_tag}) {p['desc']}")
        print(f"      命令: {p['cmd']}")
        print(f"      覆盖: {', '.join(p['covers'])} ｜当前陈旧: {', '.join(p['stale_sources'])}")


def _exec_refresh(plan: list[dict]) -> bool:
    """尝试执行刷新命令；返回是否「至少一条 live 命令成功推进了数据」。

    诚实原则：命令非零退出 / 超时 / external 跨仓 → 如实记 failed，绝不报成功。
    """
    any_progress = False
    for p in plan:
        if p["mode"] == "external":
            print(f"  ⏭️  跳过跨仓源「{p['cmd_id']}」（需到 P1-QuantFactor 仓库执行，本仓无入口）")
            continue
        print(f"  ⏳ 执行: {p['cmd']}")
        try:
            rc = subprocess.run(p["cmd"], shell=True, cwd=_ROOT,
                                timeout=_REFRESH_TIMEOUT, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print(f"      ❌ 超时（>{_REFRESH_TIMEOUT}s），刷新失败。")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"      ❌ 执行异常：{e}")
            continue
        if rc.returncode != 0:
            _tail = (rc.stderr or rc.stdout or "")[-300:].strip().replace("\n", " ")
            print(f"      ❌ 刷新失败（exit={rc.returncode}）。可能无网络/代理未起。{_tail}")
            continue
        print(f"      ✅ 命令执行成功（exit=0）。")
        any_progress = True
    return any_progress


def _main() -> int:
    no_fail = "--no-fail" in sys.argv[1:]
    do_refresh = "--refresh" in sys.argv[1:]
    do_exec = "--exec" in sys.argv[1:]

    fr = _print_board()

    if do_refresh:
        plan = build_refresh_plan(stale_only=True)
        print()
        _print_refresh_plan(plan)
        if do_exec:
            print()
            print("=" * 56)
            print("尝试执行刷新命令…")
            print("=" * 56)
            _exec_refresh(plan)
            print()
            # 刷新后重新评估，如实展示数据是否真的新了
            fr2 = _print_board()
            if fr2["status"] == "stale":
                print("⚠️ 刷新后仍有陈旧源（可能无网络/跨仓未执行），决策建议仍谨慎。")
            else:
                print(f"✅ 刷新后整体状态：{fr2['status']}，数据已更新。")
        return 0 if no_fail else 1

    if fr["status"] == "stale":
        print("⚠️ 存在陈旧数据源，决策建议需谨慎 / 刷新后参考。可用 `python scripts/check_data_health.py --refresh` 查看刷新命令。")
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
