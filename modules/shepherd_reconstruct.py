"""
牧羊人指标历史重构模块

目标：把「股海牧羊人·情绪温度计」所需的市场广度指标（上涨/下跌/涨停/跌停家数、
红盘占比）从 2007 年起尽量补全；v2 再新增横截面复盘指标
（中位数涨跌幅 / 平均股价 / 回头波>10% / 炸板家数 / 倒跌停家数）。

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
- 每只股票聚合结果落地到 data/shepherd_cache_v2/<symbol>.csv，支持断点续跑；崩溃后
  重跑只会补拉缺失标的，已缓存的不重复下载。
- v2 与 v1 缓存目录分离：v2 每股每日多存 change_pct/close/触板标记（横截面指标
  需要个股级明细，无法从 v1 的 0/1 计数聚合而来），因此 v1 缓存不能复用，需全量重拉。
- 前复权(qfq)口径说明：涨停/跌停/回头波按比例计算不受影响；平均股价为 qfq 近似值
  （绝对价位与真实不复权价有偏差，趋势仍有效）。
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import time
from typing import Optional

import numpy as np
import pandas as pd

from modules.time_utils import now_cst_str

from modules.atomic_io import atomic_json_dump, atomic_to_csv
from modules.fetch_parallel import fetch_many

logger = logging.getLogger(__name__)


def _atomic_to_csv(df: pd.DataFrame, path: str) -> None:
    """原子写 CSV：委托共享实现 modules/atomic_io（tmp 名唯一化 + replace 退避重试）。

    原来的固定 tmp 名在多写者/多进程并发下会互相覆盖并抛 PermissionError(WinError 32)，
    压测实测 160 次写入失败 7 次。详见 modules/atomic_io.py 文档。
    """
    atomic_to_csv(df, path, encoding=None)


def _atomic_json_dump(obj, path: str) -> None:
    """原子写 JSON：委托共享实现 modules/atomic_io（同上，tmp 名唯一化 + 重试）。"""
    atomic_json_dump(obj, path)


# 输出文件（与 shepherd.py 共享）
_BREADTH_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_history.csv"
)
_SYMBOLS_CACHE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_symbols.json"
)
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_cache_v2"
)

# 新浪 daily 列名
_DAILY_COLS = ["date", "open", "high", "low", "close", "volume", "amount", "outstanding_share", "turnover"]

# v2 横截面聚合口径：sum=家数计数，median/mean=横截面统计
_AGG_SPEC = {
    "up_count": "sum", "down_count": "sum", "flat_count": "sum",
    "limit_up": "sum", "limit_down": "sum",
    "touch_down": "sum", "zt_fail_count": "sum", "hb_wave10": "sum",
    "change_pct": "median", "close": "mean",
}


def _retry(max_retries: int = 3, base_delay: float = 0.6):
    """模块级重试装饰器（仅用于主线程调用的辅助函数，不要用于多进程 worker）。"""
    def deco(fn):
        def wrapper(*args, **kwargs):
            last = None
            for i in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[shepherd_reconstruct] 处理异常: {e}")
                    last = e
                    if i < max_retries - 1:
                        time.sleep(base_delay * (2 ** i) + np.random.random() * 0.3)
                        continue
            logger.debug("[shepherd_reconstruct] %s 失败: %s", getattr(fn, "__name__", "fn"), last)
            return None
        return wrapper
    return deco


def _board_limit_pct(symbol: str) -> float:
    """按代码推断日涨跌停幅度（非 ST 常规规则）。支持带前缀与裸代码：
    北交所 8xx/920=30%，科创板 68=20%，创业板 30/31=20%，其余=10%。
    """
    s = symbol.lower().strip()
    code = s[2:] if len(s) > 2 and s[:2] in ("sh", "sz", "bj") else s
    if s.startswith("bj"):
        return 0.30
    if code.startswith(("83", "87", "88", "89", "92")):  # 北交所
        return 0.30
    if code.startswith("68"):  # 科创板
        return 0.20
    if code.startswith(("30", "31")):  # 创业板 300 / 301
        return 0.20
    return 0.10


def _detect_limit(row: pd.Series, limit_pct: float, tol: float = 0.005) -> tuple[int, int, int, int]:
    """返回 (是否涨停, 是否跌停, 是否盘中触涨停, 是否盘中触跌停)。"""
    prev_close = row["prev_close"]
    close = row["close"]
    if pd.isna(prev_close) or prev_close <= 0 or pd.isna(close) or close <= 0:
        return 0, 0, 0, 0
    up_limit = prev_close * (1 + limit_pct)
    down_limit = prev_close * (1 - limit_pct)
    high = row.get("high")
    low = row.get("low")
    touch_up = 0
    touch_down = 0
    if pd.notna(high) and high >= up_limit * (1 - tol):
        touch_up = 1
    if pd.notna(low) and low <= down_limit * (1 + tol):
        touch_down = 1
    is_up = (abs(close - up_limit) / up_limit < tol) and (close > prev_close)
    is_down = (abs(close - down_limit) / down_limit < tol) and (close < prev_close)
    return int(is_up), int(is_down), touch_up, touch_down


def _normalize_daily(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """把新浪日线 DataFrame 标准化为含 date/close/high/low/volume 的 DataFrame。"""
    if df is None or len(df) < 2:
        return None
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    col_map = {}
    for want in ("date", "close", "high", "low", "volume"):
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
    if "low" in col_map:
        df["low"] = pd.to_numeric(df[col_map["low"]], errors="coerce")
    else:
        df["low"] = df["close"]
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

    v2：额外输出 change_pct/close/触板标记/回头波标记，供跨股横截面聚合
    （中位数涨跌幅/平均股价/炸板家数/倒跌停家数/回头波>10%家数）。
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
            logger.warning(f"[shepherd_reconstruct] 处理异常: {e}")
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

    sealed_up_flags, sealed_down_flags, touch_up_flags, touch_down_flags = [], [], [], []
    for _, row in df.iterrows():
        up, down, tup, tdn = _detect_limit(row, limit_pct)
        sealed_up_flags.append(up)
        sealed_down_flags.append(down)
        touch_up_flags.append(tup)
        touch_down_flags.append(tdn)

    # 回头波 = (最高-收盘)/最高 > 10%（追高者日内回撤，杨哥口径）
    hw = np.where((df["high"] > 0) & df["high"].notna(),
                  (df["high"] - df["close"]) / df["high"] * 100.0, np.nan)
    hb10 = (pd.Series(hw, index=df.index) > 10).astype(int)
    hb10 = hb10.where(~suspended, 0)

    out = pd.DataFrame({
        "date": df["date"].dt.date,
        "up_count": is_up.astype(int),
        "down_count": is_down.astype(int),
        "flat_count": is_flat.astype(int),
        "limit_up": sealed_up_flags,
        "limit_down": sealed_down_flags,
        "touch_up": touch_up_flags,
        "touch_down": touch_down_flags,
        # 炸板 = 盘中触涨停但收盘未封住（杨哥：摸板/尾盘炸板均算）
        "zt_fail_count": [int(t and not s) for t, s in zip(touch_up_flags, sealed_up_flags)],
        "hb_wave10": hb10.values,
        "change_pct": df["change_pct"].values,
        "close": df["close"].values,
    })
    return out.groupby("date").first().reset_index()


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
            _atomic_to_csv(df, path)
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
        _atomic_json_dump(df["symbol"].astype(str).tolist(), _SYMBOLS_CACHE)
    except Exception as e:  # noqa: BLE001
        logger.debug("[shepherd_reconstruct] 写代码缓存失败: %s", e)
    return df


def reconstruct_breadth(start_date: str, end_date: str, max_workers: int = 12,
                        symbols: Optional[list] = None, use_cache: bool = True) -> pd.DataFrame:
    """重构全 A 市场广度日序列（多进程 + 断点续跑，v2 含横截面复盘指标）。

    :param start_date/end_date: YYYYMMDD 或 YYYY-MM-DD。
    :param max_workers: 多进程 worker 数。
    :param symbols: 指定股票代码列表（测试用）；None 则自动获取全 A。
    :param use_cache: 是否复用/写入 data/shepherd_cache_v2 缓存。
    :returns: DataFrame[date, up_count, down_count, flat_count, limit_up, limit_down,
              touch_down, zt_fail_count, hb_wave10, median_chg, avg_price, red_ratio]
    """
    sd = pd.to_datetime(start_date).strftime("%Y%m%d")
    ed = pd.to_datetime(end_date).strftime("%Y%m%d")

    if symbols is None:
        codes_df = _fetch_a_share_codes()
        if codes_df is None or codes_df.empty:
            logger.warning("[shepherd_reconstruct] 无法获取全 A 代码列表，返回空 DataFrame")
            return pd.DataFrame(columns=["date"] + list(_AGG_SPEC.keys()) + ["red_ratio"])
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
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[shepherd_reconstruct] 处理异常: {e}")
            continue
    if not frames:
        return pd.DataFrame(columns=["date"] + list(_AGG_SPEC.keys()) + ["red_ratio"])

    # 跨股横截面聚合：家数求和 + 中位数/均值统计（v2）
    out = _aggregate_frames(frames)
    out = out[(out["date"] >= pd.to_datetime(start_date)) & (out["date"] <= pd.to_datetime(end_date))]
    return out.reset_index(drop=True)


def _aggregate_frames(frames: list) -> pd.DataFrame:
    """跨股横截面聚合（纯函数，可离线测试）。

    输入：每股 DataFrame 的列表（v2 schema：date + 计数/标记 + change_pct + close）。
    输出：DataFrame[date, up_count, ..., limit_up, limit_down, touch_down, zt_fail_count,
    hb_wave10, median_chg, avg_price, red_ratio]。
    """
    empty_cols = ["date"] + list(_AGG_SPEC.keys()) + ["red_ratio"]
    if not frames:
        return pd.DataFrame(columns=empty_cols)
    big = pd.concat(frames, ignore_index=True)
    big["date"] = pd.to_datetime(big["date"], errors="coerce")
    big = big.dropna(subset=["date"])
    if big.empty:
        return pd.DataFrame(columns=empty_cols)
    big["date"] = big["date"].dt.date
    for c, how in _AGG_SPEC.items():
        if c not in big.columns:
            big[c] = 0 if how == "sum" else np.nan
        big[c] = pd.to_numeric(big[c], errors="coerce")
        if how == "sum":
            big[c] = big[c].fillna(0).astype(np.int64)
    agg = big.groupby("date", sort=True).agg(_AGG_SPEC).reset_index()
    agg = agg.rename(columns={"change_pct": "median_chg", "close": "avg_price"})
    out = agg.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    denom = out["up_count"] + out["down_count"]
    out["red_ratio"] = np.where(denom > 0, out["up_count"] / denom * 100.0, np.nan)
    return out


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
    """拉取某日涨停池，返回 dict（含连板梯队/封成比，复用 shepherd 纯函数口径）。"""
    import akshare as ak
    from modules.shepherd import _compute_zt_pool_indicators
    d = pd.to_datetime(date).strftime("%Y%m%d")
    df = ak.stock_zt_pool_em(date=d)
    return _compute_zt_pool_indicators(df)


@_retry(max_retries=1)
def _fetch_zt_zbgc(date: str):
    """拉取某日炸板股池，返回炸板家数 dict（仅支持近约 30 交易日，业务性报错不重试）。"""
    import akshare as ak
    d = pd.to_datetime(date).strftime("%Y%m%d")
    df = ak.stock_zt_pool_zbgc_em(date=d)
    if df is None or df.empty:
        return None
    return {"zt_fail_count": float(len(df))}


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
    """对给定日期列表并发拉取 zt_pool / zbgc / previous / dtgc，返回 DataFrame。"""
    tasks = []
    for d in dates:
        ds = pd.to_datetime(d).strftime("%Y-%m-%d")

        def _pull(date=ds):
            vals = {**(_fetch_zt_pool(date) or {}), **(_fetch_zt_zbgc(date) or {}),
                    **(_fetch_zt_dtgc(date) or {}), **(_fetch_zt_previous(date) or {})}
            # 炸板率修正为杨哥口径：炸板/(涨停+炸板)
            zc, lu = vals.get("zt_fail_count"), vals.get("limit_up")
            if zc is not None and lu is not None and (zc + lu) > 0:
                vals["zt_fail_ratio"] = float(zc / (zc + lu) * 100.0)
            return vals

        tasks.append((f"zt_{ds}", _pull))

    results = fetch_many(tasks, max_workers=6, timeout=20)
    rows = []
    for d in dates:
        ds = pd.to_datetime(d).strftime("%Y-%m-%d")
        key = f"zt_{ds}"
        vals = results.get(key) or {}
        row = {"date": pd.to_datetime(d)}
        for k in ("limit_up", "limit_down", "connect_hl", "connect_2b", "fc_ratio",
                  "zt_fail_count", "zt_fail_ratio", "zt_prev_ret"):
            row[k] = vals.get(k)
        rows.append(row)
    return pd.DataFrame(rows)


def _enrich_zt_from_cache(breadth: pd.DataFrame, cache_dir: str) -> pd.DataFrame:
    """用 per-stock 缓存反推 zt_pool 类指标，覆盖全历史（不再只限近 30 天）。

    缓存文件 ``shepherd_cache_v2/<symbol>.csv`` 每行已含 ``limit_up(0/1)`` /
    ``zt_fail_count`` / ``change_pct``，足够反推：

      * ``zt_fail_ratio`` = Σ炸板 / (Σ涨停 + Σ炸板) × 100
      * ``zt_prev_ret``   = 昨日涨停股今日平均涨跌幅（打板赚钱效应）
      * ``connect_hl``    = 全市场最高连板数（逐股连板天数取最大）

    仅 fillna：历史缺失处用反推值补，近期 zt_pool 真实值优先保留。
    """
    if breadth is None or breadth.empty or not os.path.isdir(cache_dir):
        return breadth

    zf_sum, lu_sum, prev_ret_sum, prev_ret_cnt, streak_max = {}, {}, {}, {}, {}
    files = [f for f in os.listdir(cache_dir) if f.endswith(".csv")]
    for fn in files:
        try:
            df = pd.read_csv(os.path.join(cache_dir, fn))
        except Exception:  # noqa: BLE001
            continue
        if "date" not in df.columns or "limit_up" not in df.columns:
            continue
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if df.empty:
            continue
        lu = pd.to_numeric(df["limit_up"], errors="coerce").fillna(0)
        zf = pd.to_numeric(df.get("zt_fail_count"), errors="coerce").fillna(0)
        chg = pd.to_numeric(df.get("change_pct"), errors="coerce")
        # 连板天数：连续 limit_up 计数（向量化）
        s = (lu > 0).astype(int)
        grp = (s != s.shift()).cumsum()
        run = s.groupby(grp).cumcount() + 1
        streak_arr = (run * s).astype(int)
        prev_lu = lu.shift(1)
        tmp = pd.DataFrame({
            "date": df["date"], "lu": lu, "zf": zf, "chg": chg,
            "streak": streak_arr, "prev_lu": prev_lu,
        })
        for d, v in tmp.groupby("date")["lu"].sum().items():
            k = pd.Timestamp(d).normalize()
            lu_sum[k] = lu_sum.get(k, 0.0) + float(v)
        for d, v in tmp.groupby("date")["zf"].sum().items():
            k = pd.Timestamp(d).normalize()
            zf_sum[k] = zf_sum.get(k, 0.0) + float(v)
        for d, v in tmp.groupby("date")["streak"].max().items():
            k = pd.Timestamp(d).normalize()
            if v > streak_max.get(k, 0):
                streak_max[k] = int(v)
        pr = tmp[tmp["prev_lu"] == 1]
        if not pr.empty:
            for d, row in pr.groupby("date")["chg"].agg(["sum", "count"]).iterrows():
                k = pd.Timestamp(d).normalize()
                prev_ret_sum[k] = prev_ret_sum.get(k, 0.0) + float(row["sum"])
                prev_ret_cnt[k] = prev_ret_cnt.get(k, 0) + int(row["count"])

    dates_norm = pd.to_datetime(breadth["date"]).dt.normalize()
    zfr, zpr, chl = [], [], []
    for k in dates_norm:
        lu = lu_sum.get(k, 0.0)
        zf = zf_sum.get(k, 0.0)
        zfr.append(round(zf / (lu + zf) * 100, 2) if (lu + zf) > 0 else None)
        c = prev_ret_cnt.get(k, 0)
        zpr.append(round(prev_ret_sum.get(k, 0.0) / c, 3) if c > 0 else None)
        chl.append(streak_max.get(k, 0))
    out = breadth.copy()
    for col, series in (("zt_fail_ratio", pd.Series(zfr, index=breadth.index)),
                        ("zt_prev_ret", pd.Series(zpr, index=breadth.index)),
                        ("connect_hl", pd.Series(chl, index=breadth.index))):
        if col in out.columns:
            # 保留已有（近期 zt_pool 真实）值，仅用反推值补 NaN 的历史缺口
            out[col] = out[col].combine_first(series)
        else:
            out[col] = series
    return out


def build_shepherd_history(start_date: str = "2007-01-01", end_date: str = None, reconstruct: bool = True) -> pd.DataFrame:
    """构建完整的牧羊人指标历史表。

    :param start_date: 重构起始日，默认 2007-01-01。
    :param end_date: 结束日，默认今天。
    :param reconstruct: 是否执行全 A 重构（较慢）；False 则只读现有 CSV/只取近期 zt_pool。
    """
    if end_date is None:
        end_date = now_cst_str("%Y-%m-%d")

    if reconstruct:
        breadth = reconstruct_breadth(start_date, end_date)
    else:
        breadth = pd.DataFrame(columns=["date"] + list(_AGG_SPEC.keys()) + ["red_ratio"])

    # 尝试用 zt_pool 补充最近约 12 个交易日的真实涨停/跌停/连板/炸板/昨板表现
    try:
        recent_days = pd.date_range(end=pd.to_datetime(end_date), periods=15, freq="B").strftime("%Y-%m-%d").tolist()
        zt_df = fetch_zt_data_for_dates(recent_days)
        if not zt_df.empty:
            merged = breadth.merge(zt_df, on="date", how="outer", suffixes=("", "_zt"))
            for col in ("limit_up", "limit_down", "connect_hl", "connect_2b", "fc_ratio",
                        "zt_fail_count", "zt_fail_ratio", "zt_prev_ret"):
                zt_col = f"{col}_zt"
                if zt_col in merged.columns:
                    merged[col] = merged[zt_col].combine_first(merged.get(col))
                    merged.drop(columns=[zt_col], inplace=True)
            breadth = merged
    except Exception as e:  # noqa: BLE001
        logger.warning("[shepherd_reconstruct] 合并 zt_pool 失败: %s", e)

    # 用 per-stock 缓存反推 zt_pool 指标（zt_fail_ratio/zt_prev_ret/connect_hl），
    # 覆盖全历史，填补 zt_pool 仅近 30 天的空白（回测 99.6% 坍缩成「修复试探」的根因）。
    # 缓存已就绪时纯本地计算，免联网。
    try:
        breadth = _enrich_zt_from_cache(breadth, _CACHE_DIR)
    except Exception as e:  # noqa: BLE001
        logger.warning("[shepherd_reconstruct] 反推 zt_pool 指标失败: %s", e)

    # 确保列顺序（v2：新增 touch_down / zt_fail_count / hb_wave10 / median_chg / avg_price 等）
    cols = ["date", "up_count", "down_count", "flat_count", "limit_up", "limit_down", "red_ratio",
            "touch_down", "zt_fail_count", "hb_wave10", "median_chg", "avg_price",
            "connect_hl", "connect_2b", "fc_ratio", "zt_fail_ratio", "zt_prev_ret"]
    for c in cols:
        if c not in breadth.columns:
            breadth[c] = np.nan
    breadth = breadth[cols].sort_values("date").reset_index(drop=True)
    return breadth


def save_history(df: pd.DataFrame, path: Optional[str] = None) -> str:
    path = path or _BREADTH_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # ⚠️ 原子写：全量重算（5548 只股票）落盘期间若被 shepherd_note.analyze_history
    # 并发读取，直接 to_csv 会让对方读到半截文件。先写临时文件再 os.replace。
    # 保持原有 utf-8-sig：本文件是 breadth 历史主档，下游按 BOM 头读取。
    atomic_to_csv(df, path, encoding="utf-8-sig")
    logger.info("[shepherd_reconstruct] 已保存 %d 行到 %s", len(df), path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = build_shepherd_history("2007-01-01")
    save_history(df)
    print(df.tail(10).to_string(index=False))
