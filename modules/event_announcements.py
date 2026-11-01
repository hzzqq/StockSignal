# -*- coding: utf-8 -*-
"""个股/全市场公告事件适配器（第三真实事件源·东方财富）。

定位：事件因子体系现有两路真实数据——P1 EV 信号池（``load_event_pool``）与
牧羊人市场广度（``event_compare``）。本模块补第三路：**交易所公告流**（东方财富
「公告大全」，经 akshare），把「公告事件密度/类型分布」作为市场级事件输入。

数据源（已核实 akshare 1.18.64 源码 ``akshare/stock_fundamental/stock_notice.py``，
非臆造）：
    ak.stock_notice_report(symbol=报告类型, date="YYYYMMDD")
    报告类型 ∈ {"全部","重大事项","财务报告","融资公告","风险提示","资产重组",
               "信息变更","持股变动"}
    返回列（源码 rename 映射核实）：代码 / 名称 / 公告标题 / 公告类型 / 公告日期 / 网址

诚实红线：
- 网络失败/解析失败 → ``available=False`` + 中文 note，**绝不编造公告**；
- 空结果（当日无该类公告）→ ``available=True, total=0``（空是真数据，不是错误）；
- 本模块禁止任何 random/synthetic 造数（受 no_synthetic AST 护栏约束）。
"""
from __future__ import annotations

import logging

from modules.cache_utils import cached_ttl

logger = logging.getLogger(__name__)

# 公告类型全集（akshare 源码 choice 枚举，2026-11-01 核实）
NOTICE_TYPES = ("全部", "重大事项", "财务报告", "融资公告", "风险提示",
                "资产重组", "信息变更", "持股变动")

# 归一化字段 ← akshare 中文列（源码核实）
_COL_MAP = {"代码": "code", "名称": "name", "公告标题": "title",
            "公告类型": "type", "公告日期": "date", "网址": "url"}


def _ak():
    """akshare 惰性获取（可测注入点：测试 monkeypatch 本函数）。"""
    import akshare
    return akshare


def _normalize_df(df) -> list[dict]:
    """akshare 公告帧 → 归一化 rows（缺列优雅降级为空串，不 KeyError）。"""
    rows: list[dict] = []
    if df is None or len(df) == 0:
        return rows
    for _, r in df.iterrows():
        item = {}
        for cn, en in _COL_MAP.items():
            v = r.get(cn)
            item[en] = "" if v is None else str(v)
        rows.append(item)
    return rows


def _summarize(rows: list[dict], **meta) -> dict:
    by_type: dict[str, int] = {}
    for it in rows:
        t = it.get("type") or "未知"
        by_type[t] = by_type.get(t, 0) + 1
    out = {"available": True, "total": len(rows), "by_type": by_type, "rows": rows, "note": ""}
    out.update(meta)
    return out


def fetch_notice_events(date_yyyymmdd: str, symbol: str = "重大事项",
                        ttl: float = 600.0) -> dict:
    """拉取指定日期的全市场公告流并归一化。

    :param date_yyyymmdd: 交易日 "YYYYMMDD"（非交易日东方财富通常返回空表，属真数据）
    :param symbol: 报告类型，见 NOTICE_TYPES；非法值回落 "重大事项" 并告警
    :param ttl: 缓存秒数（同 (date, symbol) 结果进程内复用）
    :return: dict(available, date, symbol, total, by_type, rows, note)
             rows 每条 {code,name,title,type,date,url}，缺失字段优雅降级为空串
    """
    if symbol not in NOTICE_TYPES:
        logger.warning("[event_announcements] 非法公告类型 %r，回落「重大事项」", symbol)
        symbol = "重大事项"
    key = f"evt_notice_{date_yyyymmdd}_{symbol}"
    try:
        return cached_ttl(ttl, key, lambda: _fetch_impl(date_yyyymmdd, symbol))
    except Exception as e:  # cached_ttl 自身故障兜底：直接拉一次，再失败才降级
        logger.warning("[event_announcements] 缓存层异常 %s，直连重试", e)
        try:
            return _fetch_impl(date_yyyymmdd, symbol)
        except Exception as e2:
            logger.warning("[event_announcements] 公告拉取失败: %s", e2)
            return {"available": False, "date": date_yyyymmdd, "symbol": symbol,
                    "total": 0, "by_type": {}, "rows": [],
                    "note": f"公告源不可用（{type(e2).__name__}），不编造数据"}


def _fetch_impl(date_yyyymmdd: str, symbol: str) -> dict:
    ak = _ak()
    df = ak.stock_notice_report(symbol=symbol, date=date_yyyymmdd)
    return _summarize(_normalize_df(df), date=date_yyyymmdd, symbol=symbol)


def fetch_individual_notices(security: str, symbol: str = "全部", days: int = 30,
                             ttl: float = 900.0) -> dict:
    """个股公告流（第三真实事件源的个股级能力，为荐股排雷二道闸 T-245 预置）。

    :param security: 股票代码（如 "300237"，akshare 源码 :param security: 股票代码）
    :param symbol: 报告类型，见 NOTICE_TYPES；非法值回落 "全部"
    :param days: 向前回看自然日数（begin=今天-days, end=今天，"YYYY-MM-DD" 直传）
    :param ttl: 缓存秒数
    :return: dict(available, security, symbol, begin, end, total, by_type, rows, note)
    """
    from datetime import date as _date, timedelta as _td
    if symbol not in NOTICE_TYPES:
        logger.warning("[event_announcements] 非法公告类型 %r，回落「全部」", symbol)
        symbol = "全部"
    security = (security or "").strip()
    if not security:
        return {"available": False, "security": security, "symbol": symbol,
                "begin": None, "end": None, "total": 0, "by_type": {}, "rows": [],
                "note": "未提供股票代码，不编造公告"}
    end = _date.today()
    begin = end - _td(days=days)
    key = f"evt_notice_ind_{security}_{symbol}_{days}"
    meta = dict(security=security, symbol=symbol,
                begin=begin.isoformat(), end=end.isoformat())

    def _impl():
        ak = _ak()
        df = ak.stock_individual_notice_report(
            security=security, symbol=symbol,
            begin_date=begin.isoformat(), end_date=end.isoformat())
        return _summarize(_normalize_df(df), **meta)

    try:
        return cached_ttl(ttl, key, _impl)
    except Exception as e:
        logger.warning("[event_announcements] 缓存层异常 %s，直连重试", e)
        try:
            return _impl()
        except Exception as e2:
            logger.warning("[event_announcements] 个股公告拉取失败: %s", e2)
            return {"available": False, **meta, "total": 0, "by_type": {},
                    "rows": [], "note": f"公告源不可用（{type(e2).__name__}），不编造数据"}
