"""modules/shepherd_fetch.py.py —— 从 shepherd.py 精确切出（零修改）。"""
from __future__ import annotations  # noqa: I001
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
from .shepherd_helper import *  # noqa: F403

def _resolve(_name):
    """Run-time re-export layer lookup (monkeypatch penetration)."""
    import sys as _sys
    _sh = _sys.modules.get('modules.shepherd')
    if _sh is not None and hasattr(_sh, _name):
        return getattr(_sh, _name)
    return globals().get(_name)

def _fetch_legu():
    """涨跌家数实时快照（乐股）。"""
    import akshare as ak
    df = ak.stock_market_activity_legu()
    if df is None or df.empty or 'item' not in df.columns:
        return None
    out = {}

    def _val(name):
        sub = df[df['item'] == name]['value']
        if sub.empty:
            return None
        return _resolve('pd').to_numeric(sub.iloc[0], errors='coerce')
    for name, key in (('上涨', 'up_count'), ('下跌', 'down_count'), ('涨停', 'limit_up'), ('跌停', 'limit_down'), ('横盘', 'flat_count'), ('真实涨停', 'real_limit_up'), ('真实跌停', 'real_limit_down')):
        v = _val(name)
        if v is not None and _resolve('pd').notna(v):
            out[key] = float(v)
    return out or None

def _compute_zt_pool_indicators(df):
    """从涨停池 DataFrame 计算涨停/连板/炸板/封成比指标（纯函数，可离线测试）。"""
    if df is None or df.empty:
        return None
    out = {'limit_up': float(len(df))}
    col_hl = _resolve('_col')(df, '连板数')
    if col_hl:
        boards = _resolve('pd').to_numeric(df[col_hl], errors='coerce')
        hl = boards.max()
        if _resolve('pd').notna(hl):
            out['connect_hl'] = float(hl)
        out['connect_2b'] = float((boards >= 2).sum())
    col_zb = _resolve('_col')(df, '炸板次数')
    if col_zb:
        zb = _resolve('pd').to_numeric(df[col_zb], errors='coerce').fillna(0)
        out['zt_fail_ratio'] = float((zb > 0).mean() * 100.0)
    col_fc = _resolve('_col')(df, '封板资金')
    col_amt = _resolve('_col')(df, '成交额')
    if col_fc and col_amt and (col_fc != col_amt):
        fc = _resolve('pd').to_numeric(df[col_fc], errors='coerce')
        amt = _resolve('pd').to_numeric(df[col_amt], errors='coerce')
        ok = fc.notna() & amt.notna() & (amt > 0)
        if ok.any():
            out['fc_ratio'] = float((fc[ok] / amt[ok]).mean())
    return out

def _fetch_zt_pool(date=None):
    """涨停池：涨停家数 / 连板高度 / 连板梯队 / 炸板不稳比例 / 平均封成比。"""
    import akshare as ak
    d = date or _resolve('now_cst_str')('%Y%m%d')
    df = ak.stock_zt_pool_em(date=d)
    return _resolve('_compute_zt_pool_indicators')(df)

def _fetch_zbgc_pool(date=None):
    """炸板股池（东财 zbgc）：炸板家数（摸板未封住）。注：仅支持最近约 30 个交易日，
    更早日期为业务性报错（重试 1 次仍失败即放弃，不无限重试），历史值由重构管线从个股 high/close 反算。

    带 @_retry 与亲兄弟 _fetch_zt_pool（涨停家数）一致：东财 push2 类端点在本机会整体
    RemoteDisconnected（实测 2026-09-02，同时殃及炸板股池等东财端点），瞬断时重试 1 次
    通常能拉回，避免炸板家数/炸板率维度被静默丢弃（杨哥 V反规律与封板质量评分权重 20 的关键输入）。
    """
    import akshare as ak
    d = date or _resolve('now_cst_str')('%Y%m%d')
    df = ak.stock_zt_pool_zbgc_em(date=d)
    if df is None or df.empty:
        return None
    return {'zt_fail_count': float(len(df))}

def _fetch_dt_pool(date=None):
    """跌停股池（东财 dtgc）：跌停家数 —— legu 的独立兜底源。

    legu 是 limit_down 的主源，但被限流时会整源失效（见 _fetch_legu 注释）。
    跌停家数是次日预判里「冰点 / 退潮」判定的关键维度，不能因单源抖动而丢失，
    故用东财跌停股池（不同域名、不同限流策略）作备份。

    返回 {"limit_down": float}；**空池返回 0.0 而非 None** —— 「今日 0 家跌停」
    是有效事实（市场无恐慌），与「取数失败」语义必须区分开。
    """
    import akshare as ak
    d = date or _resolve('now_cst_str')('%Y%m%d')
    df = ak.stock_zt_pool_dtgc_em(date=d)
    if df is None or df.empty:
        return {'limit_down': 0.0}
    return {'limit_down': float(len(df))}

def _limit_pct_for_code(code):
    """按代码推断日涨跌停幅度（与 shepherd_reconstruct._board_limit_pct 同口径）。
    支持带前缀(sh/sz/bj)与裸代码；北交所 8xx/920=30%，科创板 68=20%，创业板 30/31=20%，其余=10%。
    """
    s = str(code).lower().strip()
    body = s[2:] if len(s) > 2 and s[:2] in ('sh', 'sz', 'bj') else s
    if s.startswith('bj'):
        return 0.3
    if body.startswith(('83', '87', '88', '89', '92')):
        return 0.3
    if body.startswith('68'):
        return 0.2
    if body.startswith(('30', '31')):
        return 0.2
    return 0.1

def _compute_spot_indicators(df):
    """从新浪全 A 快照计算中位数/平均股价/回头波/倒跌停/成交额（纯函数，可离线测试）。

    口径对齐视频《如何复盘非常重要》：
    - 中位数涨跌幅：剔除 ST 后全体涨跌幅的中位数 —— 当日「所有人平均赚钱还是亏钱」；
    - 平均股价：全部 A 股最新价均值（杨哥：高价股多时会拉高，观察用）；
    - 回头波>10%：日内（最高-最新）/最高 > 10% —— 追高者的回撤幅度；
    - 倒跌停：盘中最低价触及按板块跌幅计算的跌停价（含封死，杨哥单列封死跌停）。
    """
    if df is None or df.empty:
        return None
    chg = _resolve('pd').to_numeric(df.get('涨跌幅'), errors='coerce')
    price = _resolve('pd').to_numeric(df.get('最新价'), errors='coerce')
    high = _resolve('pd').to_numeric(df.get('最高'), errors='coerce')
    low = _resolve('pd').to_numeric(df.get('最低'), errors='coerce')
    prev = _resolve('pd').to_numeric(df.get('昨收'), errors='coerce')
    vol = _resolve('pd').to_numeric(df.get('成交量'), errors='coerce')
    amt = _resolve('pd').to_numeric(df.get('成交额'), errors='coerce')
    name = df.get('名称') if '名称' in df.columns else None
    active = vol.fillna(0) > 0
    out = {}
    m = active & chg.notna()
    if name is not None:
        m = m & ~name.astype(str).str.upper().str.contains('ST', na=False)
    if m.any():
        out['median_chg'] = float(chg[m].median())
    ap = active & price.notna() & (price > 0)
    if ap.any():
        out['avg_price'] = float(price[ap].mean())
    hw_ok = active & high.notna() & (high > 0) & price.notna() & (price > 0) & (high >= price)
    if hw_ok.any():
        hw = (high[hw_ok] - price[hw_ok]) / high[hw_ok] * 100.0
        out['hb_wave10'] = float((hw > 10).sum())
    codes = df.get('代码') if '代码' in df.columns else None
    if codes is not None and prev is not None and (low is not None):
        lp = codes.map(_resolve('_limit_pct_for_code')).astype(float)
        dl = prev * (1.0 - lp)
        td = active & prev.notna() & (prev > 0) & low.notna() & (low <= dl * 1.005)
        out['touch_down'] = float(td.sum())
    if amt is not None and amt.notna().any():
        out['turnover_amt'] = float(amt.sum() / 100000000.0)
    return out or None

def _fetch_sina_spot():
    """新浪全 A 快照（约 70 页、~25s），TTL 缓存 10 分钟。"""
    import akshare as ak
    df = ak.stock_zh_a_spot()
    return _resolve('_compute_spot_indicators')(df)

def _get_spot_cached():
    """带 10 分钟 TTL 缓存 + 30s 硬超时的新浪快照指标。"""
    from modules.timeout_exec import run_with_timeout
    return run_with_timeout(lambda: _resolve('_cached')(600, 'sina_spot_v2', _resolve('_fetch_sina_spot')), timeout=30)

def _fetch_prev_pool(date=None):
    """昨日涨停表现：昨日涨停股今日平均涨跌幅(%)。"""
    import akshare as ak
    d = date or _resolve('now_cst_str')('%Y%m%d')
    df = ak.stock_zt_pool_previous_em(date=d)
    if df is None or df.empty:
        return None
    col = _resolve('_col')(df, '涨跌幅', 'change_percent')
    if col is None:
        return None
    chg = _resolve('pd').to_numeric(df[col], errors='coerce').dropna()
    if chg.empty:
        return None
    return {'zt_prev_ret': float(chg.mean())}

def get_shepherd_today():
    """实时快照：合并各源，返回 (dict, meta)。

    优先 legu(涨跌/涨停/跌停/红盘占比) + zt_pool(涨停/连板/炸板) + prev_pool(昨日涨停表现)，
    全部为轻量接口，沙箱/弱网可用。meta: {available:[...], unavailable:[(k,reason)]}。
    """
    meta = {'available': [], 'unavailable': []}
    merged = {}
    from modules.fetch_parallel import fetch_many
    _tasks = [('legu', _resolve('_fetch_legu')), ('zt_pool', _resolve('_fetch_zt_pool')), ('zt_prev_ret', _resolve('_fetch_prev_pool')), ('zbgc_pool', _resolve('_fetch_zbgc_pool'))]
    _results = fetch_many(_tasks, max_workers=4, timeout=12)
    try:
        legu = _results.get('legu')
        if legu:
            merged.update(legu)
            meta['available'].extend(legu.keys())
        else:
            meta['unavailable'].append(('legu', '乐股快照暂不可用'))
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        meta['unavailable'].append(('legu', f'失败:{e}'))
    if merged.get('limit_down') is None:
        try:
            dt = _resolve('_fetch_dt_pool')()
            if dt and dt.get('limit_down') is not None:
                merged['limit_down'] = dt['limit_down']
                meta['available'].append('limit_down')
                meta['unavailable'] = [(k, r) for k, r in meta['unavailable'] if k != 'legu']
                meta['unavailable'].append(('legu', '乐股快照暂不可用（跌停数已由东财跌停池兜底）'))
        except Exception as e:
            _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
    try:
        zt = _results.get('zt_pool')
        if zt:
            for k, v in zt.items():
                if k not in merged:
                    merged[k] = v
                if k not in meta['available']:
                    meta['available'].append(k)
        else:
            meta['unavailable'].append(('zt_pool', '涨停池暂不可用'))
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        meta['unavailable'].append(('zt_pool', f'失败:{e}'))
    try:
        prev = _results.get('zt_prev_ret')
        if prev:
            merged.update(prev)
            meta['available'].extend(prev.keys())
        else:
            meta['unavailable'].append(('zt_prev_ret', '昨日涨停池暂不可用'))
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        meta['unavailable'].append(('zt_prev_ret', f'失败:{e}'))
    try:
        zbgc = _results.get('zbgc_pool')
        if zbgc:
            merged.update(zbgc)
            meta['available'].extend(zbgc.keys())
        else:
            meta['unavailable'].append(('zbgc_pool', '炸板股池暂不可用'))
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        meta['unavailable'].append(('zbgc_pool', f'失败:{e}'))
    try:
        spot = _resolve('_get_spot_cached')()
        if spot:
            merged.update(spot)
            meta['available'].extend(spot.keys())
        else:
            meta['unavailable'].append(('sina_spot', '新浪全A快照暂不可用'))
    except Exception as e:
        _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
        meta['unavailable'].append(('sina_spot', f'失败:{e}'))
    if 'zt_fail_count' in merged and 'limit_up' in merged:
        tot = merged['zt_fail_count'] + merged['limit_up']
        if tot > 0:
            merged['zt_fail_ratio'] = float(merged['zt_fail_count'] / tot * 100.0)
            if 'zt_fail_ratio' not in meta['available']:
                meta['available'].append('zt_fail_ratio')
    if 'red_ratio' not in merged and 'up_count' in merged and ('down_count' in merged):
        tot = merged['up_count'] + merged['down_count']
        if tot > 0:
            merged['red_ratio'] = float(merged['up_count'] / tot * 100.0)
            meta['available'].append('red_ratio')
    return (merged, meta)

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
    "_resolve",
    "_fetch_legu",
    "_compute_zt_pool_indicators",
    "_fetch_zt_pool",
    "_fetch_zbgc_pool",
    "_fetch_dt_pool",
    "_limit_pct_for_code",
    "_compute_spot_indicators",
    "_fetch_sina_spot",
    "_get_spot_cached",
    "_fetch_prev_pool",
    "get_shepherd_today",
]
