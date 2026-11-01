"""modules/shepherd_history.py.py —— 从 shepherd.py 精确切出（零修改）。"""
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
from .shepherd_fetch import _fetch_legu, _fetch_zt_pool, _fetch_zbgc_pool, _fetch_prev_pool, _fetch_dt_pool, _get_spot_cached

def _resolve(_name):
    """Run-time re-export layer lookup (monkeypatch penetration)."""
    import sys as _sys
    _sh = _sys.modules.get('modules.shepherd')
    if _sh is not None and hasattr(_sh, _name):
        return getattr(_sh, _name)
    return globals().get(_name)

def _trading_days(n):
    import akshare as ak
    cal = ak.tool_trade_date_hist_sina()
    cal['trade_date'] = _resolve('_pdate')(cal['trade_date'])
    today = _resolve('pd').Timestamp(_resolve('now_cst_naive')()).normalize()
    dts = cal[cal['trade_date'] <= today]['trade_date'].sort_values().tail(n)
    return [d.strftime('%Y%m%d') for d in dts]

def _fetch_shepherd_history(n_days=60):
    """循环交易日历拉真实历史：涨停/连板/炸板 + 昨日涨停表现（东财涨停池/昨日涨停池）。

    末日额外补 legu 快照（上涨/下跌/跌停/红盘占比）作为最新点。
    返回 DataFrame：date + 各指标列。任何单日/单源失败仅跳过，不影响整体。
    注：逐日全A快照(stock_zh_a_spot_em)在弱网下易中断且过慢，历史涨跌家数折线
    仅含末日快照点；涨停/昨板/连板为完整 60 日真实序列。
    """
    dates = _resolve('_trading_days')(min(n_days, _resolve('_MAX_HISTORY_DAYS')))
    rows = []
    zbgc_from = max(0, len(dates) - _resolve('_ZBGC_MAX_DAYS'))
    for i, d in enumerate(dates):
        rec = {'date': d}
        try:
            zt = _resolve('_fetch_zt_pool')(d)
            if zt:
                rec.update(zt)
        except Exception as e:
            _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
            pass
        if i >= zbgc_from:
            try:
                zbgc = _resolve('_fetch_zbgc_pool')(d)
                if zbgc:
                    rec.update(zbgc)
            except Exception as e:
                _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
                pass
        try:
            zc, lu = (rec.get('zt_fail_count'), rec.get('limit_up'))
            if zc is not None and lu is not None and (zc + lu > 0):
                rec['zt_fail_ratio'] = float(zc / (zc + lu) * 100.0)
        except Exception as e:
            _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
            pass
        try:
            prev = _resolve('_fetch_prev_pool')(d)
            if prev:
                rec.update(prev)
        except Exception as e:
            _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
            pass
        if i == len(dates) - 1:
            try:
                legu = _resolve('_fetch_legu')()
                if legu:
                    for k in ('up_count', 'down_count', 'limit_down', 'real_limit_up', 'real_limit_down'):
                        if k in legu and k not in rec:
                            rec[k] = legu[k]
                    if 'red_ratio' not in rec and 'up_count' in legu and ('down_count' in legu):
                        tot = legu['up_count'] + legu['down_count']
                        if tot > 0:
                            rec['red_ratio'] = float(legu['up_count'] / tot * 100.0)
            except Exception as e:
                _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
                pass
            try:
                spot = _resolve('_get_spot_cached')()
                if spot:
                    for k in ('median_chg', 'avg_price', 'hb_wave10', 'touch_down', 'turnover_amt'):
                        if k in spot:
                            rec[k] = spot[k]
            except Exception as e:
                _resolve('logger').warning(f'[shepherd] 处理异常: {e}')
                pass
        rows.append(rec)
        time.sleep(0.2)
    if not rows:
        return _resolve('pd').DataFrame(columns=['date'])
    df = _resolve('pd').DataFrame(rows)
    df['date'] = _resolve('_pdate')(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df

def _parse_history_csv_full():
    """原始 CSV 解析（无缓存）。返回按日期排序的全量 DataFrame，或 None。"""
    if not os.path.exists(_resolve('_HISTORY_FILE')):
        return None
    df = _resolve('pd').read_csv(_resolve('_HISTORY_FILE'))
    if df is None or df.empty:
        return None
    df['date'] = _resolve('_pdate')(df['date'])
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df

def _read_history_csv(days=None):
    """读持久 CSV 长历史（2007 起，由 scripts/run_shepherd_reconstruct.py 生成）。

    :param days: 给定则只取尾部 days 行；None/0 返回全部。

    性能：原始 CSV 解析（约 4771 行）按文件 mtime 缓存 1h；文件未变则命中，
    写入新历史即自动失效。市场情绪/状态机/全景等页在 st_autorefresh 下每 30~60s
    触发一次 get_shepherd_indicators，此前每次都重新 parse 全量 CSV，是广度页的主要
    CPU 浪费来源之一。返回副本，避免调用方改到缓存中的可变对象。
    """
    try:
        if not os.path.exists(_resolve('_HISTORY_FILE')):
            return None
        mtime = os.path.getmtime(_resolve('_HISTORY_FILE'))
        full = _resolve('_cached')(_resolve('_HISTORY_TTL'), f'hist_csv_{mtime}', _resolve('_parse_history_csv_full'))
        if full is None:
            return None
        if days and days > 0 and (len(full) > days):
            return full.tail(days).reset_index(drop=True).copy()
        return full.copy()
    except Exception as e:
        _resolve('logger').warning('[shepherd] 长历史 CSV 读取失败: %s', e)
        return None

def get_shepherd_history(days=60):
    """历史回测（TTL 缓存 1h）。

    - days >= 2000：读取持久 CSV 长历史（2007 起，由全 A 重构生成）；
    - 否则（中段视图，如近1年/近60日）：2026-11-01 修复「近1年只有 ~90 行」——
      此前中段全走实时涨停池回测，被 _MAX_HISTORY_DAYS=90 截断，preset 承诺
      250 交易日实际只给约 4.5 个月；改为优先 CSV 尾部 days 行 + 实时缺口拼接
      （近期以真实涨停池为准），CSV 不可用才走实时回测，再失败降级 CSV 尾部。
    """
    long_mode = days is not None and days >= 2000
    if long_mode:
        df = _resolve('_read_history_csv')(days)
        if df is not None and (not df.empty):
            return _resolve('_merge_recent_realtime')(df, None, None)
        _resolve('logger').warning('[shepherd] 长历史 CSV 不可用，返回空')
        return _resolve('pd').DataFrame(columns=['date'])
    df = _resolve('_read_history_csv')(days)
    if df is not None and (not df.empty):
        return _resolve('_merge_recent_realtime')(df, None, None)
    try:
        df = _resolve('_cached')(_resolve('_HISTORY_TTL'), f'shep_hist_{days}', lambda: _resolve('_fetch_shepherd_history')(days))
        if df is not None and (not df.empty):
            return df
    except Exception as e:
        _resolve('logger').warning('[shepherd] 历史回测失败，尝试 CSV 降级: %s', e)
    df = _resolve('_read_history_csv')(days)
    if df is not None and (not df.empty):
        return df
    return _resolve('pd').DataFrame(columns=['date'])

def get_shepherd_indicators(days=60):
    """统一入口：返回 (df, meta)。

    df：历史宽表（date + 各指标列），用于折线图；末行即最新值，可用于卡片。
    meta：{available, unavailable, _cache_fallback}。
    """
    df = _resolve('get_shepherd_history')(days)
    meta = {'available': [], 'unavailable': [], '_cache_fallback': False}
    if df is None or df.empty:
        meta['unavailable'] = [(k, '历史回测暂不可用（网络受限）') for k in _resolve('THRESHOLDS')]
        return (df, meta)
    cols = [c for c in _resolve('THRESHOLDS') if c in df.columns]
    meta['available'] = cols
    meta['unavailable'] = [(k, '该日数据源缺失') for k in _resolve('THRESHOLDS') if k not in df.columns]
    return (df, meta)

def _merge_recent_realtime(df, start, end):
    """长历史 CSV 与 akshare 实时涨停池回测的近期缺口拼接（真实值优先，绝不编造）。

    2026-11-01 补全（老板指令「近期的数据都没有，补全」）：data/shepherd_history.csv
    由定时任务追加，末行可能滞后于今天；这段缺口在「全部/自定义」视图断线。
    实时回测（_fetch_shepherd_history，近 _MAX_HISTORY_DAYS 交易日真实涨停池）覆盖该段。
    按日期去重拼接，重叠日以实时回测为准（真实值 > 重构值）；任何失败降级回原 df。
    """
    try:
        if df is not None and (not df.empty) and ('date' in df.columns):
            out = df.copy()
            out['date'] = _resolve('pd').to_datetime(out['date'], errors='coerce')
            out = out.dropna(subset=['date'])
            cut = out['date'].max()
        else:
            out = _resolve('pd').DataFrame(columns=list(df.columns) if df is not None and hasattr(df, 'columns') else ['date'])
            cut = None
        today = _resolve('pd').Timestamp(_resolve('now_cst_naive')()).normalize()
        eff_end = min(_resolve('pd').to_datetime(end), today) if end is not None else today
        base = cut if cut is not None else eff_end - _resolve('pd').Timedelta(days=200)
        gap_days = (eff_end - base).days
        if gap_days <= 0:
            return out
        want = int(min(_resolve('_MAX_HISTORY_DAYS'), max(30, gap_days + 15)))
        recent = _resolve('_cached')(_resolve('_HISTORY_TTL'), f'shep_hist_{want}', lambda: _resolve('_fetch_shepherd_history')(want))
        if recent is None or recent.empty or 'date' not in recent.columns:
            return out
        recent = recent.copy()
        recent['date'] = _resolve('pd').to_datetime(recent['date'], errors='coerce')
        recent = recent.dropna(subset=['date'])
        if start is not None:
            recent = recent[recent['date'] >= _resolve('pd').to_datetime(start)]
        recent = recent[recent['date'] <= eff_end]
        if cut is not None:
            recent = recent[recent['date'] > cut]
        if recent.empty:
            return out
        merged = recent if out.empty else _resolve('pd').concat([out, recent], ignore_index=True)
        merged['date'] = _resolve('pd').to_datetime(merged['date'], errors='coerce')
        merged = merged.sort_values('date').drop_duplicates(subset=['date'], keep='last').reset_index(drop=True)
        _resolve('logger').info('[shepherd] 近期缺口拼接 +%d 行（实时回测，截至 %s）', len(recent), merged['date'].max().date())
        return merged
    except Exception as e:
        _resolve('logger').warning('[shepherd] 近期实时数据拼接失败，返回原序列: %s', e)
        return df if df is not None else _resolve('pd').DataFrame(columns=['date'])

def _trading_days_range(start, end):
    """获取 [start, end] 内的交易日历（日期列表）。"""
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        cal['trade_date'] = _resolve('pd').to_datetime(cal['trade_date'])
        dts = cal[(cal['trade_date'] >= _resolve('pd').to_datetime(start)) & (cal['trade_date'] <= _resolve('pd').to_datetime(end))]['trade_date']
        return dts.tolist()
    except Exception as e:
        _resolve('logger').warning('[shepherd] 交易日历获取失败: %s', e)
        return []

def get_shepherd_history_range(start_date, end_date, backfill=False):
    """按自定义日期范围读取牧羊人历史数据。

    - 优先从 data/shepherd_history.csv 长历史中过滤；
    - backfill=True 时，对范围内缺失的最近交易日（<=15天）尝试用 akshare zt_pool
      补全涨停/连板/炸板/昨日涨停表现字段；
    - 更早的历史缺失列保持 NaN，并在后续 meta 中标记为 unavailable。
    """
    start = _resolve('pd').to_datetime(start_date).normalize()
    end = _resolve('pd').to_datetime(end_date).normalize()
    today = _resolve('pd').Timestamp(_resolve('now_cst_naive')()).normalize()
    df = _resolve('_read_history_csv')(None)
    if df is not None and (not df.empty):
        df = df[(df['date'] >= start) & (df['date'] <= end)].copy()
    if not backfill:
        return df if df is not None and (not df.empty) else _resolve('pd').DataFrame(columns=['date'])
    requested_dates = _resolve('_trading_days_range')(start, end)
    if not requested_dates:
        return df if df is not None and (not df.empty) else _resolve('pd').DataFrame(columns=['date'])
    if df is not None and (not df.empty):
        existing = set(df['date'].dt.date)
        missing_dates = [d for d in requested_dates if d.date() not in existing]
    else:
        missing_dates = requested_dates
    recent_missing = [d for d in missing_dates if (today - d).days <= 15]
    if recent_missing:
        try:
            from modules.shepherd_reconstruct import fetch_zt_data_for_dates as _fetch_zt_range
            zt_df = _fetch_zt_range([d.strftime('%Y-%m-%d') for d in recent_missing])
            if zt_df is not None and (not zt_df.empty):
                if df is None or df.empty:
                    df = zt_df
                else:
                    df = _resolve('pd').concat([df, zt_df], ignore_index=True)
                    df['date'] = _resolve('pd').to_datetime(df['date'])
                    df = df.sort_values('date').drop_duplicates(subset=['date'], keep='last').reset_index(drop=True)
        except Exception as e:
            _resolve('logger').warning('[shepherd] 补算近期缺失 zt 数据失败: %s', e)
    return df if df is not None and (not df.empty) else _resolve('pd').DataFrame(columns=['date'])

def get_shepherd_indicators_range(start_date, end_date, backfill=False):
    """按自定义日期范围返回牧羊人指标 (df, meta)。

    meta 包含：
        date_range: (start, end)
        missing_columns: {col: reason} —— 所选时段内全为 NaN 的列
        unavailable: [(col, reason)] —— 数据源未覆盖的列
    """
    df = _resolve('get_shepherd_history_range')(start_date, end_date, backfill=backfill)
    df = _resolve('_merge_recent_realtime')(df, start_date, end_date)
    meta = {'available': [], 'unavailable': [], '_cache_fallback': False, 'date_range': (str(start_date), str(end_date)), 'missing_columns': {}}
    if df is None or df.empty or 'date' not in df.columns:
        meta['unavailable'] = [(k, '所选日期范围暂无数据（未开始统计或数据源未覆盖）') for k in _resolve('THRESHOLDS')]
        return (df, meta)
    cols = [c for c in _resolve('THRESHOLDS') if c in df.columns]
    meta['available'] = cols
    for c in _resolve('THRESHOLDS'):
        if c not in df.columns:
            meta['unavailable'].append((c, '该时段数据源未覆盖，未开始统计'))
            continue
        non_na = _resolve('pd').to_numeric(df[c], errors='coerce').notna().sum()
        if non_na == 0:
            meta['missing_columns'][c] = '所选时段内该指标全为缺失'
        elif non_na < len(df) * 0.5:
            meta['missing_columns'][c] = f'所选时段内该指标缺失 {len(df) - non_na} 个交易日'
    return (df, meta)

def load_latest_snapshot() -> 'dict | None':
    """读取每日市场快照（离线兜底源），无实时数据时供页面降级使用。

    优先级：
      1) data/daily_snapshot.json（主快照，含 temperature/cycle/bias/confidence 等）；
      2) data/snapshots/ 目录下最新日期的 json 文件（按文件 mtime 取最新）；
    任何异常（文件缺失/解析失败/非预期结构）均返回 None，由调用方自行降级处理。

    诚实边界：快照是离线单点，不提供历史序列；本函数仅读取当前快照，
    绝不编造指数/行业/资金流等离线基座没有的数据。
    """
    candidates = []
    try:
        main = os.path.join(_resolve('_SHEPHERD_DATA_DIR'), 'daily_snapshot.json')
        if os.path.exists(main):
            candidates.append(main)
    except Exception:
        pass
    try:
        snap_dir = os.path.join(_resolve('_SHEPHERD_DATA_DIR'), 'snapshots')
        if os.path.isdir(snap_dir):
            files = [os.path.join(snap_dir, f) for f in os.listdir(snap_dir) if f.endswith('.json') and os.path.isfile(os.path.join(snap_dir, f))]
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            candidates.extend(files)
    except Exception:
        pass
    for path in candidates:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'temperature' in data:
                return data
        except Exception as exc:
            _resolve('logger').warning('[shepherd] 快照读取失败 %s: %s', path, exc)
            continue
    return None

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
    "_fetch_legu",
    "_fetch_zt_pool",
    "_fetch_zbgc_pool",
    "_fetch_prev_pool",
    "_fetch_dt_pool",
    "_get_spot_cached",
    "_resolve",
    "_trading_days",
    "_fetch_shepherd_history",
    "_parse_history_csv_full",
    "_read_history_csv",
    "get_shepherd_history",
    "get_shepherd_indicators",
    "_merge_recent_realtime",
    "_trading_days_range",
    "get_shepherd_history_range",
    "get_shepherd_indicators_range",
    "load_latest_snapshot",
]
