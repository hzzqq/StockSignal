"""modules/shepherd_helper.py.py —— 从 shepherd.py 精确切出（零修改）。"""
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
logger = logging.getLogger(__name__)
_SHEPHERD_DATA_DIR = os.environ.get('SS_DATA_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
_HISTORY_FILE = os.path.join(_SHEPHERD_DATA_DIR, 'shepherd_history.csv')
_HISTORY_TTL = 3600
_MAX_HISTORY_DAYS = 90
_ZBGC_MAX_DAYS = 30
THRESHOLDS = {'up_count': dict(name='上涨家数', unit='家', dir=1, hot=3000, warm=1500, hot_label='高温(可出手)', cold_label='低温(先防守)'), 'down_count': dict(name='下跌家数', unit='家', dir=-1, hot=1500, warm=3000, hot_label='低温(可出手)', cold_label='高温(先防守)'), 'limit_up': dict(name='涨停家数', unit='家', dir=1, hot=50, warm=20, hot_label='亢奋', cold_label='低迷'), 'limit_down': dict(name='跌停家数', unit='家', dir=-1, hot=5, warm=15, hot_label='安全', cold_label='恐慌(>30)'), 'zt_prev_ret': dict(name='昨日涨停表现', unit='%', dir=1, hot=3.0, warm=0.0, hot_label='炸裂', cold_label='吃面'), 'red_ratio': dict(name='红盘占比', unit='%', dir=1, hot=60.0, warm=45.0, hot_label='普涨', cold_label='普跌'), 'connect_hl': dict(name='连板高度', unit='板', dir=1, hot=6, warm=3, hot_label='高风险偏好', cold_label='冰点'), 'zt_fail_ratio': dict(name='炸板率', unit='%', dir=-1, hot=30.0, warm=50.0, hot_label='封板稳', cold_label='分歧大(≥50%易V反)'), 'real_limit_up': dict(name='有效涨停(真实涨停)', unit='家', dir=1, hot=50, warm=20, hot_label='亢奋', cold_label='低迷'), 'median_chg': dict(name='中位数涨跌幅', unit='%', dir=1, hot=1.0, warm=0.0, hot_label='普涨修复', cold_label='亏钱效应'), 'hb_wave10': dict(name='回头波>10%家数', unit='家', dir=-1, hot=20, warm=50, hot_label='追高安全', cold_label='退潮(易V反)'), 'zt_fail_count': dict(name='炸板家数', unit='家', dir=-1, hot=20, warm=45, hot_label='封板稳', cold_label='分歧大'), 'connect_2b': dict(name='连板家数(≥2板)', unit='家', dir=1, hot=15, warm=5, hot_label='梯队厚', cold_label='梯队断层'), 'touch_down': dict(name='倒跌停家数', unit='家', dir=-1, hot=15, warm=40, hot_label='安全', cold_label='恐慌抛压'), 'fc_ratio': dict(name='平均封成比', unit='', dir=1, hot=1.0, warm=0.4, hot_label='封板强', cold_label='封板弱'), 'avg_price': dict(name='平均股价', unit='元', dir=0, hot=0.0, warm=999.0, hot_label='观察', cold_label='观察'), 'turnover_amt': dict(name='全A成交额', unit='亿', dir=0, hot=0.0, warm=999.0, hot_label='观察', cold_label='观察')}

def _resolve(_name):
    """Run-time re-export layer lookup (monkeypatch penetration)."""
    import sys as _sys
    _sh = _sys.modules.get('modules.shepherd')
    if _sh is not None and hasattr(_sh, _name):
        return getattr(_sh, _name)
    return globals().get(_name)

def _cached(ttl, key, fn):
    """基于时间戳的轻量缓存（锁外执行 fn，见 modules.cache_utils.cached_ttl）。

    注：shepherd 不在此处触发代理/SSL 探测——其网络取数路径自行负责。
    """
    return _resolve('cached_ttl')(ttl, key, fn)

def _col(df, *keys):
    """按关键字（不区分大小写）在 DataFrame 列中找第一个匹配列名。"""
    if df is None or not hasattr(df, 'columns'):
        return None
    low = {str(c).lower(): c for c in df.columns}
    for k in keys:
        lk = str(k).lower()
        for lcol, col in low.items():
            if lk in lcol:
                return col
    return None

def _pdate(x):
    try:
        return _resolve('pd').to_datetime(x, errors='coerce')
    except Exception as e:
        _resolve('logger').warning('[shepherd] 日期解析异常: %s', e)
        return _resolve('pd').NaT

def _retry(max_retries=2, base_delay=0.5):

    def deco(fn):

        def wrapper(*args, **kwargs):
            last = None
            for i in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
                    last = e
                    if i < max_retries - 1:
                        time.sleep(base_delay * 2 ** i)
                        continue
            _resolve('logger').debug('[shepherd] %s 失败: %s', getattr(fn, '__name__', 'fn'), last)
            return None
        return wrapper
    return deco

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
    "logger",
    "_SHEPHERD_DATA_DIR",
    "_HISTORY_FILE",
    "_HISTORY_TTL",
    "_MAX_HISTORY_DAYS",
    "_ZBGC_MAX_DAYS",
    "THRESHOLDS",
    "_resolve",
    "_cached",
    "_col",
    "_pdate",
    "_retry",
]
