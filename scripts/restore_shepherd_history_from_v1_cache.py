# -*- coding: utf-8 -*-
"""从 v1 per-stock 缓存离线恢复牧羊人广度历史（不需要联网）。

背景（2026-09-10 事故）：
    2026-09-04 的一次窄窗口运行把 ``data/shepherd_cache_v2/`` 里 3849/5548 只股票的
    历史截成 6 行，导致 ``data/shepherd_history.csv`` 的广度家数被系统性低估
    （实测 ≈3 倍，跌停 ≈10 倍），并丢掉 2007-01-05~2009-10-30 共 677 个交易日。

本脚本的恢复源是**完好的 v1 缓存** ``data/shepherd_cache/``（5547 只 / 2007→2026-08-21 /
中位 2342 行），它每行含 date, up_count, down_count, flat_count, limit_up, limit_down
——正好覆盖广度核心列。

诚实边界（不依赖的信息一律留空，绝不拿 0 冒充）：
    * touch_down / hb_wave10 / median_chg / avg_price 需要 v2 的个股级明细
      （触板标记 / 最高价 / 收盘价），v1 缓存没有 → 这些列**写空值**，
      而不是填 0（填 0 等于把「不知道」包装成「当天没有任何一只触及跌停」）。
    * ``connect_hl`` / ``zt_fail_ratio`` / ``zt_prev_ret`` 从健康镜像
      ``data/shepherd_history.json``（2026-08-22）带过来。
    * 2026-08-22 及以后 v1 缓存没有覆盖，沿用现有 csv 的行（后续用 --refresh-days 联网补齐）。

用法：
    python -m scripts.restore_shepherd_history_from_v1_cache --dry-run
    python -m scripts.restore_shepherd_history_from_v1_cache
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import shutil
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.atomic_io import atomic_to_csv  # noqa: E402

logger = logging.getLogger("restore_shepherd_history")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1_CACHE_DIR = os.path.join(_ROOT, "data", "shepherd_cache")
HISTORY_CSV = os.path.join(_ROOT, "data", "shepherd_history.csv")
HEALTHY_JSON = os.path.join(_ROOT, "data", "shepherd_history.json")
# ⚠️ 耐久性：`data/` 被 .gitignore 忽略（第 23 行），事故时「不可 git 恢复」正是这个坑。
# 因此额外镜像一份到**被 git 追踪的** backups/ 目录，换机器/误删都能找回。
MIRROR_CSV = os.path.join(_ROOT, "backups", "shepherd_history_restored.csv")

COUNT_COLS = ["up_count", "down_count", "flat_count", "limit_up", "limit_down"]
# 与 modules/shepherd_reconstruct._aggregate_frames 的列序保持一致（下游按此读取）
OUT_COLS = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down",
            "red_ratio", "touch_down", "zt_fail_count", "hb_wave10", "median_chg",
            "avg_price", "connect_hl", "connect_2b", "fc_ratio", "zt_fail_ratio",
            "zt_prev_ret"]
# v1 缓存拿不到、必须留空的列（禁止用 0 冒充）
EMPTY_COLS = ["touch_down", "zt_fail_count", "hb_wave10", "median_chg", "avg_price"]
CARRY_FROM_JSON = ["connect_hl", "zt_fail_ratio", "zt_prev_ret"]

_BATCH = 500


def aggregate_v1_cache(cache_dir: str = V1_CACHE_DIR) -> pd.DataFrame:
    """把 v1 per-stock 缓存按日期求和，返回 DataFrame[date + COUNT_COLS]。"""
    files = sorted(glob.glob(os.path.join(cache_dir, "*.csv")))
    if not files:
        raise RuntimeError("v1 缓存目录为空，无法离线恢复：%s" % cache_dir)
    logger.info("[restore] 待聚合 v1 缓存 %d 个文件", len(files))

    partials = []
    for i in range(0, len(files), _BATCH):
        frames = []
        for f in files[i:i + _BATCH]:
            try:
                df = pd.read_csv(f)
            except Exception as e:  # noqa: BLE001
                logger.warning("[restore] 读缓存失败 %s: %s", os.path.basename(f), e)
                continue
            if "date" not in df.columns:
                continue
            keep = [c for c in COUNT_COLS if c in df.columns]
            if not keep:
                continue
            df = df[["date"] + keep].copy()
            for c in COUNT_COLS:
                if c not in df.columns:
                    df[c] = 0
            frames.append(df)
        if not frames:
            continue
        big = pd.concat(frames, ignore_index=True)
        big["date"] = pd.to_datetime(big["date"], errors="coerce")
        big = big.dropna(subset=["date"])
        for c in COUNT_COLS:
            big[c] = pd.to_numeric(big[c], errors="coerce").fillna(0)
        partials.append(big.groupby("date", sort=True)[COUNT_COLS].sum())
        logger.info("[restore] 已处理 %d/%d", min(i + _BATCH, len(files)), len(files))

    if not partials:
        raise RuntimeError("v1 缓存没有任何可解析的行")
    agg = pd.concat(partials).groupby(level=0).sum().reset_index()
    agg = agg.rename(columns={"index": "date"})
    agg = agg.sort_values("date").reset_index(drop=True)
    denom = agg["up_count"] + agg["down_count"]
    agg["red_ratio"] = np.where(denom > 0, agg["up_count"] / denom * 100.0, np.nan)
    logger.info("[restore] v1 聚合完成：%d 个交易日，区间 %s ~ %s",
                len(agg), agg["date"].min().date(), agg["date"].max().date())
    return agg


def load_healthy_json(path: str = HEALTHY_JSON) -> pd.DataFrame | None:
    """读健康镜像 json（2026-08-22 事故前快照），失败返回 None（优雅降级）。"""
    if not os.path.exists(path):
        logger.warning("[restore] 健康镜像不存在：%s（connect_hl 等列将留空）", path)
        return None
    try:
        import json
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        df = pd.DataFrame(data)
        if "date" not in df.columns:
            return None
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.dropna(subset=["date"])
    except Exception as e:  # noqa: BLE001
        logger.warning("[restore] 读健康镜像失败：%s", e)
        return None


def build_restored(v1: pd.DataFrame, healthy: pd.DataFrame | None,
                   existing: pd.DataFrame | None) -> pd.DataFrame:
    """合成恢复后的历史表：v1 覆盖 <= 其末日；更晚的行沿用现有 csv。"""
    v1 = v1.copy()
    v1["date"] = pd.to_datetime(v1["date"])
    cut = v1["date"].max()

    for c in OUT_COLS:
        if c not in v1.columns:
            v1[c] = np.nan
    base = v1[OUT_COLS].copy()

    # 2026-08-22 及以后：v1 没有覆盖 → 沿用现有 csv 的行（后续靠 --refresh-days 联网补齐）
    if existing is not None and not existing.empty:
        tail = existing.copy()
        tail["date"] = pd.to_datetime(tail["date"], errors="coerce")
        tail = tail.dropna(subset=["date"])
        tail = tail[tail["date"] > cut]
        for c in OUT_COLS:
            if c not in tail.columns:
                tail[c] = np.nan
        if not tail.empty:
            logger.info("[restore] 沿用现有 csv 的 %d 行（%s 之后，待联网刷新）",
                        len(tail), cut.date())
            base = pd.concat([base, tail[OUT_COLS]], ignore_index=True)

    # 从健康镜像带 connect_hl / zt_fail_ratio / zt_prev_ret（仅补空，不覆盖）
    if healthy is not None and not healthy.empty:
        # ⚠️ 必须先把 date 规整为 datetime：json/调用方给的日期可能是字符串（object dtype），
        # 与 base 的 datetime64 直接 merge 会抛 MergeError（不是静默错，但会让整条恢复链路断掉）。
        healthy = healthy.copy()
        healthy["date"] = pd.to_datetime(healthy["date"], errors="coerce")
        healthy = healthy.dropna(subset=["date"])
        base["date"] = pd.to_datetime(base["date"], errors="coerce")
        cols = [c for c in CARRY_FROM_JSON if c in healthy.columns]
        if cols:
            base = base.merge(healthy[["date"] + cols], on="date", how="left",
                              suffixes=("", "_h"))
            for c in cols:
                h = base[f"{c}_h"]
                base[c] = base[c].combine_first(h) if c in base.columns else h
                base.drop(columns=[f"{c}_h"], inplace=True, errors="ignore")

    # 诚实边界：v1 无法支撑的列一律留空（不拿 0 冒充）
    for c in EMPTY_COLS:
        base[c] = np.nan

    base = base.sort_values("date").reset_index(drop=True)
    return base[OUT_COLS]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="从 v1 缓存离线恢复牧羊人广度历史")
    ap.add_argument("--dry-run", action="store_true", help="只统计不落盘")
    ap.add_argument("--cache-dir", default=V1_CACHE_DIR)
    ap.add_argument("--out", default=HISTORY_CSV)
    ap.add_argument("--mirror", default=MIRROR_CSV,
                    help="额外的耐久镜像（默认落进被 git 追踪的 backups/，防 data/ 被 .gitignore 吃掉）")
    ap.add_argument("--no-mirror", action="store_true", help="不写耐久镜像")
    args = ap.parse_args()

    existing = None
    if os.path.exists(args.out):
        try:
            existing = pd.read_csv(args.out, encoding="utf-8-sig")
        except Exception as e:  # noqa: BLE001
            logger.warning("[restore] 读现有 csv 失败（将不沿用其尾部）：%s", e)

    v1 = aggregate_v1_cache(args.cache_dir)
    healthy = load_healthy_json()
    df = build_restored(v1, healthy, existing)

    logger.info("[restore] 恢复表 %d 行，区间 %s ~ %s",
                len(df), df["date"].min().date(), df["date"].max().date())

    # 交叉校验：与健康镜像比对核心列（同日必须一致）
    if healthy is not None:
        j = healthy.rename(columns={"date": "date"})
        cmp = df.merge(j[["date"] + COUNT_COLS], on="date", how="inner", suffixes=("", "_j"))
        bad = 0
        for c in COUNT_COLS:
            d = (cmp[c] - cmp[f"{c}_j"]).abs()
            n = int((d > 0.5).sum())
            bad += n
            if n:
                logger.warning("[restore] 与健康镜像不一致 %s: %d/%d 天", c, n, len(cmp))
        logger.info("[restore] 与健康镜像交叉校验：可比 %d 天，不一致合计 %d 处%s",
                    len(cmp), bad, "（含 zt_pool 覆盖期差异属正常）" if bad else "")

    if args.dry_run:
        logger.info("[restore] dry-run，不落盘")
        print(df.tail(5).to_string(index=False))
        return

    if os.path.exists(args.out):
        bak = args.out + ".polluted-20260910.bak"
        if not os.path.exists(bak):
            shutil.copy2(args.out, bak)
            logger.warning("[restore] 已备份被污染的原表 -> %s", bak)
        else:
            logger.info("[restore] 备份已存在，跳过：%s", bak)

    atomic_to_csv(df, args.out, encoding="utf-8-sig")
    logger.info("[restore] 已写入 %s", args.out)

    if not args.no_mirror and args.mirror:
        os.makedirs(os.path.dirname(args.mirror), exist_ok=True)
        atomic_to_csv(df, args.mirror, encoding="utf-8-sig")
        logger.info("[restore] 耐久镜像已写入（被 git 追踪）%s", args.mirror)

    print(df.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
