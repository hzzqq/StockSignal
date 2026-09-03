"""
页面C：自选股实时监控
────────────────────────
一览自选股实时现价与涨跌幅（A股红涨绿跌），并行拉取行情，异常自动回退本地源。
支持一键刷新、跳转「形态选股」对自选股做技术体检、跳转「个股分析」做深度诊断。
纯前端聚合，不改动任何主功能逻辑。
"""
import streamlit as st
import streamlit.components.v1 as components
import concurrent.futures as _cf
import requests
import pandas as pd
from datetime import datetime, timedelta
from modules.session import api_get, safe_switch_page, clear_auth, api_delete, api_junk_stocks, api_remove_junk_stock, api_user_score, api_save_user_score, get_token, API_BASE, _rel_time
import modules.scroll_nav as sn
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.autorefresh import st_autorefresh
from modules.page_widgets import UP as _UP, DOWN as _DOWN
from modules.ssl_helper import ssl_bypass as _ssl_bypass
from modules.page_widgets import _empty_info, _toast
from modules.fundamental_helpers import calc_alr, fund_one
from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page, get_fetcher
from modules.ui_theme import sf_card, sf_metric
from modules.ui_kit import xc_success_box, xc_warn_box
dark = render_standard_page(title='自选股监控', icon='📡', caption='实时跟踪自选股现价与涨跌幅；行情接口异常时自动回退本地源。数据仅供参考，非投资建议。', layout='wide')

sf_card("自选股监控导读", "一览自选股实时现价与涨跌幅（A股红涨绿跌），交易时段自动刷新；可一键跳转形态选股做技术体检或个股分析做深度诊断。", icon="📡")

def _is_trading_now():
    from modules.page_widgets import is_trading_now as _itn
    return _itn()
with st.expander('💡 使用说明', expanded=False, key='wl_help_exp'):
    st.markdown('**本页能做什么？**\n- 📡 **实时监控**：并行拉取自选股实时现价与涨跌幅（A股红涨绿跌）。\n- 🔄 **自动刷新**：交易时段每 60 秒自动刷新行情；也可点「🔄 刷新行情」手动刷新。\n- 🧭 **技术体检**：一键跳转「形态选股」用自选股池做技术扫描。\n- 🔔 **价格预警**：跳转「价格预警」页为关注的标的设置异动提醒。\n\n**常见问题**\n- *行情显示 — ？* 接口/网络异常时自动回退本地源；若仍无数据，请检查网络后稍候自动刷新。\n- *颜色含义？* 红涨绿跌为 A股惯例，本页严格遵循，不会被主题切换修改。\n- *行情更新时间？* 页面底部标注最近行情时间与本页刷新时间。')
fetcher = get_fetcher()

def _quote_one(code: str, token: str | None=None):
    """并行取单只实时行情：优先后端 /api/quote，失败回退本地 fetcher。

    注意：本函数运行在线程池中，不能调用任何 st.xxx（包括 get_token/session_state），
    否则子线程无 ScriptRunContext 会拿不到登录态（token=None → 误判 401 登出）。
    因此 token 必须由主线程 get_token() 取出后作为参数传入。
    """
    try:
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        resp = requests.get(f'{API_BASE}/api/quote?ticker={code}', headers=headers, timeout=5)
        if resp.status_code == 401:
            return (code, {'__auth_error': True})
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict) and body.get('status') == 'ok':
                data = body.get('data')
                if isinstance(data, dict) and data.get('current'):
                    return (code, data)
    except Exception:
        pass
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict) and q.get('current'):
            return (code, q)
    except Exception:
        pass
    return (code, None)

def _quote_batch(codes, token):
    """R90：优先批量接口（1 次网络往返替代 N 次 /api/quote），失败代码本地回退。

    返回 (quotes_dict, has_auth_error)。批量接口每只失败返回 None，由调用方渲染空态。
    """
    quotes = {}
    has_auth_error = False
    if not codes:
        return (quotes, has_auth_error)
    try:
        import urllib.parse as _up
        _qs = _up.urlencode({'tickers': ','.join(codes)})
        _sc, _body = api_get(f'/api/quote/batch?{_qs}', timeout=10)
        if _sc == 200 and isinstance(_body, dict) and (_body.get('status') == 'ok'):
            data = _body.get('data') or {}
            batch_quotes = data.get('quotes') or {}
            for code, q in batch_quotes.items():
                if isinstance(q, dict) and q.get('__auth_error'):
                    has_auth_error = True
                    quotes[code] = q
                elif isinstance(q, dict) and 'error' not in q and q.get('current'):
                    quotes[code] = q
    except Exception:
        pass
    missing = [c for c in codes if c not in quotes]
    if missing:
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            for code, q in ex.map(lambda c: _quote_one(c, token), missing):
                if q is not None:
                    quotes[code] = q
    return (quotes, has_auth_error)

@st.cache_data(show_spinner=False, ttl=3600)
def _resolve_name(code: str) -> str:
    """本地库兜底解析股票中文名；返回空串表示未知。"""
    try:
        return fetcher.get_stock_basic(code)[1] or ''
    except Exception:
        return ''

def _calc_alr(code: str):
    """委托 fundamental_helpers.calc_alr（#545-16 消除与 A_每日晨报 的逐字重复）。"""
    return calc_alr(code, fetcher)

def _fund_one(code: str):
    """委托 fundamental_helpers.fund_one（#545-16 消除重复）。"""
    return fund_one(code, fetcher)

def _fmt_amount(v):
    """成交额格式化：元 → 亿/万 单位，给长数字加可读边界（None/NaN 显示 —）。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    if v >= 100000000.0:
        return f'{v / 100000000.0:.2f}亿'
    if v >= 10000.0:
        return f'{v / 10000.0:.2f}万'
    return f'{v:.0f}'

@safe_fragment
def fragment_watchlist_monitor():
    if _is_trading_now():
        st_autorefresh(interval=60 * 1000, key='watchlist_autorefresh')
    sc, body = api_get('/api/watchlist', timeout=10)
    if sc != 200 or not isinstance(body, dict) or body.get('status') != 'ok':
        st.error('⚠️ 加载失败，请稍后重试')
        if st.button('🔄 重试', key='wl_load_retry'):
            st.rerun(scope='fragment')
        return
    items = body.get('data', []) or []
    if not items:
        _empty_info('自选股为空，请先到「行情看板 / 我的」添加，或前往「形态选股」用自选股池扫描。')
        c1, c2 = st.columns(2)
        with c1:
            if st.button('➡️ 去形态选股', width="stretch", key='wl_empty_go'):
                safe_switch_page('pages/31_形态选股.py')
        with c2:
            if st.button('📘 看新手教程', width="stretch", key='wl_empty_tut'):
                safe_switch_page('pages/96_新手教程.py')
        return
    codes = [it.get('stock_code') for it in items if isinstance(it, dict) and it.get('stock_code')]
    names = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        _fut_map = {ex.submit(fetcher.get_name_only, code): code for code in codes}
        for _fut in _cf.as_completed(_fut_map):
            _c = _fut_map[_fut]
            try:
                names[_c] = _fut.result() or _c
            except Exception:
                names[_c] = _c
    with st.spinner(f'并行获取 {len(codes)} 只自选股实时行情…'):
        quotes = {}
        _tok = get_token()
        quotes, _has_auth_err = _quote_batch(codes, _tok)
    if _has_auth_err or any((isinstance(q, dict) and q.get('__auth_error') for q in quotes.values())):
        clear_auth()
        xc_warn_box('🔐 登录已过期，请重新登录')
        return
    fund_map = {}
    if codes:
        from modules.fetch_parallel import fetch_many
        with st.spinner('并行获取市盈率与资产负债率…'):
            with _ssl_bypass():
                raw = fetch_many([(c, lambda code=c: _fund_one(code)) for c in codes], max_workers=4, timeout=15)
        for c in codes:
            r = raw.get(c)
            fund_map[c] = (r[1], r[2]) if isinstance(r, (tuple, list)) and len(r) >= 3 else (None, None)
    rows = []
    quote_times = []
    for code in codes:
        q = quotes.get(code)
        if q and q.get('current'):
            cur = float(q['current'])
            prev = float(q.get('prev_close') or 0)
            high = float(q.get('high') or 0)
            low = float(q.get('low') or 0)
            volume = int(q.get('volume') or 0)
            amount = float(q.get('amount') or 0)
            chg = (cur - prev) / prev * 100 if prev else 0.0
            change_amt = cur - prev if prev else 0.0
            amplitude = (high - low) / prev * 100 if prev else 0.0
            name = (q.get('name') if q.get('name') else None) or names.get(code) or _resolve_name(code) or code
            qt = q.get('datetime')
            if qt:
                quote_times.append(str(qt))
        else:
            cur = chg = change_amt = amplitude = volume = amount = None
            name = names.get(code) or _resolve_name(code) or code
        pe, alr = fund_map.get(code, (None, None))
        tag = ''
        if chg is not None:
            if abs(chg) >= 5:
                tag += '🔥热门 '
            if amplitude is not None and amplitude >= 6:
                tag += '📊异动'
        rows.append({'code': code, 'name': name, 'cur': cur, 'chg': chg, 'change_amt': change_amt, 'amplitude': amplitude, 'volume': volume, 'amount': amount, 'pe_ttm': f'{pe:.2f}' if isinstance(pe, (int, float)) and (not pd.isna(pe)) else '—', 'alr': f'{alr:.2f}%' if isinstance(alr, (int, float)) and (not pd.isna(alr)) else '—', 'tag': tag})
    st.caption('交易时段每 60 秒自动刷新；涨跌颜色遵循 A股 惯例：红涨绿跌。点击下方选择框可跳转个股研究页。')
    st.caption('数据来源：实时行情（新浪财经 / 东方财富）、财务数据（新浪财经）')
    up_n = sum((1 for r in rows if r['chg'] is not None and r['chg'] >= 0))
    down_n = sum((1 for r in rows if r['chg'] is not None and r['chg'] < 0))
    st.markdown(f"#### 共 {len(rows)} 只自选股 ｜ <span style='color:{_UP};font-weight:600;'>▲ {up_n}</span> ／ <span style='color:{_DOWN};font-weight:600;'>▼ {down_n}</span>", unsafe_allow_html=True)
    if quote_times:
        st.caption(f'🕒 行情更新于 {_rel_time(min(quote_times))}')
    ok_n = sum((1 for r in rows if r['cur'] is not None))
    if codes and ok_n == 0:
        xc_warn_box('⚠️ 实时行情暂时获取失败（接口/网络异常），已尝试回退本地源仍无数据；下表为持仓快照，行情相关列显示 —，交易时段将自动刷新或稍后重试。')
    if rows:
        df_rt = pd.DataFrame(rows)
        display_df = df_rt[['name', 'code', 'cur', 'change_amt', 'chg', 'amplitude', 'volume', 'amount', 'pe_ttm', 'alr', 'tag']].copy()
        display_df.rename(columns={'name': '名称', 'code': '代码', 'cur': '现价', 'change_amt': '涨跌额', 'chg': '涨跌%', 'amplitude': '振幅%', 'volume': '成交量', 'amount': '成交额', 'pe_ttm': '市盈率(TTM)', 'alr': '资产负债率', 'tag': '标记'}, inplace=True)
        display_df['成交额'] = display_df['成交额'].apply(_fmt_amount)

        def _chg_color(v):
            try:
                x = float(v)
            except Exception:
                return ''
            if x > 0:
                return 'color:{_UP};font-weight:600'
            if x < 0:
                return 'color:{_DOWN};font-weight:600'
            return 'color:#9aa0a6'
        _styled = display_df.style.map(_chg_color, subset=['涨跌额', '涨跌%'])
        st.dataframe(_styled, width="stretch", height=max(200, min(480, 40 + len(rows) * 38)), column_config={'现价': st.column_config.NumberColumn(format='¥%.2f'), '涨跌额': st.column_config.NumberColumn(format='%.2f'), '涨跌%': st.column_config.NumberColumn(format='%.2f%%'), '振幅%': st.column_config.NumberColumn(format='%.2f%%'), '成交量': st.column_config.NumberColumn(format='%d')})
        opts = [f"{r['code']} {r['name']}" for r in rows if r['cur'] is not None]
        if opts:
            sel = st.selectbox('选择股票查看 K 线', ['— 请选择 —'] + opts, key='watch_rt_jump')
            if sel and sel != '— 请选择 —':
                code = sel.split()[0]
                st.session_state['pick_stock_confirmed'] = code
                st.session_state['pick_stock_query'] = code
                safe_switch_page('pages/24_个股研究.py')
        _fav_set = st.session_state.setdefault('_wl_fav_set', set())
        _fav_sel = st.selectbox('⭐ 选择要收藏/取消收藏的标的', ['— 请选择 —'] + opts, key='wl_fav_pick')
        if st.button('🔖 切换收藏状态', key='wl_fav_toggle', width="stretch"):
            if _fav_sel and _fav_sel != '— 请选择 —':
                _fc = _fav_sel.split()[0]
                if _fc in _fav_set:
                    _fav_set.discard(_fc)
                else:
                    _fav_set.add(_fc)
        _fav_list = [c for c in codes if c in _fav_set]
        if _fav_list:
            st.markdown('**⭐ 我的收藏**')
            _fc_cols = st.columns(min(len(_fav_list), 6))
            for _i, _fc_code in enumerate(_fav_list[:6]):
                with _fc_cols[_i]:
                    if st.button(f'📈 {_fc_code}', key=f'wl_fav_{_fc_code}', width="stretch"):
                        st.session_state['pick_stock_confirmed'] = _fc_code
                        st.session_state['pick_stock_query'] = _fc_code
                        safe_switch_page('pages/24_个股研究.py')
    else:
        _empty_info('暂无可展示的实时行情（可能行情接口暂时未返回数据）。自选股列表非空但取数失败，稍候自动刷新，或检查网络后重试。')
    if rows:
        export_df = pd.DataFrame(rows)[['code', 'name', 'cur', 'change_amt', 'chg', 'amplitude', 'volume', 'amount', 'pe_ttm', 'alr']].rename(columns={'code': '代码', 'name': '名称', 'cur': '现价', 'change_amt': '涨跌额', 'chg': '涨跌%', 'amplitude': '振幅%', 'volume': '成交量', 'amount': '成交额', 'pe_ttm': '市盈率TTM', 'alr': '资产负债率'})
        csv_data = export_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button('⬇️ 导出自选股 CSV', data=csv_data, file_name=f'自选股_{datetime.now():%Y%m%d_%H%M%S}.csv', mime='text/csv', width="stretch", key='wl_export_csv')
        with st.expander('📋 复制全部自选股代码', expanded=False):
            st.code('\n'.join(codes), language='text')
            st.caption('点击代码块右上角复制按钮即可一次性复制所有自选股代码。')
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button('🔄 刷新行情', type='primary', width="stretch", key='wl_refresh'):
            pass
    with col_b:
        if st.button('🧭 用自选股做技术体检', width="stretch", key='wl_tech_check'):
            safe_switch_page('pages/31_形态选股.py')
    if st.button('🔔 去设价格预警', width="stretch", key='wl_goto_alert'):
        safe_switch_page('pages/47_价格预警.py')
    data_time = max(quote_times) if quote_times else '—'
    refresh_tag = ' ｜ 🔴 交易时段每 60 秒自动刷新' if _is_trading_now() else ''
    st.caption(f"行情时间：{(_rel_time(data_time) if data_time != '—' else '—')} ｜ 本页刷新：{datetime.now().strftime('%H:%M:%S')} ｜ 红涨绿跌（A股惯例）{refresh_tag}")
fragment_watchlist_monitor()
sf_card('📂 股票池管理', '维护自选股分组与股票池，支持批量添加 / 移除与一键盯盘。')

def _norm_code(c: str) -> str:
    if not c:
        return ''
    c = str(c).strip().lower()
    for p in ('sh', 'sz', 'bj'):
        if c.startswith(p):
            c = c[len(p):]
    return c[-6:] if len(c) > 6 else c

def _kline_thread_safe(code: str, start: str, end: str, period: str='daily', adjust: str='qfq', token: str | None=None):
    """线程安全的 K 线获取：直接走 requests，避免 api_kline 在线程内调 safe_switch_page。

    token 须由主线程传入：子线程无 ScriptRunContext，get_token() 会返回 None → 误判 401。
    """
    try:
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        params = f'symbol={code}&start={start}&period={period}&adjust={adjust}'
        if end:
            params += f'&end={end}'
        resp = requests.get(f'{API_BASE}/api/kline?{params}', headers=headers, timeout=8)
        if resp.status_code == 401:
            return {'__auth_error': True}
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict) and body.get('status') == 'ok':
                data = body.get('data')
                if isinstance(data, list) and data:
                    return data
    except Exception:
        pass
    return None

def _analyze_one(code: str, start: str, end: str, token: str | None=None):
    """获取单股 K 线并计算技术指标；失败返回 None。token 由主线程传入。"""
    try:
        records = _kline_thread_safe(code, start=start, end=end, period='daily', token=token)
        if isinstance(records, dict) and records.get('__auth_error'):
            return {'__auth_error': True}
        d = pd.DataFrame(records) if records else fetcher.get_kline(code, start=start, end=end, period='daily')
        if d is None or d.empty:
            return None
        d = DataCleaner.full_pipeline(d)
        if len(d) < 5:
            return None
        profile = SignalEngine().technical_profile(d)
        analysis = technical_full_analysis(d)
        latest = d.iloc[-1]
        prev = d.iloc[-2]
        cur = float(latest['close'])
        chg = (cur / float(prev['close']) - 1) * 100 if prev['close'] else 0.0
        vol_ratio = analysis.get('volume', {}).get('vol_ratio', 1.0)
        return {'code': code, 'name': fetcher.get_name_only(code), 'price': cur, 'change_pct': chg, 'short': profile['short'], 'mid': profile['mid'], 'long': profile['long'], 'composite': profile['composite'], 'trend_score': analysis.get('trend', {}).get('trend_score', 50), 'vol_ratio': vol_ratio}
    except Exception:
        return None

def _load_scores_map(codes: list) -> dict:
    """批量拉取当前用户对所有 code 的打分。"""
    scores = {}
    try:
        status, body = api_get('/api/user-scores', timeout=5)
        if status == 200 and isinstance(body, dict) and (body.get('status') == 'ok'):
            for r in body.get('data', []):
                if isinstance(r, dict):
                    scores[_norm_code(r.get('stock_code', ''))] = int(r.get('score', 0))
    except Exception:
        pass
    return scores

def _build_pool_df(codes: list, scores_map: dict) -> pd.DataFrame | None:
    """并行计算股票池技术指标。返回 None 表示线程内检测到 401 认证过期。"""
    end = datetime.now().date()
    start = end - timedelta(days=120)
    start_s, end_s = (start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    rows = []
    auth_error = False
    _tok = get_token()
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_analyze_one, c, start_s, end_s, _tok): c for c in codes}
        for fut in _cf.as_completed(futs):
            res = fut.result()
            if isinstance(res, dict) and res.get('__auth_error'):
                auth_error = True
                continue
            if res:
                code = res['code']
                res['user_score'] = scores_map.get(code)
                rows.append(res)
    if auth_error:
        return None
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def _render_pool_table(df: pd.DataFrame | None, pool_key: str, on_remove):
    """渲染可排序、可跳转、可改评分的股票池表格。"""
    if df is None:
        xc_warn_box('🔐 登录状态已过期，请刷新页面或重新登录。')
        return
    if df.empty:
        _empty_info('暂无数据')
        return
    display = df[['code', 'name', 'price', 'change_pct', 'short', 'mid', 'long', 'composite', 'trend_score', 'vol_ratio', 'user_score']].copy()
    display.rename(columns={'code': '代码', 'name': '名称', 'price': '现价', 'change_pct': '涨跌%', 'short': '短期', 'mid': '中期', 'long': '长期', 'composite': '综合', 'trend_score': '趋势分', 'vol_ratio': '量比', 'user_score': '用户打分'}, inplace=True)

    def _chg_color(v):
        try:
            x = float(v)
        except Exception:
            return ''
        if x > 0:
            return 'color:{_UP};font-weight:600'
        if x < 0:
            return 'color:{_DOWN};font-weight:600'
        return 'color:#9aa0a6'
    _styled = display.style.map(_chg_color, subset=['涨跌%'])
    st.dataframe(_styled, width="stretch", height=360, column_config={'涨跌%': st.column_config.NumberColumn(format='%.2f%%'), '现价': st.column_config.NumberColumn(format='¥%.2f'), '量比': st.column_config.NumberColumn(format='%.2fx')})
    st.caption(f'共 {len(df)} 只股票池标的')
    st.caption('涨跌颜色遵循 A股惯例：红涨绿跌。综合/短期/中期/长期为技术评分（0–100，越高越强）。')
    opts = [f"{r['code']} {r['name']}" for _, r in df.iterrows()]
    selected = st.selectbox('点击选择股票跳转 K 线', ['— 请选择 —'] + opts, key=f'{pool_key}_jump')
    if selected and selected != '— 请选择 —':
        code = selected.split()[0]
        st.session_state['pick_stock_confirmed'] = code
        st.session_state['pick_stock_query'] = code
        safe_switch_page('pages/24_个股研究.py')
    st.markdown('**✏️ 修改用户打分**')
    st.caption('评分范围 0–100，越高越看好；拖动滑块选择，无法输入越界值。')
    with st.form(key=f'{pool_key}_score_form'):
        c1, c2, c3 = st.columns([0.4, 0.4, 0.2])
        with c1:
            edit_code = st.selectbox('选择股票', ['—'] + opts, key=f'{pool_key}_edit_code')
        with c2:
            existing = None
            if edit_code and edit_code != '—':
                _raw_score = api_user_score(edit_code.split()[0])
                try:
                    existing = int(_raw_score)
                except (TypeError, ValueError):
                    existing = None
            edit_score = st.slider('新评分', min_value=0, max_value=100, value=existing if existing is not None else 50, step=1, key=f'{pool_key}_edit_score', help='拖动选择 0–100 之间的整数')
        with c3:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button('保存', width="stretch")
        if submitted:
            if edit_code and edit_code != '—':
                code = edit_code.split()[0]
                name = edit_code.split(maxsplit=1)[1] if ' ' in edit_code else ''
                api_save_user_score(code, int(edit_score), name)
                _toast('评分已更新')
            else:
                xc_warn_box('请先选择一只股票')
    if on_remove:
        st.markdown('**🗑️ 移除股票**')
        remove_opts = [f"{r['code']} {r['name']}" for _, r in df.iterrows()]
        rem = st.selectbox('选择要移除的股票', ['—'] + remove_opts, key=f'{pool_key}_remove')
        if rem and rem != '—':
            if st.button('确认移除', key=f'{pool_key}_remove_btn'):
                on_remove(rem.split()[0])

@safe_fragment
def fragment_pool_watchlist():
    with st.expander('📌 自选股列表', expanded=False):
        sc, body = api_get('/api/watchlist')
        wl_items = []
        if sc == 200 and isinstance(body, dict) and (body.get('status') == 'ok'):
            wl_items = body.get('data', []) or []
        if not wl_items:
            _empty_info('自选股为空。先到「股票选取」页面点击「加入自选股」添加。')
        else:
            codes = [_norm_code(it['stock_code']) for it in wl_items if isinstance(it, dict) and it.get('stock_code')]
            id_map = {_norm_code(it['stock_code']): it.get('id') for it in wl_items if isinstance(it, dict) and it.get('stock_code')}
            scores = _load_scores_map(codes)
            with st.spinner('正在计算自选股池技术指标…'):
                df_wl = _build_pool_df(codes, scores)

            def _remove_wl(code: str):
                item_id = id_map.get(_norm_code(code))
                if item_id:
                    api_delete(f'/api/watchlist/{item_id}', timeout=5)
                    _toast('已移除')
            _render_pool_table(df_wl, 'watchlist', _remove_wl)
fragment_pool_watchlist()

@safe_fragment
def fragment_pool_junk():
    with st.expander('🗑️ 垃圾股列表', expanded=False):
        junk_items = api_junk_stocks()
        if not junk_items:
            _empty_info('垃圾股为空。先到「股票选取」页面点击「加入垃圾股」添加。')
        else:
            codes = [_norm_code(it['stock_code']) for it in junk_items if isinstance(it, dict) and it.get('stock_code')]
            id_map = {_norm_code(it['stock_code']): it.get('id') for it in junk_items if isinstance(it, dict) and it.get('stock_code')}
            scores = _load_scores_map(codes)
            with st.spinner('正在计算垃圾股池技术指标…'):
                df_jk = _build_pool_df(codes, scores)

            def _remove_jk(code: str):
                item_id = id_map.get(_norm_code(code))
                if item_id:
                    api_remove_junk_stock(item_id)
                    _toast('已移除')
            _render_pool_table(df_jk, 'junk', _remove_jk)
fragment_pool_junk()
sf_card('🔗 相关标的推荐', '基于常见关注方向给出的示例标的，点击跳转个股研究页（纯前端推荐，不构成投资建议）。')
st.caption('基于常见关注方向给出的示例标的，点击跳转个股研究页（纯前端推荐，不构成投资建议）。')
_c_rec = [('600519', '贵州茅台'), ('000858', '五粮液'), ('601012', '隆基绿能'), ('300059', '东方财富'), ('600036', '招商银行')]
_c_cols = st.columns(len(_c_rec))
for _i, (_c, _n) in enumerate(_c_rec):
    with _c_cols[_i]:
        if st.button(f'{_n} {_c}', key=f'wl_rec_{_c}', width="stretch"):
            st.session_state['pick_stock_confirmed'] = _c
            st.session_state['pick_stock_query'] = _c
            safe_switch_page('pages/24_个股研究.py')
if st.button('↑ 回到顶部', key='wl_back_to_top'):
    sn.back_to_top_button()