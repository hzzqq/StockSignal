"""modules/cache_warmer.py — 日线缓存预热核心（T-250，缓存加固 B）。

背景（docs/data_cache_hardening.md 第2步）：荐股生成时才发现取不到 → 拿旧缓存
兜底（T-248 已诚实标注）不如收盘后闲时充分重试。预热把「生成时才发现」变
「15:30 后闲时先拉满」，容忍窗口从秒级放大到小时级；荐股基本全缓存命中（也快）。

键一致性铁律：预热必须以**与荐股引擎逐字节相同的参数**调用 get_daily
（start=260 天前、end=今天、adjust="qfq"）——cache_key 由参数拼接，参数不同
＝写了引擎读不到的键＝白拉。键格式归一化（滚动窗口进键导致跨日 miss 的根治）
另案随 fetcher_core 重构评估（WorkBuddy Tier1.x 在做结构性迁移，本模块先走
「预热端复刻调用方键参数」过渡路线，每日 15:30 重预热即可覆盖当日引擎调用）。

诚实语义：
- 逐只结果如实计数（warmed/failed），绝不谎报全绿；
- 整体硬超时（timeout 秒），到点如实报告「停在第几只」，绝不静默截断；
- cache.db 本身即检查点：TTL 内命中自动跳过，重跑天然续传；
- 预热宇宙 = get_all_codes(limit)（覆盖荐股 200 + 余量）；自选股/指数维度后续按需扩。
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _engine_params() -> tuple[str, str, str]:
    """与 recommend_engine._fetch_one 逐字节一致的取数参数（键一致性铁律）。"""
    now = datetime.now()
    start = (now - timedelta(days=260)).strftime("%Y-%m-%d")
    return start, now.strftime("%Y-%m-%d"), "qfq"


def warm_universe(limit: int = 400, max_workers: int = 6, timeout: float = 900.0,
                  progress=None, fetch=None, get_codes=None) -> dict:
    """预热日线缓存：候选池逐只按引擎同参拉取，TTL 内命中自动跳过。

    fetch/get_codes 为测试注入点（默认 StockFetcher）。
    返回 {"ok", "warmed", "failed", "failed_codes", "total", "elapsed_s",
          "stopped_early", "reason"}——全部如实，不编造。
    """
    t0 = time.time()
    out = {"ok": False, "warmed": 0, "failed": 0, "failed_codes": [],
           "total": 0, "elapsed_s": 0.0, "stopped_early": False, "reason": ""}
    if os.environ.get("SS_CACHE_WARM", "1") == "0":
        out["reason"] = "SS_CACHE_WARM=0，预热关闭"
        out["ok"] = True
        return out
    try:
        if fetch is None or get_codes is None:
            from modules.fetcher import StockFetcher

            _f = StockFetcher()
            fetch = fetch or _f.get_daily
            get_codes = get_codes or _f.get_all_codes
        codes = list(get_codes(limit=limit) or [])
    except Exception as e:  # noqa: BLE001 - 预热不可用如实上报，绝不拖垮调度
        out["reason"] = f"预热初始化失败: {type(e).__name__}: {e}"
        out["elapsed_s"] = round(time.time() - t0, 1)
        return out

    start, end, adjust = _engine_params()
    out["total"] = len(codes)
    for i, code in enumerate(codes, 1):
        if time.time() - t0 > timeout:
            out["stopped_early"] = True
            out["reason"] = f"硬超时 {timeout}s，停在第 {i}/{len(codes)} 只（cache.db 即检查点，重跑续传）"
            break
        try:
            df = fetch(code, start=start, end=end, adjust=adjust)
            if df is None or (hasattr(df, "empty") and df.empty):
                out["failed"] += 1
                out["failed_codes"].append(code)
            else:
                out["warmed"] += 1
        except Exception as e:  # noqa: BLE001 - 单只失败如实计数，继续预热
            out["failed"] += 1
            out["failed_codes"].append(code)
            logger.info("[cache_warmer] %s 预热失败: %s", code, e)
        if callable(progress):
            try:
                progress(i, len(codes))
            except Exception:  # noqa: BLE001
                pass
    out["ok"] = (not out["stopped_early"]) or out["warmed"] > 0
    out["elapsed_s"] = round(time.time() - t0, 1)
    logger.info("[cache_warmer] 预热完成 warmed=%s failed=%s total=%s %.1fs%s",
                out["warmed"], out["failed"], out["total"], out["elapsed_s"],
                "（提前停止）" if out["stopped_early"] else "")
    return out
