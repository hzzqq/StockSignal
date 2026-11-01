"""scripts/fundflow_health_report.py —— fundflow 数据层健康巡检 CLI（方向 3 延续）。

用法：
    python scripts/fundflow_health_report.py                 # 真实取数体检，Markdown 报告
    python scripts/fundflow_health_report.py --json         # JSON 输出（供自动化消费）
    python scripts/fundflow_health_report.py --period 20260930   # 指定业绩报告期
    python scripts/fundflow_health_report.py --skip-disclosure    # 跳过披露日历（接口慢）

退出码：0 = 全绿（无红灯）；1 = 存在红灯（接口降级/结构缺失/日频断供）。
黄灯（best-effort 空数据/新鲜度边缘）不阻断。

说明：体检调用 modules.fundflow 真实接口（TTL 缓存内命中即判健康；日频接口
按数据最新日期判新鲜度，缓存不影响该判定）。首次运行会触发一次代理探测
（fundflow 惰性机制），属预期行为。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.fundflow as f  # noqa: E402
import modules.fundflow_health as h  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="fundflow 数据层健康体检")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--period", default=h.DEFAULT_EARNINGS_PERIOD, help="业绩报表报告期")
    ap.add_argument("--skip-disclosure", action="store_true", help="跳过披露日历（接口慢）")
    args = ap.parse_args()

    providers = {
        "industry": f.get_industry_fund_flow,
        "northbound_history": f.get_northbound_history,
        "northbound_fund_flow": f.get_northbound_fund_flow,
        "market_fund_flow": lambda: f.get_market_fund_flow(days=30),
        "earnings_report": lambda: f.get_earnings_report(period=args.period),
        "earnings_forecast": lambda: f.get_earnings_forecast(period=args.period),
    }
    if not args.skip_disclosure:
        providers["disclosure_calendar"] = lambda: f.get_disclosure_calendar(
            market=h.DEFAULT_DISCLOSURE_MARKET, period=h.DEFAULT_DISCLOSURE_PERIOD)

    summary = h.summarize(providers, earnings_period=args.period)
    # 数据层降级标注：附上 fundflow 进程内最近失败记录（红灯时解释来源）
    state = f.fundflow_health_state()
    summary["last_fetch_failures"] = state["last_fetch_failures"]
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(h.render_report(summary))
        if summary["last_fetch_failures"]:
            print("\n**数据层降级记录**（进程内最后失败）：")
            for name, rec in summary["last_fetch_failures"].items():
                print(f"- {name}: {rec['ts']} {rec['error']}")
    return 0 if summary["ok_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
