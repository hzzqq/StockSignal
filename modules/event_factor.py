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


# ── R9/T-332：A4 标注层（hard_logic / horizon，benchmark 采纳清单 R9）────────
# 词表为透明规则（命中词即证据可溯源），命中不足/平票一律 unavailable 不编造。
_HARD_LOGIC_KEYWORDS = (
    "订单", "中标", "合同", "签约", "业绩预增", "预增", "扭亏", "回购", "增持",
    "扩产", "产能", "涨价", "提价", "政策", "补贴", "退税", "配额", "重组",
    "并购", "获批", "专利", "认证", "出海", "国产替代", "供需", "紧缺",
)
_SPECULATION_KEYWORDS = (
    "传闻", "据报道", "或拟", "市场消息", "概念股", "蹭", "炒作", "风口", "小作文",
)
_HORIZON_LABELS = {
    1: "当天", 3: "1-3 天", 5: "1 周",
    10: "1-2 周（10 交易日）", 20: "波段（20 交易日）",
}
_ANNOT_NO_TEXT = {"hard_logic": None, "status": "unavailable",
                  "reason": "P1 信号路径无事件文本（标注需新闻/题材源）"}


def annotate_hard_logic(texts) -> dict:
    """R9：事件文本「硬逻辑 vs 题材炒作」透明词表分类。

    硬逻辑=可验证的产业/政策/供需事件（订单/业绩/政策…）；题材炒作=传闻/概念追逐。
    词表命中计数：硬>题 → "硬逻辑"，题>硬 → "题材炒作"，平票/双零/空 → unavailable
    （不编造）；``evidence`` 返回命中词（≤5，可溯源）。
    """
    if not isinstance(texts, (list, tuple)):
        texts = [texts]
    joined = [t for t in texts if isinstance(t, str) and t.strip()]
    hits_hard = [w for w in _HARD_LOGIC_KEYWORDS if any(w in t for t in joined)]
    hits_spec = [w for w in _SPECULATION_KEYWORDS if any(w in t for t in joined)]
    n_hard, n_spec = len(hits_hard), len(hits_spec)
    if n_hard == n_spec:
        return {"hard_logic": None, "status": "unavailable",
                "reason": f"特征词平票或未命中（硬逻辑 {n_hard} vs 题材 {n_spec}）"}
    label = "硬逻辑" if n_hard > n_spec else "题材炒作"
    evidence = (hits_hard if n_hard > n_spec else hits_spec)[:5]
    return {"hard_logic": label, "status": "ok", "evidence": evidence}


def annotate_horizon(model_horizon) -> dict:
    """R9：把 P1 信号 json 自带 ``horizon``（交易日数）如实映射兑现窗口。

    非整数 / 词表外取值 → unavailable（不默认、不编造窗口）。
    """
    if isinstance(model_horizon, bool) or not isinstance(model_horizon, int):
        return {"horizon": None, "status": "unavailable",
                "model_horizon": None,
                "reason": f"信号未提供 horizon（取到 {model_horizon!r}）"}
    label = _HORIZON_LABELS.get(model_horizon)
    if label is None:
        return {"horizon": None, "status": "unavailable",
                "model_horizon": model_horizon,
                "reason": f"horizon={model_horizon} 无窗口映射"}
    return {"horizon": label, "status": "ok", "model_horizon": model_horizon}


def _loader_horizon(loader: Any, model: str):
    """读信号 json 的 horizon 字段（loader 有缓存，不额外加载大文件）。"""
    try:
        return loader.load(model).get("horizon")
    except Exception:  # noqa: BLE401 - 取不到按 unavailable 处理
        return None


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
                    "horizon": annotate_horizon(_loader_horizon(loader, model)),
                    "hard_logic": dict(_ANNOT_NO_TEXT),
                    "source": f"P1-{model}-top_long"}
        shorts = loader.top_short(model)
        s_short = next((r for r in shorts if r.get("symbol") == symbol), None)
        if s_short is not None:
            return {"available": True, "symbol": symbol,
                    "score": float(s_short.get("pred", 0.0) or 0.0),
                    "signal": "看空",
                    "rank": float(s_short.get("rank", 0.0) or 0.0),
                    "horizon": annotate_horizon(_loader_horizon(loader, model)),
                    "hard_logic": dict(_ANNOT_NO_TEXT),
                    "source": f"P1-{model}-top_short"}
    except Exception as e:
        # 榜单读取异常不致命，继续走精确路径
        logger.warning("[event_factor] top_long/top_short 读取异常，降级到精确路径: %s", e)
        pass

    # ── 精确路径：daily 逐日得分（仅当不在榜单时加载大数组）──
    try:
        df = loader.daily_df(model)
    except Exception as e:
        logger.warning("[event_factor] daily_df 读取失败（将按无信号处理）: %s", e)
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
                    "horizon": annotate_horizon(_loader_horizon(loader, model)),
                    "hard_logic": dict(_ANNOT_NO_TEXT),
                    "source": f"P1-{model}-daily"}

    # ── 第二真实源：真实东方财富新闻情感（P1 无信号时仍给出现实事件信号）──
    # 这是事件因子适配器的「多真实源」扩展：P1 EV 是 ranked pool 主源，新闻是
    # 逐标的真实事件面兜底源，两者都真实、互不替代、绝不造数。
    try:
        nw = news_event_signal(symbol)
        if nw.get("available"):
            return nw
    except Exception as e:  # noqa: BLE401
        logger.warning(f"[event_factor] 新闻事件信号兜底失败: {e}")

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

    _hz = annotate_horizon(_loader_horizon(loader, model))  # R9/T-332：兑现窗口
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
            "horizon": dict(_hz),
            "hard_logic": dict(_ANNOT_NO_TEXT),
            "raw_pred": r.get("pred"),
            "signal": "看多",
            "source": f"P1-{model}-top_long",
        })
    return out


def news_event_signal(ticker: str, limit: int = 15) -> dict:
    """真实新闻事件信号（东方财富）：抓 ticker 相关新闻 → 情感分布 → 事件得分。

    事件因子适配器的**第二个真实源**（P1 EV 之外的真实事件/新闻源）。标的不在 P1 池
    / 无 P1 信号时，仍能给出现实的新闻面事件信号，而非空。与 P1 EV 真实源独立互补、
    绝不造数——无真实新闻即 ``available=False``。

    返回结构（成功）：
        {"available": True, "symbol": ..., "score": 0-100,
         "rank": score/100（供 _event_factor_to_score 无损回映射）,
         "signal": "看多"|"看空"|"中性", "source": "eastmoney-news"}
    返回结构（无数据）：
        {"available": False, "symbol": ..., "reason": ...}
    """
    sym = ticker or ""
    if not sym:
        return {"available": False, "symbol": sym, "reason": "未提供标的代码"}
    try:
        from modules.news import NewsFetcher, SentimentAnalyzer
        news = NewsFetcher().fetch(keyword=sym, source="eastmoney", limit=limit)
    except Exception as e:  # pragma: no cover - 网络/源异常
        logger.warning(f"[event_factor] 新闻抓取失败({sym}): {e}")
        return {"available": False, "symbol": sym, "reason": f"新闻抓取失败: {e}"}
    if news is None or getattr(news, "empty", True) or news.empty:
        return {"available": False, "symbol": sym, "reason": "无相关东方财富新闻"}
    try:
        dist = SentimentAnalyzer().sentiment_distribution(news)
    except Exception as e:  # pragma: no cover - 分析异常
        logger.warning(f"[event_factor] 情感分析失败({sym}): {e}")
        return {"available": False, "symbol": sym, "reason": f"情感分析失败: {e}"}
    # 与 modules.signal._live_news_sentiment 同口径（50=多空平衡），仅作事件信号参考
    pos_pct = dist.get("正面", 0)
    neg_pct = dist.get("负面", 0)
    score = int(max(0, min(100, 50 + (pos_pct - neg_pct) * 0.6)))
    if score >= 55:
        sig = "看多"
    elif score <= 45:
        sig = "看空"
    else:
        sig = "中性"
    try:
        _titles = [str(x) for x in news["title"].tolist()]
    except Exception:  # noqa: BLE401 - 标题列缺失时按无文本处理
        _titles = []
    return {
        "available": True, "symbol": sym,
        "score": float(score), "rank": float(score) / 100.0,
        "signal": sig, "source": "eastmoney-news",
        "hard_logic": annotate_hard_logic(_titles),  # R9/T-332：新闻标题可分类
    }
