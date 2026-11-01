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


def fetch_notice_events(date_yyyymmdd: str, symbol: str = "重大事项",
                        ttl: float = 600.0) -> dict:
    """拉取指定日期的公告流并归一化。

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
    rows: list[dict] = []
    if df is not None and len(df) > 0:
        for _, r in df.iterrows():
            item = {}
            for cn, en in _COL_MAP.items():
                v = r.get(cn)
                item[en] = "" if v is None else str(v)
            rows.append(item)
    by_type: dict[str, int] = {}
    for it in rows:
        t = it.get("type") or "未知"
        by_type[t] = by_type.get(t, 0) + 1
    return {"available": True, "date": date_yyyymmdd, "symbol": symbol,
            "total": len(rows), "by_type": by_type, "rows": rows, "note": ""}
