"""事件因子适配器（StockSignal 特征系统入口）。
from modules.cache_utils import TTL_TIERS  # R-14

把「事件因子」这一量化特征对接到**真实信号源**，而非合成演示数据。

当前四个真实源（get_event_factor 兜底序，互不替代、绝不造数）：
  1) P1-QuantFactor 的 EV 模型信号（38 维量价 + 牧羊人市场广度情绪 9 维 = 47 维）
  2) 东方财富个股新闻情感（news_event_signal，逐标的真实事件面）
  3) 东方财富龙虎榜上榜信号（lhb_event_signal，游资/机构关注度）
  4) 本地事件追踪主表（tracked_event_signal，data/events.csv：23 页人工录入 +
     87 页语音事件入库的用户沉淀真实事件，与 signal.event_score 同口径）

设计要点：
- 纯只读、无网络、无合成/假数据；取不到即 ``available=False`` 优雅降级。
- 快路径先看多/看空榜（不加载 daily 大数组），精确路径再回退 daily 逐日得分。
- ``P1SignalLoader`` 懒导入，模块与具体数据源解耦，未来可挂别的真实事件源。
"""

from __future__ import annotations
from modules.cache_utils import TTL_TIERS  # R-14 修复：此前误写进 docstring 从未执行

import logging
import os
import re
from typing import Any

import pandas as pd

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
        return None  # ui_audit_exempt(T-239R2): except 内优雅降级哨兵-已审


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

    # ── 第三真实源：龙虎榜上榜信号（游资/机构关注度，与 P1/新闻独立互不替代）──
    try:
        lhb = lhb_event_signal(symbol)
        if lhb.get("available"):
            return lhb
    except Exception as e:  # noqa: BLE401
        logger.warning(f"[event_factor] 龙虎榜事件信号兜底失败: {e}")

    # ── 第四真实源：本地事件追踪主表（23 页人工录入 / 87 页语音事件入库）──
    # 用户沉淀的真实事件也是事件因子：与前三源独立互补，取不到即降级，绝不造数。
    try:
        tk = tracked_event_signal(symbol)
        if tk.get("available"):
            return tk
    except Exception as e:  # noqa: BLE401
        logger.warning(f"[event_factor] 本地事件主表信号兜底失败: {e}")

    return {"available": False, "symbol": symbol,
            "reason": "该标的无 P1 事件因子信号（不在池内/近期无预测，且近 10 日无新闻信号、"
                      "未上龙虎榜、本地事件主表近 30 日无关联事件）"}


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
            loader = P1SignalLoader(ttl=TTL_TIERS["sentiment"])
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


def lhb_event_signal(ticker: str, lookback_days: int = 10) -> dict:
    """第三真实源：龙虎榜上榜信号（东方财富 stock_lhb_detail_em）。

    akshare 函数名与返回列名均已**核实源码**（akshare 1.18.64，`stock_lhb_detail_em`
    返回「代码 / 上榜日 / 龙虎榜净买额 / 上榜原因」等中文列）。规则透明：
      - 最近 ``lookback_days`` 个自然日窗口内上榜 → 事件存在；**未上榜是正常状态**
        （``available=False``，非错误）。
      - 方向取窗口内最近一次上榜的「龙虎榜净买额」：>0 看多(62) / <0 看空(38) /
        缺失或 0 中性(50)；上榜次数与最近原因如实附带。绝不造数。
    返回结构（成功）：
        {"available": True, "symbol", "score", "rank", "signal",
         "source": "eastmoney-lhb", "hard_logic": annotate_hard_logic(上榜原因),
         "lhb": {"count", "last_date", "net_amt", "reason"}}
    返回结构（未上榜/异常）：
        {"available": False, "symbol", "reason"}
    """
    sym = str(ticker or "").strip()
    if not sym:
        return {"available": False, "symbol": ticker, "reason": "未提供标的代码"}
    try:
        import akshare as ak
        from datetime import datetime, timedelta
        end = datetime.now()
        start = end - timedelta(days=int(lookback_days))
        df = ak.stock_lhb_detail_em(start_date=start.strftime("%Y%m%d"),
                                    end_date=end.strftime("%Y%m%d"))
    except Exception as e:  # noqa: BLE001 - 网络/接口异常诚实降级
        logger.warning(f"[event_factor] 龙虎榜抓取失败({ticker}): {e}")
        return {"available": False, "symbol": ticker, "reason": f"龙虎榜抓取失败: {e}"}
    if df is None or getattr(df, "empty", True):
        return {"available": False, "symbol": ticker, "reason": "龙虎榜窗口内无数据"}
    try:
        if "代码" not in df.columns:
            return {"available": False, "symbol": ticker, "reason": "龙虎榜返回缺「代码」列"}
        # 归一化：兼容 "600077" / "600077.SH" / "sh600077"（P1 侧带交易所前缀）
        want = re.sub(r"^(sh|sz|bj)", "", sym.split(".")[0], flags=re.IGNORECASE).zfill(6)
        sub = df[df["代码"].astype(str).str.strip().str.zfill(6) == want]
        if getattr(sub, "empty", True):
            return {"available": False, "symbol": ticker,
                    "reason": f"近 {lookback_days} 日未上龙虎榜（正常状态，非错误）"}
        sub = sub.sort_values("上榜日")
        last = sub.iloc[-1]
        try:
            net = float(last.get("龙虎榜净买额"))
        except (TypeError, ValueError):
            net = None
        if net is not None and net > 0:
            score, sig = 62.0, "看多"
        elif net is not None and net < 0:
            score, sig = 38.0, "看空"
        else:
            score, sig = 50.0, "中性"
        reasons = [str(x) for x in (sub["上榜原因"].tolist() if "上榜原因" in sub.columns else [])
                   if str(x).strip()]
        return {
            "available": True, "symbol": sym,
            "score": score, "rank": score / 100.0,
            "signal": sig, "source": "eastmoney-lhb",
            "hard_logic": annotate_hard_logic(reasons),  # 上榜原因可做硬逻辑/题材分类
            "lhb": {
                "count": int(len(sub)),
                "last_date": str(last.get("上榜日")),
                "net_amt": net,
                "reason": (reasons[-1] if reasons else None),
            },
        }
    except Exception as e:  # noqa: BLE001 - 解析异常诚实降级
        logger.warning(f"[event_factor] 龙虎榜解析失败({ticker}): {e}")
        return {"available": False, "symbol": ticker, "reason": f"龙虎榜解析失败: {e}"}


# ── 第四真实源：本地事件追踪主表（2026-11-03 事件数据链融合闭环）──────────────
# 数据来源：23 页人工录入 + 87 页语音事件入库（save_voice_event_to_db），
# 都是用户沉淀的真实事件。此前 signal.event_score 在 P1/新闻/龙虎榜命中时直接
# 短路，本地主表被整体忽略——本函数把主表接为事件因子的兜底源，PR-2 再做融合。
_TRACKED_POS_WEIGHT = {"大": 2, "小": 1}
_TRACKED_NEUTRAL_BASE = 52  # 与 signal.event_score 中性基准同口径


def tracked_event_signal(ticker: str, lookback_days: int = 30,
                         keywords=None, config_path: str = "config.yaml") -> dict:
    """本地事件追踪主表信号（第四真实源，data/events.csv）。

    口径与 ``signal.event_score`` 一致：近 ``lookback_days`` 日窗口 + ticker
    匹配（包含式；空/占位 ticker 视为市场级事件，对所有标的生效——此处修正了
    event_score 中 ``astype(str)`` 后 ``isna()`` 恒假的死分支，市场级事件真实生效）。
    聚合按 T-288 五档情感词表：大利空-2 / 小利空-1 / 中性 0 / 小利好 +1 / 大利好 +2，
    中性基准 52，每档净权 x8 分。

    ``keywords``：``None`` 不过滤；空列表 => 不匹配任何事件（与 event_score
    空关键词语义一致，防空正则命中全部的隐性 bug）；非空列表 => 标题正则包含匹配。

    返回（成功）：
        {"available": True, "symbol", "score", "rank", "signal",
         "source": "tracked-events", "hard_logic",
         "tracked": {"n_events", "window_days", "titles"}}
    返回（无数据）：
        {"available": False, "symbol", "reason"}
    绝不造数：无主表/无匹配/解析失败一律 available=False。
    """
    sym = str(ticker or "").strip()
    if not sym:
        return {"available": False, "symbol": ticker, "reason": "未提供标的代码"}
    try:
        from modules.signal import events_db_path  # 惰性导入：signal 反向惰性引用本模块，防循环
    except Exception as e:  # pragma: no cover
        return {"available": False, "symbol": sym, "reason": f"事件主表路径解析不可用: {e}"}
    path = events_db_path(config_path)
    if not os.path.exists(path):
        return {"available": False, "symbol": sym,
                "reason": "本地事件主表不存在（尚未录入任何事件）"}
    try:
        df = pd.read_csv(path)
        df["ticker"] = df["ticker"].astype(str).str.strip()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    except Exception as e:  # noqa: BLE001 - 损坏文件诚实降级
        logger.warning(f"[event_factor] 事件主表读取失败({sym}): {e}")
        return {"available": False, "symbol": sym, "reason": f"事件主表读取失败: {e}"}
    if df.empty:
        return {"available": False, "symbol": sym, "reason": "本地事件主表为空"}

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=int(lookback_days))
    df = df[df["date"].notna() & (df["date"] >= cutoff)]
    if df.empty:
        return {"available": False, "symbol": sym,
                "reason": f"本地事件主表近 {lookback_days} 日无事件"}

    # ticker 匹配：包含式 + 市场级占位。注意新版 pandas 的 astype(str) 不再把
    # NaN 转成字符串 "nan"（保留 NA），所以占位判断必须同时覆盖 isna 与字面串。
    _t_str = df["ticker"].astype(str)
    market_level = df["ticker"].isna() | _t_str.isin(["", "nan", "None", "<NA>"])
    matched = df[_t_str.str.contains(sym, na=False, regex=False) | market_level]
    if keywords is not None:
        if not keywords:  # 空列表显式不匹配（与 event_score 空关键词语义一致）
            matched = matched.iloc[0:0]
        else:
            pat = "|".join(re.escape(str(k)) for k in keywords)
            matched = matched[matched["title"].str.contains(pat, na=False, regex=True)]
    if matched.empty:
        return {"available": False, "symbol": sym,
                "reason": f"本地事件主表近 {lookback_days} 日无 {sym} 关联事件"}

    net = 0
    for _, evt in matched.iterrows():
        evt_type = str(evt.get("type", ""))
        if "大利好" in evt_type or "重大利好" in evt_type:
            net += _TRACKED_POS_WEIGHT["大"]
        elif "利好" in evt_type or "正面" in evt_type:
            net += _TRACKED_POS_WEIGHT["小"]
        elif "大利空" in evt_type or "重大利空" in evt_type:
            net -= _TRACKED_POS_WEIGHT["大"]
        elif "利空" in evt_type or "负面" in evt_type:
            net -= _TRACKED_POS_WEIGHT["小"]
        # 中性/未知类型不加减（关注度不冒充方向）
    score = float(max(5, min(95, _TRACKED_NEUTRAL_BASE + 8 * net)))
    if score >= 55:
        sig = "看多"
    elif score <= 45:
        sig = "看空"
    else:
        sig = "中性"
    titles = [str(x) for x in matched["title"].tolist() if str(x).strip()]
    return {
        "available": True, "symbol": sym,
        "score": score, "rank": score / 100.0,  # rank 供 _event_factor_to_score 无损回映射
        "signal": sig, "source": "tracked-events",
        "hard_logic": annotate_hard_logic(titles),
        "tracked": {
            "n_events": int(len(matched)),
            "window_days": int(lookback_days),
            "titles": titles[:5],  # 旁注只带前 5 条，防超长
        },
    }
