"""modules/shepherd_temperature.py.py —— 从 shepherd.py 精确切出（零修改）。"""
from __future__ import annotations
import os
import time
import logging
import threading
import json
from modules.atomic_io import atomic_json_dump, atomic_to_csv
from modules.time_utils import now_cst_str, now_cst_naive
import numpy as np
import pandas as pd
from modules.cache_utils import _CACHE, _CACHE_LOCK, cached_ttl
from .shepherd_helper import *
from .shepherd_history import get_shepherd_history

def _resolve(_name):
    """Run-time re-export layer lookup (monkeypatch penetration)."""
    import sys as _sys
    _sh = _sys.modules.get('modules.shepherd')
    if _sh is not None and hasattr(_sh, _name):
        return getattr(_sh, _name)
    return globals().get(_name)

def _indicator_score(value, th, hist_series):
    """单个指标 → 0-100 热度分（单一打分真理源，shepherd_temperature / _detail 共用）。

    dir>0：值越高越热（今日值在历史中分位越高 → 越热）；
    dir<0：值越低越热（今日值在历史中分位越低 → 越热）。
    无历史（序列缺失或样本<5）退化为阈值线性打分。
    """
    if hist_series is not None and len(hist_series) >= 5:
        s = _resolve('pd').to_numeric(hist_series, errors='coerce').dropna()
        if len(s) >= 5:
            pct = float((s < value).mean())
            return pct * 100 if th['dir'] > 0 else (1 - pct) * 100
    if th['dir'] > 0:
        return 100.0 if value >= th['hot'] else 50.0 if value >= th['warm'] else 10.0
    return 100.0 if value <= th['hot'] else 50.0 if value <= th['warm'] else 10.0

def shepherd_temperature(today: dict, hist_days: int=60):
    """把今日快照映射为 0-100 综合「牧羊人温度」。

    规则：每个可用指标按其在近期历史中的分位打分（高=热 / 高=冷），均值。
    退化输入返回安全默认 50。

    :param hist_days: 分位计算所用的历史回看天数（默认 60；>=2000 取 2007 起长历史）。
                      调用方（如 MCP 工具）可透传用户指定的 days，使温度计真正反映
                      所请求的时间窗口，而非永远用固定 60 天。
    """
    if not today:
        return 50.0
    try:
        hist = _resolve('get_shepherd_history')(hist_days)
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        hist = None
    subs = []
    for k, th in _resolve('THRESHOLDS').items():
        v = today.get(k)
        if v is None or not _resolve('np').isfinite(v):
            continue
        if th.get('dir', 1) == 0:
            continue
        series = hist[k] if hist is not None and k in hist.columns else None
        subs.append(_resolve('_indicator_score')(v, th, series))
    return float(_resolve('np').mean(subs)) if subs else 50.0

def shepherd_temperature_detail(today: dict, hist_days: int=60):
    """综合温度 + 各指标贡献明细（供页面渲染分档与贡献条）。

    :returns: {"temp": float, "contributions": [ {key,name,unit,dir,value,hot,warm,heat} ]}
              heat 为 0-100 单指标热度分，与 shepherd_temperature 完全同源。
    """
    if not today:
        return {'temp': 50.0, 'contributions': []}
    try:
        hist = _resolve('get_shepherd_history')(hist_days)
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        hist = None
    subs = []
    contributions = []
    for k, th in _resolve('THRESHOLDS').items():
        v = today.get(k)
        if v is None or not _resolve('np').isfinite(v):
            continue
        if th.get('dir', 1) == 0:
            continue
        series = hist[k] if hist is not None and k in hist.columns else None
        score = _resolve('_indicator_score')(v, th, series)
        subs.append(score)
        contributions.append({'key': k, 'name': th.get('name', k), 'unit': th.get('unit', ''), 'dir': th.get('dir', 1), 'value': float(v), 'hot': th.get('hot'), 'warm': th.get('warm'), 'heat': round(float(score), 1)})
    temp = float(_resolve('np').mean(subs)) if subs else 50.0
    return {'temp': temp, 'contributions': contributions}

def _zt_pool_detail_cached(date=None):
    """涨停池明细（含 所属行业/连板数/封板资金），TTL 缓存 10 分钟。"""
    d = date or _resolve('now_cst_str')('%Y%m%d')

    def _pull():
        import akshare as ak
        df = ak.stock_zt_pool_em(date=d)
        return df if df is not None and (not df.empty) else None
    return _resolve('_cached')(600, f'zt_detail_{d}', _pull)

def get_zt_industry_distribution(top=10, date=None):
    """今日涨停按行业分布（视频：每个涨停票炒什么板块都要了如指掌）。"""
    try:
        df = _resolve('_zt_pool_detail_cached')(date)
        col = _resolve('_col')(df, '所属行业') if df is not None else None
        if df is None or col is None:
            return None
        dist = df.groupby(col).size().sort_values(ascending=False).head(top)
        return _resolve('pd').DataFrame({'行业': dist.index, '涨停家数': dist.values})
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        return None

def get_zt_top_board(date=None):
    """今日最高连板标的（视频：每天最高板代表市场情绪高度）。"""
    try:
        df = _resolve('_zt_pool_detail_cached')(date)
        col_hl = _resolve('_col')(df, '连板数') if df is not None else None
        if df is None or col_hl is None:
            return None
        boards = _resolve('pd').to_numeric(df[col_hl], errors='coerce')
        if boards.notna().sum() == 0:
            return None
        row = df.loc[boards.idxmax()]
        return {'name': str(row.get('名称', '')), 'code': str(row.get('代码', '')), 'boards': int(boards.max()), 'industry': str(row.get('所属行业', ''))}
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        return None

def get_zt_ladder(date=None, top_per_level=3):
    """连板梯队全景（视频：把每天最高标的票列出来，梯队厚度决定赚钱效应能否扩散）。

    返回 dict:
      levels  [{boards, count, stocks:[{name, code, industry, seal, amount}]}]  按连板数倒序
      total_connect  连板总家数（≥2 板）
      max_boards     最高连板数
      distribution   [(连板数, 家数)] 含首板，用于柱状图
      top            最高板标的（等同 get_zt_top_board）

    实盘意义：
      · 梯队「断层」（如 4 板 1 家、3 板 0 家、2 板 3 家）= 接力资金缺席，主线是「一只独苗」；
      · 梯队「厚」（≥15 家）= 赚钱效应线状扩散，接力顺畅；
      · 结合最高板高度判断情绪空间：高度打开 + 梯队厚 = 主升确认。
    """
    out = dict(levels=[], total_connect=0, max_boards=0, distribution=[], top=None)
    try:
        df = _resolve('_zt_pool_detail_cached')(date)
        if df is None or df.empty:
            return out
        col_hl = _resolve('_col')(df, '连板数')
        if not col_hl:
            return out
        work = df.copy()
        work['_boards'] = _resolve('pd').to_numeric(work[col_hl], errors='coerce').fillna(1).astype(int)
        col_name = _resolve('_col')(df, '名称')
        col_code = _resolve('_col')(df, '代码')
        col_ind = _resolve('_col')(df, '所属行业')
        col_seal = _resolve('_col')(df, '封板资金')
        col_amt = _resolve('_col')(df, '成交额')
        dist = work.groupby('_boards').size().sort_index(ascending=False)
        out['distribution'] = [(int(b), int(c)) for b, c in dist.items()]
        out['max_boards'] = int(work['_boards'].max())
        for boards in sorted(work['_boards'].unique(), reverse=True):
            if boards < 2:
                continue
            grp = work[work['_boards'] == boards]
            if col_seal:
                grp = grp.assign(_seal=_resolve('pd').to_numeric(grp[col_seal], errors='coerce').fillna(0))
                grp = grp.sort_values('_seal', ascending=False)
            stocks = []
            for _, r in grp.head(top_per_level).iterrows():
                stocks.append({'name': str(r.get(col_name, '')) if col_name else '', 'code': str(r.get(col_code, '')) if col_code else '', 'industry': str(r.get(col_ind, '')) if col_ind else '', 'seal': float(r.get(col_seal, 0) or 0) if col_seal else 0.0, 'amount': float(r.get(col_amt, 0) or 0) if col_amt else 0.0})
            out['levels'].append(dict(boards=int(boards), count=int(len(grp)), stocks=stocks))
        out['total_connect'] = int((work['_boards'] >= 2).sum())
        mx = work.loc[work['_boards'].idxmax()]
        out['top'] = {'name': str(mx.get(col_name, '')) if col_name else '', 'code': str(mx.get(col_code, '')) if col_code else '', 'boards': int(mx['_boards']), 'industry': str(mx.get(col_ind, '')) if col_ind else ''}
        return out
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        return out

# 导出清单（自动生成）
__all__ = [
    "annotations",
    "os",
    "time",
    "logging",
    "threading",
    "json",
    "atomic_json_dump",
    "atomic_to_csv",
    "now_cst_str",
    "now_cst_naive",
    "np",
    "pd",
    "_CACHE",
    "_CACHE_LOCK",
    "cached_ttl",
    "get_shepherd_history",
    "_resolve",
    "_indicator_score",
    "shepherd_temperature",
    "shepherd_temperature_detail",
    "_zt_pool_detail_cached",
    "get_zt_industry_distribution",
    "get_zt_top_board",
    "get_zt_ladder",
]
