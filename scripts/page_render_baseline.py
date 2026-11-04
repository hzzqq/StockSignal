#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""页面渲染性能基线（P2-8）：把冒烟测试的逐页耗时汇总成 P50 / P95 基线。

数据来源不另造轮子：``tests/test_pages_smoke.py`` 用 Streamlit ``AppTest`` 逐页真跑
（游客态 + 已登录态各一遍，网络入口被离线打桩为立即失败，走各页既有降级分支），
并把每次渲染的毫秒数写进 ``tests/.pages_smoke_report_<批次>.json``。本脚本只做统计，
不改测试、不重复渲染，因此基线与冒烟结论天然同源——不会出现「测试说页面不崩、
性能报告说另一组数字」的割裂。

口径（引用时必须一起写明，否则数字没有意义）：
1. **离线降级路径**：测的是「断网/弱网下页面多久能出来」。真实联网时首帧受取数延迟支配，
   与本基线不可直接比较；本基线管的是渲染与本地计算这部分的成本。
2. **冷启动含导入**：每页在独立 pytest 进程里第一次 ``AppTest.from_file(...).run()``，
   模块导入（streamlit / pandas / 各页依赖）计入耗时。这是「用户当天第一次打开该页」的口径，
   比热缓存口径更保守。
3. **P50 / P95 用最近秩法**（nearest-rank）：排序后取第 ceil(p·n) 个，不做插值，
   小样本下也不会跨样本编造中间值。

用法：
    python scripts/page_render_baseline.py                      # 读 tests/.pages_smoke_report_*.json
    python scripts/page_render_baseline.py --out docs/xxx.md    # 同时写出报告
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import platform
import sys
import time

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load_reports(pattern: str) -> dict:
    """合并多批冒烟报告；同一页面被多批命中时后者覆盖（重跑会刷新数值）。"""
    merged: dict = {}
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:  # 半覆盖的报告不该把统计整体打断
            print(f"[bench] 跳过无法解析的报告 {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        merged.update(data)
    return merged


def _percentile(values: list, p: float) -> float | None:
    """最近秩法分位数；空样本返回 None（不编造 0）。"""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    rank = max(1, min(n, math.ceil(p * n)))
    return ordered[rank - 1]


def _stat(values: list) -> dict:
    return {
        "n": len(values),
        "min": min(values) if values else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _fmt_ms(v) -> str:
    if v is None:
        return "—"
    if v >= 1000:
        return f"{v / 1000:.1f} s"
    return f"{v} ms"


def build(reports: dict) -> dict:
    rows = []
    guest_ms, auth_ms = [], []
    for page, rec in sorted(reports.items()):
        g = rec.get("guest_ms")
        a = rec.get("auth_ms")
        if isinstance(g, int):
            guest_ms.append(g)
        if isinstance(a, int):
            auth_ms.append(a)
        rows.append(
            {
                "page": page,
                "guest_ms": g if isinstance(g, int) else None,
                "auth_ms": a if isinstance(a, int) else None,
                "guest_exception": rec.get("guest_exception"),
                "auth_exception": rec.get("auth_exception"),
            }
        )
    return {
        "rows": rows,
        "guest": _stat(guest_ms),
        "auth": _stat(auth_ms),
        "all": _stat(guest_ms + auth_ms),
    }


def render(stats: dict, source_pattern: str) -> str:
    rows = stats["rows"]
    g, a, alls = stats["guest"], stats["auth"], stats["all"]
    if not rows:
        return "# 页面渲染性能基线\n\n未找到冒烟报告（先跑 `SMOKE_BATCH=i/10 pytest tests/test_pages_smoke.py`）。\n"

    slow = sorted((r for r in rows if r["guest_ms"] is not None), key=lambda r: -r["guest_ms"])[:10]
    bad = [r for r in rows if (r["guest_exception"] or 0) + (r["auth_exception"] or 0) > 0]

    lines = [
        "# 页面渲染性能基线（P2-8）",
        "",
        f"> 生成时点：{time.strftime('%Y-%m-%d %H:%M')}｜样本：{len(rows)} 个页面文件 × 2 态｜"
        f"机器：{platform.platform()}／{os.cpu_count()} 逻辑核｜Python {platform.python_version()}",
        "",
        "## 一、口径（必须先读）",
        "",
        "1. **离线降级路径**：冒烟测试把 requests / urllib / baostock 入口全部打桩为立即失败，"
        "页面走各自既有的降级分支。因此本基线测的是「断网、弱网下页面多久能出来」，"
        "**不是**联网取数耗时——后者受行情源延迟支配，与本表不可直接比较。",
        "2. **冷启动含导入**：每页在独立 pytest 进程里第一次 `AppTest.from_file(...).run()`，"
        "streamlit / pandas / 各页依赖的模块导入计入耗时。这正是「用户当天第一次打开该页」的口径，"
        "比热缓存口径保守。",
        "3. **P50 / P95 为最近秩法**（不做插值）：小样本下不跨样本编造中间值；空样本记 `—` 而非 0。",
        "",
        "## 二、总体基线",
        "",
        "| 指标 | 游客态 | 已登录态 | 合并样本 |",
        "| --- | ---: | ---: | ---: |",
        f"| 样本数 | {g['n']} | {a['n']} | {alls['n']} |",
        f"| 最小 | {_fmt_ms(g['min'])} | {_fmt_ms(a['min'])} | {_fmt_ms(alls['min'])} |",
        f"| **P50** | **{_fmt_ms(g['p50'])}** | **{_fmt_ms(a['p50'])}** | **{_fmt_ms(alls['p50'])}** |",
        f"| **P95** | **{_fmt_ms(g['p95'])}** | **{_fmt_ms(a['p95'])}** | **{_fmt_ms(alls['p95'])}** |",
        f"| 最大 | {_fmt_ms(g['max'])} | {_fmt_ms(a['max'])} | {_fmt_ms(alls['max'])} |",
        "",
        "## 三、最慢 10 个页面（游客态）",
        "",
        "| 页面 | 游客态 | 已登录态 | 备注 |",
        "| --- | ---: | ---: | --- |",
    ]
    for r in slow:
        note = "渲染异常" if (r["guest_exception"] or 0) + (r["auth_exception"] or 0) > 0 else ""
        lines.append(
            f"| `{r['page']}` | {_fmt_ms(r['guest_ms'])} | {_fmt_ms(r['auth_ms'])} | {note} |"
        )

    lines += [
        "",
        "## 四、异常页",
        "",
        f"冒烟报告里存在未捕获异常的页面：**{len(bad)} 个**"
        + ("（详见 `tests/.pages_smoke_report_*.json`）" if bad else "（本轮为 0）"),
        "",
    ]
    if bad:
        lines.append("| 页面 | 游客态异常数 | 已登录态异常数 |")
        lines.append("| --- | ---: | ---: |")
        for r in bad:
            lines.append(f"| `{r['page']}` | {r['guest_exception']} | {r['auth_exception']} |")
        lines.append("")

    lines += [
        "## 五、复跑方式",
        "",
        "```bash",
        "# 1) 分批跑页面冒烟（AppTest 真渲染，单批约 8 页，10 批共约 75 个页面文件）",
        "for ($i=0; $i -le 9; $i++) { $env:SMOKE_BATCH=\"$i/10\"; "
        "python -m pytest tests/test_pages_smoke.py -q }",
        "",
        "# 2) 汇总成基线（只统计，不重新渲染）",
        "python scripts/page_render_baseline.py --out docs/性能基线_页面渲染_2026-11-04.md",
        "```",
        "",
        "## 六、已知边界",
        "",
        "- 回测类耗时（`backtest_*` 脚本）不在本表：它们由数据规模与窗口长度支配，"
        "属另一类基线，需固定数据集后单独测量；本轮未做。",
        "- 页面耗时受机器负载影响，同一台机器并发跑其他任务会整体抬高；引用时应写清机器与时点。"
        "本次采集期间同机另运行过测试收集与守卫用例，**P95 / 最大值应视为上界**而非下界。",
        f"- 数据来源：`{source_pattern}`（合并 {len(rows)} 个页面文件的记录）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="汇总页面渲染 P50/P95 基线")
    ap.add_argument(
        "--reports",
        default=os.path.join(_ROOT, "tests", ".pages_smoke_report_*.json"),
        help="冒烟报告 glob（默认 tests/.pages_smoke_report_*.json）",
    )
    ap.add_argument("--out", default="", help="写出 markdown 报告的路径（可选）")
    args = ap.parse_args()

    reports = _load_reports(args.reports)
    stats = build(reports)
    text = render(stats, args.reports)

    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(_ROOT, args.out)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[bench] 已写出 {args.out}")

    alls = stats["all"]
    if alls["n"] == 0:
        print("[bench] 没有任何页面耗时数据：先跑页面冒烟（SMOKE_BATCH=i/10）", file=sys.stderr)
        return 2
    print(
        f"[bench] 样本 {alls['n']} 次渲染｜P50 {_fmt_ms(alls['p50'])}｜"
        f"P95 {_fmt_ms(alls['p95'])}｜最大 {_fmt_ms(alls['max'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
