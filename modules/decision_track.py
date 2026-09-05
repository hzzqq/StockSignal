# -*- coding: utf-8 -*-
"""
modules/decision_track.py — 「预测 vs 实际」准确率回测（差异化主线的能力验证）

为什么要这个模块（这是补「闭环最后一公里」，不是锦上添花）：
    《今日决策面板》每天给出「偏多/偏空 + 几成仓」的预判，但**从没人验证过准不准**。
    一个只给建议、从不复盘对错的系统，用户无法判断该信几分 —— 这是差异化主线
    （事件驱动 + 市场情绪）目前最该补的缺口。

    本模块把每天落盘的决策快照「记一笔预测」（date / 温度 / 周期 / 方向 / 仓位），
    之后联网拉取**次日基准指数（上证 000001）真实涨跌**，判定方向是否命中，
    积累出「方向命中率」+ 一张「预测仓位 vs 次日实际涨跌」的回测曲线。

设计约束（与安全基线一致）：
    · 不依赖 streamlit；纯 Python，定时任务与页面都能调。
    · 路径读 SS_DATA_DIR（测试隔离复用同一套机制，不写穿真实 data/）。
    · 任何单源失败（网络/akshare 缺失/基准取不到）都优雅降级：
      记录照常落、打分返回 None、页面显示「暂无可打分样本」，绝不向上抛。
    · 打分是「联网回测」动作，由页面按钮或定时任务显式触发，不在此模块 import 时自动跑。

红涨绿跌：偏多/激进=红，偏空/防御=绿（与 decision.py 一致）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from modules.atomic_io import atomic_json_dump
from typing import Any

logger = logging.getLogger(__name__)

# 项目根（modules/ 的上一级）
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
# SS_DATA_DIR 可重定向整个数据目录（测试隔离用；生产默认 data/）。
DATA_DIR = os.environ.get("SS_DATA_DIR", os.path.join(ROOT, "data"))

# 预测记录落盘位置（与 daily_snapshot.json 同目录，回测曲线读它）
PRED_PATH = os.path.join(DATA_DIR, "prediction_log.json")

# 上证指数代码（基准：判定「次日实际涨跌方向」的参照物）
_BENCH_SYMBOL = "000001"
# 方向 → 数值（偏多看涨 +1 / 偏空看跌 -1 / 中性 0 表示「不表态」，不计入命中率）
_DIR_MAP = {"偏多": 1, "偏空": -1, "中性": 0}


# ───────────────────────── 记录写入 ─────────────────────────
def record_prediction(date: str, temp, cycle_name: str, bias: str, pct: int,
                       event_adj: int | None = None,
                       event_available: bool | None = None) -> bool:
    """落盘一条预测记录（按日期幂等：同一天重复跑只覆盖当天那条）。

    在 scripts/daily_snapshot.py 落盘每日快照成功后调用，使「每天一份决策」与
    「一条预测」一一对应，后续回测才有数据源。

    :param event_adj: 当日事件驱动仓位调节(绝对百分点)；None=信号不可用。
    :param event_available: 当日事件驱动信号是否可用（布尔）。落库后供 by_event()
                            按「事件开/关」拆分命中率，回答「事件催化到底有没有用」。
    """
    if not date:
        return False
    try:
        rec = {
            "date": date,
            "temp": round(float(temp), 1) if temp is not None else None,
            "cycle": cycle_name or "",
            "bias": bias or "中性",
            "pct": int(pct) if pct is not None else None,
            "event_adj": int(event_adj) if event_adj is not None else None,
            "event_available": bool(event_available) if event_available is not None else None,
            "realized": None,   # 次日实际涨跌(%)，联网打分时回填
            "hit": None,        # 方向是否命中(True/False)，打分后回填
        }
        recs = _load()
        # 按日期去重覆盖
        replaced = False
        for i, r in enumerate(recs):
            if r.get("date") == date:
                # 已打分的记录保留 realized/hit，只更新预测侧字段；事件字段优先级：
                # 本次传入值优先（更准），缺省时沿用旧值，避免重跑把 available 抹掉
                rec["realized"] = r.get("realized")
                rec["hit"] = r.get("hit")
                if event_adj is None and r.get("event_adj") is not None:
                    rec["event_adj"] = r.get("event_adj")
                if event_available is None and r.get("event_available") is not None:
                    rec["event_available"] = r.get("event_available")
                recs[i] = rec
                replaced = True
                break
        if not replaced:
            recs.append(rec)
        _save(recs)
        logger.info("[track] 预测已记录 %s 方向=%s 仓位=%s%% 事件=%s",
                    date, rec["bias"], rec["pct"], rec["event_available"])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[track] 预测记录失败 %s: %s", date, e)
        return False


def _load() -> list[dict]:
    try:
        with open(PRED_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("[track] 预测记录读取失败: %s", e)
        return []
    return data if isinstance(data, list) else []


def _save(recs: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    atomic_json_dump(recs, PRED_PATH)


# ───────────────────────── 本地汇总（不联网） ─────────────────────────
def summary() -> dict:
    """已落盘预测的本地统计（不触发任何网络，页面加载即可看）。"""
    recs = _load()
    scored = [r for r in recs if r.get("hit") is not None]
    n_call = [r for r in scored if _DIR_MAP.get(r.get("bias"), 0) != 0]
    hits = sum(1 for r in n_call if r.get("hit"))
    accuracy = round(hits / len(n_call) * 100, 1) if n_call else None
    dates = sorted(r["date"] for r in recs)
    return {
        "n": len(recs),
        "scored": len(scored),
        "n_call": len(n_call),
        "hits": hits,
        "accuracy": accuracy,
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
    }


def chart_data() -> dict | None:
    """回测曲线数据（纯本地，读已落盘记录）。

    返回 {dates, predicted(仓位%), realized(次日涨跌%或None), cumulative_hit(累计命中率%)}
    供页面用 plotly 画「预测仓位 vs 次日实际涨跌」双轴图。
    """
    recs = [r for r in _load() if r.get("date")]
    recs.sort(key=lambda r: r["date"])
    if not recs:
        return None
    dates, predicted, realized, cum = [], [], [], []
    run_hits = 0
    run_n = 0
    for r in recs:
        dates.append(r["date"])
        predicted.append(r.get("pct"))
        realized.append(r.get("realized"))
        if r.get("hit") is not None and _DIR_MAP.get(r.get("bias"), 0) != 0:
            run_n += 1
            if r["hit"]:
                run_hits += 1
            cum.append(round(run_hits / run_n * 100, 1))
        else:
            cum.append(cum[-1] if cum else None)
    return {"dates": dates, "predicted": predicted, "realized": realized, "cumulative_hit": cum}


# ───────────────────────── 分情绪周期命中率（战术细分） ─────────────────────────
# 为什么要有这层：总体命中率是个「平均数的谎言」——
#   主升高潮期人人看对，退潮期看对才值钱。老板真正要回答的是
#   「这套情绪决策在哪些周期可信、在哪些周期該打折」，所以必须按周期拆开看。
#
# 六阶段 → 四大战术分组（分组是为了解决单阶段样本稀疏：一天一个阶段，
#   六阶段拆完每组可能只有 2~3 条，统计上没意义；合并成 4 组才有参考价值）。
CYCLE_GROUPS = {
    "主升高潮": "进攻期",
    "修复确认": "进攻期",
    "高潮分化": "分化期",
    "修复试探": "修复期",
    "冰点": "修复期",
    "退潮": "防守期",
}
# 展示顺序（非字典序：按情绪从热到冷，便于视觉上读出「越冷越准还是越热越准」）
_GROUP_ORDER = ["进攻期", "分化期", "修复期", "防守期"]


def by_cycle(min_samples: int = 0) -> list[dict]:
    """按情绪周期分组统计命中率（纯本地，不联网）。

    返回列表，每项 {cycle, group, n, n_call, hits, accuracy, avg_pct, avg_realized}：
        · cycle   具体六阶段名（未标注为空串）
        · group   归并后的四大战术分组（进攻/分化/修复/防守），样本稀疏时用这个看
        · n_call  表态次数（偏多/偏空；中性不计入分母，与 summary() 口径一致）
        · avg_pct 该周期下平均给的建议仓位（看是否敢给）
        · avg_realized 该周期下次日基准平均实际涨跌（看给的值不值）
    min_samples>0 时过滤掉表态次数不足的组（避免 1 条样本显示 100% 误导）。

    排序：先按分组热度顺序，再按表态次数降序，保证输出稳定可测。
    """
    recs = _load()
    buckets: dict[str, dict] = {}
    for r in recs:
        cyc = (r.get("cycle") or "").strip()
        key = cyc or "(未标注)"
        b = buckets.setdefault(key, {
            "cycle": cyc, "group": CYCLE_GROUPS.get(cyc, "其他"),
            "n": 0, "n_call": 0, "hits": 0, "_pct": [], "_real": [],
        })
        b["n"] += 1
        if r.get("pct") is not None:
            b["_pct"].append(float(r["pct"]))
        if r.get("realized") is not None:
            b["_real"].append(float(r["realized"]))
        if r.get("hit") is not None and _DIR_MAP.get(r.get("bias"), 0) != 0:
            b["n_call"] += 1
            if r["hit"]:
                b["hits"] += 1

    out = []
    for b in buckets.values():
        if min_samples and b["n_call"] < min_samples:
            continue
        out.append({
            "cycle": b["cycle"],
            "group": b["group"],
            "n": b["n"],
            "n_call": b["n_call"],
            "hits": b["hits"],
            "accuracy": round(b["hits"] / b["n_call"] * 100, 1) if b["n_call"] else None,
            "avg_pct": round(sum(b["_pct"]) / len(b["_pct"]), 1) if b["_pct"] else None,
            "avg_realized": round(sum(b["_real"]) / len(b["_real"]), 2) if b["_real"] else None,
        })

    gi = {g: i for i, g in enumerate(_GROUP_ORDER)}
    out.sort(key=lambda x: (gi.get(x["group"], 99), -x["n_call"], x["cycle"]))
    return out


def by_group(min_samples: int = 0) -> list[dict]:
    """在 by_cycle() 之上再按四大战术分组聚合（样本更集中，结论更稳）。"""
    agg: dict[str, dict] = {}
    for c in by_cycle():
        g = agg.setdefault(c["group"], {
            "group": c["group"], "n": 0, "n_call": 0, "hits": 0, "_pct": [], "_real": [],
        })
        g["n"] += c["n"]
        g["n_call"] += c["n_call"]
        g["hits"] += c["hits"]
        if c["avg_pct"] is not None:
            g["_pct"].append(c["avg_pct"])
        if c["avg_realized"] is not None:
            g["_real"].append(c["avg_realized"])

    out = []
    for g in agg.values():
        if min_samples and g["n_call"] < min_samples:
            continue
        out.append({
            "group": g["group"],
            "n": g["n"],
            "n_call": g["n_call"],
            "hits": g["hits"],
            "accuracy": round(g["hits"] / g["n_call"] * 100, 1) if g["n_call"] else None,
            "avg_pct": round(sum(g["_pct"]) / len(g["_pct"]), 1) if g["_pct"] else None,
            "avg_realized": round(sum(g["_real"]) / len(g["_real"]), 2) if g["_real"] else None,
        })
    gi = {g: i for i, g in enumerate(_GROUP_ORDER)}
    out.sort(key=lambda x: gi.get(x["group"], 99))
    return out


def last_scored_date() -> str | None:
    """最近一次成功打分的预测日期（由已回填 realized 的记录推算）。

    供 calibration.verdict() 判断「样本是否新鲜」——若打分自动化挂了，
    这里会停在旧日期，页面据此提示「最近打分 X 天前」，而不是假装闭环还在转。
    """
    recs = _load()
    scored = [r["date"] for r in recs if r.get("realized") is not None]
    return max(scored) if scored else None


def by_event(min_samples: int = 0) -> list[dict]:
    """按「事件驱动信号当日是否可用」拆分方向命中率，回答事件催化是否真有效。

    返回 [{"group": "事件开"|"事件关", "n", "n_call", "hits", "accuracy"|None}]。
    命中率口径与 summary() 一致（仅偏多/偏空表态计入分母；中性不计入）。
    min_samples>0 时过滤表态不足的分组（避免「事件开 1 条 100%」误导）。
    """
    recs = _load()
    buckets: dict[str, list[dict]] = {"事件开": [], "事件关": []}
    for r in recs:
        if r.get("hit") is None:
            continue  # 未打分不参与命中率
        key = "事件开" if r.get("event_available") else "事件关"
        buckets[key].append(r)
    out = []
    for name in ("事件开", "事件关"):
        rs = buckets[name]
        n_call = [r for r in rs if _DIR_MAP.get(r.get("bias"), 0) != 0]
        hits = sum(1 for r in n_call if r.get("hit"))
        if min_samples and len(n_call) < min_samples:
            out.append({"group": name, "n": len(rs), "n_call": len(n_call),
                        "hits": hits, "accuracy": None})
            continue
        out.append({"group": name, "n": len(rs), "n_call": len(n_call),
                    "hits": hits,
                    "accuracy": round(hits / len(n_call) * 100, 1) if n_call else None})
    return out


# ───────────────────────── 联网打分（次日实际走势） ─────────────────────────
def _fetch_benchmark_close() -> dict[str, float] | None:
    """拉取上证指数(000001)日线收盘，返回 {YYYY-MM-DD: close}。

    双源降级：东财 index_zh_a_hist（主）→ 新浪 stock_zh_index_daily（备）。
    为什么需要备源：东财 push2 接口在本机（无论直连还是走代理）会整体
    RemoteDisconnected（实测 2026-09-02，同时殃及炸板股池等东财端点），
    而新浪源带/不带代理都稳定可用 —— 不加备源，回测打分永远 0 条
    （08:40 自动化连日「回填 0 条」的根因）。两源列名不同
    （东财：日期/收盘；新浪：date/close），各自解析。
    失败（无网络 / akshare 缺失 / 接口变动）返回 None，由上层降级处理。
    """
    try:
        import akshare as ak
    except Exception as e:  # noqa: BLE001
        logger.warning("[track] akshare 不可用，跳过基准打分: %s", e)
        return None

    def _df_to_closes(df) -> dict[str, float] | None:
        if df is None or getattr(df, "empty", True):
            return None
        date_col = ("日期" if "日期" in df.columns
                    else "date" if "date" in df.columns else df.columns[0])
        close_col = ("收盘" if "收盘" in df.columns
                     else "close" if "close" in df.columns else None)
        if close_col is None:
            return None
        out: dict[str, float] = {}
        for _, row in df.iterrows():
            try:
                d = str(row[date_col])[:10]
                c = float(row[close_col])
                if d and c == c:
                    out[d] = c
            except Exception:  # noqa: BLE001
                continue
        return out or None

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

    # 主源：东财（列名 日期/收盘）
    try:
        df = ak.index_zh_a_hist(symbol=_BENCH_SYMBOL, period="daily",
                                start_date=start, end_date=end)
        closes = _df_to_closes(df)
        if closes:
            return closes
        logger.warning("[track] 东财基准数据为空，降级新浪源")
    except Exception as e:  # noqa: BLE001
        logger.warning("[track] 东财基准拉取失败，降级新浪源: %s", e)

    # 备源：新浪（symbol 需带交易所前缀，返回全量历史）
    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        return _df_to_closes(df)
    except Exception as e:  # noqa: BLE001
        logger.warning("[track] 新浪基准拉取失败: %s", e)
        return None


def _next_day_return(date: str, closes: dict[str, float]) -> float | None:
    """给定预测日 date，取下一个交易日相对当日收盘的涨跌幅(%)。

    若 date 非交易日（周末/节假日），以 date 当日前最近一个交易日为基准，
    取其后第一个交易日为「次日」——对齐实际资金面对应的交易日历。
    """
    sd = sorted(closes.keys())
    if not sd:
        return None
    # 找到基准日：closes 中 <= date 的最大日期（含 date 当天）
    base = None
    for d in sd:
        if d <= date:
            base = d
        else:
            break
    if base is None:
        base = sd[0]
    bi = sd.index(base)
    if bi + 1 >= len(sd):
        return None
    nxt = sd[bi + 1]
    cb, cn = closes[base], closes[nxt]
    if not cb:
        return None
    return round((cn / cb - 1) * 100, 2)


def score_predictions() -> dict:
    """联网拉取基准、对未打分的预测回填 realized/hit，返回本次打分统计。

    幂等：已打分的记录不重复拉取，只在首次调用时补 realized。
    全程不抛：网络失败则未打分记录保持 None，返回 scored=0。
    """
    recs = _load()
    pending = [r for r in recs if r.get("realized") is None]
    if not pending:
        s = summary()
        return {"scored": 0, "accuracy": s["accuracy"], "n": s["n"]}

    closes = _fetch_benchmark_close()
    if not closes:
        return {"scored": 0, "accuracy": summary()["accuracy"], "n": len(recs)}

    n_scored = 0
    for r in recs:
        if r.get("realized") is not None:
            continue
        ret = _next_day_return(r["date"], closes)
        if ret is None:
            continue
        r["realized"] = ret
        pred_dir = _DIR_MAP.get(r.get("bias"), 0)
        if pred_dir == 0:
            r["hit"] = None  # 中性不表态，不判命中
        else:
            actual_dir = 1 if ret > 0 else (-1 if ret < 0 else 0)
            r["hit"] = (pred_dir == actual_dir)
        n_scored += 1

    if n_scored:
        _save(recs)
    s = summary()
    return {"scored": n_scored, "accuracy": s["accuracy"], "n": s["n"]}
