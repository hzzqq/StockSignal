# -*- coding: utf-8 -*-
"""
本地事件库 data/events.csv 自动刷新（headless，供盘前定时任务调用）

把「真实东方财富新闻」重新抓取 → 情感分析 → 追加入库。入库走
EventMiner._save_events_csv：concat 既有 + 新抓，再按 title 去重（append-only），
**绝不覆盖既有真实数据**——所以反复跑只会增加新新闻、不会抹掉历史 5 行。

与 signal.SignalEngine.auto_mine_events 同源：auto_mine_events 内部就是
EventMiner.mine_events(auto_save=True)，本脚本只是把它 headless 化供定时任务调度，
并额外支持 --dry-run（只算不写）与 --report（仅报当前规模）。

用法：
  python scripts/refresh_event_db.py                       # 抓财经要闻刷新
  python scripts/refresh_event_db.py --keyword 600519      # 抓指定标的/关键词相关新闻
  python scripts/refresh_event_db.py --source eastmoney --limit 50
  python scripts/refresh_event_db.py --quiet               # 静默（仅失败输出）
  python scripts/refresh_event_db.py --dry-run             # 只算不写库
  python scripts/refresh_event_db.py --report              # 仅报当前事件库行数

退出码：0 成功 / 1 抓取失败 / 2 无新闻（空结果）
"""
import argparse
import os
import sys

# 脚本在 scripts/ 下，需把项目根加入模块搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402


def run_refresh(engine, keyword=None, source="eastmoney", limit=30,
                dry_run=False, quiet=False):
    """核心刷新逻辑（可注入 engine，便于测试）。返回 (exit_code, info_dict)。

    engine 需要两个能力：
      - engine.auto_mine_events(keyword, source, limit)   -> 真实抓 + 自动入库
      - engine.event_miner.mine_events(keyword, source, limit, auto_save=False)
                                                          -> 真实抓但不入库（dry-run 用）
      - engine.event_db_path                               -> data/events.csv 绝对路径
    """
    def log(*a):
        if not quiet:
            print(*a)

    try:
        if dry_run:
            df = engine.event_miner.mine_events(
                keyword=keyword, source=source, limit=limit, auto_save=False)
        else:
            df = engine.auto_mine_events(keyword=keyword, source=source, limit=limit)
    except Exception as e:  # noqa: BLE001
        return 1, {"error": f"抓取失败: {e}"}

    mined = 0 if df is None else len(df)
    info = {"mined": mined, "keyword": keyword, "source": source, "dry_run": dry_run}
    if mined == 0:
        log("[refresh_event_db] 本次无新增新闻（返回空，不改动事件库）")
        return 2, info

    # 报告刷新后事件库规模（append+去重后的真实行数）
    try:
        path = engine.event_db_path
        cur = len(pd.read_csv(path, encoding="utf-8-sig")) if os.path.exists(path) else 0
        info["csv_rows"] = cur
    except Exception:
        info["csv_rows"] = None

    if dry_run:
        log(f"[dry-run] 拟新增 {mined} 条（未写库）")
    else:
        log(f"✅ 已刷新事件库：本次抓取 {mined} 条（追加+按标题去重）· "
            f"当前 data/events.csv 共 {info.get('csv_rows')} 行")
    return 0, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="本地事件库自动刷新（真实东方财富新闻）")
    ap.add_argument("--keyword", default=None,
                    help="关键词/标的代码；None = 抓取财经要闻")
    ap.add_argument("--source", default="eastmoney")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只算不写库")
    ap.add_argument("--report", action="store_true", help="仅报当前事件库行数")
    args = ap.parse_args(argv)

    # 任何依赖 config / data 的相对路径都以项目根为基准
    os.chdir(ROOT)

    def log(*a):
        if not args.quiet:
            print(*a)

    if args.report:
        try:
            from modules.signal import SignalEngine
            eng = SignalEngine(config_path="config.yaml")
            cur = len(pd.read_csv(eng.event_db_path, encoding="utf-8-sig")) \
                if os.path.exists(eng.event_db_path) else 0
            log(f"📊 data/events.csv 当前 {cur} 行")
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"[refresh_event_db] report 失败: {e}", file=sys.stderr)
            return 1

    try:
        from modules.signal import SignalEngine
        engine = SignalEngine(config_path="config.yaml")
    except Exception as e:  # noqa: BLE001
        print(f"[refresh_event_db] 引擎初始化失败: {e}", file=sys.stderr)
        return 1

    code, _info = run_refresh(
        engine, keyword=args.keyword, source=args.source,
        limit=args.limit, dry_run=args.dry_run, quiet=args.quiet)
    return code


if __name__ == "__main__":
    sys.exit(main())
