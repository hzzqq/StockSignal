"""市场驱动力面板数据（re-export 主入口 + get_market_drivers；拆分后对外 API 零变化）。

原始 1272 行单文件按职责拆为：
- ``market_drivers_core``   ：常量登记 / TTL 缓存与 SWR / 重试 / 列名与数值归一工具
- ``market_drivers_sources``：21 指标取数（_src_*）/ 调度表 _SRC_DISPATCH
- ``market_drivers_view``   ：plot_drivers_panel / 市场温度评分

**get_market_drivers 保留在本入口**：它依赖 `_cached_swr` / `_fetch_src` /
`_get_index_close`，而这些在测试与调用方处均通过 `monkeypatch.setattr(m, ...)` 打补丁；
若下沉到子模块，函数体内的模块全局查找会绕过补丁（原同模块语义会退化）。
既有调用零改动：``from modules.market_drivers import get_market_drivers, DIMS``。
"""
from __future__ import annotations  # noqa: I001

import logging

import pandas as pd

from modules.market_drivers_core import (  # noqa: F401
    DIMS,
    INDICATORS,
    KNOWN_UNAVAILABLE,
    _CACHE_TTL,
    _SWR_INFLIGHT,
    _SWR_LOCK,
    _cached,
    _cached_swr,
    _kick_refresh,
    _retry,
    _col,
    _pdate,
    _read_last_cached_value,
    _pdate_cn,
    _norm100,
    _norm100_aligned,
)
from modules.market_drivers_sources import (  # noqa: F401
    _PCR_DAYS,
    _fetch_margin_raw,
    _src_margin_rzye,
    _src_margin_net,
    _src_north_hist,
    _src_activity,
    _src_high_low,
    _src_qvvix,
    _src_zt,
    _src_pe,
    _src_div,
    _src_m2,
    _src_financing,
    _src_yield,
    _src_pmi,
    _opt_vol_sum,
    _src_pcr,
    _get_index_close,
    _src_idx_ma,
    _src_idx_rsi,
    _src_idx_boll,
    _src_idx_bias,
    _fetch_src,
    _SRC_DISPATCH,
)
from modules.market_drivers_view import (  # noqa: F401
    _DIM_COLORS,
    _REF_COLOR,
    _MARKET_TEMP_DEFAULT,
    _DIR,
    _fig_theme,
    plot_drivers_panel,
    _score_one_dim,
    _market_temp,
    _temp_level,
)

# 转发：测试与调用方通过本模块访问共享缓存层（原模块直接 import 的同一对象）
from modules.cache_utils import _CACHE, _CACHE_LOCK, cached_ttl  # noqa: F401

# 与子模块共用同一 logger 实例（同名即同一对象），确保既有按名字打补丁/过滤的
# 观测与守卫继续生效（如 tests/test_exception_logging.py 对 logger.warning 的注入）。
logger = logging.getLogger("modules.market_drivers")


def get_market_drivers(days=180):
    """返回 (df, meta)。

    df：宽表，列 = ['date'] + 各可用指标 key（已对齐到 common 日期索引）。
    meta：{dim: {'available':[key...], 'unavailable':[(key, reason)...]}}。
    单源失败不影响其他源；无任何数据返回空 df + 全 unavailable。

    缓存策略（v2）：
      - 网络取数成功 → 结果写入 SQLite 持久缓存（modules.market_cache）
      - 网络取数完全失败 → 从 SQLite 缓存读取最近一次成功的数据（带时间戳警告）
      - 双双失败 → 返回空 df + 全 unavailable（原有行为）
    """
    def _build():
        meta = {d: {"available": [], "unavailable": []} for d in DIMS}
        collected = {}  # key -> series
        names = {}      # key -> display name
        for ind in INDICATORS:
            rows, reason = _fetch_src(ind, days)
            if rows:
                for k, nm, s in rows:
                    collected[k] = s
                    names[k] = nm
                    if k not in meta[ind["dim"]]["available"]:
                        meta[ind["dim"]]["available"].append(k)
            else:
                meta[ind["dim"]]["unavailable"].append((ind["key"], reason or "抓取失败"))

        # 大盘指数参考线（上证，归一化对比用）
        ref = _get_index_close(days)
        if ref is not None and not ref.empty:
            collected["ref"] = ref
            names["ref"] = "上证(参考)"

        # 合并到宽表
        if not collected:
            return pd.DataFrame(columns=["date"]), meta
        aligned = {}
        for k, s in collected.items():
            s = pd.Series(s.values, index=pd.to_datetime(s.index, errors="coerce"))
            aligned[k] = s
        df = pd.DataFrame(aligned)
        df.index.name = "date"
        df = df.reset_index().rename(columns={"index": "date"})
        df = df.sort_values("date").reset_index(drop=True)
        return df, meta

    try:
        # T-272④：_cached_swr 返回 (value, swr_info)，value = _build() 的 (df, meta) 元组
        # ——必须先整体接收再解包，不能 df, meta, swr = _cached_swr(...)（元组解包会炸）
        res, swr = _cached_swr(_CACHE_TTL, f"drivers_{days}", _build)
        df, meta = res
        if swr:
            # T-272④诚实语义：SWR 旧值必须可辨——meta 注入标注（浅拷贝防污染缓存内 meta）
            meta = dict(meta) if isinstance(meta, dict) else {}
            meta["_swr_stale"] = True
            meta["_swr_age_s"] = swr["age_s"]
            meta["_swr_note"] = (f"进程缓存已过期 {swr['age_s']}s，本次先展示旧值，"
                                 "后台刷新中（下次打开生效）")

        # 网络成功且有数据 → 异步写入持久化缓存（不阻塞返回）
        if df is not None and not df.empty:
            try:
                from modules.market_cache import save_drivers_to_cache
                save_drivers_to_cache(df, meta)
            except Exception as cache_err:
                logger.debug("[market_drivers] 后台写缓存失败（不阻塞）: %s", cache_err)
            return df, meta

        # 网络取数为空 → 尝试从持久化缓存降级
        logger.info("[market_drivers] 网络取数空，尝试从 SQLite 缓存降级")
        try:
            from modules.market_cache import load_drivers_from_cache
            cached_df, cached_meta = load_drivers_from_cache(days=days)
            if cached_df is not None and not cached_df.empty:
                # 合并 meta 信息
                if cached_meta:
                    meta = cached_meta
                    meta["_cache_fallback"] = True
                logger.info("[market_drivers] 缓存降级成功：%d 行", len(cached_df))
                return cached_df, meta
        except Exception as cache_err:
            logger.warning("[market_drivers] 缓存降级也失败: %s", cache_err)

        return df, meta

    except Exception as e:  # noqa
        logger.warning("get_market_drivers 最终失败：%s", e)
        # 最终兜底：尝试读缓存
        try:
            from modules.market_cache import load_drivers_from_cache
            cdf, cm = load_drivers_from_cache(days=days)
            if cdf is not None and not cdf.empty:
                if cm is None:
                    cm = {}
                cm["_cache_fallback"] = True
                cm["_cache_message"] = "网络异常，展示最近一次缓存数据"
                return cdf, cm
        except Exception as e:
            logger.warning(f"[market_drivers] 处理异常: {e}")

        meta = {d: {"available": [], "unavailable": [(i["key"], "抓取失败") for i in INDICATORS if i["dim"] == d]} for d in DIMS}
        return pd.DataFrame(columns=["date"]), meta


__all__ = [
    "DIMS",
    "INDICATORS",
    "KNOWN_UNAVAILABLE",
    "_CACHE_TTL",
    "_SWR_INFLIGHT",
    "_SWR_LOCK",
    "_cached",
    "_cached_swr",
    "_kick_refresh",
    "_retry",
    "_col",
    "_pdate",
    "_read_last_cached_value",
    "_pdate_cn",
    "_norm100",
    "_norm100_aligned",
    "_PCR_DAYS",
    "_fetch_margin_raw",
    "_src_margin_rzye",
    "_src_margin_net",
    "_src_north_hist",
    "_src_activity",
    "_src_high_low",
    "_src_qvvix",
    "_src_zt",
    "_src_pe",
    "_src_div",
    "_src_m2",
    "_src_financing",
    "_src_yield",
    "_src_pmi",
    "_opt_vol_sum",
    "_src_pcr",
    "_get_index_close",
    "_src_idx_ma",
    "_src_idx_rsi",
    "_src_idx_boll",
    "_src_idx_bias",
    "_fetch_src",
    "_SRC_DISPATCH",
    "_DIM_COLORS",
    "_REF_COLOR",
    "_MARKET_TEMP_DEFAULT",
    "_DIR",
    "_fig_theme",
    "plot_drivers_panel",
    "_score_one_dim",
    "_market_temp",
    "_temp_level",
    "get_market_drivers",
    "_CACHE", "_CACHE_LOCK", "cached_ttl", "logger",
]
