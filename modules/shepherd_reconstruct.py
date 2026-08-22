"""
牧羊人指标历史重构模块

目标：把「股海牧羊人·情绪温度计」所需的市场广度指标（上涨/下跌/涨停/跌停家数、
红盘占比）从 2007 年起尽量补全。

数据现实：
- 东财 stock_zh_a_spot_em / stock_zh_a_hist 在沙箱/部分网络环境下会被远程断连；
- 新浪 stock_zh_a_spot / stock_zh_a_daily 可用且可回溯到 2007 年左右；
- zt_pool 类接口（akshare 东财）只能拿到最近约 12 个交易日，无法覆盖长周期。

执行策略（性能/稳定性关键）：
- 新浪 stock_zh_a_daily 底层解码会实例化 V8（py_mini_racer），**多线程并发会在同一
  进程内共享 V8 导致崩溃**（partition_address_space Check failed）。因此全市场重构
  必须用「多进程」(ProcessPoolExecutor) 让每只 worker 进程各自持有独立 V8 实例。
- worker 函数必须是「模块级纯函数、不带局部闭包装饰器」，否则 multiprocessing 在
  Windows(spawn) 下 pickle 失败（Can't get local object ...wrapper）。
- 每只股票聚合结果落地到 data/shepherd_cache/<symbol>.csv，支持断点续跑；崩溃后
  重跑只会补拉缺失标的，已缓存的不重复下载。
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import time
from typing import Optional

import numpy as np
import pandas as pd

from modules.fetch_parallel import fetch_many

logger = logging.getLogger(__name__)

# 输出文件（与 shepherd.py 共享）
_BREADTH_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_history.csv"
)
_SYMBOLS_CACHE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_symbols.json"
)
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_cache"
)

# 新浪 daily 列名
_DAILY_COLS = ["date", "open", "high", "low", "close", "volume", "amount", "outstanding_share", "turnover"]


def _retry(max_retries: int = 3, base_delay: float = 0.6):
    """模块级重试装饰器（仅用于主线程调用的辅助函数，不要用于多进程 worker）。"""
    def deco(fn):
        def wrapper(*args, **kwargs):
            last = None
            for i in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    last = e
                    if i < max_retries - 1:
                        time.sleep(base_delay * (2 ** i) + np.random.random() * 0.3)
                        continue
            logger.debug("[shepherd_reconstruct] %s 失败: %s", getattr(fn, "__name__", "fn"), last)
            return None
        return wrapper
    return deco


def _board_limit_pct(symbol: str) -> float:
    """根据交易所前缀和代码段判断日涨跌停幅度（非 ST 常规规则）。"""
    s = symbol.lower().strip()
    code = s[2:] if len(s) > 2 and s[:2] in ("sh", "sz", "bj") else s
    if s.startswith("bj"):
        return 0.30
    if s.startswith("sh") and code.startswith("68"):
        return 0.20
    if s.startswith("sz") and code.startswith("30"):
        return 0.20
    return 0.10


def _detect_limit(row: pd.Series, limit_pct: float, tol: float = 0.005) -> tuple[int, int]:
    """返回 (是否涨停, 是否跌停)。"""
    prev_close = row["prev_close"]
    close = row["close"]
    if pd.isna(prev_close) or prev_close <= 0 or pd.isna(close) or close <= 0:
        return 0, 0
    up_limit = prev_close * (1 + limit_pct)
    down_limit = prev_close * (1 - limit_pct)
    is_up = (abs(close - up_limit) / up_limit < tol) and (close > prev_close)
    is_down = (abs(close - down_limit) / down_limit < tol) and (close < prev_close)
    return int(is_up), int(is_down)


def _normalize_daily(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """把新浪日线 DataFrame 标准化为含 date/close/high/volume 的 DataFrame。"""
    if df is None or len(df) < 2:
        return None
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    col_map = {}
    for want in ("date", "close", "high", "volume"):
        for c in df.columns:
            if want in c.lower():
                col_map[want] = c
                break
    if "date" not in col_map or "close" not in col_map:
        return None
    df["date"] = pd.to_datetime(df[col_map["date"]], errors="coerce")
    df["close"] = pd.to_numeric(df[col_map["close"]], errors="coerce")
    if "high" in col_map:
        df["high"] = pd.to_numeric(df[col_map["high"]], errors="coerce")
    else:
        df["high"] = df["close"]
    df["volume"] = pd.to_numeric(df.get(col_map.get("volume")), errors="coerce")
    df = df.dropna(subset=["date", "close"])
    if len(df) < 2:
        return None
    df = df.sort_values("date").reset_index(drop=True)
    df["prev_close"] = df["close"].shift(1)
    df = df.dropna(subset=["prev_close"])
    return df if not df.empty else None


def _aggregate_one_stock(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """拉取单只股票日线并聚合为每日 0/1 计数（模块级纯函数，带内部重试，无装饰器）。

    返回 DataFrame[date, up_count, down_count, flat_count, limit_up, limit_down]，
    失败返回 None。
    """
    import akshare as ak

    sd = pd.to_datetime(start_date).strftime("%Y%m%d")
    ed = pd.to_datetime(end_date).strftime("%Y%m%d")

    df = None
    last_err = None
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=symbol, start_date=sd, end_date=ed, adjust="qfq")
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < 2:
                time.sleep(0.6 * (2 ** attempt) + np.random.random() * 0.3)
                continue
    if df is None:
        logger.debug("[shepherd_reconstruct] %s 拉取失败: %s", symbol, last_err)
        return None

    df = _normalize_daily(df)
    if df is None:
        return None

    df["change_pct"] = (df["close"] - df["prev_close"]) / df["prev_close"] * 100.0
    limit_pct = _board_limit_pct(symbol)

    is_up = df["change_pct"] > 0
    is_down = df["change_pct"] < 0
    is_flat = df["change_pct"] == 0
    # 停牌或零成交量通常不计入涨跌
    suspended = df["volume"].fillna(0) <= 0
    is_up = is_up & (~suspended)
    is_down = is_down & (~suspended)
    is_flat = is_flat & (~suspended)

    limit_up_flags = []
    limit_down_flags = []
    for _, row in df.iterrows():
        up, down = _detect_limit(row, limit_pct)
        limit_up_flags.append(up)
        limit_down_flags.append(down)

    out = pd.DataFrame({
        "date": df["date"].dt.date,
        "up_count": is_up.astype(int),
        "down_count": is_down.astype(int),
        "flat_count": is_flat.astype(int),
        "limit_up": limit_up_flags,
        "limit_down": limit_down_flags,
    })
    return out.groupby("date").sum().reset_index()


def _cache_path(symbol: str, cache_dir: str) -> str:
    safe = symbol.replace("/", "_").replace("\\", "_")
    return os.path.join(cache_dir, f"{safe}.csv")


def _aggregate_cached(symbol: str, start_date: str, end_date: str, cache_dir: str, use_cache: bool) -> Optional[pd.DataFrame]:
    """带磁盘缓存的聚合：已缓存则直接读，否则计算并落盘。"""
    path = _cache_path(symbol, cache_dir)
    if use_cache and os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception as e:  # noqa: BLE001
            logger.debug("[shepherd_reconstruct] 读缓存失败 %s: %s", symbol, e)
    df = _aggregate_one_stock(symbol, start_date, end_date)
    if df is not None and not df.empty:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            df.to_csv(path, index=False)
        except Exception as e:  # noqa: BLE001
            logger.debug("[shepherd_reconstruct] 写缓存失败 %s: %s", symbol, e)
    return df


def _aggregate_worker(args) -> tuple[str, Optional[pd.DataFrame]]:
    """多进程 worker：解包参数并调用 _aggregate_cached。"""
    symbol, sd, ed, cache_dir, use_cache = args
    return symbol, _aggregate_cached(symbol, sd, ed, cache_dir, use_cache)


@_retry()
def _fetch_a_share_codes() -> Optional[pd.DataFrame]:
    """获取当前全 A 代码列表（新浪源），带本地 JSON 缓存。"""
    if os.path.exists(_SYMBOLS_CACHE):
        try:
            import json
            with open(_SYMBOLS_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return pd.DataFrame({"symbol": data})
        except Exception as e:  # noqa: BLE001
            logger.debug("[shepherd_reconstruct] 读代码缓存失败: %s", e)

    import akshare as ak
    df = ak.stock_zh_a_spot()
    if df is None or df.empty:
        return None
    code_col = None
    for c in df.columns:
        if str(c).strip() == "代码":
            code_col = c
            break
    if code_col is None:
        return None
    df = df[[code_col]].copy()
    df.rename(columns={code_col: "symbol"}, inplace=True)
    df = df[df["symbol"].astype(str).str.len() >= 8]
    try:
        import json
        os.makedirs(os.path.dirname(_SYMBOLS_CACHE), exist_ok=True)
        with open(_SYMBOLS_CACHE, "w", encoding="utf-8") as f:
            json.dump(df["symbol"].astype(str).tolist(), f, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        logger.debug("[shepherd_reconstruct] 写代码缓存失败: %s", e)
    return df


def reconstruct_breadth(start_date: str, end_date: str, max_workers: int = 12,
                        symbols: Optional[list] = None, use_cache: bool = True) -> pd.DataFrame:
    """重构全 A 市场广度日序列（多进程 + 断点续跑）。

    :param start_date/end_date: YYYYMMDD 或 YYYY-MM-DD。
    :param max_workers: 多进程 worker 数。
    :param symbols: 指定股票代码列表（测试用）；None 则自动获取全 A。
    :param use_cache: 是否复用/写入 data/shepherd_cache 缓存。
    :returns: DataFrame[date, up_count, down_count, flat_count, limit_up, limit_down, red_ratio]
    """
    sd = pd.to_datetime(start_date).strftime("%Y%m%d")
    ed = pd.to_datetime(end_date).strftime("%Y%m%d")

    if symbols is None:
        codes_df = _fetch_a_share_codes()
        if codes_df is None or codes_df.empty:
            logger.warning("[shepherd_reconstruct] 无法获取全 A 代码列表，返回空 DataFrame")
            return pd.DataFrame(columns=["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio"])
        symbols = codes_df["symbol"].astype(str).tolist()

    os.makedirs(_CACHE_DIR, exist_ok=True)

    # 命中缓存直接跳过（断点续跑 / 全量已完成时秒级重跑）
    todo = [(s, sd, ed, _CACHE_DIR, use_cache) for s in symbols
            if not (use_cache and os.path.exists(_cache_path(s, _CACHE_DIR)))]
    cached_hits = len(symbols) - len(todo)
    if cached_hits:
        logger.info("[shepherd_reconstruct] %d 只命中缓存，跳过拉取", cached_hits)

    done = 0
    failed = 0
    t0 = time.time()

    if todo:
        # 多进程：每只 worker 独立 V8 实例，避免多线程共享 V8 崩溃
        with cf.ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_aggregate_worker, t): t[0] for t in todo}
            for fut in cf.as_completed(futures):
                sym = futures[fut]
                done += 1
                try:
                    _s, _df = fut.result(timeout=60)
                    if _df is None:
                        failed += 1
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    logger.debug("[shepherd_reconstruct] %s 超时/异常: %s", sym, e)
                if done % 500 == 0:
                    logger.info("[shepherd_reconstruct] 进度 %d/%d (失败 %d)，已用 %.1fs",
                                done, len(todo), failed, time.time() - t0)

    if done or cached_hits:
        logger.info("[shepherd_reconstruct] 聚合完成 %d 只新拉 + %d 缓存命中，失败 %d，耗时 %.1fs",
                    done, cached_hits, failed, time.time() - t0)

    # 从缓存目录读取全部已聚合结果（含续跑命中），向量化合并按日期求和
    cache_files = [f for f in os.listdir(_CACHE_DIR) if f.endswith(".csv")]
    frames = []
    for fn in cache_files:
        try:
            frames.append(pd.read_csv(os.path.join(_CACHE_DIR, fn)))
        except Exception:  # noqa: BLE001
            continue
    if not frames:
        return pd.DataFrame(columns=["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio"])

    big = pd.concat(frames, ignore_index=True)
    big["date"] = pd.to_datetime(big["date"], errors="coerce")
    big = big.dropna(subset=["date"])
    big["date"] = big["date"].dt.date
    for c in ("up_count", "down_count", "flat_count", "limit_up", "limit_down"):
        if c not in big.columns:
            big[c] = 0
        big[c] = pd.to_numeric(big[c], errors="coerce").fillna(0).astype(np.int64)
    agg = big.groupby("date", sort=True)[["up_count", "down_count", "flat_count", "limit_up", "limit_down"]].sum().reset_index()
    agg.columns = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down"]
    out = agg.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)

    denom = out["up_count"] + out["down_count"]
    out["red_ratio"] = np.where(denom > 0, out["up_count"] / denom * 100.0, np.nan)

    out = out[(out["date"] >= pd.to_datetime(start_date)) & (out["date"] <= pd.to_datetime(end_date))]
    return out.reset_index(drop=True)


def _col(df, *keys):
    if df is None or not hasattr(df, "columns"):
        return None
    low = {str(c).lower(): c for c in df.columns}
    for k in keys:
        lk = str(k).lower()
        for lcol, col in low.items():
            if lk in lcol:
                return col
    return None


@_retry()
def _fetch_zt_pool(date: str):
    """拉取某日涨停池，返回 dict。"""
    import akshare as ak
    d = pd.to_datetime(date).strftime("%Y%m%d")
    df = ak.stock_zt_pool_em(date=d)
    if df is None or df.empty:
        return None
    out = {"limit_up": float(len(df))}
    col_hl = _col(df, "连板数")
    if col_hl:
        hl = pd.to_numeric(df[col_hl], errors="coerce").max()
        if pd.notna(hl):
            out["connect_hl"] = float(hl)
    col_zb = _col(df, "炸板次数")
    if col_zb:
        zb = pd.to_numeric(df[col_zb], errors="coerce").fillna(0)
        total = len(df)
        out["zt_fail_ratio"] = float((zb > 0).mean() * 100.0) if total > 0 else 0.0
    return out


@_retry()
def _fetch_zt_previous(date: str):
    """拉取某日昨日涨停表现。"""
    import akshare as ak
    d = pd.to_datetime(date).strftime("%Y%m%d")
    df = ak.stock_zt_pool_previous_em(date=d)
    if df is None or df.empty:
        return None
    col = _col(df, "涨跌幅", "change_percent")
    if col is None:
        return None
    chg = pd.to_numeric(df[col], errors="coerce").dropna()
    if chg.empty:
        return None
    return {"zt_prev_ret": float(chg.mean())}


@_retry()
def _fetch_zt_dtgc(date: str):
    """拉取某日跌停股池，用于补跌停家数（近期）。"""
    import akshare as ak
    d = pd.to_datetime(date).strftime("%Y%m%d")
    df = ak.stock_zt_pool_dtgc_em(date=d)
    if df is None:
        return None
    return {"limit_down": float(len(df))}


def fetch_zt_data_for_dates(dates: list) -> pd.DataFrame:
    """对给定日期列表并发拉取 zt_pool / previous / dtgc，返回 DataFrame。"""
    tasks = []
    for d in dates:
        ds = pd.to_datetime(d).strftime("%Y-%m-%d")
        tasks.append((f"zt_{ds}", lambda date=ds: {**(_fetch_zt_pool(date) or {}), **(_fetch_zt_dtgc(date) or {}), **(_fetch_zt_previous(date) or {})}))

    results = fetch_many(tasks, max_workers=6, timeout=20)
    rows = []
    for d in dates:
        ds = pd.to_datetime(d).strftime("%Y-%m-%d")
        key = f"zt_{ds}"
        vals = results.get(key) or {}
        row = {"date": pd.to_datetime(d)}
        for k in ("limit_up", "limit_down", "connect_hl", "zt_fail_ratio", "zt_prev_ret"):
            row[k] = vals.get(k)
        rows.append(row)
    return pd.DataFrame(rows)


def build_shepherd_history(start_date: str = "2007-01-01", end_date: str = None, reconstruct: bool = True) -> pd.DataFrame:
    """构建完整的牧羊人指标历史表。

    :param start_date: 重构起始日，默认 2007-01-01。
    :param end_date: 结束日，默认今天。
    :param reconstruct: 是否执行全 A 重构（较慢）；False 则只读现有 CSV/只取近期 zt_pool。
    """
    if end_date is None:
        end_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    if reconstruct:
        breadth = reconstruct_breadth(start_date, end_date)
    else:
        breadth = pd.DataFrame(columns=["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio"])

    # 尝试用 zt_pool 补充最近约 12 个交易日的真实涨停/跌停/连板/炸板/昨板表现
    try:
        recent_days = pd.date_range(end=pd.to_datetime(end_date), periods=15, freq="B").strftime("%Y-%m-%d").tolist()
        zt_df = fetch_zt_data_for_dates(recent_days)
        if not zt_df.empty:
            merged = breadth.merge(zt_df, on="date", how="outer", suffixes=("", "_zt"))
            for col in ("limit_up", "limit_down", "connect_hl", "zt_fail_ratio", "zt_prev_ret"):
                zt_col = f"{col}_zt"
                if zt_col in merged.columns:
                    merged[col] = merged[zt_col].combine_first(merged.get(col))
                    merged.drop(columns=[zt_col], inplace=True)
            breadth = merged
    except Exception as e:  # noqa: BLE001
        logger.warning("[shepherd_reconstruct] 合并 zt_pool 失败: %s", e)

    # 确保列顺序
    cols = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio", "connect_hl", "zt_fail_ratio", "zt_prev_ret"]
    for c in cols:
        if c not in breadth.columns:
            breadth[c] = np.nan
    breadth = breadth[cols].sort_values("date").reset_index(drop=True)
    return breadth


def save_history(df: pd.DataFrame, path: Optional[str] = None) -> str:
    path = path or _BREADTH_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("[shepherd_reconstruct] 已保存 %d 行到 %s", len(df), path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = build_shepherd_history("2007-01-01")
    save_history(df)
    print(df.tail(10).to_string(index=False))
