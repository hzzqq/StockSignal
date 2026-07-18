"""
modules/quantagent/agents/data_agent.py
----------------------------------------
数据 Agent：投研流程的「数据底座」。

职责：
1. 优先调用 StockSignal 的 StockFetcher 获取真实 A股日线；
2. 网络不可用（离线演示）时，生成一条确定性的合成行情，保证整条多智能体链路可跑通；
3. 经过 DataCleaner.full_pipeline 产出带均线/收益率的标准行情，供后续所有 Agent 共享；
4. 产出 market_brief 速览 + data_report。

这是其余 4 个分析 Agent 的唯一数据来源，避免每个 Agent 重复抓取。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict

import numpy as np
import pandas as pd

from modules.quantagent.agents.base import BaseAgent
from modules.quantagent.state import ResearchState, store_df


def _synthetic_df(ticker: str, seed: int = 42, days: int = 250) -> pd.DataFrame:
    """确定性合成行情（随机游走 + 轻微趋势），仅用于离线演示。"""
    rng = np.random.default_rng(seed + int(ticker) if ticker.isdigit() else seed)
    end = _dt.date.today()
    start = end - _dt.timedelta(days=days * 1.4)
    dates = pd.bdate_range(start, end)[:days]
    price = 100.0
    rows = []
    for d in dates:
        ret = rng.normal(0.0005, 0.02)
        price *= (1 + ret)
        high = price * (1 + abs(rng.normal(0, 0.01)))
        low = price * (1 - abs(rng.normal(0, 0.01)))
        open_ = low + (high - low) * rng.random()
        volume = int(rng.integers(5_000_000, 30_000_000))
        amount = volume * price
        rows.append([d, open_, high, low, price, volume, amount])
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
    return df


def _ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """确保DataFrame含 ma5/ma10/ma20/ma60 与 return_1d/5d/20d，缺则补算。"""
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    for w in (5, 10, 20, 60):
        col = f"ma{w}"
        if col not in df.columns and len(df) >= w:
            df[col] = df["close"].rolling(w).mean()
    for n, c in ((1, "return_1d"), (5, "return_5d"), (20, "return_20d")):
        if c not in df.columns and len(df) > n:
            df[c] = df["close"].pct_change(n) * 100
    return df


class DataAgent(BaseAgent):
    name = "data"
    role = "数据工程师：获取并标准化行情数据"

    def run(self, state: ResearchState) -> str:
        ticker = state.ticker
        today = _dt.date.today()
        start = (today - _dt.timedelta(days=365)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        df = None
        real = False
        fetcher = self._safe_import("modules.fetcher", "StockFetcher", state)
        try:
            if fetcher is not None:
                f = fetcher()
                df = f.get_daily(ticker, start=start, end=end)
                real = True
        except Exception as e:  # noqa: BLE001
            state.add_error(f"真实行情获取失败（将使用合成数据演示）: {e}")

        if df is None or (hasattr(df, "empty") and df.empty):
            df = _synthetic_df(ticker)
            state.used_real_data = False
        else:
            state.used_real_data = True

        # 标准化：补均线/收益率，供技术面/信号/回测共用
        cleaner = self._safe_import("modules.cleaner", "DataCleaner", state)
        try:
            if cleaner is not None:
                df = cleaner.full_pipeline(df)
        except Exception:
            pass
        df = _ensure_indicators(df)
        state.df = df
        store_df(state.ticker, df)  # 注册表留存，供 LangGraph 跨节点取用（避免 DataFrame 序列化）

        # 行情速览
        last = df.iloc[-1]
        close = float(last["close"])
        prev = float(df.iloc[-2]["close"]) if len(df) >= 2 else close
        chg = (close - prev) / prev * 100 if prev else 0.0
        brief = {
            "date": str(last.get("date", ""))[:10],
            "close": round(close, 2),
            "change_pct": round(chg, 2),
            "high_20": round(float(df["high"].tail(20).max()), 2),
            "low_20": round(float(df["low"].tail(20).min()), 2),
            "ma20": round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else close,
            "volume_avg_20": int(df["volume"].tail(20).mean()) if "volume" in df else 0,
            "rows": int(len(df)),
        }
        state.market_brief = brief
        state.data_report = {
            "text": (
                f"数据底座：{'真实行情（StockFetcher 四级降级链）' if real else '离线合成演示行情'}。"
                f"共 {brief['rows']} 个交易日，最新收盘 ¥{brief['close']}（{chg:+.2f}%），"
                f"20日区间 [{brief['low_20']}, {brief['high_20']}]，MA20={brief['ma20']}。"
            ),
            "brief": brief,
        }
        return f"[{self.role}] 行情就绪：{'真实' if real else '合成'}数据 {brief['rows']} 条，收盘 ¥{brief['close']}（{chg:+.2f}%）"
