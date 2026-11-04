"""lib/temperature_engine.py — 市场情绪温度计引擎（纯标准库，无第三方依赖）。

为什么存在：避免对 StockSignal 仓库的硬依赖，使本 skill 发布到 SkillHub 后，
即便使用者没有 StockSignal 也能运行（喂本地广度 JSON 即可）。

口径纪律（与 modules/market_temperature.py 对齐）：
  · **优先调用 StockSignal 的 modules.market_temperature**（单一真理源，不分叉口径）；
    读不到才退化为「本地 today dict + 内置五档镜像」，并如实标 degraded=true。
  · **温度是描述性指标**，不声称预测能力。
  · 取不到数据 → available=False + reason，**绝不编造温度值**。
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# 五档镜像（自 StockSignal modules/market_temperature.py 的 BANDS 复制）。
# 仅在无法导入 StockSignal 时兜底；可用 StockSignal 时以那边为真理源。
BANDS_MIRROR = [
    {"level": 0, "lo": 0, "hi": 20, "label": "冰点", "color": "#2563eb",
     "advice": "市场极度悲观、交投清淡。防守为主；可关注恐慌出清后的反转机会（见下方极端区信号）。"},
    {"level": 1, "lo": 20, "hi": 40, "label": "偏冷", "color": "#0891b2",
     "advice": "情绪偏弱、风险偏好低。控制仓位，等待右侧确认信号再出手。"},
    {"level": 2, "lo": 40, "hi": 60, "label": "中性", "color": "#d97706",
     "advice": "多空均衡、结构性机会为主。不追高，聚焦主线与事件驱动。"},
    {"level": 3, "lo": 60, "hi": 80, "label": "活跃", "color": "#ea580c",
     "advice": "风险偏好回升、赚钱效应好转。可积极围绕主线做多，但需留意内部分化。"},
    {"level": 4, "lo": 80, "hi": 101, "label": "狂热", "color": "#dc2626",
     "advice": "情绪过热、一致性预期强。注意分歧与兑现风险，避免高位接力。"},
]

ROOT_ENV = "STOCKSIGNAL_ROOT"


def _candidate_roots():
    """候选 StockSignal 根目录：环境变量 > 同机常见相对位置。"""
    out = []
    env = os.environ.get(ROOT_ENV)
    if env:
        out.append(env)
    base = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
    out.append(base)
    out.append(os.path.join(base, "StockSignal"))
    return out


def load_stock_signal(root: str | None = None):
    """尝试导入 StockSignal 的 modules.market_temperature / modules.shepherd。

    :return: (modules.market_temperature | None, modules.shepherd | None, root_used | None)
    """
    roots = [root] if root else _candidate_roots()
    for r in roots:
        if not r or not os.path.isdir(os.path.join(r, "modules")):
            continue
        if r not in sys.path:
            sys.path.insert(0, r)
        try:
            from modules import market_temperature as mt
            from modules import shepherd
            return mt, shepherd, r
        except Exception:
            continue
    return None, None, None


def band_of(temp, bands=None) -> dict:
    """温度 → 五档分档（纯函数，可单测）。非数值/NaN 兜底为中性 50。"""
    bands = bands or BANDS_MIRROR
    try:
        t = float(temp)
    except (TypeError, ValueError):
        t = 50.0
    if t != t:
        t = 50.0
    t = max(0.0, min(100.0, t))
    for b in bands:
        if b["lo"] <= t < b["hi"]:
            return dict(b)
    return dict(bands[-1])


def compute(today: dict | None = None, hist_days: int = 2000,
            stock_signal_root: str | None = None) -> dict:
    """算当日市场温度（含分档 / 贡献 / 极端区 / 相似日）。

    :param today: 当日广度 dict；不给则尝试从 StockSignal 取
    :return: {available, degraded, temperature, band, contributions, extreme, analogs, reason}
    """
    mt, shepherd, root_used = load_stock_signal(stock_signal_root)
    if mt is None:
        # 无 StockSignal：退化路径（需外部喂 today dict）
        if not today:
            return {"available": False, "degraded": True,
                    "reason": "未找到 StockSignal（设置 STOCKSIGNAL_ROOT 或传 --today-json），且未提供当日广度数据",
                    "temperature": None, "band": None, "contributions": None,
                    "extreme": None, "analogs": None}
        return {"available": False, "degraded": True,
                "reason": "当日广度数据已提供，但无 StockSignal 全历史分位基准，无法合成温度（需完整历史广度序列）",
                "temperature": None, "band": None, "contributions": None,
                "extreme": None, "analogs": None, "today_keys": sorted(today.keys())}

    meta = {}
    if today is None:
        try:
            _res = shepherd.get_shepherd_today()
            # ⚠️ footgun：get_shepherd_today 返回 (dict, meta) 元组，必须解包
            if isinstance(_res, tuple):
                today = _res[0] if len(_res) > 0 else None
                meta = _res[1] if len(_res) > 1 and isinstance(_res[1], dict) else {}
            else:
                today = _res
        except Exception as e:
            return {"available": False, "degraded": False, "reason": f"当日广度取数失败：{e}",
                    "temperature": None, "band": None, "contributions": None,
                    "extreme": None, "analogs": None}
    if not isinstance(today, dict) or not today:
        return {"available": False, "degraded": False,
                "reason": "当日广度数据为空（各数据源均不可用），不返回编造温度",
                "temperature": None, "band": None, "contributions": None,
                "extreme": None, "analogs": None, "sources": meta}

    try:
        temp = mt.composite_temperature(today, hist_days=hist_days)
        band = mt.temperature_band(temp)
    except Exception as e:
        return {"available": False, "degraded": False, "reason": f"温度合成失败：{e}",
                "temperature": None, "band": None, "contributions": None,
                "extreme": None, "analogs": None, "sources": meta}

    out = {"available": True, "degraded": False, "temperature": float(temp),
           "band": band, "contributions": None, "extreme": None, "analogs": None,
           "reason": "", "source": "stock_signal", "stock_signal_root": root_used,
           "sources": meta}
    for key, fn in (("contributions", mt.temperature_contributions),
                    ("extreme", mt.extreme_zone_signal),
                    ("analogs", mt.historical_analogs)):
        try:
            out[key] = fn(today)
        except Exception:
            out[key] = None
    return out


def load_today_json(path: str) -> dict:
    """读本地当日广度 JSON。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("当日广度 JSON 顶层不是对象")
    return data
