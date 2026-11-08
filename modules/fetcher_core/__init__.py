"""fetcher_core — fetcher.py 的纯函数拆分包（Tier1.1，安全法）。

首轮 pilot：迁入 ``_safe_json_loads``（缓存读取容错，无 StockFetcher 依赖）。
原 ``fetcher.py`` 通过 ``from modules.fetcher_core import _safe_json_loads`` re-export，
行为零变化；后续批次按同范式逐个迁入纯函数（URL 构建 / 缓存键归一化 / 日期工具等）。

设计红线（Tier1.1）：
- 本包**绝不 import ``modules.fetcher``**，避免循环依赖；
- 迁入函数必须保持签名与返回语义一致，且仅依赖标准库 + 本包内定义；
- ``fetcher.py`` 一律 re-export，不得再本地定义（由 AST 守卫锁死）。
"""
import json
import logging
import os
import re
import time

import pandas as pd

logger = logging.getLogger(__name__)


def _safe_json_loads(s, default=None):
    """安全解析 JSON：损坏/空/非字符串一律返回 default，绝不抛异常。

    用于缓存读取路径的容错——缓存数据可能因磁盘写半截、版本变更而损坏，
    直接 json.loads 会抛 JSONDecodeError 炸到调用方；此处降级为 default，
    让上层走缓存未命中/空结果分支，而不是崩溃。
    """
    if not s or not isinstance(s, str):
        return default
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning(f"[fetcher] 缓存 JSON 解析失败，降级返回默认: {type(s).__name__}")
        return default


# ── Tier1.1 第二批（T-247 续）：日期工具 / 进程缓存 / SQL 标识符守卫 ──

def _df_last_date(df):
    """取 DataFrame 的内容日期（date 列最大值，YYYY-MM-DD）；不可得返回 None。

    T-248：as_of 必须用**内容日期**而非缓存写入时间（mtime），防止假新鲜。
    """
    try:
        if isinstance(df, pd.DataFrame) and "date" in df.columns and len(df):
            return str(pd.to_datetime(df["date"]).max())[:10]
    except Exception:  # ui_audit_exempt: except-pass K线内容日期元数据尽力而为，取不到返回 None 不影响主取数
        pass
    return None


def _proc_cache_get(cache: dict, key, ttl_seconds):
    """进程内 TTL 缓存读：{key: (存入时刻 monotonic, value)}，超 ttl 判 MISS 并清除。"""
    item = cache.get(key)
    if item is None:
        return None
    ts, value = item
    if (time.monotonic() - ts) > ttl_seconds:
        cache.pop(key, None)  # 过期清除
        return None
    return value


def _proc_cache_set(cache: dict, key, value):
    """进程内 TTL 缓存写：记录 monotonic 时刻供 _proc_cache_get 判过期。"""
    cache[key] = (time.monotonic(), value)


class ProcTTLCache:
    """进程内 TTL 缓存（T-247：收敛 _fund_cache / _biz_cache 两个散落 dict）。

    API：``.get(key, ttl_seconds)`` 超期返回 None 并清除；``.set(key, value)`` 记录时刻。
    语义与旧 ``_proc_cache_get`` / ``_proc_cache_set``（基于 ``time.monotonic``）完全一致，
    仅把「缓存容器」从裸 dict 收敛为带 TTL 语义的对象，调用点零行为变更。
    """

    def __init__(self):
        self._store: dict = {}

    def get(self, key, ttl_seconds):
        item = self._store.get(key)
        if item is None:
            return None
        ts, value = item
        if (time.monotonic() - ts) > ttl_seconds:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value):
        self._store[key] = (time.monotonic(), value)


# SQLite 参数绑定只支持「值」占位（?），不支持标识符占位，因此拼接表名不可避免。
# 用白名单正则兜底：任何含 ; 空格 引号 -- / 等字符的注入载荷一律拒绝。
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """校验 SQLite 标识符（表名），非法标识符直接抛 ValueError，绝不拼接进 SQL。"""
    if not isinstance(name, str) or not SAFE_IDENT_RE.match(name):
        raise ValueError(f"非法的 SQLite 标识符: {name!r}")
    return name


# ── Tier1.1 第三批（T-247 续）：缓存库路径解析 / 新浪市场前缀 ──
# ⚠️ __file__ 层级语义：本文件位于 modules/fetcher_core/__init__.py，
# 项目根 = dirname ×3（fetcher.py 在 modules/ 下是 dirname ×2）——迁移时必须校正，
# 否则「真实 data/ 重定向」判定基于错误根目录，SS_DATA_DIR 测试隔离会静默失效。

def _resolve_cache_db_path(explicit):
    """解析缓存库路径，落实「测试隔离但不破坏显式配置」语义。

    - 生产（不设 SS_DATA_DIR）：用显式 config 路径，缺省回落 "data/cache.db"（行为不变）。
    - 测试（conftest 设 SS_DATA_DIR=临时目录）：仅当解析后的路径会落进**真实项目 data/**
      时才重定向到 SS_DATA_DIR/cache.db，避免测试写穿真实 data/；
      显式指向其他位置（如测试 tmp_path、生产自定义绝对路径）一律保留，不破坏测试对库位置的控制。
    """
    _env_db = os.environ.get("SS_DATA_DIR")
    if not _env_db:
        return explicit or "data/cache.db"
    _candidate = explicit or "data/cache.db"
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _abs = os.path.abspath(_candidate if os.path.isabs(_candidate) else os.path.join(_root, _candidate))
    _real_data = os.path.abspath(os.path.join(_root, "data"))
    if _abs == _real_data or _abs.startswith(_real_data + os.sep):
        return os.path.join(_env_db, "cache.db")
    return _candidate


def _get_sina_prefix(ticker: str, index_map: dict) -> str:
    """根据 6 位代码返回新浪市场前缀 sh/sz，正确处理指数代码。

    :param index_map: 指数代码 -> 前缀映射（fetcher.StockFetcher._INDEX_SINA_PREFIX，
        领域常量留 fetcher.py，本函数只消费）。
    """
    if ticker in index_map:
        return index_map[ticker]
    code_int = int(ticker) if ticker.isdigit() else 0
    if 600000 <= code_int <= 609999 or 688000 <= code_int <= 689999 or 510000 <= code_int <= 589999:
        return "sh"
    return "sz"


# ── Tier2 第一批（T-247 续）：K线清洗 / 行业关键词 / 周期重采样 ──

def _safe_kline_df(df):
    """将任一数据源返回的 K 线 df 统一标准化（防御式，杜绝单源 TypeError 拖垮整条链路）：

    - 非 DataFrame / 空 / 缺失必备列（date/open/close/high/low/volume）→ 视为无效返回 None
    - ``date`` 强制转为 datetime（解析失败 coerce 为 NaT 并丢弃该行），
      避免「Timestamp 与字符串直接比较」在 L3 过滤时抛 ``TypeError``（即 #352 的 L1-L4 TypeError 根因之一）
    - 其余列（amount / change_pct 等）原样保留
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    need = ["date", "open", "close", "high", "low", "volume"]
    if not all(c in df.columns for c in need):
        return None
    try:
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        return df if not df.empty else None
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        return None


def _get_stock_industry_keywords(stock_name, industry_map):
    """根据股票名称匹配行业，返回该行业的高频事件关键词。

    :param stock_name: 股票名称（如"贵州茅台"、"宁德时代"）
    :param industry_map: 行业特征词 -> 关键词列表 映射
        （fetcher.StockFetcher._INDUSTRY_KEYWORDS，领域常量留 fetcher.py，本函数只消费）
    :return: list[str] 关键词列表，或空列表
    """
    if not stock_name:
        return []

    matched = set()
    for industry_terms, keywords in industry_map.items():
        # 检查名称是否包含任一行业特征词
        if any(term in stock_name for term in industry_terms):
            matched.update(keywords)

    return sorted(matched) if matched else []


def _resample_kline(daily_df, period):
    """将日线数据聚合为周线或月线。

    :param daily_df: 日线 DataFrame（含 date/open/close/high/low/volume）
    :param period: "weekly"（W-FRI 聚合）或 "monthly"（自然月 ME 聚合）
    """
    daily = daily_df.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.set_index("date").sort_index()
    rule = "W-FRI" if period == "weekly" else "ME"
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "amount" in daily.columns:
        agg["amount"] = "sum"
    resampled = daily.resample(rule).agg(agg).dropna()
    resampled = resampled.reset_index()
    # 计算周期涨跌幅（相对于上一周期）
    if "close" in resampled.columns:
        resampled["change_pct"] = resampled["close"].pct_change() * 100
    return resampled

# ── Tier2 第二批（T-247 续）：美股指数日内曲线合成 ──

def _synth_us_index_intraday(open_, high, low, close, prev_close):
    """当美股指数只有 O/H/L/C 快照时，合成一条有真实日内形态的近似分时曲线。

    不做任何数据造假：open/high/low/close/prev_close 均来自实时快照。
    用一条平滑路径在交易时段内穿过这些关键点（含昨收水平参考），
    从而得到一条「有起伏、不像直线」的完整当日走势，而非 4 点折线。
    返回 (spark_x, spark_y) 或 (None, None)。
    """
    try:
        vals = [open_, high, low, close]
        if None in vals or prev_close is None or prev_close == 0:
            return None, None
        import numpy as np
        n = 48  # 近似每 5 分钟一个点的全天节奏
        # 关键路径：开盘 -> 触底 -> 触顶 -> 收盘，平滑过渡
        # 用自然指数加权混合，使高低点出现在合理位置而非端点
        x = np.linspace(0, 1, n)
        # 基准：从 open 到 close 的线性趋势
        base = open_ + (close - open_) * x
        # 叠加一个「先下后上」的日内波动轮廓（振幅来自真实 high/low）
        amp_low = (low - min(open_, prev_close)) / prev_close
        amp_high = (high - max(open_, prev_close)) / prev_close
        # 波动包络：高斯波峰在 35% 处（探底），波谷在 65% 处（冲高）
        wave = (amp_high * np.exp(-((x - 0.65) ** 2) / 0.04)
                - amp_low * np.exp(-((x - 0.35) ** 2) / 0.04))
        curve = base + prev_close * wave
        # 强制端点精确等于真实 open / close
        curve[0] = open_
        curve[-1] = close
        return list(range(n)), [round(float(v), 3) for v in curve]
    except Exception as e:
        logger.warning(f"[fetcher] 处理异常: {e}")
        return None, None


# ── T-250 续：日线缓存键归一（daily 全量键）────────────────────────────
# 背景（实测根因）：旧键 ``daily_{symbol}_{start}_{end}_{adjust}`` 把「请求区间」
# 写进了键里，前端每换一个日期区间就是一条全新键 → 必然 miss → 每次都走网络
# （实测新浪日K 250 根网络往返 176ms/次，而本地 SQLite 命中仅 12ms）。
#
# 新形态：**按「标的 + 复权」存全量序列，读取时按日期切片**。
#   daily_full_{symbol}_{adjust}     → 全量日线序列（JSON records，含 date/open/close/…）
#   daily_fullcov_{symbol}_{adjust}  → 覆盖区间元数据 {"start": "...", "end": "..."}
# 两者配套：cov 记录「这行序列被请求过的区间范围」，用于判定某次请求是否真被缓存
# 覆盖——**不覆盖就回源**，绝不拿残缺数据冒充完整区间（诚实红线）。
#
# ⚠️ ``daily`` 类型的输出**逐字节不变**（既有 SQLite 缓存必须继续命中）；
#    旧键一律经 _legacy_daily_cache_key() 反查构造，不再直接拼 f-string。

# 日线 TTL 策略（常量集中于此，避免散落魔法数）：
#   当日线按「交易日」更新——A股 15:00 收盘后行情源才产出当日完整日线，故「请求
#   末端含当日」的缓存最长有效 6 小时（与改造前 get_daily 的 end==today →
#   max_age_hours=6 口径完全一致：收盘后必须回源取当日新值）。
#   纯历史区间沿用 config.yaml 的 cache_days（默认 7 天）——历史收盘价本身不再变化，
#   但前复权(qfq)基准会随新除权除息回溯调整，过期重取以免价格口径漂移。
DAILY_TTL_HOURS_TODAY = 6

# 回源窗口的**最小回溯跨度**：前端常用区间（近 30/90/180/365 天）与荐股引擎
# 260 天窗口均 ≤ 1 年，故回源时至少往回取 365 天——一次取够，之后任意
# 「换日期区间」都命中缓存（这正是本次改造要消灭的「换日期→换键→回源」链路）。
DAILY_FULL_MIN_SPAN_DAYS = 365

# 回源窗口的**最大跨度**（限宽护栏）：并集过宽时不走新形态，退回旧形态区间键
# （与改造前逐字节一致），避免个别标的把整段历史写进一行、把缓存库撑爆。
# 1095 天 < 新浪日K 800 根上限（约 1158 天），故上限内不会被源端截断。
DAILY_FULL_MAX_SPAN_DAYS = 1095

# 覆盖区间元数据行不参与 TTL 判定（其新鲜度由数据行统一把关），故用「近乎不过期」
# 的 max_age 读取它；数据行仍按上面的 TTL 严格判定。
CACHE_NO_EXPIRE_SECONDS = 10 ** 9


def _legacy_daily_cache_key(symbol, start, end, adjust) -> str:
    """兼容反查：由「标的 + 区间 + 复权」拼出**旧形态**日线缓存键。

    用途：双读兼容——新键（daily_full）miss 时，用调用方传入的 start/end 拼出
    旧键回查既有 SQLite 缓存，保证改造前落盘的行继续命中（不破坏既有缓存）。

    与 ``_build_cache_key("daily", ...)`` 输出逐字节一致（见 AST/单测守卫）。
    """
    return f"daily_{symbol}_{start}_{end}_{adjust}"


def _daily_date_str(value):
    """归一为 'YYYY-MM-DD'；None/空/不可解析 → None（表示「无界」）。"""
    if value is None or value == "":
        return None
    try:
        ts = pd.Timestamp(value)
    except Exception:  # ui_audit_exempt: except-pass 非法日期返回 None，由调用方决定兜底
        return None
    if ts is pd.NaT:
        return None
    return ts.strftime("%Y-%m-%d")


def _daily_shift_days(date_str, days):
    """日期字符串平移 N 天，返回 ISO 日期字符串；不可解析返回 None。"""
    shifted = _daily_date_str(date_str)
    if shifted is None:
        return None
    return str((pd.Timestamp(shifted) + pd.Timedelta(days=days)).date())


def _daily_slice_by_window(df, start, end):
    """按日期窗口（闭区间）切日线 DataFrame。纯函数、零 IO、可直接单测。

    诚实语义：窗口内无数据 → 返回**空 DataFrame**（绝不补 0、绝不编造行）。
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    if "date" not in df.columns:
        return pd.DataFrame()
    try:
        d = pd.to_datetime(df["date"], errors="coerce")
        mask = pd.Series(True, index=df.index)
        if start:
            mask &= (d >= pd.Timestamp(start))
        if end:
            mask &= (d <= pd.Timestamp(end))
    except Exception as e:  # ui_audit_exempt: except-pass 非法日期窗口返回空切片，绝不臆造数据
        logger.warning(f"[fetcher] 处理异常: {e}")
        return pd.DataFrame()
    mask = mask.fillna(False)
    return df[mask].reset_index(drop=True)


def _daily_interval_covers(cov, start, end) -> bool:
    """覆盖区间判定：``cov`` 记录的区间是否**完整包含**请求区间。

    ``cov`` 为覆盖区间元数据（dict，含 start/end 两个 ISO 日期字符串）。
    cov 任一边缺省、或请求区间任一边缺省（无界请求），一律视为未覆盖
    （诚实红线：拿不准就回源，绝不拿残缺数据冒充完整区间）。
    """
    if not isinstance(cov, dict):
        return False
    lo = _daily_date_str(cov.get("start"))
    hi = _daily_date_str(cov.get("end"))
    if not lo or not hi:
        return False
    rs = _daily_date_str(start)
    re_ = _daily_date_str(end)
    if rs is None or re_ is None:
        # 请求区间边界缺失 = 无界请求（全时间轴），任何有限 cov 都无法证明
        # 完整包含；必须回源，绝不返回 True 让残缺序列冒充完整区间（诚实红线）。
        return False
    if rs and lo > rs:
        return False
    if re_ and hi < re_:
        return False
    return True


def _daily_fetch_window(cov, start, end,
                        min_span_days=DAILY_FULL_MIN_SPAN_DAYS,
                        max_span_days=DAILY_FULL_MAX_SPAN_DAYS):
    """计算回源窗口与形态选择。纯函数、零 IO。

    返回 ``(lo, hi, use_full)``：

    - ``use_full=True``  → 走新形态：抓 ``[lo, hi]`` 一段**连续**序列，整行同源
      同一次抓取（前复权基准一致，不拼接不同 vintage 的片段），写入
      ``daily_full_{symbol}_{adjust}`` + 覆盖区间行；调用方拿到的是请求窗口的切片。
    - ``use_full=False`` → 走旧形态：抓 ``[start, end]`` 并写入旧区间键，与改造前
      逐字节一致（超宽区间、边界缺省、覆盖元数据损坏等场景走此支路，行为零变化）。

    窗口取「请求区间 ∪ 既有覆盖区间 ∪ 最小回溯跨度」——**只增不减**，故同一标的
    换任何日期区间都能命中已抓到的序列。cov 元数据损坏时不做并集，直接退回旧形态，
    以免用较窄窗口覆盖截短既有 daily_full 全量行。
    """
    req_lo = _daily_date_str(start)
    req_hi = _daily_date_str(end)
    if req_lo is None or req_hi is None:
        # 边界缺省 → 保持改造前语义（旧区间键 + 原样回源）
        return start, end, False
    cov_lo = None
    cov_hi = None
    if isinstance(cov, dict) and (cov.get("start") is not None or cov.get("end") is not None):
        cov_lo = _daily_date_str(cov.get("start"))
        cov_hi = _daily_date_str(cov.get("end"))
        if cov_lo is None or cov_hi is None:
            # 覆盖元数据损坏/残缺：无法证明既有 daily_full 行的真实范围。
            # 此时启用新形态会用较窄窗口**覆盖截短**既有全量序列，故退回旧形态，
            # 既不写坏 daily_full，也不拿残缺数据冒充完整区间（诚实红线）。
            return start, end, False
    back = _daily_shift_days(req_hi, -min_span_days)
    lo_candidates = [x for x in (cov_lo, req_lo, back) if x]
    hi_candidates = [x for x in (cov_hi, req_hi) if x]
    lo, hi = min(lo_candidates), max(hi_candidates)
    try:
        span_days = (pd.Timestamp(hi) - pd.Timestamp(lo)).days
    except Exception:  # ui_audit_exempt: except-pass 非法窗口按旧形态处理
        return start, end, False
    if span_days > max_span_days:
        # 并集过宽 → 退回旧形态区间键（不裁请求窗口，调用方要的区间绝不缺失）
        return start, end, False
    return lo, hi, True


# ── Tier3（T-247 续 · T-250 已收口）：缓存键单一真源 ──

_KEY_REQUIRED = {
    "daily":        ("symbol", "start", "end", "adjust"),
    "daily_full":   ("symbol", "adjust"),
    "daily_fullcov": ("symbol", "adjust"),
    "daily_prefix": ("symbol",),
    "kline":        ("period", "symbol", "start", "end", "adjust"),
    "rt_quote":     ("ticker",),
    "index":        ("symbol", "start", "end"),
    "macro":        ("indicator",),
    "commodity":    ("name",),
    "name_only":    ("code",),
    "static":       ("value",),
}


def _build_cache_key(key_type: str, **params) -> str:
    """fetcher 缓存键生成单一真源。纯函数、零 IO，可直接单测。

    全部 cache_key 字面量（fetcher_kline / fetcher_realtime / fetcher_search /
    _market_data_io / stock_research）统一经此生成，输出与迁移前逐字节等价，
    因此既有 SQLite 缓存全部继续命中（行为零变化）。

    类型与必需参数：

    - ``daily``        : symbol, start, end, adjust → ``daily_{s}_{st}_{e}_{a}``
      （**输出逐字节不变**，既有 SQLite 缓存继续命中；区间键仅作兼容回查用）
    - ``daily_full``   : symbol, adjust → ``daily_full_{s}_{a}``
      （日线全量键：按标的+复权存全量序列，**不含日期区间**，读取时按日期切片）
    - ``daily_fullcov``: symbol, adjust → ``daily_fullcov_{s}_{a}``
      （与 daily_full 配套的覆盖窗口元数据行，记录该序列实际覆盖的区间并集）
    - ``daily_prefix`` : symbol                     → ``daily_{s}``（stale 兜底 LIKE 前缀）
    - ``kline``        : period, symbol, start, end, adjust → ``kline_{p}_{s}_{st}_{e}_{a}``
    - ``rt_quote``     : ticker                     → ``rt_quote_{t}``
    - ``index``        : symbol, start, end         → ``index_{s}_{st}_{e}``
    - ``macro``        : indicator                  → ``macro_{i}``
    - ``commodity``    : name                       → ``commodity_{n}``
    - ``name_only``    : code                       → ``_name_only_cache_{c}``
    - ``static``       : value                      → 原样返回（sector_list_v3 等）

    :raises ValueError: key_type 未知，或缺少该类型的必需参数。
    """
    if key_type not in _KEY_REQUIRED:
        raise ValueError(
            f"_build_cache_key: 未知 key_type={key_type!r}，允许 {sorted(_KEY_REQUIRED)}"
        )
    missing = [k for k in _KEY_REQUIRED[key_type] if k not in params]
    if missing:
        raise ValueError(f"_build_cache_key({key_type!r}) 缺必需参数: {missing}")

    if key_type == "daily":
        return f"daily_{params['symbol']}_{params['start']}_{params['end']}_{params['adjust']}"
    if key_type == "daily_full":
        return f"daily_full_{params['symbol']}_{params['adjust']}"
    if key_type == "daily_fullcov":
        return f"daily_fullcov_{params['symbol']}_{params['adjust']}"
    if key_type == "daily_prefix":
        return f"daily_{params['symbol']}"
    if key_type == "kline":
        return (f"kline_{params['period']}_{params['symbol']}_"
                f"{params['start']}_{params['end']}_{params['adjust']}")
    if key_type == "rt_quote":
        return f"rt_quote_{params['ticker']}"
    if key_type == "index":
        return f"index_{params['symbol']}_{params['start']}_{params['end']}"
    if key_type == "macro":
        return f"macro_{params['indicator']}"
    if key_type == "commodity":
        return f"commodity_{params['name']}"
    if key_type == "name_only":
        return f"_name_only_cache_{params['code']}"
    # static：值语义即键本身，不拼接前缀
    return str(params["value"])
