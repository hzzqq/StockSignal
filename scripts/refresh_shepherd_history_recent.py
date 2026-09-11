# -*- coding: utf-8 -*-
"""日常增量刷新：把最近若干交易日的广度**合并**进 data/shepherd_history.csv。

为什么不能用 scripts/run_shepherd_reconstruct.py 直接补？
    那个入口是「从 shepherd_cache_v2 全量重建整张历史表」。而 v2 缓存已被 2026-09-04 的
    窄窗口运行截断（3849/5548 只只剩 6 行），拿它重建会把 P1 用完好 v1 缓存恢复出来的
    2007→2026-08-21 真值**再次覆盖成稀疏口径**。所以本脚本：

    1. 以恢复好的 data/shepherd_history.csv 为**基底**（历史以它为准，不重建）；
    2. 只让 v2 管线刷新「最近窗口」（refresh_days 增量合并进 per-stock 缓存）；
    3. 把刷新出来的**最近若干天**按日期合并进基底（新值优先，历史行不动）；
    4. 同时写入被 git 追踪的 backups/ 镜像（防 data/ 被 .gitignore 吃掉）。

用法：
    python -m scripts.refresh_shepherd_history_recent --dry-run
    python -m scripts.refresh_shepherd_history_recent --since 2026-08-22 --workers 12
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.atomic_io import atomic_to_csv  # noqa: E402
from modules.shepherd_reconstruct import build_shepherd_history  # noqa: E402

logger = logging.getLogger("refresh_shepherd_recent")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_CSV = os.path.join(_ROOT, "data", "shepherd_history.csv")
MIRROR_CSV = os.path.join(_ROOT, "backups", "shepherd_history_restored.csv")

# v1 缓存的覆盖末日（2026-08-21）之后的第一天：从这天起 v1 帮不上忙，必须联网刷新。
DEFAULT_SINCE = "2026-08-22"
# 多取 7 天作为「预热窗口」：_normalize_daily 用 shift(1) 算 prev_close，
# 若窗口正好从 since 开始，since 当天会因缺前收盘被丢掉。
WARMUP_DAYS = 7


BREADTH_COLS = ("up_count", "down_count", "flat_count")


def drop_breadthless_new_dates(recent: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """丢弃「基表里没有该日期、且广度家数全空」的空白行（纯函数，可离线测试）。

    场景：zt_pool 的覆盖窗口含**当天**，盘前跑时当天还没开盘 → 会多出一条
    up/down/flat 全 NaN 的未来行。它虽然会被回测脚本的 ``sample >= min_sample``
    过滤掉（NaN 比较为 False），但脏行留在基表里会污染「最新快照」类读取方，
    且让行数校验（新增 N 行）产生误导。所以**新日期必须有广度才收**。
    """
    if recent is None or recent.empty:
        return recent
    r = recent.copy()
    r["date"] = pd.to_datetime(r["date"], errors="coerce")
    known = set(pd.to_datetime(base["date"], errors="coerce").dropna())
    cols = [c for c in BREADTH_COLS if c in r.columns]
    if not cols:
        return recent
    has_breadth = r[cols].notna().any(axis=1)
    return r[has_breadth | r["date"].isin(known)].reset_index(drop=True)


def merge_recent(base: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
    """把 recent 的行合并进 base：同日期以 recent 的非空值优先，历史行原样保留。"""
    b = base.copy()
    r = recent.copy()
    b["date"] = pd.to_datetime(b["date"], errors="coerce")
    r["date"] = pd.to_datetime(r["date"], errors="coerce")
    b = b.dropna(subset=["date"]).set_index("date")
    r = r.dropna(subset=["date"]).set_index("date")
    if r.empty:
        return b.reset_index()

    idx = b.index.union(r.index)
    b = b.reindex(idx)
    for col in r.columns:
        if col not in b.columns:
            b[col] = np.nan
        # r[col].combine_first(b[col])：r 非空处覆盖旧值；r 为空处保留旧值；
        # 仅 r 有的新日期自然取 r 的值。
        b[col] = r[col].combine_first(b[col])
    return b.sort_index().reset_index()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="增量刷新牧羊人广度历史（合并，不重建）")
    ap.add_argument("--since", default=DEFAULT_SINCE,
                    help="最早接受的刷新日期（默认 v1 覆盖末日之后，即 %s）" % DEFAULT_SINCE)
    ap.add_argument("--end", default=None, help="结束日，默认今天")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--csv", default=HISTORY_CSV)
    ap.add_argument("--mirror", default=MIRROR_CSV)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="联网但不落盘")
    ap.add_argument("--offline", action="store_true",
                    help="纯离线：不增量重拉、不联网补 zt_pool，只用本地 v2 缓存补算聚合。"
                         "用于「抓取阶段已完成、但聚合阶段被 OOM 打断」后的续跑。")
    ap.add_argument("--zt-only", action="store_true",
                    help="只做 zt_pool 联网补充（近约 15 个交易日的有界小请求，非全市场扫描）："
                         "把 limit_up/limit_down/connect_*/zt_fail_*/fc_ratio 换回**真实涨停池**口径，"
                         "覆盖离线反推的近似值；不碰广度家数。")
    args = ap.parse_args()

    base = pd.read_csv(args.csv, encoding="utf-8-sig")
    base["date"] = pd.to_datetime(base["date"], errors="coerce")
    base = base.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    logger.info("[refresh] 基底 %d 行，区间 %s ~ %s",
                len(base), base["date"].min().date(), base["date"].max().date())

    since = pd.Timestamp(args.since)
    fetch_from = (since - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    end = args.end or pd.Timestamp.now().strftime("%Y-%m-%d")
    # refresh_days 需足够大，使 fetch_start 落在 fetch_from（而不是更晚）
    gap = (pd.Timestamp(end) - pd.Timestamp(fetch_from)).days + 1
    if args.offline:
        # 离线续跑：缓存里已有抓取结果，只补算聚合。refresh_days=0 → 命中缓存即复用（零重拉），
        # enrich_network=False → 跳过 zt_pool 联网。注意：若存在**未缓存**标的，
        # 仍会走一次有界的窄窗口拉取（已带 socket 超时 + 总墙钟上限 + shutdown(wait=False)）。
        gap = 0
        logger.info("[refresh] 离线模式：只补算聚合，不重拉、不联网补 zt_pool")
    logger.info("[refresh] v2 增量刷新区间 %s ~ %s（预热从 %s 起，refresh_days=%d）",
                since.date(), end, fetch_from, gap)

    if args.zt_only:
        # 既有表里 limit_up/connect_hl/zt_fail_ratio 等列对近端窗口应取**真实涨停池**，
        # 而不是离线反推的近似值。reconstruct=False → 不做全市场扫描，只打
        # 近约 15 个交易日的 zt_pool（有界小请求）；广度家数缺省为 NaN，merge 时保留基表原值。
        logger.info("[refresh] zt-only 模式：只拉近端真实涨停池，不重算广度、不做全市场扫描")
        zt = build_shepherd_history(start_date=fetch_from, end_date=end,
                                    reconstruct=False, enrich_network=True)
        if zt is None or zt.empty:
            logger.error("[refresh] zt_pool 未取到任何数据，放弃（不改动基表）")
            return 1
        zt = zt.copy()
        zt["date"] = pd.to_datetime(zt["date"], errors="coerce")
        zt = zt.dropna(subset=["date"])
        zt = zt[zt["date"] >= since]
        has_lu = zt["limit_up"].notna().sum() if "limit_up" in zt.columns else 0
        logger.info("[refresh] 真实涨停池覆盖 %d 天（limit_up 非空 %d 天）", len(zt), has_lu)
        recent = zt
    else:
        recent = build_shepherd_history(start_date=fetch_from, end_date=end,
                                        reconstruct=True, refresh_days=gap,
                                        enrich_network=not args.offline)
    if recent is None or recent.empty:
        logger.error("[refresh] 未取到任何数据，放弃（不改动基表）")
        return 1
    recent = recent.copy()
    recent["date"] = pd.to_datetime(recent["date"], errors="coerce")
    recent = recent[recent["date"] >= since]
    _before = len(recent)
    recent = drop_breadthless_new_dates(recent, base)
    if len(recent) != _before:
        logger.info("[refresh] 丢弃 %d 行无广度数据的空白日期（典型：盘前的当天）",
                    _before - len(recent))
    logger.info("[refresh] 刷新得到 %d 行：%s ~ %s",
                len(recent),
                recent["date"].min().date() if len(recent) else "-",
                recent["date"].max().date() if len(recent) else "-")
    if recent.empty:
        logger.error("[refresh] 刷新区间为空，放弃（不改动基表）")
        return 1
    covered = recent["up_count"].notna().sum()
    logger.info("[refresh] 其中 up_count 非空 %d/%d 天", covered, len(recent))

    merged = merge_recent(base, recent[recent.columns.intersection(
        set(base.columns) | set(recent.columns))])
    added = len(merged) - len(base)
    logger.info("[refresh] 合并后 %d 行（新增 %d，覆盖历史 %d 行）",
                len(merged), added, len(recent) - max(added, 0))

    if args.dry_run:
        logger.info("[refresh] dry-run，不落盘")
        print(merged.tail(12).to_string(index=False))
        return 0

    atomic_to_csv(merged, args.csv, encoding="utf-8-sig")
    logger.info("[refresh] 已写入 %s", args.csv)
    if not args.no_mirror and args.mirror:
        os.makedirs(os.path.dirname(args.mirror), exist_ok=True)
        atomic_to_csv(merged, args.mirror, encoding="utf-8-sig")
        logger.info("[refresh] 耐久镜像已更新 %s", args.mirror)
    print(merged.tail(12).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
