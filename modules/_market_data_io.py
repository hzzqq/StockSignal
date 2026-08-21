"""
市场数据 I/O 叶子模块（从 modules.fetcher 按主题下沉，#锐评整改）。

承载 StockFetcher 的「市场数据」主题方法群：指数 / 板块 / 概念 / 宏观 / 商品 / 财务。
每个函数接收 fetcher 实例（替代原 self），复用其 SQLite 缓存基础设施与 _feed_io 取数器。
共享符号（logger / _is_market_open 等）来自 modules._feed_io；_AK_OK 经 fetcher 模块延迟读
（避免值拷贝导致 monkeypatch 失效，见 _ak_available）。本模块不反向 import fetcher，零循环。

接口约定（与 fetcher 原方法一一对应，调用方无感）：
    fetcher.get_index(...)        -> fetch_index(fetcher, ...)
    fetcher.get_index_minute(...) -> fetch_index_minute(fetcher, ...)
    fetcher.get_sector_list(...)  -> fetch_sector_list(fetcher, ...)
    fetcher.get_sector_stocks(...) -> fetch_sector_stocks(fetcher, ...)
    fetcher.get_concept_list(...) -> fetch_concept_list(fetcher, ...)
    fetcher.get_concept_stocks(...) -> fetch_concept_stocks(fetcher, ...)
    fetcher.get_macro(...)        -> fetch_macro(fetcher, ...)
    fetcher.get_commodity_price(...) -> fetch_commodity_price(fetcher, ...)
    fetcher.get_financial(...)    -> fetch_financial(fetcher, ...)
"""
import io
import json
from datetime import datetime

import pandas as pd

from modules._feed_io import (
    logger,
    _is_market_open,
    _is_midday_break,
    _validate_sector_data,
    _retry_request,
    _BaoStockFetcher,
    _UrllibFetcher,
)


def _ak_available():
    """延迟读 fetcher 模块的 _AK_OK（避免值拷贝坑）。

    拆分后实现在本模块，而测试/调用方可能 monkeypatch
    ``modules.fetcher._AK_OK``（R95 前后均为 fetcher 的 re-export 引用）。
    若此处直接持 ``from modules._feed_io import _AK_OK`` 值拷贝，
    patch 不会生效；改为运行时读 fetcher 模块属性（延迟 import 防循环）。
    """
    from modules import fetcher as _fm
    return bool(getattr(_fm, "_AK_OK", False))



def fetch_index(fetcher, symbol="000001", start="2024-01-01", end=None):
    """
    获取指数日线行情。
    降级链：akshare -> BaoStock -> 东方财富(urllib) -> 缓存兜底
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"index_{symbol}_{start}_{end}"
    conn = fetcher._get_conn()
    try:
        cached = fetcher._read_cache(conn, "index_cache", cache_key)
        if cached is not None:
            return cached

        df = None
        errors = []

        # ── L1: akshare ──
        if _ak_available():
            import akshare as ak  # 局部导入：与 _AK_OK 同源
            try:
                df = _retry_request(
                    lambda: ak.stock_zh_index_daily(
                        symbol=f"sh{symbol}" if symbol.startswith("000") else f"sz{symbol}"
                    ),
                    max_retries=2, base_delay=2,
                )
                df = df.rename(columns={
                    "date": "date", "open": "open", "close": "close",
                    "high": "high", "low": "low", "volume": "volume",
                })
                df["date"] = pd.to_datetime(df["date"])
                logger.debug(f"[StockFetcher] L1-akshare 指数 OK {symbol}")
            except Exception as e:
                errors.append(f"akshare: {type(e).__name__}")
                df = None

        # ── L2: BaoStock ──
        if df is None or df.empty:
            df = _BaoStockFetcher.fetch_index_kline(symbol, start, end)
            if df is not None and not df.empty:
                logger.debug(f"[StockFetcher] L2-BaoStock 指数 OK {symbol}")
            else:
                errors.append("BaoStock: 无数据")

        # ── L3: 东方财富 urllib ──
        if df is None or df.empty:
            df = _UrllibFetcher.fetch_kline(symbol, start, end, is_index=True)
            if df is not None and not df.empty:
                logger.debug(f"[StockFetcher] L3-东方财富 指数 OK {symbol}")
            else:
                errors.append("东方财富: 无数据")

        # ── L4: 缓存兜底 ──
        if df is None or df.empty:
            stale = fetcher._read_stale_cache(conn, "index_cache", f"index_{symbol}")
            if stale is not None:
                logger.debug(f"[StockFetcher] L4-缓存兜底 指数 OK {symbol}")
                return stale
            errors.append("缓存: 无可用数据")

        if df is None or df.empty:
            detail = "\n   • ".join(errors)
            raise RuntimeError(
                f"ERROR 无法获取 {symbol} 指数数据\n"
                f"   数据源全部失败：\n   • {detail}"
            )

        df = df[(df["date"] >= start) & (df["date"] <= end)]
        df = df.sort_values("date").reset_index(drop=True)
        fetcher._write_cache(conn, "index_cache", cache_key, df)
        return df
    finally:
        conn.close()


def fetch_index_minute(fetcher, symbol="000001", trade_date=None):
    """
    获取指数当日 1 分钟 K 线，返回 DataFrame[time, open, close, high, low, volume]。
    失败返回 None；网络/证书异常时内部降级为 None，由调用方使用日线/OHLC 兜底。
    """
    if not _ak_available():
        return None
    import akshare as ak  # 局部导入：_AK_OK=True 才执行到此
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")
    try:
        with fetcher._ak_ssl_context():
            df = ak.index_zh_a_hist_min_em(symbol=symbol, period="1", start_date=trade_date, end_date=trade_date)
        if df is None or df.empty:
            return None
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        col_map = {
            "时间": "time",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        for c in ["open", "close", "high", "low", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["time"] = df["time"].astype(str)
        # 明确按交易时间升序，避免接口返回顺序不确定导致走势标签误判
        if "time" in df.columns:
            df = df.sort_values("time").reset_index(drop=True)
        return df.reset_index(drop=True)
    except Exception as e:
        logger.info(f"[StockFetcher] 指数分钟线失败 {symbol}: {type(e).__name__}")
        return None


def fetch_sector_list(fetcher, force_refresh=False):
    """
    行业板块列表。
    降级链：本地实时缓存 -> 东方财富(urllib) -> 同花顺 akshare -> BaoStock -> 过期缓存兜底
    交易时间内缓存 6 分钟，休市时延用最后一个交易日缓存（7 天内）。
    """
    cache_key = "sector_list_v3"
    conn = fetcher._get_conn()
    try:
        market_open = _is_market_open()
        midday_break = _is_midday_break()
        if market_open:
            cache_ttl_hours = 0.1  # 交易时 6 分钟
        elif midday_break:
            cache_ttl_hours = 0.5  # 午间休市 30 分钟，避免延用昨日数据
        else:
            cache_ttl_hours = 24 * 7  # 已收盘/周末/盘前：7 天

        if not force_refresh:
            cached = fetcher._read_cache(conn, "sector_cache", cache_key, max_age_hours=cache_ttl_hours)
            if cached is not None and not cached.empty:
                # 缓存命中后校验：全零数据（如 BaoStock 兜底写入的）视为 miss，继续降级
                if _validate_sector_data(cached):
                    return cached
                else:
                    logger.warning("[StockFetcher] L0缓存数据校验未通过（可能为全零兜底），尝试重新获取")
                    cached = None  # 视为 miss
    except Exception as e:
        logger.info(f"[StockFetcher] 板块缓存读取失败: {e}")
    finally:
        conn.close()

    df = None
    errors = []
    source = None

    # ── L1: 东方财富 urllib（通常最快）──
    try:
        df = _UrllibFetcher.fetch_sector_list()
        if df is not None and not df.empty and not _validate_sector_data(df):
            logger.info("[StockFetcher] L1-东方财富 数据异常，尝试降级")
            df = None
        if df is not None and not df.empty:
            source = "东方财富"
            logger.debug("[StockFetcher] L1-东方财富 板块 OK")
    except Exception as e:
        errors.append(f"东方财富: {type(e).__name__}")
        df = None

    # ── L2: 同花顺 akshare（东财接口被关闭时的可靠备用）──
    if df is None or df.empty:
        if _ak_available():
            import akshare as ak  # 局部导入：与 _AK_OK 同源
            try:
                df = _retry_request(
                    lambda: ak.stock_board_industry_summary_ths(),
                    max_retries=1, base_delay=1,
                )
                df = df.rename(columns={"板块": "sector", "涨跌幅": "change_pct"})
                df = df[["sector", "change_pct"]]
                if not _validate_sector_data(df):
                    logger.info("[StockFetcher] L2-同花顺 数据异常，尝试降级")
                    df = None
                else:
                    source = "同花顺"
                    logger.debug("[StockFetcher] L2-同花顺 板块 OK")
            except Exception as e:
                errors.append(f"同花顺: {type(e).__name__}")
                df = None

    # ── L3: BaoStock（只有行业名称，无涨跌幅，作为兜底）──
    if df is None or df.empty:
        try:
            df = _BaoStockFetcher.fetch_sector_list()
            if df is not None and not df.empty:
                # BaoStock 硬编码 change_pct=0.0，必须校验拦截
                if _validate_sector_data(df):
                    source = "BaoStock"
                    logger.debug("[StockFetcher] L3-BaoStock 板块 OK")
                else:
                    logger.info("[StockFetcher] L3-BaoStock 数据全零（无涨跌幅），降级到过期缓存")
                    df = None  # 全零 → 视为无效，继续降级
        except Exception as e:
            errors.append(f"BaoStock: {type(e).__name__}")
            df = None

    # ── L4: 过期缓存兜底（含交易日归档键回退）──
    if df is None or df.empty:
        conn = fetcher._get_conn()
        try:
            # 4a: 尝试主缓存键的过期数据
            stale = fetcher._read_stale_cache(conn, "sector_cache", "sector_list_v3")
            if stale is not None and not stale.empty and _validate_sector_data(stale):
                source = "过期缓存"
                logger.debug("[StockFetcher] L4a-过期缓存 板块 OK")
                return stale

            # 4b: 周末/休市 → 查找最近一个交易日的归档缓存（sector_list_v3_YYYYMMDD）
            if not _is_market_open():
                archive_row = conn.execute(
                    "SELECT data_json, updated_at FROM sector_cache "
                    "WHERE cache_key LIKE 'sector_list_v3_%' "
                    "AND cache_key NOT LIKE '%_source' "
                    "AND LENGTH(cache_key) = 19 "  # sector_list_v3_YYYYMMDD = 19 chars
                    "ORDER BY cache_key DESC LIMIT 1"
                ).fetchone()
                if archive_row:
                    archive_df = pd.read_json(io.StringIO(archive_row[0]))
                    if not archive_df.empty and _validate_sector_data(archive_df):
                        source = f"交易日归档({archive_row[0][:19]})"
                        logger.debug(f"[StockFetcher] L4b-交易日归档 板块 OK ({archive_row[0][:19]})")
                        return archive_df
        finally:
            conn.close()
        errors.append("缓存: 无可用数据")

    if df is None or df.empty:
        detail = "、".join(errors) if errors else "未知原因"
        raise RuntimeError(
            f"ERROR 无法获取板块数据\n   数据源全部失败：\n   • {detail}"
        )

    # 标准化列类型
    df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)
    df = df[df["sector"].astype(str).str.strip() != ""].reset_index(drop=True)

    # 写入缓存 + 来源标记（仅含真实涨跌幅的数据源才写主缓存，防止 BaoStock 全零污染）
    if source in ("东方财富", "同花顺"):
        conn = fetcher._get_conn()
        try:
            fetcher._write_cache(conn, "sector_cache", cache_key, df)
            # 同时写入交易日归档键（按日期），供休市期间显式回退
            trade_date = datetime.now().strftime("%Y%m%d")
            archive_key = f"{cache_key}_{trade_date}"
            fetcher._write_cache(conn, "sector_cache", archive_key, df)
            fetcher._write_cache_raw(conn, "sector_cache", f"{cache_key}_source", json.dumps({"source": source}, ensure_ascii=False))
        finally:
            conn.close()
    else:
        logger.debug(f"[StockFetcher] 跳过缓存写入：数据源={source}，不含真实涨跌幅")

    return df


def fetch_sector_stocks(fetcher, sector_name):
    """指定行业的成分股列表（仅 akshare）。"""
    if not _ak_available():
        raise RuntimeError("akshare 未安装，无法获取成分股")
    import akshare as ak  # 局部导入：与 _AK_OK 同源
    df = _retry_request(
        lambda: ak.stock_board_industry_cons_em(symbol=sector_name),
        max_retries=2, base_delay=2,
    )
    df = df.rename(columns={
        "代码": "code", "名称": "name", "涨跌幅": "change_pct",
        "最新价": "close", "总市值": "market_cap",
    })
    return df[["code", "name", "close", "change_pct", "market_cap"]]


def fetch_concept_list(fetcher, force_refresh=False):
    """概念板块列表（东方财富）。返回 DataFrame(sector, change_pct)。失败返回空 DataFrame。"""
    cache_key = "concept_list_v1"
    try:
        if not force_refresh:
            conn = fetcher._get_conn()
            cached = fetcher._read_cache(conn, "sector_cache", cache_key, max_age_hours=0.1)
            if cached is not None and not cached.empty:
                return cached
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        pass
    try:
        import akshare as ak  # 局部导入：未装时 ImportError 由下方 except 兜底返回空
        df = _retry_request(
            lambda: ak.stock_board_concept_name_em(),
            max_retries=2, base_delay=2,
        )
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        return pd.DataFrame(columns=["sector", "change_pct"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["sector", "change_pct"])
    df = df.rename(columns={"板块名称": "sector", "涨跌幅": "change_pct"})
    keep = [c for c in ["sector", "change_pct"] if c in df.columns]
    df = df[keep].copy() if keep else df
    try:
        conn = fetcher._get_conn()
        fetcher._write_cache(conn, "sector_cache", cache_key, df)
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        pass
    return df


def fetch_concept_stocks(fetcher, concept_name):
    """指定概念板块的成分股列表（东方财富）。失败抛异常由调用方兜底。"""
    if not _ak_available():
        raise RuntimeError("akshare 未安装，无法获取成分股")
    import akshare as ak  # 局部导入：与 _AK_OK 同源
    df = _retry_request(
        lambda: ak.stock_board_concept_cons_em(symbol=concept_name),
        max_retries=2, base_delay=2,
    )
    df = df.rename(columns={
        "代码": "code", "名称": "name", "涨跌幅": "change_pct",
        "最新价": "close", "总市值": "market_cap",
    })
    return df[["code", "name", "close", "change_pct", "market_cap"]]


def fetch_macro(fetcher, indicator="pmi_mfg"):
    indicator_map = {
        "pmi_mfg": ("macro_china_pmi", {}),
        "cpi": ("macro_china_cpi_monthly", {}),
        "m2": ("macro_china_money_supply", {}),
    }
    if indicator not in indicator_map:
        raise ValueError(f"不支持的指标: {indicator}")

    func_name, kwargs = indicator_map[indicator]
    cache_key = f"macro_{indicator}"
    conn = fetcher._get_conn()
    try:
        cached = fetcher._read_cache(conn, "macro_cache", cache_key)
        if cached is not None:
            return cached

        if not _ak_available():
            raise RuntimeError("akshare 未安装")

        import akshare as ak
        func = getattr(ak, func_name)
        df = _retry_request(lambda: func(**kwargs), max_retries=2, base_delay=3)
        df = df.rename(columns={
            "月份": "date", "日期": "date",
            "制造业-Loss": "pmi_mfg", "全国-当月": "cpi_yoy",
            "M2-数量": "m2", "M2-同比增长": "m2_yoy",
        })
        df = df.tail(60).reset_index(drop=True)
        fetcher._write_cache(conn, "macro_cache", cache_key, df)
        return df
    finally:
        conn.close()


def fetch_commodity_price(fetcher, name="煤炭"):
    cache_key = f"commodity_{name}"
    conn = fetcher._get_conn()
    try:
        cached = fetcher._read_cache(conn, "commodity_cache", cache_key)
        if cached is not None:
            return cached

        if not _ak_available():
            raise RuntimeError("akshare 未安装")
        import akshare as ak  # 局部导入：与 _AK_OK 同源
        df = _retry_request(
            lambda: ak.spot_price_qsx(symbol="全部"),
            max_retries=2, base_delay=3,
        )
        df = df[df["品种"].str.contains(name, na=False)]
        df = df.rename(columns={"日期": "date", "品种": "name", "价格": "price"})
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date", "name", "price"]].sort_values("date").reset_index(drop=True)
        fetcher._write_cache(conn, "commodity_cache", cache_key, df)
        return df
    finally:
        conn.close()


def fetch_financial(fetcher, symbol="600519", report_type="income"):
    if not _ak_available():
        raise RuntimeError("akshare 未安装")
    import akshare as ak  # 局部导入：与 _AK_OK 同源
    func_map = {
        "income": ak.stock_financial_report_sina,
        "balance": ak.stock_financial_report_sina,
        "cash": ak.stock_financial_report_sina,
    }
    report_map = {"income": "利润表", "balance": "资产负债表", "cash": "现金流量表"}
    df = func_map[report_type](stock=f"sh{symbol}", symbol=report_map[report_type])
    return df.head(8)
