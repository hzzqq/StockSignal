"""
智能选股引擎（移植自 stock-selecter skill 的 11 种策略）

数据源切换说明（相对原 skill）：
- 技术面 6 策略（macd/trend/bollinger/volume_surge/low_position/pattern）：
  价格数据走 StockSignal 自带 ``StockFetcher.get_daily`` / ``get_kline(period='weekly')``，
  技术指标复用 ``screener_indicators``（纯 pandas），不依赖任何外部 API。
- 基本面 5 策略（roe/dividend/valuation/growth/cashflow_quality/shareholder_concentration）：
  财务指标走 akshare ``stock_financial_analysis_indicator``；股息率/PE/PB 走 akshare
  ``stock_a_indicator_lg``；股东户数走 akshare ``stock_zh_a_gdhs``；利润表/现金流走
  ``StockFetcher.get_financial``。所有基本面取数均 try/except 包裹，失败则该股被该策略剔除，
  不中断整体扫描。

组合模式：and（交集）/ or（并集）/ score（综合评分，同并集按总分排序）。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import pandas as pd
import numpy as np

from .screener_indicators import (
    calculate_macd, analyze_trend, detect_bottom_divergence,
    check_volume_surge, calculate_rsi, calculate_bollinger_bands,
    calculate_financial_ratios,
)
from .fetcher import StockFetcher

logger = logging.getLogger("stock_screener")

# ── 策略元信息 ──────────────────────────────────────────────────────────
STRATEGY_NAMES_CN = {
    "roe": "ROE盈利能力",
    "macd": "MACD底背离",
    "dividend": "高股息",
    "valuation": "低估值",
    "growth": "费雪成长股",
    "low_position": "长期低位",
    "volume_surge": "近期放量",
    "trend": "趋势分析",
    "pattern": "K线形态",
    "bollinger": "布林带下轨",
    "shareholder_concentration": "筹码集中",
    "cashflow_quality": "现金流质量",
}

ALL_STRATEGIES = list(STRATEGY_NAMES_CN.keys())

# 每条策略默认参数（扁平结构，与 skill 对齐）
DEFAULT_PARAMS = {
    "roe": {"roe_threshold": 15.0, "roa_threshold": 5.0, "include_roa": True,
            "min_report_periods": 4, "top_n": 0},
    "macd": {"data_period_years": 3, "min_data_points": 100, "k_slope_max": 0.0,
             "k_r2_min": 0.3, "macd_slope_min": 0.0, "macd_r2_min": 0.2,
             "divergence_lookback": 12, "volume_surge_weeks": 5,
             "volume_surge_threshold": 1.5, "require_divergence": True,
             "require_volume_surge": True, "top_n": 0},
    "dividend": {"min_dv_ratio": 3.0, "min_consecutive_years": 3, "min_roe": 8.0,
                 "max_pe": 30, "top_n": 0},
    "valuation": {"max_pe": 25.0, "max_pb": 3.0, "max_peg": 1.5,
                   "industry_discount": 0.85, "min_roe": 8.0, "top_n": 0},
    "growth": {"min_revenue_growth": 20.0, "min_profit_growth": 20.0,
               "min_gross_margin": 30.0, "min_consecutive_quarters": 3,
               "min_roe": 12.0, "top_n": 0},
    "low_position": {"lookback_days": 250, "low_position_pct": 25.0, "rsi_max": 40.0,
                     "rsi_window": 14, "data_period_years": 2, "top_n": 0},
    "volume_surge": {"volume_surge_ratio": 2.0, "volume_avg_days": 20, "rsi_max": 45.0,
                     "rsi_window": 14, "rebound_pct_min": 3.0, "rebound_days": 5,
                     "price_change_max": 10.0, "data_period_years": 1, "top_n": 0},
    "trend": {"ma_short": 5, "ma_mid": 20, "ma_long": 60, "trend_r2_min": 0.5,
              "adx_min": 25.0, "require_ma_bullish": True, "data_period_years": 1, "top_n": 0},
    "pattern": {"detect_double_bottom": True, "detect_head_shoulders_bottom": True,
                "detect_flag_breakout": True, "detect_golden_cross": True,
                "detect_morning_star": True, "detect_bullish_engulfing": True,
                "detect_cup_handle": True, "min_pattern_score": 1,
                "data_period_years": 1, "top_n": 0},
    "bollinger": {"bb_window": 20, "bb_std": 2.0, "rsi_max": 45.0, "rsi_window": 14,
                  "lookback_days": 120, "price_change_max": 9.0, "top_n": 0},
    "shareholder_concentration": {"min_consecutive_quarters": 3, "max_holder_growth": -5.0,
                                  "min_roe": 8.0, "data_period_quarters": 8, "top_n": 0},
    "cashflow_quality": {"min_match_quarters": 3, "total_periods": 4,
                         "min_cashflow_ratio": 0.8, "min_roe": 8.0,
                         "max_goodwill_pct": 30.0, "top_n": 0},
}

_INDUSTRY_PE_BENCHMARK = {
    "银行": 8, "保险": 12, "证券": 18, "房地产": 12, "建筑装饰": 10,
    "医药生物": 28, "食品饮料": 25, "家用电器": 18, "电子": 32,
    "计算机": 40, "通信": 22, "电力设备": 28, "机械设备": 20,
    "汽车": 18, "化工": 16, "钢铁": 10, "煤炭": 10,
    "公用事业": 14, "农林牧渔": 18, "传媒": 25, "环保": 22,
    "国防军工": 30, "有色金属": 15, "纺织服装": 15, "轻工制造": 18,
    "商业贸易": 15, "交通运输": 12, "建筑材料": 15,
}
_DEFAULT_PE_BENCHMARK = 22


def _ak():
    """懒加载 akshare，避免无网络环境下导入报错。"""
    import akshare as ak
    return ak


def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _years_ago(years: int) -> str:
    return (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")


def _norm_col(df: pd.DataFrame, mapping: Dict[str, List[str]]) -> pd.DataFrame:
    """按中文子串模糊匹配，把 akshare 中文列名规范为英文列名。"""
    if df is None or not isinstance(df, pd.DataFrame):
        return df
    df = df.copy()
    rename = {}
    for eng, candidates in mapping.items():
        for cand in candidates:
            hit = [c for c in df.columns if cand in str(c)]
            if hit:
                rename[hit[0]] = eng
                break
    return df.rename(columns=rename)


def _norm_price(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """价格数据列名归一：兼容原 skill 的 ``vol``/``pct_chg`` 与 StockSignal
    数据源的 ``volume``/``change_pct``，双向补齐别名，使分析器代码无需关心差异。"""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    df = df.copy()
    if "vol" not in df.columns and "volume" in df.columns:
        df["vol"] = df["volume"]
    if "volume" not in df.columns and "vol" in df.columns:
        df["volume"] = df["vol"]
    if "pct_chg" not in df.columns and "change_pct" in df.columns:
        df["pct_chg"] = df["change_pct"]
    if "change_pct" not in df.columns and "pct_chg" in df.columns:
        df["change_pct"] = df["pct_chg"]
    return df


class StockScreener:
    """智能选股引擎：移植 stock-selecter 11 策略，数据源切换为 StockSignal 体系。"""

    def __init__(self):
        self.fetcher = StockFetcher()

    # ── 股票池 ───────────────────────────────────────────────────────
    def get_universe(self, limit: int = 250, sector: str = None,
                     watchlist: List[str] = None) -> List[Tuple[str, str]]:
        """返回 [(code, name), ...]。优先级：自选 > 板块 > 全市场前 N。"""
        if watchlist:
            out = []
            for c in watchlist:
                c = str(c).strip().zfill(6)
                out.append((c, self.fetcher.get_name_only(c) or c))
            return out
        if sector:
            try:
                codes = self.fetcher.get_sector_stocks(sector) or []
                return [(c, self.fetcher.get_name_only(c) or c) for c in codes]
            except Exception as e:
                logger.warning("板块股票池获取失败 %s: %s", sector, e)
        codes = self.fetcher.get_all_codes(limit=limit)
        return [(c, self.fetcher.get_name_only(c) or c) for c in codes]

    # ── 数据桥 ───────────────────────────────────────────────────────
    def _daily(self, code: str, years: int = 1) -> Optional[pd.DataFrame]:
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
            df = self.fetcher.get_daily(code, start=start, end=end)
            return _norm_price(df) if df is not None and not df.empty else None
        except Exception as e:
            logger.debug("_daily %s 失败: %s", code, e)
            return None

    def _weekly(self, code: str, years: int = 3) -> Optional[pd.DataFrame]:
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
            df = self.fetcher.get_kline(code, start=start, end=end, period="weekly")
            return _norm_price(df) if df is not None and not df.empty else None
        except Exception as e:
            logger.debug("_weekly %s 失败: %s", code, e)
            return None

    def _fina_indicator(self, code: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """akshare 财务指标（roe/roa/毛利率/净利率/负债率/流动比率/yoy 等）。"""
        try:
            ak = _ak()
            raw = ak.stock_financial_analysis_indicator(symbol=code, start_year=2019)
            if raw is None or raw.empty:
                return None
            mapping = {
                "roe": ["净资产收益率"],
                "roa": ["总资产净利润率", "总资产报酬率", "资产报酬率"],
                "grossprofit_margin": ["毛利率"],
                "netprofit_margin": ["净利润率"],
                "debt_ratio": ["资产负债率"],
                "current_ratio": ["流动比率"],
                "goodwill": ["商誉"],
                "total_assets": ["总资产"],
                "total_liab": ["负债合计", "总负债"],
                "netprofit": ["净利润"],
                "total_revenue": ["营业总收入", "营业收入"],
                "netprofit_yoy": ["净利润同比增长率", "净利润同比"],
                "or_yoy": ["营业总收入同比增长率", "营收同比"],
                "end_date": ["交易日期", "报告期"],
                "ts_code": ["股票代码"],
            }
            df = _norm_col(raw, mapping)
            # 数值化
            for col in ["roe", "roa", "grossprofit_margin", "netprofit_margin",
                        "debt_ratio", "current_ratio", "goodwill", "total_assets",
                        "total_liab", "netprofit", "total_revenue", "netprofit_yoy",
                        "or_yoy"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "end_date" in df.columns:
                df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
                df = df.sort_values("end_date", ascending=False).reset_index(drop=True)
            return df.head(limit) if "end_date" in df.columns else df.head(limit)
        except Exception as e:
            logger.debug("_fina_indicator %s 失败: %s", code, e)
            return None

    def _daily_basic_ak(self, code: str) -> Optional[Dict[str, float]]:
        """akshare 估值指标：股息率/PE/PB。"""
        try:
            ak = _ak()
            df = ak.stock_a_indicator_lg(symbol=code)
            if df is None or df.empty:
                return None
            df = df.rename(columns={"股息率(%)": "dv_ratio", "市盈率(TTM)": "pe_ttm",
                                    "市净率": "pb"})
            last = df.iloc[-1]
            return {
                "dv_ratio": float(last.get("dv_ratio")) if pd.notna(last.get("dv_ratio")) else None,
                "pe_ttm": float(last.get("pe_ttm")) if pd.notna(last.get("pe_ttm")) else None,
                "pb": float(last.get("pb")) if pd.notna(last.get("pb")) else None,
            }
        except Exception as e:
            logger.debug("_daily_basic_ak %s 失败: %s", code, e)
            return None

    def _holder_number(self, code: str, limit: int = 8) -> Optional[pd.DataFrame]:
        """akshare 股东户数序列（升序）。"""
        try:
            ak = _ak()
            df = ak.stock_zh_a_gdhs(symbol=code)
            if df is None or df.empty:
                return None
            df = df.rename(columns={"截止日期": "end_date", "股东户数": "holder_number"})
            if "end_date" not in df.columns or "holder_number" not in df.columns:
                return None
            df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
            df["holder_number"] = pd.to_numeric(df["holder_number"], errors="coerce")
            df = df.dropna(subset=["holder_number", "end_date"]).sort_values("end_date").reset_index(drop=True)
            return df.tail(limit) if len(df) > limit else df
        except Exception as e:
            logger.debug("_holder_number %s 失败: %s", code, e)
            return None

    def _income(self, code: str) -> Optional[pd.DataFrame]:
        try:
            df = self.fetcher.get_financial(code, "income")
            if df is None or df.empty:
                return None
            df = df.rename(columns={"净利润": "netprofit", "营业收入": "total_revenue",
                                    "营业总收入": "total_revenue"})
            for c in ("netprofit", "total_revenue"):
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df
        except Exception as e:
            logger.debug("_income %s 失败: %s", code, e)
            return None

    def _cash(self, code: str) -> Optional[pd.DataFrame]:
        try:
            df = self.fetcher.get_financial(code, "cash")
            if df is None or df.empty:
                return None
            df = df.rename(columns={"经营现金流量净额": "ocf", "经营活动产生的现金流量净额": "ocf"})
            if "ocf" in df.columns:
                df["ocf"] = pd.to_numeric(df["ocf"], errors="coerce")
            return df
        except Exception as e:
            logger.debug("_cash %s 失败: %s", code, e)
            return None

    # ═══════════════════════════════════════════════════════════════════
    # 11 个策略分析器（返回 None=不符合；dict=命中，含 score）
    # ═══════════════════════════════════════════════════════════════════
    def _analyze_roe(self, code, name, p) -> Optional[Dict]:
        fina = self._fina_indicator(code, p["min_report_periods"])
        if fina is None or fina.empty:
            return None
        r = calculate_financial_ratios(fina)
        if not r:
            return None
        roe, roa = r.get("roe"), r.get("roa")
        if roe is None or roe < p["roe_threshold"]:
            return None
        if p["include_roa"] and roa is not None and roa < p["roa_threshold"]:
            return None
        roe_series = pd.to_numeric(fina["roe"], errors="coerce").dropna().sort_index()
        roe_trend = float(roe_series.iloc[-1] - roe_series.iloc[0]) if len(roe_series) >= 3 else 0
        gm = r.get("gross_profit_margin") or 0
        nm = r.get("net_profit_margin") or 0
        dr = r.get("debt_ratio") or 50
        cr = r.get("current_ratio") or 1
        s = min(roe / 25 * 35, 35) + min(roa / 10 * 15, 15) + min(gm / 40 * 15, 15) \
            + min(nm / 20 * 10, 10) + max(0, 10 - dr / 10) + max(0, min(cr / 2 * 5, 5)) \
            + max(0, min(roe_trend / 5 * 15, 15))
        return {"code": code, "name": name, "strategy": "roe",
                "roe": round(roe, 2), "roa": round(roa, 2) if roa else None,
                "gross_margin": round(gm, 2), "net_margin": round(nm, 2),
                "debt_ratio": round(dr, 2), "current_ratio": round(cr, 2),
                "roe_trend": round(roe_trend, 2), "score": round(min(max(s, 0), 100), 2)}

    def _analyze_macd(self, code, name, p) -> Optional[Dict]:
        df = self._weekly(code, p["data_period_years"])
        if df is None or len(df) < p["min_data_points"]:
            return None
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        vol = pd.to_numeric(df["vol"], errors="coerce").dropna()
        if len(close) < p["min_data_points"]:
            return None
        k_slope, k_r2 = analyze_trend(close)
        if k_slope is None or k_slope >= p["k_slope_max"] or k_r2 < p["k_r2_min"]:
            return None
        macd_line, _, macd_hist = calculate_macd(close)
        if macd_hist is None or len(macd_hist.dropna()) < 50:
            return None
        macd_slope, macd_r2 = analyze_trend(macd_line.dropna())
        if macd_slope is None or macd_slope <= p["macd_slope_min"] or macd_r2 < p["macd_r2_min"]:
            return None
        if p["require_divergence"] and not detect_bottom_divergence(close, macd_hist.dropna(), lookback=p["divergence_lookback"]):
            return None
        surge_ratio = None
        if p["require_volume_surge"]:
            is_surge, ratio = check_volume_surge(vol, weeks=p["volume_surge_weeks"], threshold=p["volume_surge_threshold"])
            if not is_surge:
                return None
            surge_ratio = ratio
        rsi = calculate_rsi(close, 14)
        cur_rsi = float(rsi.iloc[-1]) if (rsi is not None and len(rsi) > 0) else None
        s = 0
        if k_slope < -0.01 and k_r2 > 0.5:
            s += 30
        elif k_slope < -0.005 and k_r2 > 0.4:
            s += 20
        elif k_slope < 0 and k_r2 > 0.3:
            s += 10
        if macd_slope > 0.01 and macd_r2 > 0.5:
            s += 30
        elif macd_slope > 0.005 and macd_r2 > 0.4:
            s += 20
        elif macd_slope > 0 and macd_r2 > 0.2:
            s += 10
        if surge_ratio:
            if surge_ratio >= 3.0:
                s += 25
            elif surge_ratio >= 2.0:
                s += 20
            elif surge_ratio >= 1.5:
                s += 15
            elif surge_ratio >= 1.2:
                s += 8
        if cur_rsi:
            if 30 <= cur_rsi <= 70:
                s += 15
            elif 20 <= cur_rsi <= 80:
                s += 8
        return {"code": code, "name": name, "strategy": "macd",
                "k_slope": round(k_slope, 4), "k_r2": round(k_r2, 4),
                "macd_slope": round(macd_slope, 4), "macd_r2": round(macd_r2, 4),
                "surge_ratio": surge_ratio, "rsi": round(cur_rsi, 2) if cur_rsi else None,
                "score": round(min(max(s, 0), 100), 2)}

    def _analyze_dividend(self, code, name, p) -> Optional[Dict]:
        basic = self._daily_basic_ak(code)
        if not basic:
            return None
        dv = basic.get("dv_ratio")
        pe = basic.get("pe_ttm")
        pb = basic.get("pb")
        if dv is None or dv < p["min_dv_ratio"]:
            return None
        if pe and p.get("max_pe") and pe > p["max_pe"]:
            return None
        fina = self._fina_indicator(code, 8)
        if fina is None or fina.empty or "roe" not in fina.columns:
            return None
        roe = pd.to_numeric(fina["roe"], errors="coerce").iloc[0]
        if pd.isna(roe) or roe < p["min_roe"]:
            return None
        years = 0
        if "end_date" in fina.columns:
            years = fina["end_date"].apply(lambda x: str(x)[:4] if pd.notna(x) else None).dropna().unique().size
        if years < p["min_consecutive_years"]:
            return None
        s = min(dv / 8 * 35, 35) + min(roe / 20 * 20, 20) + min(years / 5 * 20, 20)
        if pe and pe > 0:
            s += max(0, min(15 * (1 - pe / 40), 15))
        if pb and pb > 0:
            s += max(0, min(10 * (1 - pb / 5), 10))
        return {"code": code, "name": name, "strategy": "dividend",
                "dv_ratio": round(dv, 2), "roe": round(roe, 2),
                "pe_ttm": round(pe, 2) if pe else None, "pb": round(pb, 2) if pb else None,
                "consecutive_years": years, "score": round(min(max(s, 0), 100), 2)}

    def _analyze_valuation(self, code, name, p) -> Optional[Dict]:
        fund = self.fetcher.get_fundamentals(code)
        basic = self._daily_basic_ak(code)
        pe = (basic or {}).get("pe_ttm") or fund.get("pe_ttm")
        pb = (basic or {}).get("pb")
        if pe is None or pb is None:
            return None
        if pe <= 0 or pe > p["max_pe"] or pb <= 0 or pb > p["max_pb"]:
            return None
        fina = self._fina_indicator(code, 4)
        if fina is None or fina.empty or "roe" not in fina.columns:
            return None
        roe = pd.to_numeric(fina["roe"], errors="coerce").iloc[0]
        if pd.isna(roe) or roe < p["min_roe"]:
            return None
        peg = pe / roe if roe and roe > 0 else None
        if peg and peg > p["max_peg"]:
            return None
        industry = fund.get("industry", "") or ""
        benchmark = _INDUSTRY_PE_BENCHMARK.get(industry, _DEFAULT_PE_BENCHMARK)
        discount = pe / (benchmark * p["industry_discount"]) if benchmark else 1.0
        s = max(0, min(25 * (1 - pe / 40), 25)) + max(0, min(20 * (1 - pb / 5), 20))
        if peg:
            s += max(0, min(20 * (1.5 - peg) / 1.5, 20))
        s += min(roe / 25 * 15, 15)
        if discount < 1:
            s += min((1 - discount) * 50, 10)
        return {"code": code, "name": name, "strategy": "valuation",
                "pe_ttm": round(pe, 2), "pb": round(pb, 2),
                "peg": round(peg, 2) if peg else None, "roe": round(roe, 2),
                "industry": industry or "未知", "pe_discount": round(discount, 3),
                "score": round(min(max(s, 0), 100), 2)}

    def _analyze_growth(self, code, name, p) -> Optional[Dict]:
        fina = self._fina_indicator(code, 8)
        if fina is None or fina.empty or len(fina) < 2 or "roe" not in fina.columns:
            return None
        roe = pd.to_numeric(fina["roe"], errors="coerce").iloc[0]
        gm = pd.to_numeric(fina.get("grossprofit_margin"), errors="coerce").iloc[0] if "grossprofit_margin" in fina else None
        if pd.isna(roe) or roe < p["min_roe"]:
            return None
        if gm is None or pd.isna(gm) or gm < p["min_gross_margin"]:
            return None
        latest = fina.iloc[0]
        profit_gr = None
        revenue_gr = None
        for f in ("netprofit_yoy", "or_yoy"):
            v = latest.get(f)
            if v is not None:
                try:
                    if f == "netprofit_yoy":
                        profit_gr = float(v)
                    else:
                        revenue_gr = float(v)
                except (TypeError, ValueError):
                    pass
        if "netprofit" in fina.columns and (profit_gr is None) and len(fina) >= 5:
            cur = pd.to_numeric(fina["netprofit"], errors="coerce").iloc[0]
            prev = pd.to_numeric(fina["netprofit"], errors="coerce").iloc[4]
            if pd.notna(cur) and pd.notna(prev) and prev != 0:
                profit_gr = (cur - prev) / abs(prev) * 100
        if "total_revenue" in fina.columns and (revenue_gr is None) and len(fina) >= 5:
            cur = pd.to_numeric(fina["total_revenue"], errors="coerce").iloc[0]
            prev = pd.to_numeric(fina["total_revenue"], errors="coerce").iloc[4]
            if pd.notna(cur) and pd.notna(prev) and prev != 0:
                revenue_gr = (cur - prev) / abs(prev) * 100
        if revenue_gr is None or revenue_gr < p["min_revenue_growth"]:
            return None
        if profit_gr is None or profit_gr < p["min_profit_growth"]:
            return None
        if "netprofit" in fina.columns:
            profits = pd.to_numeric(fina["netprofit"], errors="coerce").dropna()
            if len(profits) >= p["min_consecutive_quarters"] + 1:
                consec = sum(1 for j in range(1, p["min_consecutive_quarters"] + 1)
                             if profits.iloc[j - 1] > profits.iloc[j])
                if consec < p["min_consecutive_quarters"]:
                    return None
        s = min(revenue_gr / 50 * 25, 25) + min(profit_gr / 50 * 25, 25) \
            + min(gm / 60 * 25, 25) + min(roe / 25 * 25, 25)
        return {"code": code, "name": name, "strategy": "growth",
                "revenue_growth": round(revenue_gr, 2), "profit_growth": round(profit_gr, 2),
                "gross_margin": round(gm, 2), "roe": round(roe, 2),
                "score": round(min(max(s, 0), 100), 2)}

    def _analyze_low_position(self, code, name, p) -> Optional[Dict]:
        df = self._daily(code, p["data_period_years"])
        if df is None or len(df) < 60:
            return None
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(close) < 60:
            return None
        lookback = min(p["lookback_days"], len(close))
        hist = close.iloc[-lookback:]
        min_p, max_p = hist.min(), hist.max()
        pct_rank = (close.iloc[-1] - min_p) / (max_p - min_p + 1e-9) * 100
        if pct_rank > p["low_position_pct"]:
            return None
        rsi = calculate_rsi(close, p["rsi_window"])
        if rsi is None or len(rsi) == 0:
            return None
        cur_rsi = float(rsi.iloc[-1])
        if cur_rsi > p["rsi_max"]:
            return None
        low_idx = close.iloc[-lookback:].idxmin()
        days_from_low = len(close) - close.index.get_loc(low_idx) if low_idx in close.index else lookback
        s = max(0, 40 - pct_rank * 1.6) + max(0, min(35, (p["rsi_max"] - cur_rsi) / p["rsi_max"] * 35)) \
            + max(0, 25 - min(days_from_low / 10 * 25, 25))
        return {"code": code, "name": name, "strategy": "low_position",
                "current_price": round(float(close.iloc[-1]), 2), "price_pct_rank": round(pct_rank, 1),
                "rsi": round(cur_rsi, 2), "days_from_low": int(days_from_low),
                "score": round(min(max(s, 0), 100), 2)}

    def _analyze_volume_surge(self, code, name, p) -> Optional[Dict]:
        df = self._daily(code, p["data_period_years"])
        if df is None or len(df) < 30:
            return None
        close = pd.to_numeric(df["close"], errors="coerce")
        vol = pd.to_numeric(df["vol"], errors="coerce")
        df = df.assign(close=close, vol=vol)
        df = df.dropna(subset=["close", "vol"])
        if len(df) < 30:
            return None
        avg_days = int(p["volume_avg_days"])
        avg_vol = vol.iloc[-(avg_days + 1):-1].mean()
        recent_vol = vol.iloc[-1]
        if avg_vol <= 0:
            return None
        surge = recent_vol / avg_vol
        if surge < p["volume_surge_ratio"]:
            return None
        if "pct_chg" in df.columns:
            pct = float(df["pct_chg"].iloc[-1]) if pd.notna(df["pct_chg"].iloc[-1]) else 0
            if abs(pct) > p["price_change_max"]:
                return None
        rsi = calculate_rsi(close, p["rsi_window"])
        if rsi is None or len(rsi) == 0:
            return None
        cur_rsi = float(rsi.iloc[-1])
        if cur_rsi > p["rsi_max"]:
            return None
        reb_days = int(p["rebound_days"])
        reb_low = close.iloc[-reb_days:].min()
        reb_pct = (close.iloc[-1] - reb_low) / reb_low * 100 if reb_low else 0
        if reb_pct < p["rebound_pct_min"]:
            return None
        consec = int((vol.iloc[-6:-1] > avg_vol * surge).sum())
        s = min(surge / 5 * 35, 35) + max(0, min(30, (p["rsi_max"] - cur_rsi) / p["rsi_max"] * 30)) \
            + min(reb_pct / 10 * 20, 20) + min(consec * 3, 15)
        return {"code": code, "name": name, "strategy": "volume_surge",
                "current_price": round(float(close.iloc[-1]), 2), "volume_surge_ratio": round(surge, 2),
                "rsi": round(cur_rsi, 2), "rebound_pct": round(reb_pct, 2),
                "consecutive_surge_days": consec, "score": round(min(max(s, 0), 100), 2)}

    def _analyze_trend(self, code, name, p) -> Optional[Dict]:
        df = self._daily(code, p["data_period_years"])
        if df is None or len(df) < 80:
            return None
        for c in ["close", "high", "low"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["close", "high", "low"])
        if len(df) < 80:
            return None
        close, high, low = df["close"], df["high"], df["low"]
        ma5 = close.rolling(p["ma_short"]).mean()
        ma20 = close.rolling(p["ma_mid"]).mean()
        ma60 = close.rolling(p["ma_long"]).mean()
        ma_bullish = close.iloc[-1] > ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1]
        if p["require_ma_bullish"] and not ma_bullish:
            return None
        slope, r2 = analyze_trend(close.iloc[-60:])
        if slope is None or slope <= 0 or r2 < p["trend_r2_min"]:
            return None
        adx = self._calc_adx(close, high, low, 14)
        if adx is None or adx < p["adx_min"]:
            return None
        rsi = calculate_rsi(close, 14)
        cur_rsi = float(rsi.iloc[-1]) if (rsi is not None and len(rsi) > 0) else None
        atr = self._calc_atr(high, low, close, 14)
        vol = atr / close.iloc[-1] * 100 if atr else None
        s = min(slope * 2000, 25) + min(r2 * 30, 20) + min(adx / 50 * 20, 20)
        if cur_rsi:
            if 40 <= cur_rsi <= 70:
                s += 15
            elif 30 <= cur_rsi <= 80:
                s += 8
        if ma_bullish:
            s += 10
        elif ma5.iloc[-1] > ma20.iloc[-1] and ma20.iloc[-1] > ma60.iloc[-1]:
            s += 5
        if vol:
            if 1 <= vol <= 5:
                s += 10
            elif vol > 5:
                s += 5
        return {"code": code, "name": name, "strategy": "trend",
                "trend_slope": round(slope, 4), "trend_r2": round(r2, 4), "adx": round(adx, 2),
                "rsi": round(cur_rsi, 2) if cur_rsi else None,
                "volatility_pct": round(vol, 2) if vol else None, "score": round(min(max(s, 0), 100), 2)}

    def _analyze_pattern(self, code, name, p) -> Optional[Dict]:
        df = self._daily(code, p["data_period_years"])
        if df is None or len(df) < 60:
            return None
        for c in ["open", "close", "high", "low", "vol"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open", "close", "high", "low"])
        if len(df) < 60:
            return None
        hit = []
        if p["detect_golden_cross"]:
            ma5 = df["close"].rolling(5).mean()
            ma20 = df["close"].rolling(20).mean()
            if ma5.iloc[-2] <= ma20.iloc[-2] and ma5.iloc[-1] > ma20.iloc[-1]:
                hit.append("golden_cross")
        if p["detect_bullish_engulfing"]:
            o, c = df["open"].values, df["close"].values
            if len(c) >= 2 and c[-2] < o[-2] and c[-1] > o[-1] and c[-1] > o[-2] and o[-1] < c[-2]:
                hit.append("bullish_engulfing")
        if p["detect_morning_star"]:
            o, c = df["open"].values, df["close"].values
            if len(c) >= 3:
                b1, b2 = abs(c[-3] - o[-3]), abs(c[-2] - o[-2])
                if c[-3] < o[-3] and b2 < b1 * 0.3 and c[-1] > o[-1] and max(o[-2], c[-2]) < min(o[-3], c[-3]):
                    hit.append("morning_star")
        if p["detect_flag_breakout"]:
            close, vol = df["close"], df["vol"]
            if len(close) >= 25:
                fr = close.iloc[-21:-1].max() - close.iloc[-21:-1].min()
                fm = close.iloc[-21:-1].mean()
                if fr / fm < 0.08 and close.iloc[-1] > close.iloc[-21:-1].max() and vol.iloc[-1] > vol.iloc[-21:-1].mean() * 1.5:
                    hit.append("flag_breakout")
        if p["detect_double_bottom"]:
            close = df["close"].iloc[-60:]
            lows = close[close == close.rolling(5, center=True).min()].dropna()
            if len(lows) >= 2:
                sl = lows.sort_values()
                if abs(sl.iloc[0] - sl.iloc[1]) / (sl.iloc[0] + 1e-9) < 0.05:
                    hit.append("double_bottom")
        if p["detect_head_shoulders_bottom"]:
            close = df["close"].iloc[-80:]
            if len(close) >= 30:
                seg = len(close) // 3
                l, h, r = close.iloc[:seg].min(), close.iloc[seg:2 * seg].min(), close.iloc[2 * seg:].min()
                if h < l * 0.98 and h < r * 0.98 and abs(l - r) / (l + 1e-9) < 0.05:
                    hit.append("head_shoulders_bottom")
        if p["detect_cup_handle"]:
            close = df["close"].iloc[-60:]
            if len(close) >= 40:
                cl, cb, cr = close.iloc[:10].mean(), close.iloc[10:30].mean(), close.iloc[30:40].mean()
                if cb < cl * 0.92 and cr > cb * 1.05 and abs(cl - cr) / cl < 0.08:
                    hit.append("cup_handle")
        if len(hit) < p["min_pattern_score"]:
            return None
        return {"code": code, "name": name, "strategy": "pattern",
                "patterns": hit, "pattern_count": len(hit),
                "score": round(len(hit) / 7 * 100, 2)}

    def _analyze_bollinger(self, code, name, p) -> Optional[Dict]:
        df = self._daily(code, 1)
        if df is None or len(df) < p["bb_window"] + 5:
            return None
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(close) < p["bb_window"] + 5:
            return None
        upper, middle, lower = calculate_bollinger_bands(close, p["bb_window"], p["bb_std"])
        if upper is None:
            return None
        lc, lu, lm, ll = close.iloc[-1], upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]
        pct = abs(float(df["pct_chg"].iloc[-1])) if "pct_chg" in df.columns and pd.notna(df["pct_chg"].iloc[-1]) else 0
        if pct > p["price_change_max"]:
            return None
        bw = lu - ll
        touch = (lc - ll) / bw if bw > 0 else 1.0
        if touch > 0.15:
            return None
        rsi = calculate_rsi(close, p["rsi_window"])
        if rsi is None or rsi.empty:
            return None
        lr = float(rsi.iloc[-1])
        if lr > p["rsi_max"]:
            return None
        s = max(0, min(35, (0.15 - touch) / 0.15 * 35)) + max(0, min(35, (p["rsi_max"] - lr) / p["rsi_max"] * 35))
        if bw > 0:
            s += max(0, min(30, (lc - ll) / bw * 30))
        return {"code": code, "name": name, "strategy": "bollinger",
                "bb_touch": round(touch * 100, 2), "rsi": round(lr, 2),
                "close": round(lc, 2), "bb_lower": round(ll, 2),
                "score": round(min(max(s, 0), 100), 2)}

    def _analyze_shareholder(self, code, name, p) -> Optional[Dict]:
        hdf = self._holder_number(code, p["data_period_quarters"])
        if hdf is None or len(hdf) < p["min_consecutive_quarters"] + 1:
            return None
        fina = self._fina_indicator(code, 2)
        if fina is None or fina.empty or "roe" not in fina.columns:
            return None
        roe = pd.to_numeric(fina["roe"], errors="coerce").iloc[0]
        if pd.isna(roe) or roe < p["min_roe"]:
            return None
        latest = hdf["holder_number"].iloc[-1]
        if latest <= 0:
            return None
        consec = 0
        changes = []
        for i in range(1, len(hdf)):
            prev = hdf["holder_number"].iloc[-i - 1]
            curr = hdf["holder_number"].iloc[-i]
            if prev <= 0:
                continue
            chg = (curr - prev) / prev * 100
            changes.append(round(chg, 2))
            if chg <= 0:
                consec += 1
            else:
                break
        if consec < p["min_consecutive_quarters"]:
            return None
        oldest = hdf["holder_number"].iloc[0]
        total = (latest - oldest) / oldest * 100 if oldest > 0 else 0
        s = max(0, min(40, -total / 30 * 40)) + max(0, min(30, len(hdf) * 4)) + max(0, min(30, roe / 20 * 30))
        return {"code": code, "name": name, "strategy": "shareholder_concentration",
                "consecutive_decreases": consec, "total_change": round(total, 2),
                "latest_holders": int(latest), "roe": round(roe, 2),
                "score": round(min(max(s, 0), 100), 2)}

    def _analyze_cashflow(self, code, name, p) -> Optional[Dict]:
        income = self._income(code)
        if income is None or income.empty or len(income) < p["min_match_quarters"]:
            return None
        cash = self._cash(code)
        if cash is None or cash.empty:
            return None
        fina = self._fina_indicator(code, 2)
        roe = None
        if fina is not None and not fina.empty and "roe" in fina.columns:
            rv = pd.to_numeric(fina["roe"], errors="coerce").iloc[0]
            roe = None if pd.isna(rv) else float(rv)
        if roe is not None and roe < p["min_roe"]:
            return None
        np_field = "netprofit" if "netprofit" in income.columns else None
        ocf_field = "ocf" if "ocf" in cash.columns else None
        if not np_field or not ocf_field:
            return None
        income = income.copy()
        cash = cash.copy()
        income[np_field] = pd.to_numeric(income[np_field], errors="coerce")
        cash[ocf_field] = pd.to_numeric(cash[ocf_field], errors="coerce")
        period_col = "报告期" if "报告期" in income.columns else (income.columns[0])
        income = income.dropna(subset=[np_field]).head(p["min_match_quarters"])
        match, ratios, avg = 0, [], 0.0
        for _, irow in income.iterrows():
            profit = irow[np_field]
            if pd.isna(profit) or profit == 0:
                continue
            matched = cash[cash[period_col] == irow[period_col]] if period_col in cash.columns else cash.iloc[[0]]
            if matched.empty:
                continue
            ocf = matched[ocf_field].iloc[0]
            if pd.isna(ocf) or ocf == 0:
                continue
            ratio = ocf / profit
            ratios.append(ratio)
            if ratio >= p["min_cashflow_ratio"]:
                match += 1
        if match < p["min_match_quarters"]:
            return None
        avg = sum(ratios) / len(ratios) if ratios else 0.0
        s = max(0, min(40, match / p["total_periods"] * 40)) + max(0, min(35, min(avg, 1.5) / 1.5 * 35)) \
            + (max(0, min(25, roe / 20 * 25)) if roe else 0)
        return {"code": code, "name": name, "strategy": "cashflow_quality",
                "match_quarters": match, "avg_cashflow_ratio": round(avg, 2),
                "roe": round(roe, 2) if roe else None, "score": round(min(max(s, 0), 100), 2)}

    # ── ADX / ATR 工具（趋势策略用）────────────────────────────────────
    @staticmethod
    def _calc_adx(close, high, low, period=14):
        try:
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            dm_p = (high - high.shift(1)).clip(lower=0)
            dm_m = (low.shift(1) - low).clip(lower=0)
            dm_p[dm_p < dm_m] = 0
            dm_m[dm_m < dm_p] = 0
            atr = tr.ewm(span=period, adjust=False).mean()
            di_p = dm_p.ewm(span=period, adjust=False).mean() / (atr + 1e-9) * 100
            di_m = dm_m.ewm(span=period, adjust=False).mean() / (atr + 1e-9) * 100
            dx = (di_p - di_m).abs() / (di_p + di_m + 1e-9) * 100
            adx = dx.ewm(span=period, adjust=False).mean()
            return float(adx.iloc[-1])
        except Exception as e:
            logger.warning(f"[stock_screener] 处理异常: {e}")
            return None

    @staticmethod
    def _calc_atr(high, low, close, period=14):
        try:
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])
        except Exception as e:
            logger.warning(f"[stock_screener] 处理异常: {e}")
            return None

    # ── 执行入口 ───────────────────────────────────────────────────────
    def run(self, strategy_names: List[str], mode: str = "and",
            params: Dict[str, Any] = None, top_n: int = 0,
            limit: int = 250, sector: str = None, watchlist: List[str] = None,
            workers: int = 4, progress=None) -> Dict[str, Any]:
        """统一选股入口。返回 {success, results, count, message, metadata}。"""
        params = params or {}
        start = time.time()
        universe = self.get_universe(limit=limit, sector=sector, watchlist=watchlist)
        total = len(universe)
        if total == 0:
            return {"success": False, "results": [], "count": 0,
                    "message": "股票池为空（检查网络或自选列表）", "metadata": {}}

        analyzers = {
            "roe": self._analyze_roe, "macd": self._analyze_macd,
            "dividend": self._analyze_dividend, "valuation": self._analyze_valuation,
            "growth": self._analyze_growth, "low_position": self._analyze_low_position,
            "volume_surge": self._analyze_volume_surge, "trend": self._analyze_trend,
            "pattern": self._analyze_pattern, "bollinger": self._analyze_bollinger,
            "shareholder_concentration": self._analyze_shareholder,
            "cashflow_quality": self._analyze_cashflow,
        }

        results_map = {}
        for name in strategy_names:
            analyzer = analyzers.get(name)
            if not analyzer:
                continue
            sp = dict(DEFAULT_PARAMS.get(name, {}))
            sp.update({k[len(name) + 1:]: v for k, v in params.items() if k.startswith(name + ".")})
            sp.update({k: v for k, v in params.items() if "." not in k})
            valid = sp

            def _one(args, analyzer=analyzer, valid=valid):
                code, sname = args
                try:
                    r = analyzer(code, sname, valid)
                    if r:
                        try:
                            if code:
                                r.setdefault("industry", self.fetcher.get_fundamentals(code).get("industry", "未知"))
                        except Exception as e:
                            logger.warning(f"[stock_screener] 处理异常: {e}")
                            r.setdefault("industry", "未知")
                    return r
                except Exception as e:
                    logger.debug("%s %s 分析异常: %s", name, code, e)
                    return None

            hits = []
            done = 0
            if workers and workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futs = {pool.submit(_one, s): s for s in universe}
                    for fut in as_completed(futs):
                        res = fut.result()
                        done += 1
                        if res:
                            hits.append(res)
                        if progress and done % 25 == 0:
                            progress(name, done, total)
            else:
                for s in universe:
                    res = _one(s)
                    done += 1
                    if res:
                        hits.append(res)
                    if progress and done % 25 == 0:
                        progress(name, done, total)
            if progress:
                progress(name, total, total)
            results_map[name] = {"results": hits, "count": len(hits)}

        if len(strategy_names) == 1:
            final = results_map[strategy_names[0]]["results"]
        elif mode == "and":
            final = self._combine_and(results_map)
        else:
            final = self._combine_or(results_map)

        if top_n and top_n > 0:
            final = final[:top_n]
        elapsed = round(time.time() - start, 2)
        return {
            "success": True, "results": final, "count": len(final),
            "message": f"{mode.upper()} 模式 策略 {strategy_names} 命中 {len(final)}/{total} 只，耗时 {elapsed}s",
            "metadata": {"strategies_used": strategy_names, "mode": mode,
                         "execution_time": elapsed, "total_stocks": total,
                         "per_strategy_counts": {n: results_map[n]["count"] for n in strategy_names}},
        }

    @staticmethod
    def _combine_and(results_map):
        if not results_map:
            return []
        code_sets, code_to = [], {}
        for name, res in results_map.items():
            codes = set()
            for r in res["results"]:
                code = r["code"]
                codes.add(code)
                code_to.setdefault(code, {})[name] = r
            code_sets.append(codes)
        inter = code_sets[0].copy()
        for s in code_sets[1:]:
            inter &= s
        out = []
        for code in inter:
            merged = {"code": code, "strategies_hit": list(results_map.keys()), "scores": {}}
            for name, r in code_to[code].items():
                merged.setdefault("name", r.get("name", code))
                merged.setdefault("industry", r.get("industry", "未知"))
                merged["scores"][name] = r.get("score", 0)
                for k, v in r.items():
                    if k not in ("code", "name", "industry", "strategy"):
                        merged[f"{name}_{k}"] = v
            merged["total_score"] = sum(merged["scores"].values())
            merged["score"] = merged["total_score"]
            out.append(merged)
        out.sort(key=lambda x: x["total_score"], reverse=True)
        return out

    @staticmethod
    def _combine_or(results_map):
        all_codes = {}
        for name, res in results_map.items():
            for r in res["results"]:
                code = r["code"]
                if code not in all_codes:
                    all_codes[code] = {"code": code, "name": r.get("name", code),
                                       "industry": r.get("industry", "未知"),
                                       "strategies_hit": [], "scores": {}, "score": 0}
                all_codes[code]["strategies_hit"].append(name)
                all_codes[code]["scores"][name] = r.get("score", 0)
                all_codes[code]["score"] += r.get("score", 0)
        out = list(all_codes.values())
        out.sort(key=lambda x: (len(x["strategies_hit"]), x["score"]), reverse=True)
        return out