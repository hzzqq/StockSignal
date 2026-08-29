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
  有效涨停        真实涨停（乐股，剔除 ST/未封死）               >50 / 20~50 / <20
  跌停家数        当日收盘跌停个股数（全A快照反算）              <5 / 5~15 / >15（>30 恐慌）
  昨日涨停表现    昨日涨停股今日平均涨跌幅(%)                    >3% / 0~3% / <0%（吃面）
  红盘占比        上涨/(上涨+下跌)×100%                         >60% / 45~60% / <45%
  连板高度        当日最高连板数（涨停池 max 连板数）            ≥6板 / 3~5板 / <3板
  炸板家数        炸板股池家数（东财 zbgc，摸板未封住）          <20 / 20~45 / >45
  炸板率          炸板/(涨停+炸板)×100%（杨哥口径：49/128=38%）  <30% / 30~50% / >50%（次日易V反）

v2 新增（源自视频《如何复盘非常重要》完整方法论，2026-08-29 接入）：
  中位数涨跌幅    剔除 ST 后全A 涨跌幅中位数（当日人均赚/亏）    >1% / 0~1% / <0%（亏钱效应）
  回头波>10%家数  (最高-收盘)/最高>10% 的家数（追高者回撤）      <20 / 20~50 / ≥30~50（次日易V反）
  连板家数(≥2板)  2 板及以上家数（赚钱效应梯队厚度）             >15 / 5~15 / <5（梯队断层）
  倒跌停家数      盘中最低价触及跌停价的家数（恐慌抛压）         <15 / 15~40 / >40
  平均封成比      涨停池 封板资金/成交额 均值（封板强度）        >1.0 / 0.4~1.0 / <0.4
  平均股价        全A 最新价均值（观察项，不参与温度计）          —
  全A成交额       新浪快照成交额合计(亿元)（观察项）             —

杨哥规律（信号文案内置）：
  - 炸板率 ≥50% → 次日大概率 V 反；
  - 回头波>10% 家数 ≥30/50 → 次日易 V 反（退潮修复特征）；
  - 两融余额持续增加 + 指数不创新高 = 顶背离 → 警惕见顶（页面端结合市场驱动力数据展示）。

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
    # ── 核心 8 项（v1 情绪温度计）──
    "up_count":      dict(name="上涨家数", unit="家", dir=1, hot=3000, warm=1500, hot_label="高温(可出手)", cold_label="低温(先防守)"),
    "down_count":    dict(name="下跌家数", unit="家", dir=-1, hot=1500, warm=3000, hot_label="低温(可出手)", cold_label="高温(先防守)"),
    "limit_up":      dict(name="涨停家数", unit="家", dir=1, hot=50, warm=20, hot_label="亢奋", cold_label="低迷"),
    "limit_down":    dict(name="跌停家数", unit="家", dir=-1, hot=5, warm=15, hot_label="安全", cold_label="恐慌(>30)"),
    "zt_prev_ret":   dict(name="昨日涨停表现", unit="%", dir=1, hot=3.0, warm=0.0, hot_label="炸裂", cold_label="吃面"),
    "red_ratio":     dict(name="红盘占比", unit="%", dir=1, hot=60.0, warm=45.0, hot_label="普涨", cold_label="普跌"),
    "connect_hl":    dict(name="连板高度", unit="板", dir=1, hot=6, warm=3, hot_label="高风险偏好", cold_label="冰点"),
    "zt_fail_ratio": dict(name="炸板率", unit="%", dir=-1, hot=30.0, warm=50.0, hot_label="封板稳", cold_label="分歧大(≥50%易V反)"),
    # ── 复盘方法论新增（视频《如何复盘非常重要》，2026-08-29）──
    "real_limit_up": dict(name="有效涨停(真实涨停)", unit="家", dir=1, hot=50, warm=20, hot_label="亢奋", cold_label="低迷"),
    "median_chg":    dict(name="中位数涨跌幅", unit="%", dir=1, hot=1.0, warm=0.0, hot_label="普涨修复", cold_label="亏钱效应"),
    "hb_wave10":     dict(name="回头波>10%家数", unit="家", dir=-1, hot=20, warm=50, hot_label="追高安全", cold_label="退潮(易V反)"),
    "zt_fail_count": dict(name="炸板家数", unit="家", dir=-1, hot=20, warm=45, hot_label="封板稳", cold_label="分歧大"),
    "connect_2b":    dict(name="连板家数(≥2板)", unit="家", dir=1, hot=15, warm=5, hot_label="梯队厚", cold_label="梯队断层"),
    "touch_down":    dict(name="倒跌停家数", unit="家", dir=-1, hot=15, warm=40, hot_label="安全", cold_label="恐慌抛压"),
    "fc_ratio":      dict(name="平均封成比", unit="", dir=1, hot=1.0, warm=0.4, hot_label="封板强", cold_label="封板弱"),
    # ── 观察项（dir=0，不参与温度计打分，仅展示）──
    "avg_price":     dict(name="平均股价", unit="元", dir=0, hot=0.0, warm=999.0, hot_label="观察", cold_label="观察"),
    "turnover_amt":  dict(name="全A成交额", unit="亿", dir=0, hot=0.0, warm=999.0, hot_label="观察", cold_label="观察"),
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
                      ("涨停", "limit_up"), ("跌停", "limit_down"), ("横盘", "flat_count"),
                      ("真实涨停", "real_limit_up"), ("真实跌停", "real_limit_down")):
        v = _val(name)
        if v is not None and pd.notna(v):
            out[key] = float(v)
    return out or None


def _compute_zt_pool_indicators(df):
    """从涨停池 DataFrame 计算涨停/连板/炸板/封成比指标（纯函数，可离线测试）。"""
    if df is None or df.empty:
        return None
    out = {"limit_up": float(len(df))}
    col_hl = _col(df, "连板数")
    if col_hl:
        boards = pd.to_numeric(df[col_hl], errors="coerce")
        hl = boards.max()
        if pd.notna(hl):
            out["connect_hl"] = float(hl)
        out["connect_2b"] = float((boards >= 2).sum())
    col_zb = _col(df, "炸板次数")
    if col_zb:
        zb = pd.to_numeric(df[col_zb], errors="coerce").fillna(0)
        out["zt_fail_ratio"] = float((zb > 0).mean() * 100.0)
    # 平均封成比：封板资金(元)/成交额(元) —— 杨哥用封成比代替手数涨停家数（有封单才有封成比）
    col_fc = _col(df, "封板资金")
    col_amt = _col(df, "成交额")
    if col_fc and col_amt and col_fc != col_amt:
        fc = pd.to_numeric(df[col_fc], errors="coerce")
        amt = pd.to_numeric(df[col_amt], errors="coerce")
        ok = fc.notna() & amt.notna() & (amt > 0)
        if ok.any():
            out["fc_ratio"] = float((fc[ok] / amt[ok]).mean())
    return out


@_retry()
def _fetch_zt_pool(date=None):
    """涨停池：涨停家数 / 连板高度 / 连板梯队 / 炸板不稳比例 / 平均封成比。"""
    import akshare as ak
    d = date or pd.Timestamp.now().strftime("%Y%m%d")
    df = ak.stock_zt_pool_em(date=d)
    return _compute_zt_pool_indicators(df)


@_retry(max_retries=1)
def _fetch_zbgc_pool(date=None):
    """炸板股池（东财 zbgc）：炸板家数（摸板未封住）。注：仅支持最近约 30 个交易日，
    更早日期为业务性报错（不重试），历史值由重构管线从个股 high/close 反算。"""
    import akshare as ak
    d = date or pd.Timestamp.now().strftime("%Y%m%d")
    df = ak.stock_zt_pool_zbgc_em(date=d)
    if df is None or df.empty:
        return None
    return {"zt_fail_count": float(len(df))}


def _limit_pct_for_code(code):
    """按代码前缀推断日涨跌停幅度（与 shepherd_reconstruct._board_limit_pct 同口径）。"""
    s = str(code).lower().strip()
    body = s[2:] if len(s) > 2 and s[:2] in ("sh", "sz", "bj") else s
    if s.startswith("bj"):
        return 0.30
    if body.startswith("68"):  # 科创板（仅沪市存在 68 段）
        return 0.20
    if body.startswith("30"):  # 创业板（仅深市存在 30 段）
        return 0.20
    return 0.10


def _compute_spot_indicators(df):
    """从新浪全 A 快照计算中位数/平均股价/回头波/倒跌停/成交额（纯函数，可离线测试）。

    口径对齐视频《如何复盘非常重要》：
    - 中位数涨跌幅：剔除 ST 后全体涨跌幅的中位数 —— 当日「所有人平均赚钱还是亏钱」；
    - 平均股价：全部 A 股最新价均值（杨哥：高价股多时会拉高，观察用）；
    - 回头波>10%：日内（最高-最新）/最高 > 10% —— 追高者的回撤幅度；
    - 倒跌停：盘中最低价触及按板块跌幅计算的跌停价（含封死，杨哥单列封死跌停）。
    """
    if df is None or df.empty:
        return None
    chg = pd.to_numeric(df.get("涨跌幅"), errors="coerce")
    price = pd.to_numeric(df.get("最新价"), errors="coerce")
    high = pd.to_numeric(df.get("最高"), errors="coerce")
    low = pd.to_numeric(df.get("最低"), errors="coerce")
    prev = pd.to_numeric(df.get("昨收"), errors="coerce")
    vol = pd.to_numeric(df.get("成交量"), errors="coerce")
    amt = pd.to_numeric(df.get("成交额"), errors="coerce")
    name = df.get("名称") if "名称" in df.columns else None
    active = vol.fillna(0) > 0
    out = {}
    # 中位数涨跌幅（剔除 ST，杨哥口径）
    m = active & chg.notna()
    if name is not None:
        m = m & (~name.astype(str).str.upper().str.contains("ST", na=False))
    if m.any():
        out["median_chg"] = float(chg[m].median())
    # 平均股价（全部 A 股，含 ST）
    ap = active & price.notna() & (price > 0)
    if ap.any():
        out["avg_price"] = float(price[ap].mean())
    # 回头波>10%家数
    hw_ok = active & high.notna() & (high > 0) & price.notna() & (price > 0) & (high >= price)
    if hw_ok.any():
        hw = (high[hw_ok] - price[hw_ok]) / high[hw_ok] * 100.0
        out["hb_wave10"] = float((hw > 10).sum())
    # 倒跌停家数（盘中触及跌停价）
    codes = df.get("代码") if "代码" in df.columns else None
    if codes is not None and prev is not None and low is not None:
        lp = codes.map(_limit_pct_for_code).astype(float)
        dl = prev * (1.0 - lp)
        td = active & prev.notna() & (prev > 0) & low.notna() & (low <= dl * 1.005)
        out["touch_down"] = float(td.sum())
    # 全A成交额（亿元）
    if amt is not None and amt.notna().any():
        out["turnover_amt"] = float(amt.sum() / 1e8)
    return out or None


@_retry(max_retries=1)
def _fetch_sina_spot():
    """新浪全 A 快照（约 70 页、~25s），TTL 缓存 10 分钟。"""
    import akshare as ak
    df = ak.stock_zh_a_spot()
    return _compute_spot_indicators(df)


def _get_spot_cached():
    """带 10 分钟 TTL 缓存 + 30s 硬超时的新浪快照指标。"""
    from modules.timeout_exec import run_with_timeout
    return run_with_timeout(lambda: _cached(600, "sina_spot_v2", _fetch_sina_spot), timeout=30)


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
        ("zbgc_pool", _fetch_zbgc_pool),
    ]
    _results = fetch_many(_tasks, max_workers=4, timeout=12)

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

    # 4) 炸板股池（炸板家数，杨哥复盘第 3 项）
    try:
        zbgc = _results.get("zbgc_pool")
        if zbgc:
            merged.update(zbgc)
            meta["available"].extend(zbgc.keys())
        else:
            meta["unavailable"].append(("zbgc_pool", "炸板股池暂不可用"))
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        meta["unavailable"].append(("zbgc_pool", f"失败:{e}"))

    # 5) 新浪全 A 快照（重，~25s，TTL 10 分钟缓存）：中位数/平均股价/回头波/倒跌停/成交额
    try:
        spot = _get_spot_cached()
        if spot:
            merged.update(spot)
            meta["available"].extend(spot.keys())
        else:
            meta["unavailable"].append(("sina_spot", "新浪全A快照暂不可用"))
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        meta["unavailable"].append(("sina_spot", f"失败:{e}"))

    # 炸板率修正为杨哥口径：炸板/(涨停+炸板)×100%（视频案例：49/(79+49)=38%）
    if "zt_fail_count" in merged and "limit_up" in merged:
        tot = merged["zt_fail_count"] + merged["limit_up"]
        if tot > 0:
            merged["zt_fail_ratio"] = float(merged["zt_fail_count"] / tot * 100.0)
            if "zt_fail_ratio" not in meta["available"]:
                meta["available"].append("zt_fail_ratio")

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
        except Exception as e:  # noqa
            logger.warning(f"[shepherd] 处理异常: {e}")
            pass
        try:
            zbgc = _fetch_zbgc_pool(d)
            if zbgc:
                rec.update(zbgc)
        except Exception as e:  # noqa
            logger.warning(f"[shepherd] 处理异常: {e}")
            pass
        # 炸板率修正为杨哥口径：炸板/(涨停+炸板)
        try:
            zc, lu = rec.get("zt_fail_count"), rec.get("limit_up")
            if zc is not None and lu is not None and (zc + lu) > 0:
                rec["zt_fail_ratio"] = float(zc / (zc + lu) * 100.0)
        except Exception as e:  # noqa
            logger.warning(f"[shepherd] 处理异常: {e}")
            pass
        try:
            prev = _fetch_prev_pool(d)
            if prev:
                rec.update(prev)
        except Exception as e:  # noqa
            logger.warning(f"[shepherd] 处理异常: {e}")
            pass
        # 仅末日补 legu 快照（涨跌/跌停/红盘占比/真实涨停），避免逐日全A快照（重且沙箱不可用）
        if i == len(dates) - 1:
            try:
                legu = _fetch_legu()
                if legu:
                    for k in ("up_count", "down_count", "limit_down", "real_limit_up", "real_limit_down"):
                        if k in legu and k not in rec:
                            rec[k] = legu[k]
                    if "red_ratio" not in rec and "up_count" in legu and "down_count" in legu:
                        tot = legu["up_count"] + legu["down_count"]
                        if tot > 0:
                            rec["red_ratio"] = float(legu["up_count"] / tot * 100.0)
            except Exception as e:  # noqa
                logger.warning(f"[shepherd] 处理异常: {e}")
                pass
            # 新浪快照（中位数/平均股价/回头波/倒跌停/成交额）——仅末日，TTL 缓存 10 分钟
            try:
                spot = _get_spot_cached()
                if spot:
                    for k in ("median_chg", "avg_price", "hb_wave10", "touch_down", "turnover_amt"):
                        if k in spot:
                            rec[k] = spot[k]
            except Exception as e:  # noqa
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
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        hist = None
    subs = []
    for k, th in THRESHOLDS.items():
        v = today.get(k)
        if v is None or not np.isfinite(v):
            continue
        if th.get("dir", 1) == 0:
            continue  # 观察项（平均股价/成交额）不参与温度打分
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


# ───────── 涨停板复盘辅助（视频第三表：每票板块/行业/最高板标的）─────────
def _zt_pool_detail_cached(date=None):
    """涨停池明细（含 所属行业/连板数/封板资金），TTL 缓存 10 分钟。"""
    d = (date or pd.Timestamp.now().strftime("%Y%m%d"))

    def _pull():
        import akshare as ak
        df = ak.stock_zt_pool_em(date=d)
        return df if (df is not None and not df.empty) else None

    return _cached(600, f"zt_detail_{d}", _pull)


def get_zt_industry_distribution(top=10, date=None):
    """今日涨停按行业分布（视频：每个涨停票炒什么板块都要了如指掌）。"""
    try:
        df = _zt_pool_detail_cached(date)
        col = _col(df, "所属行业") if df is not None else None
        if df is None or col is None:
            return None
        dist = df.groupby(col).size().sort_values(ascending=False).head(top)
        return pd.DataFrame({"行业": dist.index, "涨停家数": dist.values})
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        return None


def get_zt_top_board(date=None):
    """今日最高连板标的（视频：每天最高板代表市场情绪高度）。"""
    try:
        df = _zt_pool_detail_cached(date)
        col_hl = _col(df, "连板数") if df is not None else None
        if df is None or col_hl is None:
            return None
        boards = pd.to_numeric(df[col_hl], errors="coerce")
        if boards.notna().sum() == 0:
            return None
        row = df.loc[boards.idxmax()]
        return {
            "name": str(row.get("名称", "")),
            "code": str(row.get("代码", "")),
            "boards": int(boards.max()),
            "industry": str(row.get("所属行业", "")),
        }
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        return None


def get_zt_ladder(date=None, top_per_level=3):
    """连板梯队全景（视频：把每天最高标的票列出来，梯队厚度决定赚钱效应能否扩散）。

    返回 dict:
      levels  [{boards, count, stocks:[{name, code, industry, seal, amount}]}]  按连板数倒序
      total_connect  连板总家数（≥2 板）
      max_boards     最高连板数
      distribution   [(连板数, 家数)] 含首板，用于柱状图
      top            最高板标的（等同 get_zt_top_board）

    实盘意义：
      · 梯队「断层」（如 4 板 1 家、3 板 0 家、2 板 3 家）= 接力资金缺席，主线是「一只独苗」；
      · 梯队「厚」（≥15 家）= 赚钱效应线状扩散，接力顺畅；
      · 结合最高板高度判断情绪空间：高度打开 + 梯队厚 = 主升确认。
    """
    out = dict(levels=[], total_connect=0, max_boards=0, distribution=[], top=None)
    try:
        df = _zt_pool_detail_cached(date)
        if df is None or df.empty:
            return out
        col_hl = _col(df, "连板数")
        if not col_hl:
            return out
        work = df.copy()
        work["_boards"] = pd.to_numeric(work[col_hl], errors="coerce").fillna(1).astype(int)
        col_name = _col(df, "名称")
        col_code = _col(df, "代码")
        col_ind = _col(df, "所属行业")
        col_seal = _col(df, "封板资金")
        col_amt = _col(df, "成交额")

        # 分布（含首板），供柱状图
        dist = work.groupby("_boards").size().sort_index(ascending=False)
        out["distribution"] = [(int(b), int(c)) for b, c in dist.items()]
        out["max_boards"] = int(work["_boards"].max())

        # 逐档（≥2 板）取代表股：优先封单大的
        for boards in sorted(work["_boards"].unique(), reverse=True):
            if boards < 2:
                continue
            grp = work[work["_boards"] == boards]
            if col_seal:
                grp = grp.assign(_seal=pd.to_numeric(grp[col_seal], errors="coerce").fillna(0))
                grp = grp.sort_values("_seal", ascending=False)
            stocks = []
            for _, r in grp.head(top_per_level).iterrows():
                stocks.append({
                    "name": str(r.get(col_name, "")) if col_name else "",
                    "code": str(r.get(col_code, "")) if col_code else "",
                    "industry": str(r.get(col_ind, "")) if col_ind else "",
                    "seal": (float(r.get(col_seal, 0) or 0) if col_seal else 0.0),
                    "amount": (float(r.get(col_amt, 0) or 0) if col_amt else 0.0),
                })
            out["levels"].append(dict(boards=int(boards), count=int(len(grp)), stocks=stocks))

        out["total_connect"] = int((work["_boards"] >= 2).sum())
        mx = work.loc[work["_boards"].idxmax()]
        out["top"] = {
            "name": str(mx.get(col_name, "")) if col_name else "",
            "code": str(mx.get(col_code, "")) if col_code else "",
            "boards": int(mx["_boards"]),
            "industry": str(mx.get(col_ind, "")) if col_ind else "",
        }
        return out
    except Exception as e:  # noqa
        logger.warning(f"[shepherd] 处理异常: {e}")
        return out


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
            merge_cols = [c for c in ("limit_up", "limit_down", "real_limit_up", "real_limit_down",
                                      "connect_hl", "connect_2b", "zt_fail_ratio", "zt_fail_count",
                                      "zt_prev_ret", "median_chg", "hb_wave10", "touch_down",
                                      "fc_ratio", "avg_price", "turnover_amt")
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
