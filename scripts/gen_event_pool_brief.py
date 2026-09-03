# -*- coding: utf-8 -*-
"""
事件因子选股池 · 每日晨报 / 自动推送素材生成（headless，供定时任务调用）

把「事件驱动看多榜」落成**可直接转发**的格式：
  - data/event_pool_brief.md   富文本 Markdown（推送到微信 / 邮件 / 早报正文用）
  - data/event_pool_brief.json 结构化（供外部自动推送 automation 解析用）

与 pages/51_每日晨报.py 的「📈 事件驱动看多榜」板块、**pages/54_今日决策面板.py**
的 fragment_event_driven_pool 同源（都读 modules.event_factor.event_driven_long_list），
保证 in-app 展示、晨报正文、外部自动推送三处素材完全一致。

用法：
  python scripts/gen_event_pool_brief.py                 # 生成 md + json
  python scripts/gen_event_pool_brief.py --top-n 30     # 取前 30
  python scripts/gen_event_pool_brief.py --model gru   # 换模型
  python scripts/gen_event_pool_brief.py --quiet        # 静默（仅失败输出）
  python scripts/gen_event_pool_brief.py --dry-run      # 只算不写
  python scripts/gen_event_pool_brief.py --json-only    # 仅 json
  python scripts/gen_event_pool_brief.py --md-only      # 仅 md

退出码：0 成功 / 1 抓取失败 / 2 落盘失败
"""
import argparse
import json
import os
import sys
from datetime import date

# 脚本在 scripts/ 下，需把项目根加入模块搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.event_factor import event_driven_long_list  # noqa: E402


def _build_markdown(rows, model, dstr) -> str:
    lines = [
        f"# 📈 事件驱动看多榜（{dstr}）",
        "",
        "> 由 P1-QuantFactor 神经网络产出的**事件因子多头候选池**（EV 模型，已并入牧羊人情绪 "
        "9 维事件/regime 通道）。",
        "> 这是统计意义上的超额收益概率排序，**非买卖指令**；建议仅取多头侧，并结合板块/自选股信号综合判断。",
        "",
    ]
    if not rows:
        lines.append("_今日无事件因子信号（data/p1_signals/ 无可用文件）。_")
        return "\n".join(lines)
    lines.append("| # | 代码 | 事件因子分 | 来源 |")
    lines.append("| -- | -- | -- | -- |")
    for i, r in enumerate(rows, 1):
        sc = r.get("score")
        sc_txt = f"{sc:.1f}" if isinstance(sc, (int, float)) else "—"
        lines.append(f"| {i} | `{r.get('symbol', '')}` | {sc_txt} | {r.get('source', '')} |")
    lines.append("")
    lines.append(f"_口径：事件因子分 = P1 模型百分位排名 × 100（越高越看多）。模型：{model}。_")
    return "\n".join(lines)


def _build_json(rows, model, dstr) -> dict:
    return {
        "date": dstr,
        "model": model,
        "source": "P1-QuantFactor EV 事件因子",
        "note": "统计意义上的超额收益概率排序，非买卖指令",
        "count": len(rows),
        "pool": [
            {
                "rank": i,
                "symbol": r.get("symbol"),
                "score": r.get("score"),
                "raw_rank": r.get("raw_rank"),
                "raw_pred": r.get("raw_pred"),
                "signal": r.get("signal"),
                "source": r.get("source"),
            }
            for i, r in enumerate(rows, 1)
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="事件因子选股池素材生成（晨报/自动推送）")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--model", default="ev")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--md-only", action="store_true")
    args = ap.parse_args(argv)

    def log(*a):
        if not args.quiet:
            print(*a)

    dstr = date.today().strftime("%Y-%m-%d")
    try:
        rows = event_driven_long_list(top_n=args.top_n, model=args.model)
    except Exception as e:  # noqa: BLE001
        print(f"[gen_event_pool_brief] 抓取失败: {e}", file=sys.stderr)
        return 1

    md = _build_markdown(rows, args.model, dstr)
    js = _build_json(rows, args.model, dstr)

    if args.dry_run:
        log(f"[dry-run] 取 {len(rows)} 条 · 模型={args.model}")
        log(md)
        return 0

    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    try:
        if not args.json_only:
            with open(os.path.join(data_dir, "event_pool_brief.md"), "w", encoding="utf-8") as f:
                f.write(md + "\n")
            log(f"✅ 已写 data/event_pool_brief.md（{len(rows)} 条）")
        if not args.md_only:
            with open(os.path.join(data_dir, "event_pool_brief.json"), "w", encoding="utf-8") as f:
                json.dump(js, f, ensure_ascii=False, indent=2)
            log(f"✅ 已写 data/event_pool_brief.json（{len(rows)} 条）")
    except Exception as e:  # noqa: BLE001
        print(f"[gen_event_pool_brief] 落盘失败: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
