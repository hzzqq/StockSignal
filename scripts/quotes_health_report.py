"""scripts/quotes_health_report.py —— 行情取数层健康体检 CLI。

用法：
    python scripts/quotes_health_report.py            # Markdown 报告，退出码 0=全绿/1=有红灯
    python scripts/quotes_health_report.py --json    # JSON 输出

真实取数（linear_trends 缓存 + 12s 硬超时兜底），约 10~30 秒。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.linear_trends import get_index_series, get_industry_index_series, get_etf_series, quotes_fetch_state  # noqa: E402
from modules import quotes_health as h  # noqa: E402


def _providers():
    return {
        # 体检用短窗口：够测结构契约与最新日期新鲜度，且显著低于页面默认窗口
        "index": lambda: get_index_series(days=30),
        "industry_board": lambda: get_industry_index_series(top_n=3, days=30),
        "etf": lambda: get_etf_series(days=30),
    }


def main():
    ap = argparse.ArgumentParser(description="行情取数层健康体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    summary = h.summarize(_providers())
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps({"quotes_fetch_state": quotes_fetch_state()}, ensure_ascii=False, indent=2))
    else:
        print(h.render_report(summary))
        fb = quotes_fetch_state()["last_fallbacks"]
        if fb:
            print("\n## 数据层降级记录（备源启用）")
            for name, ev in fb.items():
                print(f"- {name}: {ev['ts']} 降级到 {ev['fallback_to']}（{ev['detail']}）")
        else:
            print("\n## 数据层降级记录\n- 无（主源直连成功）")
    return 0 if summary["ok_all"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
