"""
牧羊人指标（股海牧羊人·情绪温度计）数据层

背景：用户要求把抖音博主「股海牧羊人」视频《炒股绕不开的第一步》里提到的
「衡量市场指标」提炼为一类专属指标——「牧羊人指标」，接入《市场情绪》模块。

该视频的方法论本质是「情绪温度计」：
  第一步别盯指数红绿，先看大盘脸色——涨跌家数 / 涨停跌停家数 / 昨日涨停表现。
经多源交叉验证（同类「情绪温度计」教程），核心指标集合如下：

  指标            含义/算法                                      高温 / 常温 / 低温（牧羊人温度计）
  ──────────────────────────────────────────────────────────────────────────────
  上涨家数        全市场上涨个股数                               >3000 / 1500~3000 / <1500
  下跌家数        全市场下跌个股数                               <1500 / 1500~3000 / >3000（防守）
  涨停家数        当日收盘涨停个股数（东财涨停池）               >50 / 20~50 / <20
  跌停家数        当日收盘跌停个股数（全A快照反算）              <5 / 5~15 / >15（>30 恐慌）
  昨日涨停表现    昨日涨停股今日平均涨跌幅(%)                    >3% / 0~3% / <0%（吃面）
  红盘占比        上涨/(上涨+下跌)×100%                         >60% / 45~60% / <45%
  连板高度        当日最高连板数（涨停池 max 连板数）            ≥6板 / 3~5板 / <3板
  炸板率          涨停池中「炸板次数>0」占比(%)（封板不稳代理）  <30% / 30~50% / >50%

数据层设计（对齐 modules/market_drivers 的优雅降级约定）：
- get_shepherd_today()   实时快照（约 3 次轻量请求，<1s），供温度计卡使用。
- get_shepherd_history() 历史回测（按交易日历循环 akshare，重，TTL 缓存 1h），供折线图使用；
                          整体失败则降级读取 data/shepherd_history.csv 持久缓存。
- get_shepherd_indicators(days) 统一入口，返回 (df, meta)。
- 单源失败不影响其他源，绝不抛红错；无网络时返回空 df + unavailable 标注。
"""
import os
import time
import logging
import threading

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ───────── 配置 ─────────
_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "shepherd_history.csv")
_HISTORY_TTL = 3600  # 1h
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_MAX_HISTORY_DAYS = 90


def _cached(ttl, key, fn):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and (now - hit[0]) < ttl:
            return hit[1]
    val = fn()
    with _CACHE_LOCK:
        _CACHE[key] = (now, val)
    return val


def _col(df, *keys):
    """按关键字（不区分大小写）在 DataFrame 列中找第一个匹配列名。"""
    if df is None or not hasattr(df, "columns"):
        return None
    low = {str(c).lower(): c for c in df.columns}
    for k in keys:
        lk = str(k).lower()
        for lcol, col in low.items():
            if lk in lcol:
                return col
    return None


def _pdate(x):
    try:
        return pd.to_datetime(x, errors="coerce")
    except Exception as e:  # noqa
        logger.warning("[shepherd] 日期解析异常: %s", e)
        return pd.NaT


def _retry(max_retries=2, base_delay=0.5):
    def deco(fn):
        def wrapper(*args, **kwargs):
            last = None
            for i in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa
                    logger.warning(f"[shepherd] 处理异常: {e}")
                    last = e
                    if i < max_retries - 1:
                        time.sleep(base_delay * (2 ** i))
                        continue
            logger.debug("[shepherd] %s 失败: %s", getattr(fn, "__name__", "fn"), last)
            return None
        return wrapper
    return deco


# ───────── 高温/常温/低温 阈值（牧羊人温度计）─────────
# dir: +1 越高越热；-1 越高越冷
THRESHOLDS = {
    "up_count":      dict(name="上涨家数", unit="家", dir=1, hot=3000, warm=1500, hot_label="高温(可出手)", cold_label="低温(先防守)"),
    "down_count":    dict(name="下跌家数", unit="家", dir=-1, hot=1500, warm=3000, hot_label="低温(可出手)", cold_label="高温(先防守)"),
    "limit_up":      dict(name="涨停家数", unit="家", dir=1, hot=50, warm=20, hot_label="亢奋", cold_label="低迷"),
    "limit_down":    dict(name="跌停家数", unit="家", dir=-1, hot=5, warm=15, hot_label="安全", cold_label="恐慌(>30)"),
    "zt_prev_ret":   dict(name="昨日涨停表现", unit="%", dir=1, hot=3.0, warm=0.0, hot_label="炸裂", cold_label="吃面"),
    "red_ratio":     dict(name="红盘占比", unit="%", dir=1, hot=60.0, warm=45.0, hot_label="普涨", cold_label="普跌"),
    "connect_hl":    dict(name="连板高度", unit="板", dir=1, hot=6, warm=3, hot_label="高风险偏好", cold_label="冰点"),
    "zt_fail_ratio": dict(name="炸板率", unit="%", dir=-1, hot=30.0, warm=50.0, hot_label="封板稳", cold_label="分歧大"),
}


# ───────── 各数据源抓取（每个返回 dict 或 None）─────────
@_retry()
def _fetch_legu():
    """涨跌家数实时快照（乐股）。"""
    import akshare as ak
    df = ak.stock_market_activity_legu()
    if df is None or df.empty or "item" not in df.columns:
        return None
    out = {}
    def _val(name):
        sub = df[df["item"] == name]["value"]
        if sub.empty:
            return None
        return pd.to_numeric(sub.iloc[0], errors="coerce")
    for name, key in (("上涨", "up_count"), ("下跌", "down_count"),
                      ("涨停", "limit_up"), ("跌停", "limit_down"), ("横盘", "flat_count")):
        v = _val(name)
        if v is not None and pd.notna(v):
            out[key] = float(v)
    return out or None


@_retry()
def _fetch_zt_pool(date=None):
    """涨停池：涨停家数 / 连板高度 / 炸板不稳比例。"""
    import akshare as ak
    d = date or pd.Timestamp.now().strftime("%Y%m%d")
    df = ak.stock_zt_pool_em(date=d)
    if df is None or df.empty:
        return None
    out = {"limit_up": float(len(df))}
    if "连板数" in df.columns:
        hl = pd.to_numeric(df["连板数"], errors="coerce").max()
        if pd.notna(hl):
            out["connect_hl"] = float(hl)
    if "炸板次数" in df.columns:
        zb = pd.to_numeric(df["炸板次数"], errors="coerce").fillna(0)
        out["zt_fail_ratio"] = float((zb > 0).mean() * 100.0)
    return out


@_retry()
def _fetch_prev_pool(date=None):
    """昨日涨停表现：昨日涨停股今日平均涨跌幅(%)。"""
    import akshare as ak
    d = date or pd.Timestamp.now().strftime("%Y%m%d")
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


# 注：全A快照 stock_zh_a_spot_em 在沙箱/弱网下常被远程中断且逐日回测过慢，
# 涨跌/跌停/红盘占比改由乐股快照(legu)提供当日值；历史折线图仅含末日快照点。
# 用户真实环境（代理在线）spot_em 可用，如需补全历史涨跌家数折线，
# 可在 _fetch_shepherd_history 末日分支之外再按日补 spot（已留 _retry 容错）。


def get_shepherd_today():
    """实时快照：合并各源，返回 (dict, meta)。

    优先 legu(涨跌/涨停/跌停/红盘占比) + zt_pool(涨停/连板/炸板) + prev_pool(昨日涨停表现)，
    全部为轻量接口，沙箱/弱网可用。meta: {available:[...], unavailable:[(k,reason)]}。
    """
    meta = {"available": [], "unavailable": []}
    merged = {}

    # 并发预取三源（legu / zt_pool / prev_pool），用共享有界池 + 整批超时，
    # 避免顺序请求叠加延迟（每源一个网络往返），整体耗时≈最慢单源。
    from modules.fetch_parallel import fetch_many

    _tasks = [
        ("legu", _fetch_legu),
        ("zt_pool", _fetch_zt_pool),
        ("zt_prev_ret", _fetch_prev_pool),
    ]
    _results = fetch_many(_tasks, max_workers=3, timeout=12)

    # 1) legu 涨跌家数 + 涨停/跌停/红盘占比（快）
    try:
        legu = _results.get("legu")
        if legu:
            merged.update(legu)
            meta["available"].extend(legu.keys())
        else:
            meta["unavailable"].append(("legu", "乐股快照暂不可用"))
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        meta["unavailable"].append(("legu", f"失败:{e}"))

    # 2) 涨停池（连板高度 / 炸板率，并补涨停家数）
    try:
        zt = _results.get("zt_pool")
        if zt:
            for k, v in zt.items():
                if k not in merged:
                    merged[k] = v
                if k not in meta["available"]:
                    meta["available"].append(k)
        else:
            meta["unavailable"].append(("zt_pool", "涨停池暂不可用"))
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        meta["unavailable"].append(("zt_pool", f"失败:{e}"))

    # 3) 昨日涨停表现
    try:
        prev = _results.get("zt_prev_ret")
        if prev:
            merged.update(prev)
            meta["available"].extend(prev.keys())
        else:
            meta["unavailable"].append(("zt_prev_ret", "昨日涨停池暂不可用"))
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        meta["unavailable"].append(("zt_prev_ret", f"失败:{e}"))

    # 红盘占比若 legu 有 up/down 但无 red_ratio，补算
    if "red_ratio" not in merged and "up_count" in merged and "down_count" in merged:
        tot = merged["up_count"] + merged["down_count"]
        if tot > 0:
            merged["red_ratio"] = float(merged["up_count"] / tot * 100.0)
            meta["available"].append("red_ratio")

    return merged, meta


# ───────── 历史回测（折线图数据源）─────────
def _trading_days(n):
    import akshare as ak
    cal = ak.tool_trade_date_hist_sina()
    cal["trade_date"] = _pdate(cal["trade_date"])
    today = pd.Timestamp.now().normalize()
    dts = cal[cal["trade_date"] <= today]["trade_date"].sort_values().tail(n)
    return [d.strftime("%Y%m%d") for d in dts]


def _fetch_shepherd_history(n_days=60):
    """循环交易日历拉真实历史：涨停/连板/炸板 + 昨日涨停表现（东财涨停池/昨日涨停池）。

    末日额外补 legu 快照（上涨/下跌/跌停/红盘占比）作为最新点。
    返回 DataFrame：date + 各指标列。任何单日/单源失败仅跳过，不影响整体。
    注：逐日全A快照(stock_zh_a_spot_em)在弱网下易中断且过慢，历史涨跌家数折线
    仅含末日快照点；涨停/昨板/连板为完整 60 日真实序列。
    """
    dates = _trading_days(min(n_days, _MAX_HISTORY_DAYS))
    rows = []
    for i, d in enumerate(dates):
        rec = {"date": d}
        try:
            zt = _fetch_zt_pool(d)
            if zt:
                rec.update(zt)
        except Exception:  # noqa as e:
            logger.warning(f"[shepherd] 处理异常: {e}")
            pass
        try:
            prev = _fetch_prev_pool(d)
            if prev:
                rec.update(prev)
        except Exception:  # noqa as e:
            logger.warning(f"[shepherd] 处理异常: {e}")
            pass
        # 仅末日补 legu 快照（涨跌/跌停/红盘占比），避免逐日全A快照（重且沙箱不可用）
        if i == len(dates) - 1:
            try:
                legu = _fetch_legu()
                if legu:
                    for k in ("up_count", "down_count", "limit_down"):
                        if k in legu and k not in rec:
                            rec[k] = legu[k]
                    if "red_ratio" not in rec and "up_count" in legu and "down_count" in legu:
                        tot = legu["up_count"] + legu["down_count"]
                        if tot > 0:
                            rec["red_ratio"] = float(legu["up_count"] / tot * 100.0)
            except Exception:  # noqa as e:
                logger.warning(f"[shepherd] 处理异常: {e}")
                pass
        rows.append(rec)
        time.sleep(0.2)
    if not rows:
        return pd.DataFrame(columns=["date"])
    df = pd.DataFrame(rows)
    df["date"] = _pdate(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _read_history_csv(days=None):
    """读持久 CSV 长历史（2007 起，由 scripts/run_shepherd_reconstruct.py 生成）。

    :param days: 给定则只取尾部 days 行；None/0 返回全部。
    """
    try:
        if not os.path.exists(_HISTORY_FILE):
            return None
        df = pd.read_csv(_HISTORY_FILE)
        if df.empty:
            return None
        df["date"] = _pdate(df["date"])
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if days and days > 0 and len(df) > days:
            df = df.tail(days).reset_index(drop=True)
        return df
    except Exception as e:  # noqa
        logger.warning("[shepherd] 长历史 CSV 读取失败: %s", e)
        return None


def get_shepherd_history(days=60):
    """历史回测（TTL 缓存 1h）。

    - days >= 2000：读取持久 CSV 长历史（2007 起，由全 A 重构生成）；
    - 否则：优先实时涨停池回测（近 90 日内真实连板/炸板/昨板），失败降级读 CSV 尾部 days 行。
    """
    long_mode = days is not None and days >= 2000
    if long_mode:
        df = _read_history_csv(days)
        if df is not None and not df.empty:
            return df
        logger.warning("[shepherd] 长历史 CSV 不可用，返回空")
        return pd.DataFrame(columns=["date"])
    try:
        df = _cached(_HISTORY_TTL, f"shep_hist_{days}", lambda: _fetch_shepherd_history(days))
        if df is not None and not df.empty:
            return df
    except Exception as e:  # noqa
        logger.warning("[shepherd] 历史回测失败，尝试 CSV 降级: %s", e)
    df = _read_history_csv(days)
    if df is not None and not df.empty:
        return df
    return pd.DataFrame(columns=["date"])


def get_shepherd_indicators(days=60):
    """统一入口：返回 (df, meta)。

    df：历史宽表（date + 各指标列），用于折线图；末行即最新值，可用于卡片。
    meta：{available, unavailable, _cache_fallback}。
    """
    df = get_shepherd_history(days)
    meta = {"available": [], "unavailable": [], "_cache_fallback": False}
    if df is None or df.empty:
        meta["unavailable"] = [(k, "历史回测暂不可用（网络受限）") for k in THRESHOLDS]
        return df, meta
    cols = [c for c in THRESHOLDS if c in df.columns]
    meta["available"] = cols
    meta["unavailable"] = [(k, "该日数据源缺失") for k in THRESHOLDS if k not in df.columns]
    return df, meta


# ───────── 自定义日期范围回溯（带缺失提示与近期补算）─────────
def _trading_days_range(start, end):
    """获取 [start, end] 内的交易日历（日期列表）。"""
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        cal["trade_date"] = pd.to_datetime(cal["trade_date"])
        dts = cal[(cal["trade_date"] >= pd.to_datetime(start)) & (cal["trade_date"] <= pd.to_datetime(end))]["trade_date"]
        return dts.tolist()
    except Exception as e:  # noqa
        logger.warning("[shepherd] 交易日历获取失败: %s", e)
        return []


def get_shepherd_history_range(start_date, end_date, backfill=False):
    """按自定义日期范围读取牧羊人历史数据。

    - 优先从 data/shepherd_history.csv 长历史中过滤；
    - backfill=True 时，对范围内缺失的最近交易日（<=15天）尝试用 akshare zt_pool
      补全涨停/连板/炸板/昨日涨停表现字段；
    - 更早的历史缺失列保持 NaN，并在后续 meta 中标记为 unavailable。
    """
    start = pd.to_datetime(start_date).normalize()
    end = pd.to_datetime(end_date).normalize()
    today = pd.Timestamp.now().normalize()

    df = _read_history_csv(None)
    if df is not None and not df.empty:
        df = df[(df["date"] >= start) & (df["date"] <= end)].copy()

    if not backfill:
        return df if df is not None and not df.empty else pd.DataFrame(columns=["date"])

    # 获取缺失交易日
    requested_dates = _trading_days_range(start, end)
    if not requested_dates:
        return df if df is not None and not df.empty else pd.DataFrame(columns=["date"])

    if df is not None and not df.empty:
        existing = set(df["date"].dt.date)
        missing_dates = [d for d in requested_dates if d.date() not in existing]
    else:
        missing_dates = requested_dates

    # 仅对最近 <=15 天的缺失日补 zt 数据（东财涨停池只保留近期）
    recent_missing = [d for d in missing_dates if (today - d).days <= 15]
    if recent_missing:
        try:
            from modules.shepherd_reconstruct import fetch_zt_data_for_dates as _fetch_zt_range
            zt_df = _fetch_zt_range([d.strftime("%Y-%m-%d") for d in recent_missing])
            if zt_df is not None and not zt_df.empty:
                if df is None or df.empty:
                    df = zt_df
                else:
                    df = pd.concat([df, zt_df], ignore_index=True)
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        except Exception as e:  # noqa
            logger.warning("[shepherd] 补算近期缺失 zt 数据失败: %s", e)

    return df if df is not None and not df.empty else pd.DataFrame(columns=["date"])


def get_shepherd_indicators_range(start_date, end_date, backfill=False):
    """按自定义日期范围返回牧羊人指标 (df, meta)。

    meta 包含：
        date_range: (start, end)
        missing_columns: {col: reason} —— 所选时段内全为 NaN 的列
        unavailable: [(col, reason)] —— 数据源未覆盖的列
    """
    df = get_shepherd_history_range(start_date, end_date, backfill=backfill)
    meta = {
        "available": [],
        "unavailable": [],
        "_cache_fallback": False,
        "date_range": (str(start_date), str(end_date)),
        "missing_columns": {},
    }
    if df is None or df.empty or "date" not in df.columns:
        meta["unavailable"] = [(k, "所选日期范围暂无数据（未开始统计或数据源未覆盖）") for k in THRESHOLDS]
        return df, meta
    cols = [c for c in THRESHOLDS if c in df.columns]
    meta["available"] = cols
    for c in THRESHOLDS:
        if c not in df.columns:
            meta["unavailable"].append((c, "该时段数据源未覆盖，未开始统计"))
            continue
        non_na = pd.to_numeric(df[c], errors="coerce").notna().sum()
        if non_na == 0:
            meta["missing_columns"][c] = "所选时段内该指标全为缺失"
        elif non_na < len(df) * 0.5:
            meta["missing_columns"][c] = f"所选时段内该指标缺失 {len(df)-non_na} 个交易日"
    return df, meta


# ───────── 牧羊人温度计评分（0-100，与价格涨跌红绿无关）─────────
def shepherd_temperature(today: dict, hist_days: int = 60):
    """把今日快照映射为 0-100 综合「牧羊人温度」。

    规则：每个可用指标按其在近期历史中的分位打分（高=热 / 高=冷），均值。
    退化输入返回安全默认 50。

    :param hist_days: 分位计算所用的历史回看天数（默认 60；>=2000 取 2007 起长历史）。
                      调用方（如 MCP 工具）可透传用户指定的 days，使温度计真正反映
                      所请求的时间窗口，而非永远用固定 60 天。
    """
    if not today:
        return 50.0
    try:
        hist = get_shepherd_history(hist_days)
    except Exception:  # noqa as e:
        logger.warning(f"[shepherd] 处理异常: {e}")
        hist = None
    subs = []
    for k, th in THRESHOLDS.items():
        v = today.get(k)
        if v is None or not np.isfinite(v):
            continue
        if hist is not None and k in hist.columns and len(hist) >= 5:
            s = pd.to_numeric(hist[k], errors="coerce").dropna()
            if len(s) >= 5:
                # 今日值 today[k] 在历史时期分布中的经验分位（0-1）：
                # 历史中小于今日值的比例，避免旧实现误用「历史末值」打分导致 today 形同虚设。
                pct = float((s < v).mean())
                subs.append(pct * 100 if th["dir"] > 0 else (1 - pct) * 100)
                continue
        # 无历史时退化为阈值线性打分
        if th["dir"] > 0:
            score = 100.0 if v >= th["hot"] else (50.0 if v >= th["warm"] else 10.0)
        else:
            score = 100.0 if v <= th["hot"] else (50.0 if v <= th["warm"] else 10.0)
        subs.append(score)
    return float(np.mean(subs)) if subs else 50.0


if __name__ == "__main__":
    # 命令行入口（安全刷新，不覆盖长历史）：
    # - 若已有长历史 CSV（2007 起），只拉最近 live 数据（涨停/连板/炸板/昨板）并合并到尾部；
    # - 若无长历史，退化为旧行为（仅近期回测）。
    # 全量重建（2007 起）请用：python -m scripts.run_shepherd_reconstruct
    import json
    n = int(os.environ.get("SHEPHERD_DAYS", "30"))
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    long_df = _read_history_csv(None)  # 读现有长历史（可能为空）
    if long_df is not None and not long_df.empty and len(long_df) > 200:
        logger.info("[shepherd] 检测到长历史 %d 行（%s 起），仅刷新尾部实时数据", len(long_df), long_df["date"].min().date())
        live = _fetch_shepherd_history(n)  # 近期真实 zt_pool
        if live is not None and not live.empty:
            live_dates = {d.date() for d in live["date"]}
            tail_mask = long_df["date"].dt.date.isin(live_dates)
            df = long_df.copy()
            merge_cols = [c for c in ("limit_up", "limit_down", "connect_hl", "zt_fail_ratio", "zt_prev_ret")
                          if c in live.columns]
            if merge_cols:
                idx = {d.date(): i for i, d in enumerate(live["date"])}
                for i, row in df[tail_mask].iterrows():
                    li = idx.get(row["date"].date())
                    if li is not None:
                        for c in merge_cols:
                            if pd.notna(live[c].iloc[li]):
                                df.at[i, c] = live[c].iloc[li]
            df = df.sort_values("date").reset_index(drop=True)
        else:
            df = long_df
        logger.info("[shepherd] 刷新后 %d 行 → %s", len(df), _HISTORY_FILE)
    else:
        df = _fetch_shepherd_history(n)
        if df is None or df.empty:
            logger.warning("[shepherd] 未取到任何历史数据")
            df = pd.DataFrame(columns=["date"])
    if not df.empty:
        df.to_csv(_HISTORY_FILE, index=False, encoding="utf-8-sig")
        with open(os.path.join(os.path.dirname(_HISTORY_FILE), "shepherd_history.json"),
                  "w", encoding="utf-8") as f:
            _js = df.copy()
            _js["date"] = _js["date"].astype(str)
            json.dump(_js.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
        logger.info("[shepherd] 已保存 %d 行 → %s", len(df), _HISTORY_FILE)
        print(df.tail(3).to_string())
