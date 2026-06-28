"""
数据采集模块
封装 AKShare / Tushare 接口，提供统一的股票行情、财务数据、宏观数据获取方法。
所有请求默认走本地 SQLite 缓存，cache_days 内不重复请求网络。
"""

import os
import sqlite3
import time
from datetime import datetime, timedelta

import pandas as pd
import yaml

try:
    import akshare as ak
    _AK_OK = True
except ImportError:
    _AK_OK = False

try:
    import tushare as ts
    _TS_OK = True
except ImportError:
    _TS_OK = False


def load_config(config_path="config.yaml"):
    """读取全局配置文件。"""
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class StockFetcher:
    """股票行情与宏观数据采集器。"""

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        db_path = self.config.get("database", {}).get("path", "data/cache.db")
        self.db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.cache_days = self.config.get("default", {}).get("cache_days", 7)

        # 初始化 Tushare（可选）
        self.ts_api = None
        token = self.config.get("tushare", {}).get("token", "")
        if token and _TS_OK:
            ts.set_token(token)
            self.ts_api = ts.pro_api()

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------
    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_cache_table(self, conn, table_name):
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                cache_key   TEXT PRIMARY KEY,
                data_json   TEXT,
                updated_at  TEXT
            )
        """)
        conn.commit()

    def _read_cache(self, conn, table_name, cache_key):
        self._init_cache_table(conn, table_name)
        row = conn.execute(
            f"SELECT data_json, updated_at FROM {table_name} WHERE cache_key = ?",
            (cache_key,)
        ).fetchone()
        if row is None:
            return None
        updated_at = datetime.fromisoformat(row[1])
        if datetime.now() - updated_at < timedelta(days=self.cache_days):
            return pd.read_json(row[0])
        return None

    def _write_cache(self, conn, table_name, cache_key, df):
        self._init_cache_table(conn, table_name)
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} (cache_key, data_json, updated_at) VALUES (?, ?, ?)",
            (cache_key, df.to_json(orient="records", date_format="iso"), datetime.now().isoformat())
        )
        conn.commit()

    # ------------------------------------------------------------------
    # 行情数据
    # ------------------------------------------------------------------
    def get_daily(self, symbol, start="2024-01-01", end=None, adjust="qfq"):
        """
        获取个股日线行情（前复权）。
        :param symbol: 股票代码，如 "600519"
        :param start:  起始日期 "YYYY-MM-DD"
        :param end:    截止日期，默认今天
        :param adjust: 复权类型 qfq前复权 / hfq后复权 / 空字符串不复权
        :return: DataFrame[open, close, high, low, volume, amount, change_pct]
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        cache_key = f"daily_{symbol}_{start}_{end}_{adjust}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "daily_cache", cache_key)
            if cached is not None:
                return cached

            if not _AK_OK:
                raise RuntimeError("akshare 未安装，请 pip install akshare")

            df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                    start_date=start.replace("-", ""),
                                    end_date=end.replace("-", ""), adjust=adjust)
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount", "涨跌幅": "change_pct"
            })
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "open", "close", "high", "low", "volume", "amount", "change_pct"]]
            df = df.sort_values("date").reset_index(drop=True)

            self._write_cache(conn, "daily_cache", cache_key, df)
            return df
        finally:
            conn.close()

    def get_index(self, symbol="000001", start="2024-01-01", end=None):
        """
        获取指数日线行情。
        :param symbol: 指数代码，如 "000001"(上证指数) / "399001"(深证成指) / "399006"(创业板指)
        """
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        cache_key = f"index_{symbol}_{start}_{end}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "index_cache", cache_key)
            if cached is not None:
                return cached

            if not _AK_OK:
                raise RuntimeError("akshare 未安装，请 pip install akshare")

            df = ak.stock_zh_index_daily(symbol=f"sh{symbol}" if symbol.startswith("000") else f"sz{symbol}")
            df = df.rename(columns={"date": "date", "open": "open", "close": "close",
                                    "high": "high", "low": "low", "volume": "volume"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= start) & (df["date"] <= end)]
            df = df[["date", "open", "close", "high", "low", "volume"]].sort_values("date").reset_index(drop=True)

            self._write_cache(conn, "index_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 板块数据
    # ------------------------------------------------------------------
    def get_sector_list(self):
        """获取申万一级行业板块列表及当日涨跌幅。"""
        if not _AK_OK:
            raise RuntimeError("akshare 未安装")
        df = ak.stock_board_industry_name_em()
        df = df.rename(columns={"板块名称": "sector", "涨跌幅": "change_pct"})
        return df[["sector", "change_pct"]]

    def get_sector_stocks(self, sector_name):
        """获取指定行业板块的成分股列表。"""
        if not _AK_OK:
            raise RuntimeError("akshare 未安装")
        df = ak.stock_board_industry_cons_em(symbol=sector_name)
        df = df.rename(columns={
            "代码": "code", "名称": "name", "涨跌幅": "change_pct",
            "最新价": "close", "总市值": "market_cap"
        })
        return df[["code", "name", "close", "change_pct", "market_cap"]]

    # ------------------------------------------------------------------
    # 宏观数据
    # ------------------------------------------------------------------
    def get_macro(self, indicator="pmi_mfg"):
        """
        获取宏观经济指标。
        :param indicator: pmi_mfg(制造业PMI) / cpi(居民消费价格指数) / m2(广义货币)
        """
        indicator_map = {
            "pmi_mfg": ("macro_china_pmi", {}),
            "cpi": ("macro_china_cpi_monthly", {}),
            "m2": ("macro_china_money_supply", {}),
        }
        if indicator not in indicator_map:
            raise ValueError(f"不支持的指标: {indicator}，可选: {list(indicator_map.keys())}")

        func_name, kwargs = indicator_map[indicator]
        cache_key = f"macro_{indicator}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "macro_cache", cache_key)
            if cached is not None:
                return cached

            if not _AK_OK:
                raise RuntimeError("akshare 未安装")

            func = getattr(ak, func_name)
            df = func(**kwargs)
            df = df.rename(columns={
                "月份": "date", "日期": "date",
                "制造业-Loss": "pmi_mfg", "全国-当月": "cpi_yoy",
                "M2-数量": "m2", "M2-同比增长": "m2_yoy"
            })
            # 取最近 60 条记录
            df = df.tail(60).reset_index(drop=True)
            self._write_cache(conn, "macro_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 大宗商品 / 价格信号
    # ------------------------------------------------------------------
    def get_commodity_price(self, name="煤炭"):
        """
        获取大宗商品价格。
        :param name: 煤炭 / 螺纹钢 / 铜 / MLCC 等（通过 AKShare 现货接口）
        """
        cache_key = f"commodity_{name}"
        conn = self._get_conn()
        try:
            cached = self._read_cache(conn, "commodity_cache", cache_key)
            if cached is not None:
                return cached

            if not _AK_OK:
                raise RuntimeError("akshare 未安装")

            # 使用现货价格指数接口
            df = ak.spot_price_qsx(symbol="全部")
            df = df[df["品种"].str.contains(name, na=False)]
            df = df.rename(columns={"日期": "date", "品种": "name", "价格": "price"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "name", "price"]].sort_values("date").reset_index(drop=True)

            self._write_cache(conn, "commodity_cache", cache_key, df)
            return df
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 财务数据
    # ------------------------------------------------------------------
    def get_financial(self, symbol="600519", report_type="income"):
        """
        获取个股财务报表。
        :param report_type: income(利润表) / balance(资产负债表) / cash(现金流量表)
        """
        if not _AK_OK:
            raise RuntimeError("akshare 未安装")

        func_map = {
            "income": ak.stock_financial_report_sina,
            "balance": ak.stock_financial_report_sina,
            "cash": ak.stock_financial_report_sina,
        }
        report_map = {"income": "利润表", "balance": "资产负债表", "cash": "现金流量表"}
        df = func_map[report_type](stock=f"sh{symbol}", symbol=report_map[report_type])
        return df.head(8)  # 最近8期报告
