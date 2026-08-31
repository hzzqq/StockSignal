# -*- coding: utf-8 -*-
"""
每日收盘后落盘「决策快照 + 连板梯队快照」（供定时任务调用，也可手动跑）

为什么需要它（这是补数据地基的洞，不是锦上添花）：
    梯队分布原本**只在打开《市场情绪》页面时才顺手写一次**（pages/50_市场情绪.py）。
    哪天没打开页面，那天的梯队数据就永久丢失 → 晋级率跨日递推断链 →
    「连板梯队晋级率」「情绪周期六阶段」这两个差异化指标的历史回测全是空中楼阁。
    实测 data/shepherd_ladder_history.json 曾只有 2 天，其中 1 天还是隔天补记的。

做三件事：
    1. 抓今日连板梯队 → 落盘 data/shepherd_ladder_history.json（按日期累积）
    2. 抓今日牧羊人指标 → 算温度 / 情绪周期 / 次日预判 / 晋级率
    3. 用 modules.decision 推导仓位 → 落盘 data/daily_snapshot.json（首页直读）
       + 归档 data/snapshots/YYYY-MM-DD.json（复盘回测的数据源）

用法：
    python scripts/daily_snapshot.py                # 抓今天，落盘
    python scripts/daily_snapshot.py --dry-run      # 只算不写，看会得到什么
    python scripts/daily_snapshot.py --quiet        # 静默（定时任务用），仅失败时输出

退出码：0 成功 / 1 抓取失败 / 2 落盘失败
"""
import argparse
import os
import sys
from datetime import datetime

# 脚本在 scripts/ 下，需把项目根加入模块搜索路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import decision as _dec  # noqa: E402
from modules import shepherd_ladder as _sl  # noqa: E402
from modules import shepherd_forecast as _sf  # noqa: E402
from modules.shepherd import (  # noqa: E402
    get_shepherd_indicators, shepherd_temperature, get_zt_ladder,
)


def _row_to_indicators(df, i=-1) -> dict:
    """牧羊人 DataFrame 第 i 行 → 指标 dict（与决策面板同一套语义）。"""
    if df is None or getattr(df, "empty", True):
        return {}
    try:
        row = df.iloc[i]
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for k in df.columns:
        if k == "date":
            continue
        try:
            v = float(row[k])
            if v == v:  # 过滤 NaN
                out[k] = v
        except Exception:  # noqa: BLE001
            continue
    return out


def _data_date(df) -> str:
    """取**数据日期**（权威）而非 now()。

    ⚠️ 周末/盘后跑脚本时 now() 会记一个非交易日，跨日晋级率递推会把周末当「昨日」，
       晋级率直接算错。这是踩过的坑，别改回 now()。
    """
    try:
        return str(df.iloc[-1]["date"])[:10]
    except Exception:  # noqa: BLE001
        return _guess_trading_date()


def _guess_trading_date() -> str:
    """推测最近交易日：周六/周日回退到上周五。

    只用于「牧羊人还没抓到、拿不到权威日期」时先落盘梯队。
    拿到牧羊人的权威日期后会用它重新校正一次（见 main 里的日期校正）。
    """
    from datetime import timedelta
    d = datetime.now()
    if d.weekday() >= 5:  # 5=周六 6=周日
        d = d - timedelta(days=d.weekday() - 4)
    return d.strftime("%Y-%m-%d")


def _record_ladder(date: str, ladder: dict, log) -> bool:
    """落盘梯队快照。按日期覆盖，一天跑多次只留最后一次（幂等）。"""
    try:
        _sl.record_ladder_snapshot(
            date, ladder.get("distribution"),
            ladder.get("max_boards"), ladder.get("total_connect"),
        )
        log(f"[ok] 梯队快照已落盘 {date}: {ladder.get('distribution')}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 梯队快照落盘失败: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="每日收盘后落盘决策快照 + 连板梯队快照")
    ap.add_argument("--dry-run", action="store_true", help="只计算不落盘，打印将要写入的内容")
    ap.add_argument("--quiet", action="store_true", help="静默模式（定时任务用），仅失败时输出")
    args = ap.parse_args()

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    # ── 1. 抓连板梯队并落盘（**放最前面**：它最实时、也最容易丢）──
    # 设计要点：梯队快照绝不能被牧羊人抓取失败阻塞。盘中牧羊人常有指标取不到
    # （如炸板股池限 30 日），但梯队分布始终可抓；若因前者提前 return，
    # 今天这份梯队就永久丢失，晋级率链条断裂 —— 那正是本脚本存在的理由。
    ladder = None
    try:
        ladder = get_zt_ladder(top_per_level=3)
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 连板梯队抓取失败（晋级率将缺失）: {e}")

    if isinstance(ladder, dict) and ladder.get("distribution"):
        _record_ladder(_guess_trading_date(), ladder, log)
    else:
        log("[warn] 无梯队数据，跳过梯队快照落盘")

    # ── 2. 抓牧羊人指标 ──
    try:
        df = get_shepherd_indicators(days=60)
    except Exception as e:  # noqa: BLE001
        _dec.append_log(f"FAIL 牧羊人指标抓取失败: {e}")
        print(f"[FAIL] 牧羊人指标抓取失败: {e}（梯队快照已尝试落盘，不受影响）")
        return 1
    if df is None or getattr(df, "empty", True):
        _dec.append_log("FAIL 牧羊人指标为空")
        print("[FAIL] 牧羊人指标为空（网络/数据源受限）；梯队快照已尝试落盘，不受影响")
        return 1

    date = _data_date(df)
    today = _row_to_indicators(df, -1)
    prev = _row_to_indicators(df, -2) if len(df) >= 2 else None

    # 日期校正：上面梯队用的是「推测交易日」，这里拿到了牧羊人的权威数据日期。
    # 两者不一致时按权威日期重写一次，避免把周末/非交易日写进晋级率链条。
    if isinstance(ladder, dict) and ladder.get("distribution") and date != _guess_trading_date():
        log(f"[fix] 梯队日期校正：{_guess_trading_date()} → {date}")
        _record_ladder(date, ladder, log)

    # ── 3. 温度 / 预判 / 晋级率 → 仓位 ──
    try:
        temp = shepherd_temperature(today)
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 温度计算失败，兜底 50: {e}")
        temp = 50.0

    try:
        fc = _sf.forecast_next_day(today, prev)
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 次日预判失败: {e}")
        fc = {}

    try:
        promo = _sl.ladder_promotion_rates()
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 晋级率计算失败: {e}")
        promo = {}

    snap = _dec.build_snapshot(date, today, temp, fc, promo, ladder)
    pos = snap.get("position") or {}

    log(
        f"[snapshot] {date} 温度={snap.get('temperature')} "
        f"周期={snap.get('cycle') or '-'} 方向={snap.get('bias') or '-'} "
        f"晋级率={snap.get('promo_overall')} → 仓位 {pos.get('pct')}% ({pos.get('band')})"
    )

    if args.dry_run:
        print("[dry-run] 未写入磁盘。快照内容：")
        import json
        print(json.dumps(snap, ensure_ascii=False, indent=2)[:2000])
        return 0

    # ── 4. 落盘 ──
    if not _dec.save_snapshot(snap):
        _dec.append_log(f"FAIL 快照落盘失败 {date}")
        print("[FAIL] 快照落盘失败")
        return 2

    _dec.append_log(
        f"OK {date} temp={snap.get('temperature')} cycle={snap.get('cycle')} "
        f"bias={snap.get('bias')} pos={pos.get('pct')}%({pos.get('band')})"
    )
    log(f"[done] 快照已写入 data/daily_snapshot.json 并归档 data/snapshots/{date}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
