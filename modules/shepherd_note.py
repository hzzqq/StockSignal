"""
modules/shepherd_note.py — 情绪笔记（每日情绪快照 + 历史情绪回测分析）

功能：
  1. 每日情绪快照落盘（指标 + 次日预判 + 老板手记），存 data/shepherd_notes.json
  2. 自动回填「次日实际走势」，用来验证预判准不准（形成闭环复盘）
  3. 历史情绪回测：对过去 N 天逐日重跑情绪周期定位，统计
     · 各周期阶段出现频次
     · 各阶段「次日实际表现」的平均涨跌与胜率  ← 真正验证规律是否在本市场成立
     · 预判方向准确率

设计原则：
  ✅ 纯函数与 IO 分离：分析函数（analyze_history）吃 DataFrame 出结果，可离线单测
  ✅ 文件损坏/缺失优雅降级，绝不抛异常到页面
  ✅ 只做统计复盘，不构成投资建议
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE_DIR = os.path.join(_ROOT, "data")
NOTE_FILE = os.path.join(NOTE_DIR, "shepherd_notes.json")

_lock = threading.Lock()

# 次日实际走势的判定阈值
# 主口径：次日「打板赚钱效应」zt_prev_ret（牧羊人核心指标，历史全期可得）
#   注意：历史长周期没有 median_chg（需跑 v2 重构脚本才有全A快照），
#   而 zt_prev_ret 来自涨停池、覆盖完整，因此用它作「次日情绪走向」的代理更稳。
UP_TH = 1.0        # 次日昨板溢价 ≥ +1.0% 判「偏强」
DOWN_TH = -1.0     # ≤ -1.0% 判「偏弱」，之间为「震荡」
# 备用口径（zt_prev_ret 缺失时用涨停家数环比）
LU_RATIO = 1.15    # 次日涨停家数 ≥ 当日 ×1.15 → 偏强
LU_RATIO_DN = 0.85 # ≤ 当日 ×0.85 → 偏弱


# ═══════════════════════════════════════════════════════════════
#  一、读写（IO）
# ═══════════════════════════════════════════════════════════════
def _ensure_dir():
    try:
        os.makedirs(NOTE_DIR, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_note] 建目录失败: {e}")


def load_notes() -> dict:
    """读取全部笔记 {date_str: note}。文件缺失/损坏返回 {}。"""
    try:
        if not os.path.exists(NOTE_FILE):
            return {}
        with open(NOTE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_note] 读取笔记失败: {e}")
        return {}


def _save_notes(notes: dict) -> bool:
    try:
        _ensure_dir()
        tmp = NOTE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NOTE_FILE)   # 原子替换，避免写一半崩掉导致文件损坏
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_note] 保存笔记失败: {e}")
        return False


def _ds(v):
    """把 Timestamp/date/str 统一成 'YYYY-MM-DD'。"""
    try:
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        return str(v)[:10]
    except Exception:
        return str(v)[:10]


def save_note(date, indicators: dict, forecast: dict = None, user_note: str = "") -> bool:
    """保存/更新某日情绪笔记。

    indicators: 当日指标 dict
    forecast:   forecast_next_day 的输出（可为空，后续补算）
    user_note:  老板手记（空字符串表示不改动手记）
    """
    with _lock:
        notes = load_notes()
        d = _ds(date)
        rec = notes.get(d, {})
        rec["date"] = d
        rec["indicators"] = {k: (None if v != v else v) for k, v in (indicators or {}).items()}
        if forecast:
            cyc = forecast.get("cycle") or {}
            rec["forecast"] = {
                "cycle_id": cyc.get("id"),
                "cycle_name": cyc.get("name"),
                "cycle_emoji": cyc.get("emoji"),
                "score": forecast.get("score"),
                "bias": forecast.get("bias"),
                "confidence": forecast.get("confidence"),
                "signals": [s.get("name") for s in (forecast.get("signals") or [])],
                "summary": forecast.get("summary"),
            }
        if user_note:
            rec["user_note"] = user_note
        rec.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
        notes[d] = rec
        return _save_notes(notes)


def set_user_note(date, text: str) -> bool:
    """只更新某日的手记。"""
    with _lock:
        notes = load_notes()
        d = _ds(date)
        if d not in notes:
            return False
        notes[d]["user_note"] = text
        notes[d]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return _save_notes(notes)


def delete_note(date) -> bool:
    with _lock:
        notes = load_notes()
        d = _ds(date)
        if d not in notes:
            return False
        notes.pop(d, None)
        return _save_notes(notes)


# ═══════════════════════════════════════════════════════════════
#  二、次日实际走势回填（用历史 DataFrame 补齐 actual_next）
# ═══════════════════════════════════════════════════════════════
def _fnum(v):
    """安全转 float，缺失/NaN 返回 None。"""
    try:
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def _verdict(next_ret, next_lu=None, cur_lu=None):
    """判定「次日实际情绪走向」。

    主口径：次日 zt_prev_ret（次日打板赚钱效应）—— 牧羊人体系里最能代表
            「次日能不能赚钱」的可得指标，且历史全期覆盖。
    备用口径：次日涨停家数相对当日的环比（zt_prev_ret 缺失时）。
    """
    v = _fnum(next_ret)
    if v is not None:
        if v >= UP_TH:
            return "偏强"
        if v <= DOWN_TH:
            return "偏弱"
        return "震荡"
    # 备用：涨停家数环比
    n, c = _fnum(next_lu), _fnum(cur_lu)
    if n is not None and c is not None and c > 0:
        r = n / c
        if r >= LU_RATIO:
            return "偏强"
        if r <= LU_RATIO_DN:
            return "偏弱"
        return "震荡"
    return "未知"


def backfill_actuals(df) -> int:
    """用历史指标 DataFrame 回填每条笔记的「次日实际走势」。

    df 需含 date 列与 zt_prev_ret（次日走势主口径），可选 median_chg / limit_up。
    返回回填成功的条数。
    """
    if df is None or df.empty or "date" not in df.columns:
        return 0
    try:
        import pandas as pd
        work = df.copy()
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        work = work.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if len(work) < 2:
            return 0
        # 日期 -> (当日行, 次日行)
        nxt = {}
        for i in range(len(work) - 1):
            nxt[work["date"].iloc[i].strftime("%Y-%m-%d")] = (work.iloc[i], work.iloc[i + 1])

        notes = load_notes()
        changed = 0
        for d, rec in notes.items():
            pair = nxt.get(d)
            if pair is None:
                continue
            cur_row, row = pair
            ret = row.get("zt_prev_ret")
            actual = {
                "date": row["date"].strftime("%Y-%m-%d"),
                "zt_prev_ret": _fnum(ret),
                "median_chg": _fnum(row.get("median_chg")),
                "verdict": _verdict(ret, row.get("limit_up"), cur_row.get("limit_up")),
            }
            for k in ("limit_up", "connect_hl", "zt_fail_ratio"):
                actual[k] = _fnum(row.get(k))
            if rec.get("actual_next") != actual:
                rec["actual_next"] = actual
                changed += 1
        if changed:
            _save_notes(notes)
        return changed
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_note] 回填次日走势失败: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════
#  三、历史情绪回测分析（纯分析，可离线单测）
# ═══════════════════════════════════════════════════════════════
def analyze_history(df) -> dict:
    """对历史逐日重跑情绪周期定位，统计各阶段的次日实际表现。

    这是「分析过去的情绪」的核心：不是只看当时多热，而是验证
    「当时处于某阶段 → 次日平均怎么走」，用本市场真实数据检验规律。

    Args:
        df: get_shepherd_indicators 返回的 DataFrame（含 date + 各项指标）

    Returns:
        dict:
          rows       逐日明细 [{date, cycle, cycle_name, emoji, score, bias,
                                next_median, next_verdict, hit}]
          by_cycle   按阶段聚合 [{cycle_id, name, emoji, color, count,
                                 avg_next, win_rate, up_cnt, flat_cnt, down_cnt}]
          accuracy   预判准确率 {total, hit, rate}
          verdict_dist  次日实际走势分布
    """
    empty = dict(rows=[], by_cycle=[], accuracy=dict(total=0, hit=0, rate=0.0), verdict_dist={})
    if df is None or df.empty or "date" not in df.columns:
        return empty

    try:
        import pandas as pd
        from modules.shepherd_forecast import locate_cycle, score_next_day, forecast_next_day

        work = df.copy()
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        work = work.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if len(work) < 3:
            return empty

        # 指标列（数值型）
        keys = [c for c in work.columns if c not in ("date",)]

        rows = []
        for i in range(len(work) - 1):
            cur, nxt = work.iloc[i], work.iloc[i + 1]
            today = {}
            for k in keys:
                try:
                    v = float(cur[k])
                    if v == v:
                        today[k] = v
                except Exception:
                    pass
            prev = {}
            if i > 0:
                for k in keys:
                    try:
                        v = float(work.iloc[i - 1][k])
                        if v == v:
                            prev[k] = v
                    except Exception:
                        pass
            try:
                cyc = locate_cycle(today, prev or None)
                sc = score_next_day(today, prev or None)
                fc = forecast_next_day(today, prev or None)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[shepherd_note] 历史回测第 {i} 行失败: {e}")
                continue

            # 次日实际：主口径 zt_prev_ret（次日打板赚钱效应），备用涨停家数环比
            nret = nxt.get("zt_prev_ret")
            verdict = _verdict(nret, nxt.get("limit_up"), cur.get("limit_up"))

            # 命中判定：偏多→次日偏强 / 偏空→次日偏弱 / 中性→震荡
            bias = fc.get("bias")
            hit = (bias == "偏多" and verdict == "偏强") or \
                  (bias == "偏空" and verdict == "偏弱") or \
                  (bias == "中性" and verdict == "震荡")

            rows.append(dict(
                date=cur["date"].strftime("%Y-%m-%d"),
                cycle=cyc["id"], cycle_name=cyc["name"], emoji=cyc["emoji"], color=cyc["color"],
                score=sc["total"], bias=bias,
                next_ret=_fnum(nret), next_median=_fnum(nxt.get("median_chg")),
                next_verdict=verdict, hit=bool(hit),
            ))

        if not rows:
            return empty

        # 准确率只统计「有效样本」（次日走势可判定，非未知），
        # 否则大量缺失日会把准确率稀释成假性低分。
        valid = [r for r in rows if r["next_verdict"] != "未知"]
        hits = sum(1 for r in valid if r["hit"])

        # 各阶段聚合同样只统计有效样本
        buckets = {}
        for r in rows:
            b = buckets.setdefault(r["cycle"], dict(
                cycle_id=r["cycle"], name=r["cycle_name"], emoji=r["emoji"], color=r["color"],
                count=0, valid=0, up=0, flat=0, down=0, rets=[]))
            b["count"] += 1
            if r["next_verdict"] == "未知":
                continue
            b["valid"] += 1
            if r["next_verdict"] == "偏强":
                b["up"] += 1
            elif r["next_verdict"] == "偏弱":
                b["down"] += 1
            elif r["next_verdict"] == "震荡":
                b["flat"] += 1
            if r.get("next_ret") is not None:
                b["rets"].append(r["next_ret"])

        by_cycle = []
        for b in buckets.values():
            rs = b["rets"]
            denom = b["valid"] or 1
            by_cycle.append(dict(
                cycle_id=b["cycle_id"], name=b["name"], emoji=b["emoji"], color=b["color"],
                count=b["count"], valid=b["valid"],
                avg_next=(round(sum(rs) / len(rs), 3) if rs else None),
                win_rate=(round(b["up"] / denom * 100, 1) if b["valid"] else None),
                up=b["up"], flat=b["flat"], down=b["down"],
            ))
        by_cycle.sort(key=lambda x: -x["count"])

        vd = {}
        for r in rows:
            vd[r["next_verdict"]] = vd.get(r["next_verdict"], 0) + 1

        return dict(
            rows=rows,
            by_cycle=by_cycle,
            accuracy=dict(total=len(rows), valid=len(valid), hit=hits,
                          rate=round(hits / len(valid) * 100, 1) if valid else None),
            verdict_dist=vd,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_note] 历史情绪分析失败: {e}")
        return empty


def backtest_real(days: int = 60) -> tuple:
    """真机历史回测：拉取真实区间数据（含 backfill 近期 zt 字段）后跑 analyze_history。

    与页面里直接 get_shepherd_indicators + analyze_history 的区别：
      本函数走 get_shepherd_indicators_range(..., backfill=True)，对所选窗口内
      缺失的近期（≤15 交易日）涨停池数据做真实补算，使 zt_prev_ret / 连板等
      「次日走势主口径」真正可得，回测准确率不再是「暂无有效样本」。

    返回 (analysis, meta)：网络/数据源失败时 analysis 返回空结构、meta 含 error，
    页面可据此提示「网络受限」。惰性导入 get_shepherd_indicators_range 避免循环依赖。
    """
    empty = dict(rows=[], by_cycle=[], accuracy=dict(total=0, hit=0, rate=None), verdict_dist={})
    try:
        from datetime import timedelta
        from modules.shepherd import get_shepherd_indicators_range
        end = datetime.now()
        start = end - timedelta(days=int(days * 1.6))   # 日历日放宽覆盖，取交易日子集
        df, meta = get_shepherd_indicators_range(
            start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), backfill=True)
        if df is None or df.empty or "date" not in df.columns:
            meta = meta or {}
            meta["error"] = "所选区间暂无数据（未开始统计或数据源未覆盖）"
            return empty, meta
        analysis = analyze_history(df)
        return analysis, meta
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_note] 真机回测失败: {e}")
        return empty, {"error": str(e)}


def summary_of(analysis: dict) -> str:
    """把回测结果压成一段人话总结（供页面 caption 用）。"""
    if not analysis or not analysis.get("rows"):
        return "历史样本不足，暂无回测结论。"
    acc = analysis.get("accuracy", {})
    n, valid, hit, rate = (acc.get(k) for k in ("total", "valid", "hit", "rate"))
    parts = [f"回测 {n} 个交易日"]
    if valid:
        parts.append(f"，其中 {valid} 日可判定次日走势，方向命中 {hit} 次（准确率 {rate:.1f}%）")
    else:
        parts.append("，但均无法判定次日走势（历史缺 zt_prev_ret，需跑 v2 重构补齐）")
    for b in (analysis.get("by_cycle") or [])[:3]:
        avg, wr = b.get("avg_next"), b.get("win_rate")
        s = f"；{b['emoji']}{b['name']}出现 {b['count']} 次"
        if b.get("valid"):
            if avg is not None:
                s += f"（{b['valid']} 日有效，次日打板溢价均值 {avg:+.2f}%，次日偏强 {wr:.0f}%）"
            else:
                s += f"（{b['valid']} 日有效，次日偏强 {wr:.0f}%）"
        else:
            s += "（无有效次日样本）"
        parts.append(s)
    return "".join(parts) + "。"
