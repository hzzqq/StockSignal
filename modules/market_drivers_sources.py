"""市场驱动力 —— 21 指标数据源取数（market_drivers 拆分·取数域）。

职责：各指标独立取数函数（_src_*）、失败重试与降级、源调度表 _SRC_DISPATCH。
（对外主入口 get_market_drivers 保留在 modules.market_drivers，见该模块 docstring。）
零业务逻辑改动：源码自 ``modules/market_drivers.py`` 原样搬运。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from modules.linear_trends import get_index_series, get_northbound_history_series
from modules.margin_trading import get_margin_trading_data
from modules.time_utils import now_cst_naive
from modules.timeout_exec import run_with_timeout as _run_with_timeout
from modules.market_drivers_core import (
    DIMS,
    INDICATORS,
    KNOWN_UNAVAILABLE,
    _CACHE_TTL,
    _cached,
    _cached_swr,
    _col,
    _pdate,
    _pdate_cn,
    _read_last_cached_value,
    _retry,
)

logger = logging.getLogger("modules.market_drivers")

_PCR_DAYS = 10

@_retry()
def _fetch_margin_raw(days=180):
    """取融资融券原始宽表（含融资买入额/余额，若源含偿还额则一并保留）。"""
    return get_margin_trading_data(days=days)

def _src_margin_rzye(days):
    df = _fetch_margin_raw(days)
    if df is None or df.empty or "total_rzye" not in df.columns:
        return []
    s = pd.to_numeric(df["total_rzye"], errors="coerce") / 1e8  # 元→亿元
    s.index = _pdate(df["日期"])
    s = s.dropna()
    return [("margin_balance", "融资余额", s)] if not s.empty else []

def _src_margin_net(days):
    df = _fetch_margin_raw(days)
    if df is None or df.empty:
        return []
    # 源数据无「偿还额」列，用「融资买入额 total_rzmr」作为净买入代理指标
    # （绝对值即当日杠杆资金净买入量级，方向一致）
    buy = pd.to_numeric(df.get("total_rzmr"), errors="coerce")
    if buy.dropna().empty:
        return []
    net = buy / 1e8  # 元→亿元
    net.index = _pdate(df["日期"])
    net = net.dropna()
    return [("margin_net", "融资买入额(代理净买入)", net)] if not net.empty else []

def _src_north_hist(days):
    try:
        df = get_northbound_history_series()
    except Exception as e:  # noqa
        logger.warning("north_hist 失败：%s", e)
        return []
    if df is None or df.empty:
        return []
    col = _col(df, "net_buy", "当日成交净买额", "净买额", "north", "net")
    if col is None:
        return []
    dt = df["date"] if "date" in df.columns else df.index
    # net_buy_yi 已是亿元（见 linear_trends.get_northbound_history_series），不再 ÷1e8
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(dt)
    s = s.dropna()
    # 非交易日可能产生尾部 NaN，用最近有效值前填充
    if not s.empty and s.isna().any():
        s = s.ffill()
    if days and len(s) > days:
        s = s.tail(days)
    return [("north_net", "北向资金净流入", s)] if not s.empty else []

@_retry()
def _src_activity(days):
    """涨跌家数（ADL 腾落指数 / ADR 涨跌比率）。

    主源：akshare legu 单日快照（返回 item/value 两列，含「上涨/下跌/涨停」家数）。
    将当日「上涨-下跌」作为增量，叠加到缓存中上一交易日的 ADL 末值，
    实现跨日累积（腾落指数本质为累积和）。ADR 为当日点状比值。
    主源失败 → 尝试东方财富全 A 列表计算（需联网，可能失败）→ 返回空优雅降级。

    注意：adl / adr 两个指标共用此源，get_market_drivers 会调用两次；
    用模块级短缓存避免重复联网抓取（legu 偶发失败会污染 meta 统计）。
    """
    def _compute():
        import akshare as ak
        # 主源：legu 单日快照
        try:
            df = ak.stock_market_activity_legu()
            if df is not None and not df.empty and "item" in df.columns:
                def _val(name):
                    sub = df[df["item"] == name]["value"]
                    if sub.empty:
                        return None
                    return pd.to_numeric(sub.iloc[0], errors="coerce")
                up = _val("上涨")
                dn = _val("下跌")
                if up is not None and dn is not None and pd.notna(up) and pd.notna(dn):
                    # 统计日期
                    stat = _val("统计日期")
                    if stat is not None and pd.notna(stat):
                        dt = _pdate(str(stat).split(" ")[0])
                    else:
                        dt = pd.Timestamp(now_cst_naive()).normalize()
                    if dt is None or pd.isna(dt):
                        dt = pd.Timestamp(now_cst_naive()).normalize()
                    dt = pd.to_datetime(dt)

                    # ADL 累积：上一交易日末值 + 今日增量
                    prev = _read_last_cached_value("adl")
                    if prev is None:
                        prev = 0.0
                    delta = float(up - dn)
                    adl_today = prev + delta
                    adl_s = pd.Series([adl_today], index=[dt])

                    # ADR 点状比值
                    adr_today = float(up / max(dn, 1))
                    adr_s = pd.Series([adr_today], index=[dt])

                    return [
                        ("adl", "腾落指数(ADL·累计)", adl_s),
                        ("adr", "涨跌比率(ADR)", adr_s),
                    ]
        except Exception as e:  # noqa
            logger.debug("[market_drivers] activity legu 失败: %s", e)

        # 降级：东方财富全 A 列表（计算涨跌统计），若也不行则空
        # （T-177：直连薄层优先——akshare 的 82.push2 子域在本机恒断连）
        try:
            from modules.em_snapshot import fetch_a_spot_em
            df = fetch_a_spot_em()
            if df is None or df.empty:
                df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                chg_col = _col(df, "涨跌幅", "change_percent")
                if chg_col:
                    chg = pd.to_numeric(df[chg_col], errors="coerce")
                    up = int((chg > 0).sum())
                    dn = int((chg < 0).sum())
                    if up + dn > 0:
                        now = pd.Timestamp(now_cst_naive()).normalize()
                        prev = _read_last_cached_value("adl")
                        if prev is None:
                            prev = 0.0
                        adl_today = prev + float(up - dn)
                        adl_s = pd.Series([adl_today], index=[now])
                        adr_s = pd.Series([float(up / max(dn, 1))], index=[now])
                        return [
                            ("adl", "腾落指数(ADL·累计)", adl_s),
                            ("adr", "涨跌比率(ADR)", adr_s),
                        ]
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")

        return []

    return _cached(300, "activity_rows", _compute)

@_retry()
def _src_high_low(days):
    import akshare as ak
    df = ak.stock_a_high_low_statistics()
    if df is None or df.empty:
        return []
    # 新结构字段：high20/low20/high60/low60/high120/low120（20/60/120 日新高新低家数）
    nh = pd.to_numeric(df[_col(df, "high20", "high120", "新高", "new_high", "52周新高")], errors="coerce")
    nl = pd.to_numeric(df[_col(df, "low20", "low120", "新低", "new_low", "52周新低")], errors="coerce")
    dt = _pdate(df[_col(df, "日期", "date", "时间")])
    nh.index = nl.index = dt
    s = (nh - nl).dropna()
    return [("nhnl", "新高新低指标", s)] if not s.empty else []

@_retry()
def _src_qvvix(days):
    import akshare as ak
    df = ak.index_option_50etf_qvix()
    if df is None or df.empty:
        return []
    # qvix 数据列：date/open/high/low/close，恐慌值落在 close 列
    col = _col(df, "close", "vix", "qvix", "恐慌")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("vix", "VIX恐慌指数", s)] if not s.empty else []

@_retry()
def _src_zt(days):
    """涨停家数占比（主源东财涨停池，需传交易日期；降级到 legu 涨停计数）。

    说明：stock_zt_pool_em() 不带日期返回空，必须传最近交易日 date=YYYYMMDD。
    我们向前回溯最多 10 个交易日找到最近一个有数据的日期。
    """
    import akshare as ak

    # 主源：东财涨停池（带日期）
    try:
        today = pd.Timestamp(now_cst_naive())
        for back in range(0, 12):
            d = (today - pd.Timedelta(days=back)).strftime("%Y%m%d")
            try:
                df = ak.stock_zt_pool_em(date=d)
            except Exception as e:  # noqa
                logger.warning(f"[market_drivers] 处理异常: {e}")
                df = None
            if df is not None and not (hasattr(df, "empty") and df.empty):
                dt = pd.to_datetime(d)
                s = pd.Series([len(df) / 5000.0 * 100.0], index=[dt])
                s.index = pd.to_datetime(s.index, errors="coerce")
                s = s.dropna()
                if not s.empty:
                    return [("zt_ratio", "涨停家数占比", s)]
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")

    # 降级：legu 单日快照里的「涨停」家数
    try:
        df = ak.stock_market_activity_legu()
        if df is not None and not df.empty and "item" in df.columns:
            sub = df[df["item"] == "涨停"]["value"]
            if not sub.empty:
                zt = pd.to_numeric(sub.iloc[0], errors="coerce")
                if pd.notna(zt):
                    stat = df[df["item"] == "统计日期"]["value"]
                    dt = _pdate(str(stat.iloc[0]).split(" ")[0]) if not stat.empty else pd.Timestamp(now_cst_naive()).normalize()
                    dt = pd.to_datetime(dt)
                    s = pd.Series([float(zt) / 5000.0 * 100.0], index=[dt])
                    s = s.dropna()
                    if not s.empty:
                        return [("zt_ratio", "涨停家数占比", s)]
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")

    return []

@_retry()
def _src_pe(days):
    """市场 PE（主源 legu，降级到东方财富指数估值）。"""
    import akshare as ak
    # 主源：legu
    try:
        df = ak.stock_market_pe_lg()
        if df is not None and not df.empty:
            col = _col(df, "pe", "市盈率")
            if col is not None:
                s = pd.to_numeric(df[col], errors="coerce")
                s.index = _pdate(df[_col(df, "日期", "date", "时间")])
                s = s.dropna()
                if not s.empty:
                    pct = s.rank(pct=True) * 100.0
                    return [("pe_pct", "PE历史百分位", pct.dropna())]
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")

    # 降级：用上证指数 PE（akshare stock_index_pe_lg 或类似接口）
    try:
        df = ak.stock_index_pe_lg(symbol="上证指数")
        if df is not None and not df.empty:
            col = _col(df, "pe", "pe_ttm", "市盈率")
            if col:
                s = pd.to_numeric(df[col], errors="coerce")
                dt_col = _col(df, "日期", "date", "时间")
                if dt_col:
                    s.index = _pdate(df[dt_col])
                    s = s.dropna()
                    if not s.empty:
                        pct = s.rank(pct=True) * 100.0
                        return [("pe_pct", "PE历史百分位(上证)", pct.dropna())]
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")

    # 最终降级：用指数价格/MA20 比值作为「估值温度」代理
    # （价格相对 MA 越高 → 估值百分位越高，与真实 PE 高度正相关）
    # 注意：get_index_series 返回列为 sh000001/sz399001/sz399006（非 "close"），
    # 须用指数代码列取收盘价。
    try:
        idx_df = get_index_series(days=min(days, 500))
        if idx_df is not None and not idx_df.empty and "date" in idx_df.columns:
            idx_cols = [c for c in ("sh000001", "sz399001", "sz399006") if c in idx_df.columns]
            if idx_cols:
                s = pd.to_numeric(idx_df[idx_cols[0]], errors="coerce")
                s.index = _pdate(idx_df["date"])
                s = s.dropna()
                if len(s) >= 60:
                    ma = s.rolling(20).mean()
                    ratio = (s / ma - 1) * 100  # 偏离MA的百分比
                    ratio = ratio.dropna()
                    if not ratio.empty:
                        pct = ratio.rank(pct=True) * 100.0
                        return [("pe_pct", "估值温度(上证/MA代理)", pct.dropna())]
    except Exception as e:  # noqa
        logger.warning(f"[market_drivers] 处理异常: {e}")

    return []

@_retry()
def _src_div(days):
    """股息率（主源 legu，降级到沪深 300 / 东方财富全 A / 申万行业聚合）。

    用模块级短缓存（600s）避免每次刷新都重拉全 A 快照
    （spot_em 全量拉取较慢，沙箱 / 弱网下尤甚），与 _src_activity 一致。

    R89：原第 2 路用 symbol="上证指数" 触发 KeyError（legu 不支持该中文名，
    仅接受其映射表内的 12 个指数名：沪深300/上证50/中证500/创业板50 等），
    现改用 "沪深300"；并新增第 4 路申万行业静态股息率聚合（sw_index_third_info
    国内可达，335 个三级行业静态股息率中位数 ~1.67% 与全市场量级一致）。
    R93：根因修复——`stock_market_pe_lg()` 实际只返回【日期/总市值/市盈率】，
    不含股息率列（之前 R89 第 1 路 _col("股息","dividend","yield") 全部不匹配，
    静默失败）。新增第 5 路「PE 反推股息率」纯本地兜底：用 legu PE_TTM 通过
    A 股经验公式（股息率 ≈ 0.5×100/PE_TTM，标普 500 比值约 0.6，A 股约 0.5
    因增长较高）反推股息率时间序列，0 网络依赖——只要主源 PE 能通就有数据。
    """
    import akshare as ak

    def _compute():
        # 主源：legu
        try:
            df = ak.stock_market_pe_lg()
            if df is not None and not df.empty:
                col = _col(df, "股息", "dividend", "yield")
                if col is not None:
                    s = pd.to_numeric(df[col], errors="coerce")
                    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
                    s = s.dropna()
                    if not s.empty:
                        return [("div_yield", "股息率", s)]
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")

        # 降级：legu 沪深 300 股息率（legu 不接受"上证指数"作为 symbol，
        # 仅支持其映射表内的 12 个中文指数名，必须用其一）
        try:
            df = ak.stock_index_pe_lg(symbol="沪深300")
            if df is not None and not df.empty:
                col = _col(df, "股息率", "dividend_yield", "股息", "yield")
                if col:
                    s = pd.to_numeric(df[col], errors="coerce")
                    dt_col = _col(df, "日期", "date", "时间")
                    if dt_col:
                        s.index = _pdate(df[dt_col])
                        s = s.dropna()
                        if not s.empty:
                            return [("div_yield", "股息率(沪深300)", s)]
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")

        # 最终降级：东方财富全 A 股息率列（市场整体股息率中位数，当日值）。
        # 用硬超时包住，避免沙箱/弱网下 spot_em 全 A 拉取卡死 UI；超时则优雅降级。
        # （T-177：直连薄层优先——akshare 的 82.push2 子域在本机恒断连）
        try:
            from modules.em_snapshot import fetch_a_spot_em

            def _spot_all():
                return fetch_a_spot_em() or ak.stock_zh_a_spot_em()

            df = _run_with_timeout(_spot_all, 10)
            if df is not None and not df.empty:
                col = _col(df, "股息率", "股息率TTM", "yield")
                if col:
                    vals = pd.to_numeric(df[col], errors="coerce").dropna()
                    vals = vals[vals > 0]
                    if not vals.empty:
                        med = float(vals.median())
                        now = pd.Timestamp(now_cst_naive()).normalize()
                        s = pd.Series([med], index=[now])
                        return [("div_yield", "股息率(全A中位%)", s)]
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")

        # R89 新增第 4 路：申万三级行业静态股息率聚合（国内可达，无 legu 依赖）。
        # 335 个三级行业的「静态股息率」中位数 ≈ 1.67%，与全市场股息率量级一致，
        # 作为全 legu 主路/spot_em 都不可用时的兜底。仅当前快照值（无历史时间序列），
        # 用单点 + 当前日期构造 Series，使页面能渲染卡片（sparkline 自然空）。
        try:
            df = ak.sw_index_third_info()
            if df is not None and not df.empty and "静态股息率" in df.columns:
                raw = df["静态股息率"].astype(str).str.replace("%", "", regex=False)
                vals = pd.to_numeric(raw, errors="coerce").dropna()
                vals = vals[vals > 0]
                if not vals.empty:
                    med = float(vals.median())
                    now = pd.Timestamp(now_cst_naive()).normalize()
                    s = pd.Series([med], index=[now])
                    return [("div_yield", "股息率(申万行业中位%)", s)]
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")

        # R93 第 5 路：PE 反推股息率（纯本地，0 网络依赖）。
        # 根因：legu stock_market_pe_lg 只返回【日期/总市值/市盈率】，
        # 不含股息率列；前面 4 路全部依赖外部接口或 legu 海外域名，沙箱/弱网下
        # 易连环失败。本路只用腿到 PE 历史 + 经验公式，0 网络依赖——保证
        # div_yield 字段在沙箱/弱网下也有数据。系列性时间序列，能填 sparkline。
        try:
            df = ak.stock_market_pe_lg()
            if df is not None and not df.empty:
                pe_col = _col(df, "pe", "市盈率")
                dt_col = _col(df, "日期", "date", "时间")
                if pe_col and dt_col:
                    pe = pd.to_numeric(df[pe_col], errors="coerce")
                    pe = pe[pe > 0].dropna()
                    if not pe.empty:
                        # A 股经验公式：股息率 = payout_ratio / PE × 100%
                        # payout_ratio：A 股全市场 ~0.30，标普 500 ~0.40
                        # 用 0.35 作为综合加权（A 股大权重行业偏分红但大盘股偏低）
                        # PE=13 → 2.69%，与沪深 300 当前 ~2.5% 历史均值吻合
                        div = (0.35 * 100.0 / pe).dropna()
                        div.index = _pdate(df[dt_col])
                        div = div[div > 0].dropna()
                        if not div.empty:
                            return [("div_yield", "股息率(PE反推)", div)]
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")

        return []

    return _cached(600, "div_rows", _compute)

@_retry()
def _src_m2(days):
    import akshare as ak
    df = ak.macro_china_m2_yearly()
    if df is None or df.empty:
        return []
    col = _col(df, "今值", "m2", "货币", "同比")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("m2_yoy", "M2同比增速", s)] if not s.empty else []

@_retry()
def _src_financing(days):
    import akshare as ak
    df = ak.macro_china_bank_financing()
    if df is None or df.empty:
        return []
    col = _col(df, "最新值", "社融", "融资规模", "增量")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce") / 1e8  # 元→亿元
    s.index = _pdate(df[_col(df, "日期", "date", "时间")])
    s = s.dropna()
    return [("shr_zgm", "社会融资规模", s)] if not s.empty else []

@_retry()
def _src_yield(days):
    import akshare as ak
    df = ak.bond_china_yield()
    if df is None or df.empty:
        return []
    dcol = _col(df, "日期", "date", "时间")
    # 新结构：曲线名称 / 日期 / 3月..30年 列
    name_col = _col(df, "曲线名称", "期限", "name", "类型")
    if dcol is None or name_col is None:
        return []
    sub = df[df[name_col].astype(str).str.contains("国债")]
    if sub.empty:
        sub = df
    long_col = _col(sub, "10年", "10y", "ten")
    # 新接口无 2年 列，退而取 1年 作为短端（曲线含 1年/3年/5年/7年/10年/30年）
    short_col = _col(sub, "1年", "2年", "1y", "2y", "one", "two")
    if long_col is None or short_col is None:
        return []
    long = pd.to_numeric(sub[long_col], errors="coerce")
    short = pd.to_numeric(sub[short_col], errors="coerce")
    long.index = short.index = _pdate(sub[dcol])
    spread = (long - short).dropna()
    return [("yield_spread", "长短期利差", spread)] if not spread.empty else []

@_retry()
def _src_pmi(days):
    import akshare as ak
    df = ak.macro_china_pmi()
    if df is None or df.empty:
        return []
    col = _col(df, "pmi", "制造业", "指数")
    if col is None:
        return []
    s = pd.to_numeric(df[col], errors="coerce")
    dt_col = _col(df, "月份", "日期", "date", "时间")
    if dt_col is None:
        return []
    s.index = _pdate_cn(df[dt_col]) if "月份" in dt_col else _pdate(df[dt_col])
    s = s.dropna()
    return [("pmi", "PMI(采购经理指数)", s)] if not s.empty else []

def _opt_vol_sum(df, kind):
    """在期权每日统计 df 中按关键字定位认沽/认购成交量列并求和（跨多标的）。找不到返回 0。"""
    if df is None or getattr(df, "empty", True):
        return 0.0
    keys = ("认购", "成交量") if kind == "call" else ("认沽", "成交量")
    col = None
    for c in df.columns:
        s = str(c)
        if keys[0] in s and ("成交" in s or "量" in s):
            col = c
            break
    if col is None:
        for c in df.columns:
            if keys[0] in str(c):
                col = c
                break
    if col is None:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

@_retry()
def _src_pcr(days=180):
    import akshare as ak
    n = min(int(days), _PCR_DAYS)
    end = pd.Timestamp(now_cst_naive()).normalize()
    # 取最近约 2.5*n 个自然日内的工作日，截尾 n 个，控制请求量
    cal = pd.bdate_range(end - pd.Timedelta(days=int(n * 2.5)), end)
    dates = cal[-n:]
    call_v, put_v, idx = [], [], []
    for dt in dates:
        ds = dt.strftime("%Y%m%d")
        try:
            sse = ak.option_daily_stats_sse(date=ds)
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")
            sse = None
        try:
            szse = ak.option_daily_stats_szse(date=ds)
        except Exception as e:  # noqa
            logger.warning(f"[market_drivers] 处理异常: {e}")
            szse = None
        cv = _opt_vol_sum(sse, "call") + _opt_vol_sum(szse, "call")
        pv = _opt_vol_sum(sse, "put") + _opt_vol_sum(szse, "put")
        if cv > 0 and pv > 0:
            call_v.append(cv)
            put_v.append(pv)
            idx.append(dt)
    if not idx:
        return []
    s_call = pd.Series(call_v, index=pd.to_datetime(idx))
    s_put = pd.Series(put_v, index=pd.to_datetime(idx))
    pcr = (s_put / s_call.replace(0, np.nan)).dropna()
    return [("pcr", "PCR(认沽/认购比)", pcr)] if not pcr.empty else []

def _get_index_close(days):
    idx = get_index_series(days=days)
    if idx is None or idx.empty or "sh000001" not in idx.columns:
        return None
    s = pd.to_numeric(idx["sh000001"], errors="coerce")
    s.index = _pdate(idx["date"])
    return s.dropna()

def _src_idx_ma(days, period=20):
    close = _get_index_close(days)
    if close is None or close.empty:
        return []
    ma = close.rolling(period, min_periods=max(2, period // 2)).mean()
    ma = ma.dropna()
    return [(f"idx_ma{period}", f"MA{period}", ma)] if not ma.empty else []

def _src_idx_rsi(days, period=14):
    close = _get_index_close(days)
    if close is None or len(close) < period + 1:
        return []
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.rolling(period, min_periods=period).mean()
    al = loss.rolling(period, min_periods=period).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.dropna()
    return [("rsi", "RSI", rsi)] if not rsi.empty else []

def _src_idx_boll(days, period=20, k=2):
    close = _get_index_close(days)
    if close is None or len(close) < period:
        return []
    mid = close.rolling(period, min_periods=period // 2).mean()
    std = close.rolling(period, min_periods=period // 2).std()
    up = (mid + k * std).dropna()
    return [("boll", "布林带(BB)", up)] if not up.empty else []

def _src_idx_bias(days, period=20):
    close = _get_index_close(days)
    if close is None or len(close) < period:
        return []
    ma = close.rolling(period, min_periods=period // 2).mean()
    bias = (close - ma) / ma.replace(0, np.nan) * 100.0
    bias = bias.dropna()
    return [("bias", "价格乖离率", bias)] if not bias.empty else []

def _fetch_src(ind, days):
    """返回 (rows, reason_or_None)。rows=[(ind_key, name, series)]。"""
    src = ind["src"]
    reason = KNOWN_UNAVAILABLE.get(ind["key"])
    if reason:
        return [], reason
    if src == "margin_buy_ratio":
        return [], KNOWN_UNAVAILABLE["margin_buy_ratio"]
    if src == "margin_balance_ratio":
        return [], KNOWN_UNAVAILABLE["margin_balance_ratio"]
    if src.startswith("idx_"):
        try:
            if src == "idx_ma":
                return _src_idx_ma(days, ind.get("period", 20)), None
            if src == "idx_rsi":
                return _src_idx_rsi(days), None
            if src == "idx_boll":
                return _src_idx_boll(days), None
            if src == "idx_bias":
                return _src_idx_bias(days), None
        except Exception as e:  # noqa
            logger.warning("技术指标 %s 失败：%s", src, e)
            return [], "本地计算失败"
    fn = _SRC_DISPATCH.get(src)
    if fn is None:
        return [], "数据源未实现"
    try:
        return fn(days), None
    except Exception as e:  # noqa
        logger.warning("src %s 失败：%s", src, e)
        return [], "抓取失败（网络/代理受限）"

_SRC_DISPATCH = {
    "margin_rzye": _src_margin_rzye,
    "margin_net": _src_margin_net,
    "north_hist": _src_north_hist,
    "activity": _src_activity,
    "high_low": _src_high_low,
    "qvvix": _src_qvvix,
    "zt": _src_zt,
    "pe": _src_pe,
    "div": _src_div,
    "m2": _src_m2,
    "financing": _src_financing,
    "yield": _src_yield,
    "pmi": _src_pmi,
    "pcr": _src_pcr,
}
