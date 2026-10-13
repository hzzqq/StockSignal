# -*- coding: utf-8 -*-
"""
modules/source_metrics_persist.py — 数据源/缓存层指标长周期落盘与趋势汇总（T-273D）。

背景：SOURCE_METRICS（数据源成功率，T-249 前后）与 CACHE_METRICS（缓存层命中率，
T-272①）均为**进程内计数**，重启清零——「上周新浪挂了几天」这类问题无从回答。
本模块把快照按日落盘为 JSON（复用 data/health_observations 观测目录范式），
并提供近 N 日趋势汇总。

诚实语义：
- 进程内计数只反映**本进程自启动以来**的调用——落盘快照带 process_hint
  （sys.argv[0] basename），跨进程不汇总，趋势按「逐日快照拼接」口径如实呈现；
- 落盘失败只留痕返回 written=False，绝不影响主业务路径；
- 趋势汇总对坏文件/缺字段容错跳过，绝不编造缺失日的数据。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_OBS_SUBDIR = "health_observations"


def _obs_dir() -> Path:
    base = os.environ.get("SS_DATA_DIR") or str(_PROJECT_ROOT / "data")
    d = Path(base) / _OBS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path(day: str | None = None) -> Path:
    day = day or datetime.now().strftime("%Y-%m-%d")
    return _obs_dir() / f"source_metrics_{day}.json"


def snapshot_metrics_to_disk() -> dict:
    """把当前数据源/缓存层指标快照落盘为当日 JSON（幂等：同日覆盖）。

    :returns: {ok, path, note}——ok=False 时 note 说明原因（绝不静默）。
    """
    try:
        from modules._feed_io import get_cache_metrics, get_source_metrics
        src = get_source_metrics()
        cache = get_cache_metrics()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": None, "note": f"指标读取失败: {type(e).__name__}: {e}"}

    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "process_hint": Path(sys.argv[0] or "?").name,  # 仅本进程口径的诚实标注
        "source_metrics": src,
        "cache_metrics": cache,
    }
    p = _snapshot_path()
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
        return {"ok": True, "path": str(p),
                "note": f"快照已落盘（{len(src)} 源 / {len(cache)} 缓存层）"}
    except OSError as e:
        logger.warning("[metrics_persist] 快照落盘失败: %s", e)
        return {"ok": False, "path": str(p), "note": f"写盘失败: {e}"}


def _load_day(p: Path) -> dict | None:
    """读单日快照；损坏/缺字段返回 None（容错跳过，不编造）。"""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("date"):
            return d
    except Exception:  # noqa: BLE001
        pass
    return None


def metrics_trend(days: int = 7) -> dict:
    """近 N 日指标趋势（逐日快照拼接口径）。

    :returns: {days_available, source_trend: {src: [{date, success_rate, calls}]},
               cache_trend: {layer: [{date, hit_rate, calls}]}, missing_days}
    缺失日如实列入 missing_days（不插值不编造）。
    """
    days = max(1, min(int(days), 90))
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range(days)]
    dates.reverse()  # 旧 → 新

    src_trend: dict[str, list] = {}
    cache_trend: dict[str, list] = {}
    found: list[str] = []
    missing: list[str] = []
    for d in dates:
        p = _snapshot_path(d)
        snap = _load_day(p)
        if snap is None:
            missing.append(d)
            continue
        found.append(d)
        for src, m in (snap.get("source_metrics") or {}).items():
            if not isinstance(m, dict) or not m.get("calls"):
                continue
            src_trend.setdefault(src, []).append(
                {"date": d, "success_rate": m.get("success_rate"), "calls": m.get("calls")})
        for layer, m in (snap.get("cache_metrics") or {}).items():
            if not isinstance(m, dict) or not m.get("calls"):
                continue
            cache_trend.setdefault(layer, []).append(
                {"date": d, "hit_rate": m.get("hit_rate"), "calls": m.get("calls")})

    return {"days_available": found, "missing_days": missing,
            "source_trend": src_trend, "cache_trend": cache_trend}
