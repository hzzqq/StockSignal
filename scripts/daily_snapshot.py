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
    python scripts/daily_snapshot.py --ladder-only  # 盘中高频：仅落盘连板梯队（不抓牧羊人）
    python scripts/daily_snapshot.py --score-only   # 次日回填：只给历史预测打分（不抓数据）
    python scripts/daily_snapshot.py --backfill-date YYYY-MM-DD [更多日期...]
                                            # 历史回填：补算过去某日的快照+预测（时点诚实，仅写归档）

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
from modules import decision_track as _track  # noqa: E402
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
        return _sl.trading_date()


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


def _backfill(dates: list[str], log) -> int:
    """补算历史日期的决策快照与预测记录（时点诚实口径）。

    为什么需要：08-31/09-01 因「牧羊人漏解包」footgun 损失了两天样本
    （快照 FAIL 但梯队快照已落盘），校准样本起点被拖后。本函数在事后把
    这两天补回来，且**绝不偷看未来数据**：

      · 牧羊人指标逐行取该日（指标本就是逐日计算，历史行天然时点正确）
      · 晋级率 ladder_promotion_rates(as_of=D) 只递推 ≤ D 的梯队历史
      · 梯队分布取当日**已落盘**的梯队快照（盘中/收盘 automation 当时的原始值）
      · 预判 forecast_next_day(today_D, prev_D) 只用该日及其前一日的指标

    落盘纪律：
      · 只写归档 snapshots/D.json（archive_only=True），绝不覆盖今日 daily_snapshot
      · record_prediction 按日期幂等，重复跑只覆盖同日一条
      · 牧羊人无该日行 → 明确跳过（不编造）

    补完后跑 `--score-only` 可立即回填已可打分的次日涨跌（该日次日已收盘）。
    """
    # ⚠️ get_shepherd_indicators 返回 (df, meta) 二元组，必须解包（见主流程注释）。
    try:
        df, _shepherd_meta = get_shepherd_indicators(days=60)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 牧羊人指标抓取失败: {e}")
        return 1
    if df is None or getattr(df, "empty", True):
        print("[FAIL] 牧羊人指标为空")
        return 1
    try:
        dcol = df["date"].astype(str).str[:10]
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 牧羊人数据日期列不可用: {e}")
        return 1

    hist = _sl.load_history()
    n_ok = 0
    for d in dates:
        sub = df[dcol <= d]
        if sub.empty or str(sub.iloc[-1]["date"])[:10] != d:
            log(f"[skip] {d}: 牧羊人数据无该日行（不编造）")
            continue
        today = _row_to_indicators(sub, -1)
        prev = _row_to_indicators(sub, -2) if len(sub) >= 2 else None

        try:
            temp = shepherd_temperature(today)
        except Exception as e:  # noqa: BLE001
            log(f"[warn] {d} 温度计算失败，兜底 50: {e}")
            temp = 50.0
        try:
            fc = _sf.forecast_next_day(today, prev)
        except Exception as e:  # noqa: BLE001
            log(f"[warn] {d} 次日预判失败: {e}")
            fc = {}
        try:
            promo = _sl.ladder_promotion_rates(as_of=d)
        except Exception as e:  # noqa: BLE001
            log(f"[warn] {d} 晋级率计算失败: {e}")
            promo = {}

        entry = hist.get(d) if isinstance(hist, dict) else None
        ladder = ({"distribution": entry.get("distribution"),
                   "max_boards": entry.get("max_boards"),
                   "total_connect": entry.get("total_connect")}
                  if isinstance(entry, dict) and entry.get("distribution") else None)

        snap = _dec.build_snapshot(d, today, temp, fc, promo, ladder)
        pos = snap.get("position") or {}
        if not _dec.save_snapshot(snap, archive_only=True):
            log(f"[FAIL] {d} 归档写入失败")
            continue
        try:
            ef = snap.get("event_factor") or {}
            _track.record_prediction(d, temp, snap.get("cycle") or "",
                                     snap.get("bias") or "中性", pos.get("pct"),
                                     event_adj=ef.get("adj"),
                                     event_available=ef.get("available"))
        except Exception as e:  # noqa: BLE001
            log(f"[warn] {d} 预测记录失败: {e}")
        n_ok += 1
        log(f"[backfill] {d} 温度={snap.get('temperature')} 周期={snap.get('cycle')} "
            f"方向={snap.get('bias')} 晋级率={snap.get('promo_overall')} "
            f"→ 仓位 {pos.get('pct')}% ({pos.get('band')})")

    _dec.append_log(f"BACKFILL 成功 {n_ok}/{len(dates)}: {', '.join(dates)}")
    print(f"[backfill] 完成 {n_ok}/{len(dates)}；"
          f"跑 --score-only 可立即回填已可打分的次日涨跌")
    return 0 if n_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="每日收盘后落盘决策快照 + 连板梯队快照")
    ap.add_argument("--dry-run", action="store_true", help="只计算不落盘，打印将要写入的内容")
    ap.add_argument("--quiet", action="store_true", help="静默模式（定时任务用），仅失败时输出")
    ap.add_argument("--audit", action="store_true",
                    help="体检梯队历史，列出不可信条目（只读，不触发任何网络抓取）")
    ap.add_argument("--mark-suspect", metavar="DATE", nargs="+",
                    help="把指定日期标记为不可信（软处理：数据不删，仅不参与晋级率计算，可撤销）")
    ap.add_argument("--unmark-suspect", metavar="DATE", nargs="+", help="撤销不可信标记")
    ap.add_argument("--ladder-only", action="store_true",
                    help="仅落盘连板梯队快照（盘中高频用：不抓牧羊人、不写 daily_snapshot）")
    ap.add_argument("--score-only", action="store_true",
                    help="仅给历史预测回填次日实际涨跌（回测打分）：不抓牧羊人/梯队，不写快照")
    ap.add_argument("--backfill-date", metavar="DATE", nargs="+",
                    help="补算历史日期的决策快照+预测（时点诚实口径：只用截至该日已可见的"
                         "数据；仅写归档 snapshots/<date>.json，绝不覆盖今日 daily_snapshot）")
    args = ap.parse_args()

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    # ── 0. 只读体检 / 软标记：不触发任何网络抓取，也不影响正常落盘流程 ──
    if args.audit:
        report = _sl.audit_history()
        if not report:
            print("[audit] 梯队历史未发现可疑条目")
            return 0
        bad = [d for d, r in report.items() if r["severity"] == "bad"]
        warn = [d for d, r in report.items() if r["severity"] == "warn"]
        pending = [d for d in bad if not report[d].get("marked")]
        print(f"[audit] 发现 {len(report)} 条可疑：{len(bad)} 条强烈建议排除 / {len(warn)} 条仅提示"
              f"（其中 {len(pending)} 条待处理）")
        for d in sorted(report):
            r = report[d]
            tag = "bad " if r["severity"] == "bad" else "warn"
            state = " [已排除]" if r.get("marked") else ""
            print(f"  [{tag}] {d}  {r['reason']}：{r['detail']}{state}")
        if pending:
            print("\n排除（软标记，可撤销，数据不删）：")
            print(f"  python scripts/daily_snapshot.py --mark-suspect {' '.join(sorted(pending))}")
        elif bad:
            print("\n所有强烈建议排除的条目均已处理。")
        return 0

    if args.mark_suspect:
        n = _sl.mark_suspect(args.mark_suspect, reason="daily_snapshot --mark-suspect")
        print(f"[mark] 已标记 {n} 条为不可信，不再参与晋级率计算：{', '.join(args.mark_suspect)}")
        print("  撤销：python scripts/daily_snapshot.py --unmark-suspect <日期...>")
        return 0

    if args.unmark_suspect:
        n = _sl.unmark_suspect(args.unmark_suspect)
        print(f"[unmark] 已撤销 {n} 条标记：{', '.join(args.unmark_suspect)}")
        return 0

    # ── 盘中高频模式：仅落盘连板梯队（不抓牧羊人、不写 daily_snapshot）──
    # 用途：交易时段每 30 分钟跑一次，确保今天梯队一定被捕获——
    #   即使 15:30 全量跑因网络失败（EXIT=1），梯队历史也不丢；
    #   且能在收盘附近（15:00）就记下当日分布，不依赖盘后全量。
    # 幂等：同一交易日多次运行只覆盖当天那一条。
    if args.ladder_only:
        lad = None
        try:
            lad = get_zt_ladder(top_per_level=3)
        except Exception as e:  # noqa: BLE001
            log(f"[FAIL] 连板梯队抓取失败: {e}")
            return 1
        if isinstance(lad, dict) and lad.get("distribution"):
            _record_ladder(_sl.trading_date(), lad, log)
            return 0
        log("[FAIL] 无梯队数据")
        return 1

    # ── 回测打分模式：只给历史预测回填「次日实际涨跌」，不抓行情 ──
    # 为什么单独开一个模式：打分只需要拉上证日线（一次请求），而全量落盘要抓
    # 牧羊人 17 项 + 连板梯队（慢且可能失败）。把打分拆出来做成轻量定时任务，
    # 命中率才能每天自动长起来 —— 否则只靠人工点页面按钮，样本永远积累不起来。
    # 幂等：已打分的记录不会重复拉取（score_predictions 内部跳过 realized 非空的）。
    if args.score_only:
        try:
            res = _track.score_predictions()
        except Exception as e:  # noqa: BLE001
            _dec.append_log(f"FAIL 回测打分异常: {e}")
            print(f"[FAIL] 回测打分异常: {e}")
            return 1
        if not args.quiet:
            s = _track.summary()
            print(f"[score] 本次回填 {res.get('scored')} 条；"
                  f"累计 {s['n']} 条预测 / {s['n_call']} 次表态 / 命中率 {s['accuracy']}%")
            byc = _track.by_cycle()
            if byc:
                print("[score] 分情绪周期命中率：")
                for c in byc:
                    acc = "—" if c["accuracy"] is None else f"{c['accuracy']}%"
                    print(f"    {c['cycle'] or '(未标注)'}: {acc}  （{c['hits']}/{c['n_call']}）")
        elif res.get("scored", 0) > 0:
            # 静默（定时任务）模式下，仅在真正回填了新数据时留一行日志，便于排障
            print(f"[score] 回填 {res['scored']} 条")
        _dec.append_log(f"SCORE 回填 {res.get('scored')} 条 / 命中率 {res.get('accuracy')}%")
        return 0

    # ── 历史回填模式：补算历史日期的快照+预测（时点诚实，仅写归档）──
    if args.backfill_date:
        return _backfill(args.backfill_date, log)

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
        _record_ladder(_sl.trading_date(), ladder, log)
    else:
        log("[warn] 无梯队数据，跳过梯队快照落盘")

    # ── 2. 抓牧羊人指标 ──
    # ⚠️ get_shepherd_indicators 返回的是 (df, meta) 二元组，必须解包。
    # 曾漏解包：df 实为元组 → 元组无 .empty → 下面 getattr(..., True) 的默认值恒定生效
    # → 100% 误判「牧羊人指标为空」→ 快照永不落盘 → record_prediction 永不触发
    # → 「预测 vs 实际回测」与「仓位刻度校准」的样本永远是 0（整条闭环被掐死在源头）。
    # 守卫见 tests/test_daily_snapshot_wiring.py，改动此处前先跑它。
    try:
        df, _shepherd_meta = get_shepherd_indicators(days=60)
    except Exception as e:  # noqa: BLE001
        _dec.append_log(f"FAIL 牧羊人指标抓取失败: {e}")
        print(f"[FAIL] 牧羊人指标抓取失败: {e}（梯队快照已尝试落盘，不受影响）")
        return 1
    if df is None or getattr(df, "empty", True):
        _dec.append_log("FAIL 牧羊人指标为空")
        print("[FAIL] 牧羊人指标为空（网络/数据源受限）；梯队快照已尝试落盘，不受影响")
        return 1
    # 部分指标不可用不算致命（单源失败有降级），但要留痕便于排查数据质量
    if isinstance(_shepherd_meta, dict) and _shepherd_meta.get("unavailable"):
        log(f"[warn] 牧羊人部分指标不可用: {_shepherd_meta['unavailable']}")

    date = _data_date(df)
    today = _row_to_indicators(df, -1)
    prev = _row_to_indicators(df, -2) if len(df) >= 2 else None

    # 日期校正：上面梯队用的是「推测交易日」，这里拿到了牧羊人的权威数据日期。
    # 两者不一致时按权威日期重写一次，避免把周末/非交易日写进晋级率链条。
    if isinstance(ladder, dict) and ladder.get("distribution") and date != _sl.trading_date():
        log(f"[fix] 梯队日期校正：{_sl.trading_date()} → {date}")
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

    # 决策级新鲜度守卫全量覆盖（S14）：把连板晋级率/市场温度缓存的「真实数据截止日」
    # 也透传给 build_snapshot——否则这两个决策输入陈旧时守卫是 theater（只查牧羊人+事件）。
    # 复用 data_health 抽取器作单一真理源；任一抽不到则对应源不入守卫（与 dashboard 同款容错）。
    try:
        from modules import data_health as _dh
        _ladder_asof = _dh.source_as_of(next(e for e in _dh.DATA_SOURCES if e["key"] == "ladder"))
        _mtemp_asof = _dh.source_as_of(next(e for e in _dh.DATA_SOURCES if e["key"] == "market_temp"))
    except Exception:  # noqa: BLE001
        _ladder_asof = _mtemp_asof = None

    snap = _dec.build_snapshot(date, today, temp, fc, promo, ladder,
                               ladder_as_of=_ladder_asof, market_temp_as_of=_mtemp_asof)
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

    # ── 5. 记一笔预测（供「预测 vs 实际」回测；与每日快照一一对应）──
    try:
        ef = snap.get("event_factor") or {}
        _track.record_prediction(date, temp, snap.get("cycle") or "", snap.get("bias") or "中性",
                                 pos.get("pct"),
                                 event_adj=ef.get("adj"), event_available=ef.get("available"))
    except Exception as e:  # noqa: BLE001
        log(f"[warn] 预测记录失败（不影响快照）: {e}")

    _dec.append_log(
        f"OK {date} temp={snap.get('temperature')} cycle={snap.get('cycle')} "
        f"bias={snap.get('bias')} pos={pos.get('pct')}%({pos.get('band')})"
    )
    log(f"[done] 快照已写入 data/daily_snapshot.json 并归档 data/snapshots/{date}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
