"""牧羊人指标全量历史回测入口（2007-01-01 ~ 今天）。

用法：
    python -m scripts.run_shepherd_reconstruct
    python -m scripts.run_shepherd_reconstruct --start 2007-01-01 --workers 10

结果写入 data/shepherd_history.csv（utf-8-sig），供报告脚本与页面读取。
支持断点续跑：每只股票聚合结果已缓存在 data/shepherd_cache/，重跑只会补拉缺失标的。
"""
from __future__ import annotations

import argparse
import logging
import time

from modules.shepherd_reconstruct import build_shepherd_history, save_history


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="牧羊人指标全量历史回测")
    parser.add_argument("--start", default="2007-01-01", help="重构起始日 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束日 YYYY-MM-DD（默认今天）")
    parser.add_argument("--workers", type=int, default=10, help="多进程 worker 数")
    parser.add_argument("--no-reconstruct", action="store_true", help="跳过全 A 重构，仅合并近期 zt_pool")
    args = parser.parse_args()

    t0 = time.time()
    df = build_shepherd_history(
        start_date=args.start,
        end_date=args.end,
        reconstruct=not args.no_reconstruct,
    )
    path = save_history(df)
    elapsed = time.time() - t0

    logging.info("[run_shepherd_reconstruct] 完成：%d 行 -> %s，耗时 %.1fs", len(df), path, elapsed)
    if not df.empty:
        logging.info("[run_shepherd_reconstruct] 区间 %s ~ %s",
                     df["date"].min(), df["date"].max())
        # 简要统计
        logging.info("[run_shepherd_reconstruct] 末日快照: %s",
                     df.iloc[-1][["up_count", "down_count", "limit_up", "limit_down", "red_ratio",
                                  "connect_hl", "zt_fail_ratio", "zt_prev_ret"]].to_dict())


if __name__ == "__main__":
    main()
