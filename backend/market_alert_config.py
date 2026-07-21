"""
市场异动扫描策略配置（管理员可调）
==================================
- 默认策略内置在 DEFAULT_CONFIG。
- 环境变量可覆盖基础参数（扫描间隔/冷却/延迟/阈值 JSON）。
- 后端提供 GET/POST /api/market-alerts/config（admin）做运行时调参；
  前端系统配置页经该接口读写。运行时覆盖由 admin 接口负责持久化/缓存，
  本模块只负责「读取环境变量默认值 + 把阈值覆盖应用到规则表」。
"""
from __future__ import annotations

import json
import os
from typing import Any

# 可被环境变量覆盖的基础参数默认值。
DEFAULT_CONFIG: dict[str, Any] = {
    "scan_interval_minutes": 15,
    "cooldown_hours": 6,
    "initial_delay_seconds": 10,
    # 阈值覆盖：{ metric_key: {"warn_hi":..,"danger_hi":..,"warn_lo":..,"danger_lo":..,"hi_msg":..,"lo_msg":..} }
    "thresholds": {},
    # 启用的指标 key 白名单；None 表示全部启用
    "enabled_rules": None,
}

# 运行时覆盖（由管理员经 /api/market-alerts/config 写入，重启后失效）。
# 仅用于「立即生效」；持久化由部署方通过环境变量完成。
_RUNTIME_OVERRIDES: dict[str, Any] = {}


def _env_int(name: str, default: int) -> int:
    try:
        v = os.environ.get(name)
        return int(v) if v not in (None, "") else default
    except Exception:
        return default


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if v is not None:
            out[k] = v
    return out


def get_alert_config() -> dict:
    """返回当前生效的基础配置（环境变量 + 运行时覆盖 覆盖默认值）。"""
    cfg = dict(DEFAULT_CONFIG)
    cfg["scan_interval_minutes"] = _env_int(
        "MARKET_ALERT_SCAN_INTERVAL_MINUTES", cfg["scan_interval_minutes"]
    )
    cfg["cooldown_hours"] = _env_int("MARKET_ALERT_COOLDOWN_HOURS", cfg["cooldown_hours"])
    cfg["initial_delay_seconds"] = _env_int(
        "MARKET_ALERT_INITIAL_DELAY_SECONDS", cfg["initial_delay_seconds"]
    )

    raw = os.environ.get("MARKET_ALERT_THRESHOLDS")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                cfg["thresholds"] = parsed
        except Exception:
            pass

    # 运行时覆盖优先（管理员经 API 设置）
    cfg = _deep_merge(cfg, _RUNTIME_OVERRIDES)
    return cfg


def set_runtime_overrides(overrides: dict[str, Any]) -> dict:
    """写入运行时覆盖并返回生效后配置。非法字段被忽略。"""
    global _RUNTIME_OVERRIDES
    allowed = {
        "scan_interval_minutes": int,
        "cooldown_hours": int,
        "initial_delay_seconds": int,
        "thresholds": dict,
        "enabled_rules": (list, type(None)),
    }
    clean: dict[str, Any] = {}
    for k, typ in allowed.items():
        if k in overrides and overrides[k] is not None:
            val = overrides[k]
            if isinstance(typ, tuple):
                if not isinstance(val, typ):
                    continue
            elif not isinstance(val, typ):
                # 容忍字符串型的数字
                if typ is int and isinstance(val, str) and val.isdigit():
                    val = int(val)
                else:
                    continue
            clean[k] = val
    _RUNTIME_OVERRIDES = _deep_merge(_RUNTIME_OVERRIDES, clean)
    return get_alert_config()


def get_runtime_overrides() -> dict:
    return dict(_RUNTIME_OVERRIDES)


def resolve_rules(base_rules: list[dict]) -> list[dict]:
    """
    基于配置（thresholds / enabled_rules 覆盖）返回最终生效的规则表。

    - enabled_rules 为 list 时，仅保留其中的指标 key；
    - thresholds 中出现的 key 会就地覆盖 warn_hi/danger_hi/warn_lo/danger_lo/hi_msg/lo_msg。
    """
    cfg = get_alert_config()
    overrides = cfg.get("thresholds") or {}
    enabled = cfg.get("enabled_rules")

    out: list[dict] = []
    for r in base_rules:
        key = r["key"]
        if enabled is not None and key not in enabled:
            continue
        rule = dict(r)
        ov = overrides.get(key)
        if isinstance(ov, dict):
            for k in ("warn_hi", "danger_hi", "warn_lo", "danger_lo", "hi_msg", "lo_msg"):
                if k in ov:
                    rule[k] = ov[k]
        out.append(rule)
    return out
