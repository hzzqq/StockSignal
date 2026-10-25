"""modules/decision_replay.py — T-325 方向D：决策复盘回放器（编排薄层）。

把「按交易日回放当日决策依据」做成毕设「决策可追踪」叙事的落地页：
给定日期 → 当日当时真实归档快照（温度/周期/仓位/理由/新鲜度）+ 次日实际广度对照
+ 预测打分对账，一站拼装。

数据基础（全部现成，不新建数据链）：
- 归档快照：``modules.decision.load_archive / list_archive_dates``
  （``data/snapshots/YYYY-MM-DD.json``，当前 24 天 2026-08-31~2026-10-23，稀疏归档）
- 次日对照：``data/shepherd_history.csv``（4810 交易日广度真值，T-323 激活）
- 预测对账：``modules.decision_track``（prediction_log.json，含平盘日口径纠正 R7）

诚实边界（AC-R，不可回退）：
- **只回放归档日**：无归档 → ``status="unavailable"``，绝不拿事后重构值冒充
  「当日当时快照」（重构口径与归档口径不可混淆，这是本功能的诚实性底线）；
- **P1 历史未归档**：sj 空间覆盖式导出，历史信号不存在 → 事件因子仅透传归档
  时点数据并如实标注；事件看多/看空榜在回放中**不展示**（无历史数据可回放）；
- **次日对照**：取 date 之后第一个交易日；末日/缺失 → None，绝不默认 0。
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import pandas as pd

logger = logging.getLogger(__name__)

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HISTORY_CSV = os.path.join(_ROOT, "data", "shepherd_history.csv")

P1_REPLAY_NOTE = ("P1 历史信号未归档（sj 空间覆盖式导出，无历史导出可回放），"
                  "回放页事件因子仅展示归档时点数据")


def list_replayable_dates() -> list[str]:
    """可回放日期 = 已归档快照日期（升序；无归档返回空列表）。"""
    from modules.decision import list_archive_dates
    return list_archive_dates()


@lru_cache(maxsize=8)
def _history_df(path: str) -> pd.DataFrame:
    """广度历史（按 path 缓存；只读 date/up_count/down_count 三列）。"""
    df = pd.read_csv(path, usecols=["date", "up_count", "down_count"],
                     encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def next_trading_row(date: str, path: str | None = None) -> dict | None:
    """date 之后第一个交易日的广度行（次日实际对照；纯数据函数，离线可测）。

    - 严格 ``> date`` 的最小日期行（date 当日行不算）；
    - 末日 / 无数据 / up_count 缺失（CSV 稀疏段）→ 如实返 None / None 值，不默认 0。
    """
    p = path or HISTORY_CSV
    try:
        df = _history_df(p)
    except Exception as e:  # noqa: BLE001
        logger.error("[replay] 广度历史读取失败（%s）：%s", p, e)
        return None
    after = df[df["date"] > pd.Timestamp(date)]
    if after.empty:
        return None
    r = after.iloc[0]

    def _int(v):
        return None if pd.isna(v) else int(v)

    return {"date": r["date"].strftime("%Y-%m-%d"),
            "up_count": _int(r["up_count"]),
            "down_count": _int(r["down_count"])}


def build_replay(date: str, *, history_path: str | None = None) -> dict:
    """拼装指定日期的回放包（编排薄层；离线可测）。

    :return: ``{status, date, snapshot, next_day, prediction, p1_note}``；
             无归档 → ``status="unavailable"`` + ``reason``（诚实降级）。
    """
    from modules.decision import load_archive
    from modules.decision_track import find_prediction
    snap = load_archive(date)
    if not snap:
        return {"status": "unavailable", "date": date,
                "reason": "该日期无归档快照（归档链自 2026-08-31 起，稀疏归档）"}
    try:
        pred = find_prediction(date)
    except Exception as e:  # noqa: BLE001
        logger.warning("[replay] 预测记录查询失败 %s: %s", date, e)
        pred = None
    return {
        "status": "ok",
        "date": date,
        "snapshot": snap,                      # 当日当时真实快照，原样透传不粉饰
        "next_day": next_trading_row(date, history_path),
        "prediction": pred,                    # 当日预测与次日打分（None=未记录）
        "p1_note": P1_REPLAY_NOTE,
    }
