"""事件因子适配器（StockSignal 特征系统入口）。

把「事件因子」这一量化特征对接到**真实信号源**，而非合成演示数据。

当前真实源：P1-QuantFactor 的 EV 模型信号（在 38 维量价特征上并入「牧羊人市场广度
情绪」9 维作为事件/regime 通道，共 47 维）——即一个已落地的真实事件因子。

设计要点：
- 纯只读、无网络、无合成/假数据；取不到即 ``available=False`` 优雅降级。
- 快路径先看多/看空榜（不加载 daily 大数组），精确路径再回退 daily 逐日得分。
- ``P1SignalLoader`` 懒导入，模块与具体数据源解耦，未来可挂别的真实事件源。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_event_factor(symbol: str, model: str = "ev", loader: Any | None = None) -> dict:
    """返回某标的的真实事件因子信号。

    返回结构（成功）：
        {"available": True, "symbol": ..., "score": float|None,
         "signal": "看多"|"看空"|..., "rank": float|None,
         "date": str|None, "source": "P1-ev-top_long"|...}
    返回结构（无数据）：
        {"available": False, "symbol": ..., "reason": ...}

    绝不返回合成/随机值——取不到就明说取不到。
    """
    if not symbol:
        return {"available": False, "symbol": symbol, "reason": "未提供标的代码"}

    # 懒导入，避免与具体数据源强耦合（也防 p1_signal 异常时拖垮导入方）
    if loader is None:
        try:
            from modules.p1_signal import P1SignalLoader
        except Exception as e:  # pragma: no cover - 模块级依赖异常
            return {"available": False, "symbol": symbol,
                    "reason": f"P1 信号加载器不可用: {e}"}
        try:
            loader = P1SignalLoader()
        except Exception as e:  # pragma: no cover - 初始化异常
            return {"available": False, "symbol": symbol,
                    "reason": f"加载器初始化失败: {e}"}

    try:
        models = loader.available_models()
    except Exception as e:
        return {"available": False, "symbol": symbol, "reason": f"信号目录扫描失败: {e}"}
    if model not in models:
        return {"available": False, "symbol": symbol,
                "reason": f"模型 {model} 无信号文件（已搜索：{loader.source_dirs})"}

    # ── 快路径：看多 / 看空榜（小数组，不加载 daily 大文件）──
    try:
        longs = loader.top_long(model)
        s_long = next((r for r in longs if r.get("symbol") == symbol), None)
        if s_long is not None:
            return {"available": True, "symbol": symbol,
                    "score": float(s_long.get("pred", 0.0) or 0.0),
                    "signal": "看多",
                    "rank": float(s_long.get("rank", 0.0) or 0.0),
                    "source": f"P1-{model}-top_long"}
        shorts = loader.top_short(model)
        s_short = next((r for r in shorts if r.get("symbol") == symbol), None)
        if s_short is not None:
            return {"available": True, "symbol": symbol,
                    "score": float(s_short.get("pred", 0.0) or 0.0),
                    "signal": "看空",
                    "rank": float(s_short.get("rank", 0.0) or 0.0),
                    "source": f"P1-{model}-top_short"}
    except Exception:
        # 榜单读取异常不致命，继续走精确路径
        pass

    # ── 精确路径：daily 逐日得分（仅当不在榜单时加载大数组）──
    try:
        df = loader.daily_df(model)
    except Exception:
        df = None
    if df is not None and not getattr(df, "empty", True):
        try:
            sub = df[df["symbol"] == symbol]
        except Exception:
            sub = None
        if sub is not None and not getattr(sub, "empty", True):
            row = sub.sort_values("date").iloc[-1]
            return {"available": True, "symbol": symbol,
                    "score": float(row.get("score", 0.0) or 0.0),
                    "signal": row.get("signal"),
                    "date": str(row.get("date")),
                    "source": f"P1-{model}-daily"}

    return {"available": False, "symbol": symbol,
            "reason": "该标的无 P1 事件因子信号（不在池内或近期无预测）"}


def event_driven_long_list(top_n: int = 20, model: str = "ev",
                            loader: Any | None = None) -> list[dict]:
    """返回「事件驱动看多榜」——按真实事件因子排序的多头候选池。

    来源即 P1 ``top_long``（EV 模型 = EV 事件因子，已并入牧羊人情绪 9 维
    事件/regime 通道），天然带模型自身百分位排名，无需对全市场 5000 股
    实时重排序。

    返回每项（已统一展示量纲）：
        {"symbol", "score"(0-100 由 rank 映射), "raw_rank", "raw_pred",
         "signal"(恒为"看多"), "source"}

    取不到真实信号（无文件 / 模型缺失 / 异常）优雅返回 ``[]``，
    调用方应展示「无信号」提示而非报错。
    """
    if loader is None:
        try:
            from modules.p1_signal import P1SignalLoader
            loader = P1SignalLoader(ttl=300)
        except Exception as e:  # pragma: no cover - 模块级依赖异常
            logger.warning(f"[event_factor] 事件驱动看多榜加载器不可用: {e}")
            return []
    try:
        rows = loader.top_long(model, top_n)
    except Exception as e:  # pragma: no cover - 视图层异常
        logger.warning(f"[event_factor] 读取 top_long 失败: {e}")
        return []

    out: list[dict] = []
    for r in rows:
        rank = r.get("rank")
        pct = None
        if isinstance(rank, (int, float)):
            pct = round(float(rank) * 100, 1)  # rank 0-1 → 0-100 百分位
        out.append({
            "symbol": r.get("symbol"),
            "score": pct,
            "raw_rank": rank,
            "raw_pred": r.get("pred"),
            "signal": "看多",
            "source": f"P1-{model}-top_long",
        })
    return out
