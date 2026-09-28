# -*- coding: utf-8 -*-
"""
modules/em_snapshot.py — 东方财富全市场 A 股快照直连薄层（T-177）。

为什么绕开 akshare：
    akshare ``stock_zh_a_spot_em`` 硬编码 ``82.push2.eastmoney.com`` 子域，
    本机网络环境（2026-09-27 实测矩阵，E:/tmp/t177_matrix.json）下该子域
    恒 RemoteDisconnected，而主域 ``push2.eastmoney.com`` 同路径 0.2s 正常——
    实时强势榜 / 市场驱动力共 3 个调用点全部取数失败。本薄层直连主域，
    产出与 akshare 同款中文列 DataFrame，下游零改动。

约定（务必遵守）：
    1. 诚实降级：全部失败返回 None，绝不返回空 DataFrame 假装成功；
    2. 重试有界：默认 3 次（attempt 间 sleep 递增），绝不无限循环；
    3. 请求规范：浏览器 UA + quote.eastmoney.com Referer（风控实测友好）；
    4. 纯直连，不 import akshare（故障隔离：akshare 挂不影响本层）。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# 主域（不要用 82.push2 / push2delay 等子域——本机实测恒断连）
CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
# 沪深京 A 股全量板块过滤（深主板/创业板/沪主板/科创板/北交所）
FS_A = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f20,f21,f23"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
}

# f 字段 → akshare stock_zh_a_spot_em 同款中文列（下游 COL 候选表/降级逻辑依赖）
COLMAP = {
    "f12": "代码", "f14": "名称", "f2": "最新价", "f3": "涨跌幅", "f4": "涨跌额",
    "f5": "成交量", "f6": "成交额", "f7": "振幅", "f8": "换手率",
    "f9": "市盈率-动态", "f10": "量比", "f20": "总市值", "f21": "流通市值",
    "f23": "市净率",
}
_TEXT_COLS = {"代码", "名称"}  # 其余全部转 numeric（'-' 占位 → NaN 诚实缺失）


def _http_get_raw(url: str, **kwargs):
    """requests 抽象层：测试可 monkeypatch，运行时零包装。"""
    return requests.get(url, **kwargs)


def _sleep(sec: float) -> None:
    time.sleep(sec)


# ── 风控防御状态（T-177 实测：clist 端点有频率风控，连续高频后断连 >2min；
#    冷却期内继续打请求只会火上浇油，故失败累积后主动静默降温）──
_COOLDOWN_SEC = 300.0     # 连续失败 ≥2 轮后冷却 5 分钟
_FAIL_STREAK_COOL = 2     # 触发冷却的连续失败轮数
_CACHE_TTL = 60.0         # 成功结果共享缓存（强势榜/市场驱动力等多调用方共用一次拉取）
_state = {"fail_streak": 0, "cool_until": 0.0, "df": None, "ts": 0.0}


def _reset_state_for_test() -> None:
    _state.update({"fail_streak": 0, "cool_until": 0.0, "df": None, "ts": 0.0})


def _to_num(v: Any) -> float:
    """'-' / None / 空串 → NaN；其余转 float。诚实缺失，不编 0。"""
    if v is None or v == "-" or v == "":
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def map_diff_to_df(diff: list[dict]) -> pd.DataFrame:
    """push2 data.diff 列表 → akshare 同款中文列 DataFrame。"""
    rows = []
    for item in diff or []:
        row = {}
        for f, col in COLMAP.items():
            raw = item.get(f)
            row[col] = raw if col in _TEXT_COLS else _to_num(raw)
        rows.append(row)
    df = pd.DataFrame(rows, columns=list(COLMAP.values()))
    for col in COLMAP.values():
        if col not in _TEXT_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _fetch_page(pn: int, pz: int, timeout: float = 10.0) -> dict:
    """拉单页，返回 data 字典（含 total / diff）。HTTP 非 200 或无 data 抛异常。

    ⚠️ URL 必须字符串手工拼接（fs 里的 ``+`` 保持字面）：requests 的 params
    dict 会把 ``+`` 编码成 ``%2B``，东财 WAF 对该形态直接断连（T-177 实测，
    akshare 的 params 方式同此死法）。
    """
    url = (f"{CLIST_URL}?pn={pn}&pz={pz}&po=1&np=1&fltt=2&invt=2"
           f"&fid=f12&fs={FS_A}&fields={FIELDS}")
    resp = _http_get_raw(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = (resp.json() or {}).get("data") or {}
    if not data:
        raise ValueError("empty data payload")
    return data


def fetch_a_spot_em(max_pages: int = 12, pz: int = 500,
                    retries: int = 3, timeout: float = 10.0) -> pd.DataFrame | None:
    """拉全市场 A 股快照（分页合并）。全部失败返回 None（诚实降级）。

    防风控四件套（T-177/T-178 实测 clist 端点有频率风控，触发阈值极低——
    连续 4 请求即封 >2min；单页 pz 超限会被截断为 600 行且 total 失真）：
      1. 共享缓存：成功结果 60s 内直接复用（强势榜/市场驱动力等共用一次拉取）；
      2. 冷却退避：连续失败 ≥2 轮进入 5 分钟冷却，期内不打请求（快速返回 None）；
      3. 请求强度最小化：pz=500 × 12 页 + 页间 0.25s 节流
         （akshare 60 页无间隔循环正是触封主因；pz=1000 实测被截断成 600 行）；
      4. 诚实降级：全失败返 None，绝不编造。
    """
    now = time.time()
    if now - _state["ts"] < _CACHE_TTL and _state["df"] is not None:
        return _state["df"].copy()
    if now < _state["cool_until"]:
        logger.debug("[em_snapshot] clist 风控冷却中（剩 %.0fs），跳过请求",
                     _state["cool_until"] - now)
        return None

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            rows: list[dict] = []
            total: int | None = None
            for pn in range(1, max_pages + 1):
                if pn > 1:
                    _sleep(0.25)  # 页间节流：连发即触风控
                data = _fetch_page(pn, pz, timeout=timeout)
                page_total = int(data.get("total") or 0)
                diff = data.get("diff") or []
                if total is None:
                    total = page_total
                rows.extend(diff)
                if not diff or pn * pz >= total:
                    break
            if rows:
                df = map_diff_to_df(rows)
                _state.update({"fail_streak": 0, "df": df, "ts": now})
                logger.info("[em_snapshot] 全市场快照 %d 只（total=%s, %d 页）",
                            len(df), total, (len(rows) + pz - 1) // pz)
                return df
            last_err = ValueError(f"no rows (total={total})")
        except Exception as e:  # noqa: BLE001 - 网络层一切失败统一重试
            last_err = e
            logger.debug("[em_snapshot] 第 %d 次尝试失败: %s", attempt + 1, e)
        if attempt < retries - 1:
            _sleep(1.0 + attempt)

    _state["fail_streak"] += 1
    if _state["fail_streak"] >= _FAIL_STREAK_COOL:
        _state["cool_until"] = time.time() + _COOLDOWN_SEC
        logger.warning("[em_snapshot] 连续 %d 轮失败，进入 %.0fs 风控冷却: %s",
                       _state["fail_streak"], _COOLDOWN_SEC, last_err)
    return None
