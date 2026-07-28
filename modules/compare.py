"""多股票横向对比引擎 + 前端

模仿 compare-analysis-20260710.html 的暗色 .sf-* 视觉风格（卡片 / 横向对比表 /
两两 VS 卡 / 综合评分雷达 / 分层操作建议）。

数据来源（全部程序化、可离线降级）：
  - modules.fetcher.StockFetcher.get_daily / get_stock_name
  - modules.cleaner.DataCleaner.full_pipeline
  - modules.technical.full_analysis  （趋势/动量/量能/形态 四维打分）
  - 价格相关性（横截 Pearson）作为「关联度」
  - 启发式「订单催化 / 弹性」代理指标
  - best-effort：akshare 个股信息（总市值 / 行业）与估值（TTM 市盈率）

配色严格遵循 A 股约定：涨/利好/买入=红(#ff4d4f)，跌/利空/卖出=绿(#00d486)，
中性/持有=琥珀(#ffa502)。这与本仓库 K 线及个股分析页一致。
"""
from __future__ import annotations

import datetime as _dt
import time as _time
import re
import logging

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules._compare_render import _biz_groups  # 拆分后此共享小工具位于渲染层（叶子模块）


# =====================================================================
# 数据层
# =====================================================================
def fetch_compare(codes: List[str], period_days: int = 120) -> List[Dict[str, Any]]:
    """对每只股票拉取数据并计算所有对比维度，返回 list[dict]（一只一个）。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    codes = [str(c).strip().zfill(6) for c in codes if c]
    rows: List[Dict[str, Any]] = [None] * len(codes)
    with ThreadPoolExecutor(max_workers=min(len(codes), 4)) as ex:
        future_to_idx = {
            ex.submit(_build_row, None, code, period_days): i
            for i, code in enumerate(codes)
        }
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            rows[i] = future.result()
    _fill_business_correlation(rows)
    return rows


def _build_row(fetcher: Optional[StockFetcher], code: str, period_days: int) -> Dict[str, Any]:
    """构建单只股票对比行；每个线程自己创建 fetcher，避免 SQLite 连接竞争。"""
    fetcher = fetcher or StockFetcher()
    name = ""
    try:
        # 1) 本地缓存最可靠，且会自动 warm-up
        _, basic_name = fetcher.get_stock_basic(code)
        if basic_name and str(basic_name).strip() and str(basic_name).strip() != code:
            name = basic_name.strip()
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        pass

    # 2) 本地无名称时，尝试 BaoStock 并解析 "600519(贵州茅台)"
    if not name:
        try:
            raw = fetcher.get_stock_name(code) or ""
            if raw and str(raw).strip() and str(raw).strip() != code:
                raw = raw.strip()
                if "(" in raw and ")" in raw:
                    name = raw.split("(", 1)[1].split(")", 1)[0].strip()
                else:
                    name = raw
        except Exception as e:
            logger.warning(f"[compare] 未处理异常: {e}")
            pass

    # 3) 兜底：代码本身
    if not name:
        name = code

    row: Dict[str, Any] = {"code": code, "name": name}

    end = _dt.datetime.now().strftime("%Y-%m-%d")
    start = (_dt.datetime.now() - _dt.timedelta(days=period_days)).strftime("%Y-%m-%d")
    try:
        df = fetcher.get_daily(code, start=start, end=end)
        df = DataCleaner.full_pipeline(df)
        row["df"] = df
        row["asof"] = str(df.iloc[-1]["date"])[:10]
        last = df.iloc[-1]
        row["close"] = float(last["close"])
        row["chg_pct"] = float(last.get("return_1d", 0.0) or 0.0)

        ta = full_analysis(df)
        row["ta"] = ta
        trend = float(ta["trend"]["trend_score"])
        mom = float(ta["momentum"]["momentum_score"])
        vol = float(ta["volume"]["volume_price_score"])
        pat = _pattern_score(ta.get("patterns", []))
        composite = int(round(0.30 * trend + 0.25 * mom + 0.20 * vol + 0.25 * pat))
        row["scores"] = {"trend": trend, "momentum": mom, "volume": vol,
                         "pattern": pat, "composite": composite}
        # 弹性（年化波动率 %）
        rets = df["close"].pct_change().dropna()
        row["elasticity"] = float(rets.std() * np.sqrt(242) * 100) if len(rets) > 1 else 0.0
        row["signal"] = _signal_from(composite, ta)
        row["catalyst"] = _catalyst_score(ta)
        recent = df.tail(60)
        row["support"] = float(recent["low"].min())
        row["resistance"] = float(recent["high"].max())
    except Exception as e:
        logger.warning(f"[compare] 处理异常: {e}")
        # 行情不可用 → 中性默认，不影响整体渲染
        row["error"] = str(e)
        row["df"] = None
        row["asof"] = end
        row["close"] = None
        row["chg_pct"] = 0.0
        row["scores"] = {"trend": 50, "momentum": 50, "volume": 50,
                         "pattern": 50, "composite": 50}
        row["elasticity"] = 0.0
        row["signal"] = "持有"
        row["catalyst"] = 50
        row["support"] = None
        row["resistance"] = None

    _fill_fundamentals(row, fetcher)
    _fill_extra_metrics(row, fetcher)
    return row


def _pattern_score(patterns) -> float:
    """形态信号打分：看涨 +12 / 看跌 -12 / 中性 0，封顶 0-100。"""
    s = 50.0
    for p in (patterns or []):
        bias = str(p.get("bias", ""))
        if "看涨" in bias:
            s += 12
        elif "看跌" in bias:
            s -= 12
    return float(max(0, min(100, s)))


def _catalyst_score(ta) -> float:
    """订单/催化代理分（0-100）：动量 + 量能 + 形态突破。"""
    mom = float(ta["momentum"]["momentum_score"])
    vol = float(ta["volume"]["volume_price_score"])
    pat = _pattern_score(ta.get("patterns", []))
    s = 50 + (mom - 50) * 0.45 + (vol - 50) * 0.30 + (pat - 50) * 0.35
    return float(max(0, min(100, s)))


def _signal_from(composite: int, ta) -> str:
    mom_label = str(ta.get("momentum", {}).get("momentum_label", ""))
    strong = any(k in mom_label for k in ("上攻", "走强", "上涨"))
    if composite >= 68 and strong:
        return "买入"
    if composite >= 55:
        return "持有"
    return "卖出"


# 行业大类映射：用于「业务关联度」的板块亲和度判断


def _biz_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """两只股票的业务相似度（0-100）：同行业最高，同大类次之，否则弱相关。"""
    ia, ib = (a.get("industry") or ""), (b.get("industry") or "")
    if not ia or not ib:
        return 0.0
    if ia == ib:
        return 90.0
    if ia in ib or ib in ia:
        return 60.0
    ga, gb = _biz_groups(ia), _biz_groups(ib)
    if ga and gb and set(ga) & set(gb):
        return 55.0
    return 12.0


def _fill_business_correlation(rows: List[Dict[str, Any]]) -> None:
    """以组内业务相似度均值作为「业务关联度」（替代原价格相关性关联度）。"""
    for r in rows:
        others = [o for o in rows if o is not r]
        if others:
            sims = [_biz_similarity(r, o) for o in others]
            r["business_corr"] = float(sum(sims) / len(sims))
        else:
            r["business_corr"] = 0.0


def _fill_fundamentals(row: Dict[str, Any], fetcher: "StockFetcher" = None) -> None:
    """基本面（东方财富 push2 / akshare）：总市值(亿) / 市盈率TTM / 行业 / 核心业务。
    失败时重试 2 次；仍失败则基于股票名称做行业推断兜底。核心业务来自同花顺主营构成。"""
    row["market_cap"] = None
    row["pe_ttm"] = None
    row["industry"] = None
    row["core_business"] = None
    try:
        if fetcher is None:
            fetcher = StockFetcher()
        f = None
        last_err = None
        for _ in range(3):
            try:
                f = fetcher.get_fundamentals(row["code"])
                if f:
                    break
            except Exception as e:  # noqa: BLE001
                last_err = e
                _time.sleep(0.5)
        if f:
            row["market_cap"] = f.get("market_cap")
            row["pe_ttm"] = f.get("pe_ttm")
            ind = f.get("industry") or ""
            row["industry"] = ind if ind else None
            # 本地名称缺失时用东方财富名称兜底
            if (not row.get("name") or row["name"] == row["code"]) and f.get("name"):
                row["name"] = f["name"]
        elif last_err:
            logger.warning(f"[compare] 基本面获取失败 {row['code']}: {last_err}")
        # 行业兜底：基于股票名称关键词推断
        if not row.get("industry") and row.get("name") and row["name"] != row["code"]:
            try:
                kws = fetcher.get_stock_keywords(row["name"], top_k=2)
                if kws:
                    row["industry"] = kws.split(",")[0]
            except Exception as e:
                logger.warning(f"[compare] 未处理异常: {e}")
                pass
        # 核心业务：同花顺主营构成（真实主营业务，而非行业标签）
        try:
            biz = fetcher.get_core_business(row["code"])
            row["core_business"] = biz if biz else None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[compare] 核心业务获取失败 {row['code']}: {e}")
            row["core_business"] = None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[compare] 基本面获取失败 {row['code']}: {e}")


def _fill_extra_metrics(row: Dict[str, Any], fetcher: "StockFetcher" = None) -> None:
    """新增对比维度：估值补充(PB/PS/股息率TTM)、财务(ROE/营收同比/净利同比)、
    资金面(主力净流入/大单)。全部 best-effort，失败时留 None（前端渲染「—」）。"""
    code = row.get("code", "")
    for k in ("pb", "ps", "dv_ttm", "roe", "revenue_yoy", "profit_yoy",
               "fund_main_net", "fund_main_net_pct", "fund_big_net",
               "fund_source", "fund_date"):
        row.setdefault(k, None)

    # 估值补充：市净率 / 市销率 / 股息率(TTM) —— 复用与 PE 同源的百度估值接口
    try:
        import akshare as ak
        for ind, key in (("市净率", "pb"), ("市销率", "ps"), ("股息率TTM", "dv_ttm")):
            try:
                df = ak.stock_zh_valuation_baidu(symbol=code, indicator=ind, period="近一年")
                if df is not None and not df.empty:
                    v = df.iloc[-1].get("value")
                    try:
                        row[key] = float(str(v).replace(",", ""))
                    except Exception as e:
                        logger.warning(f"[compare] 未处理异常: {e}")
                        pass
            except Exception as e:
                logger.warning(f"[compare] 未处理异常: {e}")
                pass
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        pass

    # 财务：ROE / 营收同比 / 净利润同比 —— 同花顺财务指标
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator(
            symbol=code, start_year=str(_dt.datetime.now().year - 1))
        if df is not None and not df.empty:
            last = df.iloc[-1]

            def _pick(*names):
                for n in names:
                    for col in df.columns:
                        cn = col.replace(" ", "")
                        if n.replace(" ", "") in cn:
                            try:
                                return float(str(last[col]).replace(",", ""))
                            except Exception as e:
                                logger.warning(f"[compare] 未处理异常: {e}")
                                return None
                return None

            row["roe"] = _pick("净资产收益率", "ROE")
            row["revenue_yoy"] = _pick("营业收入同比增长率", "营收同比")
            row["profit_yoy"] = _pick("净利润同比增长率", "净利润同比")
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        pass

    # 资金面：个股主力资金（akshare 或量价估算兜底）
    try:
        from modules.fundflow import get_individual_fund_flow
        r = get_individual_fund_flow(code)
        if r:
            row["fund_main_net"] = r.get("main_net")
            row["fund_main_net_pct"] = r.get("main_net_pct")
            row["fund_big_net"] = r.get("big_net")
            row["fund_source"] = r.get("source")
            row["fund_date"] = r.get("latest_date")
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        pass


# =====================================================================
# 前端（白天模式 .compare-wrap 风格，1:1 还原参考 HTML）
# =====================================================================
# =====================================================================
# 兼容层：拆分 _compare_render 后，原 modules.compare 的全部公开名保持可导入
# =====================================================================
from modules._compare_render import (  # noqa: E402,F401
    _is_dark,
    _sf,
    SERIES_COLORS,
    _hex_to_rgba,
    _INDUSTRY_GROUPS,
    _biz_groups,
    compare_css,
    _tag,
    _sig_tag,
    _corr_tag,
    _catalyst_tag,
    _elasticity_label,
    _stock_type_label,
    _score_badge,
    _stock_bullets,
    _pair_conclusion,
    build_pairwise_card,
    _vs_box_v2,
    build_header,
    build_one_line,
    build_table,
    build_extra_card,
    _fmt,
    _fmt_pct,
    _fund_yi_cell,
    build_vs_cards,
    _vs_box,
    build_radar,
    _one_liner,
    build_radar_right,
    build_action_plan,
    build_footer,
    METHODS,
    _POLICY_FRIENDLY,
    _BULL_CUES,
    _BEAR_CUES,
    _EVENT_INDUSTRY_MAP,
    _safe,
    _row_score,
    _norm,
    _event_stance,
    compute_method_scores,
    _ranked,
    rank_methods,
    _method_summary,
    _method_analysis,
    _method_score_badge,
    _method_vs_box,
    _method_pair_conclusion,
    build_method_card,
    build_aggregate_card,
)
