"""持仓中心渲染主体（P0-1 契约抽取产物，2026-10-30）。

承载原 pages/46_自选股监控.py、pages/40_仓位管理.py、pages/41_组合收益.py 的页面语句
（docstring 后全部顶层语句原序搬入，imports 留在函数体内原位；装饰器随调用重建，与原
exec 每次 rerun 重新执行语义一致——同 modules/stock_research.py 先例）。子页文件保留为
独立入口 shim，safe_switch_page / page_link 直跳不受影响。勿在模块级新增其它逻辑。
"""


def render_watchlist_monitor() -> None:
    import streamlit as st
    import streamlit.components.v1 as components
    import concurrent.futures as _cf
    import logging
    import requests
    import pandas as pd
    from datetime import datetime, timedelta
    from modules.session import api_get, safe_switch_page, clear_auth, api_delete, api_junk_stocks, api_remove_junk_stock, api_user_score, api_save_user_score, get_token, API_BASE, _rel_time
    import modules.scroll_nav as sn
    from modules.cleaner import DataCleaner
    from modules.technical import full_analysis as technical_full_analysis
    from modules.signal import SignalEngine
    from modules.page_widgets import UP as _UP, DOWN as _DOWN
    from modules.ssl_helper import ssl_bypass as _ssl_bypass
    from modules.page_widgets import _empty_info, _toast
    from modules.fundamental_helpers import calc_alr, fund_one
    from modules.page_guard import safe_fragment
    from modules.page_utils import render_standard_page, get_fetcher, latest_quote_time
    from modules.ui_theme import sf_card, sf_metric
    from modules.ui_kit import xc_success_box, xc_warn_box

    logger = logging.getLogger(__name__)
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
        except Exception as exc:  # noqa: BLE001
            # T-317：后端取价失败静默转本地回退——降级链本身良性（有 fallback），
            # 但零留痕会让用户看到空态时无法判断「接口挂了」还是「真的没行情」。
            logger.warning("[自选股监控] 后端 /api/quote 取价失败，回退本地 fetcher: %s", exc)
        try:
            q = fetcher.get_realtime_quote(code)
            if isinstance(q, dict) and q.get('current'):
                return (code, q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[自选股监控] 本地 fetcher 取价失败（%s）: %s", code, exc)
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
        except Exception as e:
            print(f"[R-01] batch_quotes 批量取行情失败: {e}")
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

    @safe_fragment(run_every=60 if _is_trading_now() else None)
    def fragment_watchlist_monitor():
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
            st.caption(f'🕒 行情更新于 {_rel_time(latest_quote_time(quote_times))}')
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
            if st.button('🔄', type='primary', key='wl_refresh', help='刷新行情：重新拉取自选股最新行情'):
                pass
        with col_b:
            if st.button('🧭 用自选股做技术体检', width="stretch", key='wl_tech_check'):
                safe_switch_page('pages/31_形态选股.py')
        if st.button('🔔 去设价格预警', width="stretch", key='wl_goto_alert'):
            safe_switch_page('pages/47_价格预警.py')
        data_time = latest_quote_time(quote_times)
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
        except Exception as e:
            print(f"[R-01] _analyze_one K线取数失败 code={code}: {e}")
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
        except Exception as e:
            # T-205：用户打分取数失败曾静默吞——打分将静默显示为缺失
            logger.warning(f"[自选股监控] 用户打分取数失败，打分将显示为空: {e}")
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


def render_position_manager() -> None:
    import os
    import json
    import logging
    import streamlit as st
    import streamlit.components.v1 as components
    import pandas as pd
    from datetime import datetime
    from modules.page_utils import render_standard_page
    from modules.ui_theme import sf_card, sf_metric
    from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner
    render_standard_page(title='仓位管理', icon='💰', caption='⚠️ 本页为模拟/历史持仓管理，仅供学习，不构成投资建议。', layout='wide')


    _c1, _c2 = st.columns(2)
    with _c1:
        st.page_link('pages/42_模拟交易.py', label='🎮 前往模拟交易', icon='🎮')
    with _c2:
        st.page_link('pages/41_组合收益.py', label='📈 前往组合收益', icon='📈')
    if st.button('🔄', key='pm_refresh_top', help='刷新：重新加载本页持仓与行情'):
        st.rerun()
    st.session_state.setdefault('_pm_recent', [])
    _PM_PREF_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pm_prefs.json')
    logger = logging.getLogger(__name__)

    def _load_pm_pref(k, d):
        try:
            if os.path.exists(_PM_PREF_PATH):
                return json.load(open(_PM_PREF_PATH, encoding='utf-8')).get(k, d)
        except Exception as e:
            logger.warning(f"[R-01] _load_pm_pref 读取偏好失败: {e}")
            pass
        return d

    def _save_pm_pref(k, v):
        try:
            _d = {}
            if os.path.exists(_PM_PREF_PATH):
                _d = json.load(open(_PM_PREF_PATH, encoding='utf-8'))
            _d[k] = v
            json.dump(_d, open(_PM_PREF_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        except Exception as e:
            # T-160：偏好写盘失败留痕——静默吞掉会让用户以为设置已保存
            logger.warning('[pm] 仓位偏好写盘失败(%s): %s', _PM_PREF_PATH, e)
    from modules.portfolio import PortfolioManager
    from modules.search_ui import stock_search_input
    from modules.fetcher import StockFetcher
    from modules.session import api_quote, api_kline
    from modules.page_widgets import _empty_info, _toast
    from modules.format_helpers import safe_int

    def _fmt_money(x, prefix='¥', nd=2):
        try:
            v = float(x)
        except Exception:
            return f'{prefix}—'
        if v != v:
            return f'{prefix}—'
        if v in (float('inf'), float('-inf')):
            return f'{prefix}—'
        return f'{prefix}{v:,.{nd}f}'

    def _fmt_signed_pct(x, nd=2):
        try:
            v = float(x)
        except Exception:
            return '—'
        if v != v:
            return '—'
        if v in (float('inf'), float('-inf')):
            return '—'
        return f'{v:+.{nd}f}%'

    def _fmt_int(x):
        try:
            v = float(x)
        except Exception:
            return '—'
        if v != v:
            return '—'
        return f'{int(v):,}'

    def _fmt_rel(ts):
        from datetime import datetime
        try:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace('Z', ''))
            elif hasattr(ts, 'to_pydatetime'):
                ts = ts.to_pydatetime()
            sec = (datetime.now() - ts).total_seconds()
            if sec < 60:
                return '刚刚'
            if sec < 3600:
                return f'{int(sec // 60)}分钟前'
            if sec < 86400:
                return f'{int(sec // 3600)}小时前'
            return f'{int(sec // 86400)}天前'
        except Exception:
            return str(ts) if ts is not None else ''
    pm = PortfolioManager()
    fetcher = StockFetcher()
    if 'default_shares' not in st.session_state:
        st.session_state.default_shares = _load_pm_pref('default_shares', 1000)

    def format_quote_table(quote):
        """把实时行情格式化成买卖盘 DataFrame。

        加法式健壮性：行情接口（api_quote / get_realtime_quote）返回结构不稳定，
        可能缺 bid/ask 或档位不足 5 档、字段非数值。原实现直接下标访问会抛 KeyError/TypeError，
        导致整个买入/卖出表单崩溃。这里对缺失键、档位不足、字段类型异常做降级。
        """
        if not quote:
            return None
        bid = quote.get('bid') or []
        ask = quote.get('ask') or []
        if not bid or not ask:
            return None
        rows = []
        for i in range(min(5, len(bid), len(ask))):
            try:
                b = bid[i]
                a = ask[i]
                rows.append({'买盘': f'买{i + 1}', '买价': f"¥{float(b['price']):.2f}", '买量': f"{int(b['volume']):,}", '卖盘': f'卖{i + 1}', '卖价': f"¥{float(a['price']):.2f}", '卖量': f"{int(a['volume']):,}"})
            except (KeyError, TypeError, ValueError):
                continue
        return pd.DataFrame(rows) if rows else None
    sf_card('📊 当前持仓概览', '跟踪所有持仓的买入成本、剩余股数与实时市值；支持搜索与批量加自选 / 平仓。')
    positions = pm.get_positions()
    st.caption(f'📊 当前持仓：共 {len(positions)} 条')
    if positions.empty:
        _empty_info('暂无持仓记录。在上方「添加持仓」表单录入代码、价格与股数后，即可开始跟踪。')
    else:
        display_pos = positions.copy()
        if 'name' in display_pos.columns:
            display_pos = display_pos.drop(columns=['name'])
        display_pos['股票'] = display_pos['ticker'].apply(lambda x: fetcher.get_name_only(x) or fetcher.get_stock_name(x))
        if 'shares' in display_pos.columns:
            display_pos['买入股数'] = display_pos['shares'].apply(_fmt_int)
        if 'remaining_shares' in display_pos.columns:
            display_pos['剩余股数'] = display_pos['remaining_shares'].apply(_fmt_int)
        if 'buy_price' in display_pos.columns:
            display_pos['买入价'] = display_pos['buy_price'].apply(_fmt_money)
        if 'cost' in display_pos.columns:
            display_pos['成本'] = display_pos['cost'].apply(_fmt_money)
        if 'buy_date' in display_pos.columns:
            display_pos['买入日期'] = display_pos['buy_date'].apply(_fmt_rel)
        if 'note' in display_pos.columns:
            display_pos['备注'] = display_pos['note'].fillna('')
        else:
            display_pos['备注'] = ''
        show_cols = ['股票', 'ticker', '买入日期', '买入价', '买入股数', '剩余股数', '成本', '备注']
        show_cols = [c for c in show_cols if c in display_pos.columns]
        _kw = st.text_input('🔍 搜索持仓（代码 / 名称）', key='pm_pos_filter')
        if _kw and _kw.strip():
            _kw = _kw.strip()
            _pmask = display_pos[['股票', 'ticker']].astype(str).apply(lambda col: col.str.contains(_kw, case=False, na=False)).any(axis=1)
            display_pos = display_pos[_pmask]
            if display_pos.empty:
                st.caption('🔍 未找到匹配的持仓。')
        _pshow_key = 'pm_pos_show'
        _pshow_n = st.session_state.get(_pshow_key, 10)
        st.dataframe(display_pos[show_cols].head(_pshow_n), width="stretch", hide_index=True, height=400)
        if len(display_pos) > _pshow_n:
            if st.button('显示更多 ▼', key='pm_pos_more'):
                st.session_state[_pshow_key] = min(_pshow_n + 10, len(display_pos))
        st.markdown('**批量操作（持仓概览）**')
        _pm_sel = []
        if not positions.empty:
            for _n, (_i, _pr) in enumerate(positions.iterrows()):
                _t = _pr['ticker']
                if st.checkbox(f'选择 {_t}', key=f'pm_sel_{_t}_{_n}'):
                    _pm_sel.append(_t)
        if _pm_sel:
            _pb1, _pb2 = st.columns(2)
            with _pb1:
                if st.button('⭐ 批量加自选', key='pm_batch_fav', width="stretch"):
                    try:
                        from modules.admin_api import add_watchlist
                        for _t in _pm_sel:
                            add_watchlist(_t)
                        _toast(f"已加自选：{', '.join(_pm_sel)}")
                    except Exception as e:
                        xc_handle_error("批量加自选失败", e, hint="请稍后重试，或检查网络与数据源连接")
            with _pb2:
                if st.button('📤 批量平仓', key='pm_batch_close', width="stretch"):
                    try:
                        for _t in _pm_sel:
                            _q = api_quote(_t) or fetcher.get_realtime_quote(_t)
                            _p = _q.get('current') if _q else None
                            if _p is None:
                                _ks = (datetime.now() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
                                _ke = datetime.now().strftime('%Y-%m-%d')
                                _rec = api_kline(_t, start=_ks, end=_ke)
                                _pdf = pd.DataFrame(_rec) if _rec is not None else fetcher.get_daily(_t, start=_ks, end=_ke)
                                _p = float(_pdf.iloc[-1]['close']) if _pdf is not None and (not _pdf.empty) else None
                            if _p is None:
                                xc_warn_box(f'无法获取 {_t} 现价，跳过平仓。')
                                continue
                            _ss = pm.get_sellable_shares(_t)
                            if _ss and _ss > 0:
                                pm.sell_position(ticker=_t, sell_date=datetime.now().strftime('%Y-%m-%d'), sell_price=float(_p), sell_shares=int(_ss), note='批量平仓')
                        _toast(f"已批量平仓：{', '.join(_pm_sel)}")
                        st.rerun()
                    except Exception as e:
                        xc_handle_error("批量平仓失败", e, hint="请稍后重试，或检查网络与数据源连接")
    sf_card('➕ 买入股票', '录入代码、价格与股数添加持仓；支持 100 / 500 / 1000 等快捷股数按钮。')
    st.markdown('**⚡ 快捷选择股数：**')
    quick_cols = st.columns(5)
    for col, qv in zip(quick_cols, [100, 500, 1000, 2000, 5000]):
        if col.button(f'{qv:,} 股', width="stretch", key=f'buy_quick_{qv}'):
            st.session_state.default_shares = qv
            _save_pm_pref('default_shares', qv)
            st.rerun()
    buy_quote = None
    with st.form('buy_position_form'):
        col1, col2, col3 = st.columns(3)
        with col1:
            buy_ticker = stock_search_input(label='股票搜索', key='buy_ticker', default='601088', placeholder='输入代码或名称搜索，如：601088 / 中国神华 / 神华')
            buy_label = fetcher.get_stock_name(buy_ticker) or buy_ticker
            if buy_ticker:
                with st.spinner('获取实时行情中…'):
                    buy_quote = api_quote(buy_ticker)
                    if buy_quote is None:
                        buy_quote = fetcher.get_realtime_quote(buy_ticker)
                if buy_quote:
                    try:
                        _cur = buy_quote.get('current')
                        _dt = buy_quote.get('datetime', '')
                        if _cur is not None:
                            st.caption(f'📈 最新价 ¥{float(_cur):.2f}  {_dt}')
                        _qdf = format_quote_table(buy_quote)
                        if _qdf is not None:
                            st.dataframe(_qdf, width="stretch", hide_index=True, height=400)
                        else:
                            st.caption('⚠️ 五档行情暂不可用')
                    except Exception:
                        st.caption('⚠️ 行情数据解析失败，已跳过五档展示')
                else:
                    st.caption('⚠️ 未能获取实时行情')
        with col2:
            buy_date = st.date_input('买入日期', value=datetime.now(), key='buy_date', help='该笔持仓的买入日期，用于计算持有天数与收益率。')
            default_buy_price = 20.0
            _buy_price_from_quote = False
            if buy_quote and buy_quote.get('ask'):
                try:
                    _a0 = buy_quote['ask'][0]
                    if _a0 and 'price' in _a0:
                        default_buy_price = float(_a0['price'])
                        _buy_price_from_quote = True
                except (KeyError, TypeError, ValueError, IndexError):
                    _buy_price_from_quote = False
            if not _buy_price_from_quote:
                try:
                    _kline_start = (datetime.now() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
                    _kline_end = datetime.now().strftime('%Y-%m-%d')
                    _records = api_kline(buy_ticker, start=_kline_start, end=_kline_end)
                    price_df = pd.DataFrame(_records) if _records is not None else fetcher.get_daily(buy_ticker, start=_kline_start, end=_kline_end)
                    if price_df is not None and (not price_df.empty):
                        _close = price_df.iloc[-1].get('close') if hasattr(price_df, 'iloc') else None
                        if _close is not None:
                            default_buy_price = float(_close)
                except Exception:
                    default_buy_price = 20.0
            buy_price = st.number_input('买入成交价', value=round(default_buy_price, 2), step=0.01, format='%.2f', min_value=0.01, placeholder='如 20.00', help='默认按卖一价填充，可手动修改为卖二价或其他实际成交价')
            if buy_price <= 0:
                st.error('⚠️ 买入成交价必须大于 0。')
        with col3:
            buy_shares = st.number_input('📊 买入股数', value=st.session_state.default_shares, min_value=1, step=100, format='%d', placeholder='如 1000', help='点击 ± 按钮步进调节，或直接输入数字')
            if buy_shares < 100 or buy_shares % 100 != 0:
                xc_warn_box('⚠️ 买入股数建议为 100 股整数倍（A 股最小交易单位）。')
            buy_note = st.text_input('备注', value='', key='buy_note', placeholder='如：建仓理由 / 止盈目标', help='为该笔持仓添加备注（如建仓理由、止盈目标），便于后续回顾。')
        buy_submitted = st.form_submit_button('✅ 添加持仓')
    if buy_submitted:
        try:
            pm.add_position(ticker=buy_ticker, buy_date=buy_date.strftime('%Y-%m-%d'), buy_price=buy_price, shares=int(buy_shares), note=buy_note)
            _toast(f'买入成功: {buy_label} ({buy_ticker}) {int(buy_shares):,}股 @¥{buy_price:.2f}')
            st.session_state['_pm_recent'] = ([buy_ticker] + [x for x in st.session_state['_pm_recent'] if x != buy_ticker])[:10]
            st.rerun()
        except Exception as e:
            xc_handle_error("买入失败", e, hint="请稍后重试，或检查网络与数据源连接")
    # ── T-230：自选/收藏等辅助操作收进折叠区（主区留给买入/卖出/盈亏）──
    with st.expander("⚙️ 更多操作（加入自选 · 本地收藏 · 最近浏览）", expanded=False):
        _ma1, _ma2 = st.columns([1, 1])
        with _ma1:
            if st.button('⭐ ＋自选（当前买入标的）', key='pm_add_watch', width="stretch"):
                try:
                    from modules.admin_api import add_watchlist
                    add_watchlist(buy_ticker)
                    _toast(f'已加入自选：{buy_label} ({buy_ticker})')
                except Exception as e:
                    xc_handle_error("加入自选失败", e, hint="请稍后重试，或检查网络与数据源连接")
        with _ma2:
            if st.button('⭐ 收藏（本地星标）', key='pm_fav_add', width="stretch"):
                st.session_state.setdefault('_pm_fav', [])
                _ft = (buy_ticker or '').strip()
                if _ft and _ft not in st.session_state['_pm_fav']:
                    st.session_state['_pm_fav'].append(_ft)
                    _toast(f'已收藏（星标）：{_ft}')
                else:
                    xc_warn_box('该标的已收藏或代码为空。')
        if st.session_state.get('_pm_recent'):
            st.caption('🕘 最近浏览：' + '  '.join((f'`{c}`' for c in st.session_state['_pm_recent'][-6:][::-1])))
    sf_card('💸 卖出股票', '记录卖出成交，自动计算已实现盈亏并扣减剩余股数。')
    if not positions.empty:
        remaining = positions['remaining_shares'] if 'remaining_shares' in positions.columns else positions['shares']
        sellable_positions = positions[remaining > 0].copy()
    else:
        sellable_positions = positions.copy()
    if sellable_positions.empty:
        info_banner('当前没有可卖出的持仓。请先在上方「买入股票」录入一笔持仓（代码、价格、股数）后，再来这里卖出。')
    else:
        sell_quote = None
        with st.form('sell_position_form'):
            sell_options = {}
            for _, row in sellable_positions.iterrows():
                ticker = row['ticker']
                name = fetcher.get_stock_name(ticker) or ticker
                sellable = safe_int(row.get('remaining_shares', row.get('shares', 0)), 0)
                sell_options[f'{name} ({ticker}) — 可卖 {sellable:,} 股'] = ticker
            selected_label = st.selectbox('选择要卖出的持仓', options=list(sell_options.keys()), key='sell_select')
            sell_ticker = sell_options[selected_label]
            sellable_shares = pm.get_sellable_shares(sell_ticker)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric('可卖股数', f'{sellable_shares:,} 股', delta_color="off")
                with st.spinner('获取实时行情中…'):
                    sell_quote = api_quote(sell_ticker)
                    if sell_quote is None:
                        sell_quote = fetcher.get_realtime_quote(sell_ticker)
                if sell_quote:
                    try:
                        _cur = sell_quote.get('current')
                        _dt = sell_quote.get('datetime', '')
                        if _cur is not None:
                            st.caption(f'📈 最新价 ¥{float(_cur):.2f}  {_dt}')
                        _qdf = format_quote_table(sell_quote)
                        if _qdf is not None:
                            st.dataframe(_qdf, width="stretch", hide_index=True, height=400)
                        else:
                            st.caption('⚠️ 五档行情暂不可用')
                    except Exception:
                        st.caption('⚠️ 行情数据解析失败，已跳过五档展示')
                else:
                    st.caption('⚠️ 未能获取实时行情')
            with col2:
                sell_date = st.date_input('卖出日期', value=datetime.now(), key='sell_date')
                default_sell_price = 20.0
                _sell_price_from_quote = False
                if sell_quote and sell_quote.get('bid'):
                    try:
                        _b0 = sell_quote['bid'][0]
                        if _b0 and 'price' in _b0:
                            default_sell_price = float(_b0['price'])
                            _sell_price_from_quote = True
                    except (KeyError, TypeError, ValueError, IndexError):
                        _sell_price_from_quote = False
                if not _sell_price_from_quote:
                    try:
                        _kline_start = (datetime.now() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
                        _kline_end = datetime.now().strftime('%Y-%m-%d')
                        _records = api_kline(sell_ticker, start=_kline_start, end=_kline_end)
                        price_df = pd.DataFrame(_records) if _records is not None else fetcher.get_daily(sell_ticker, start=_kline_start, end=_kline_end)
                        if price_df is not None and (not price_df.empty):
                            _close = price_df.iloc[-1].get('close') if hasattr(price_df, 'iloc') else None
                            if _close is not None:
                                default_sell_price = float(_close)
                    except Exception:
                        default_sell_price = 20.0
            sell_price = st.number_input('卖出成交价', value=round(default_sell_price, 2), step=0.01, format='%.2f', min_value=0.01, placeholder='如 20.00', help='默认按买一价填充，可手动修改为买二价或其他实际成交价')
            with col3:
                sell_shares = st.number_input('📊 卖出股数', value=min(1000, sellable_shares), min_value=1, max_value=int(sellable_shares), step=100, format='%d', placeholder='如 1000', help='最多可卖剩余股数')
                if sell_shares < 100 or sell_shares % 100 != 0:
                    xc_warn_box('⚠️ 卖出股数建议为 100 股整数倍。')
                elif sell_shares > sellable_shares:
                    st.error('⚠️ 卖出股数超过可卖数量。')
                sell_note = st.text_input('备注', value='', key='sell_note', placeholder='如：止盈离场 / 补仓计划')
            sell_submitted = st.form_submit_button('✅ 记录卖出')
        if sell_submitted:
            try:
                result = pm.sell_position(ticker=sell_ticker, sell_date=sell_date.strftime('%Y-%m-%d'), sell_price=sell_price, sell_shares=int(sell_shares), note=sell_note)
                sell_label = fetcher.get_stock_name(sell_ticker) or sell_ticker
                xc_success_box(f"卖出成功: {sell_label} ({sell_ticker}) {int(sell_shares):,}股 @¥{sell_price:.2f}，成交金额 ¥{result['proceeds']:,.2f}")
                st.session_state['_pm_recent'] = ([sell_ticker] + [x for x in st.session_state['_pm_recent'] if x != sell_ticker])[:10]
                st.rerun()
            except Exception as e:
                xc_handle_error("卖出失败", e, hint="请稍后重试，或检查网络与数据源连接")
    st.markdown('---')
    with st.expander('🗑️ 删除持仓'):
        positions = pm.get_positions()
        if positions.empty:
            _empty_info('暂无持仓可删除。当前没有已记录的持仓，无需清理。')
        else:
            del_index = st.number_input('选择要删除的行号（从 0 开始）', min_value=0, max_value=len(positions) - 1, value=0, step=1, placeholder=f'0 ~ {len(positions) - 1}', help='行号对应上方持仓列表的序号（从 0 开始）。删除不可恢复，请确认后再点「确认删除」。')
            _idx_map = '；'.join((f"{i}: {positions.iloc[i]['ticker']}" for i in range(len(positions))))
            st.caption(f'行号对照（从 0 起）：{_idx_map}')
            c_del, _ = st.columns([1, 4])
            _ck = 'pm_del_cfm'
            if st.session_state.get(_ck):
                _ok = st.confirm('确定删除该持仓？此操作不可撤销。', key='pm_del_confirm')
                if c_del.button('⚠️ 确认删除', type='primary', disabled=not _ok):
                    removed = pm.remove_position(int(del_index))
                    st.session_state.pop(_ck, None)
                    if removed is not None:
                        _toast(f"已删除: {removed.get('ticker', '')}")
                        st.rerun()
                if st.button('取消', key='pm_del_cancel'):
                    st.session_state.pop(_ck, None)
            elif c_del.button('🗑️ 删除持仓', type='secondary'):
                st.session_state[_ck] = True
    sf_card('🧾 卖出记录', '查看历史卖出明细与成交金额，便于复盘与导出。')
    trades = pm.get_trades()
    st.caption(f'🧾 卖出记录：共 {len(trades)} 条')
    if trades.empty:
        _empty_info('暂无卖出记录。')
    else:
        display_trades = trades.copy()
        if 'name' in display_trades.columns:
            display_trades = display_trades.drop(columns=['name'])
        display_trades['股票'] = display_trades['ticker'].apply(lambda x: fetcher.get_name_only(x) or fetcher.get_stock_name(x))
        display_trades['卖出日期'] = display_trades['sell_date']
        display_trades['卖出价'] = display_trades['sell_price'].apply(_fmt_money)
        display_trades['卖出股数'] = display_trades['sell_shares'].apply(_fmt_int)
        display_trades['成交金额'] = display_trades['proceeds'].apply(_fmt_money)
        display_trades['备注'] = display_trades['note'].fillna('')
        show_cols = ['股票', 'ticker', '卖出日期', '卖出价', '卖出股数', '成交金额', '备注']
        st.dataframe(display_trades[show_cols], width="stretch", hide_index=True, height=400)
    sf_card('📈 盈亏统计', '汇总总成本、总市值、总盈亏与收益率，并绘制盈亏曲线与持仓明细。')
    positions = pm.get_positions()
    if not positions.empty:
        with st.spinner('正在获取行情并计算盈亏...'):
            try:
                pnl_df = pm.calc_pnl()
                summary = pm.summary()
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric('总成本', f"¥{summary.get('total_cost', 0):,.2f}", delta_color="off")
                with col2:
                    st.metric('总市值', f"¥{summary.get('total_market_value', 0):,.2f}", delta_color="off")
                with col3:
                    delta_pnl = summary.get('delta_pnl', 0)
                    st.metric('总盈亏', f"¥{summary.get('total_pnl', 0):,.2f}", delta=f"{summary.get('delta_pnl', 0):+.2f}" if abs(delta_pnl or 0) > 0.01 else None, delta_color="inverse")
                with col4:
                    st.metric('总收益率', f"{summary.get('total_pnl_pct', 0):+.2f}%", delta_color="inverse")
                st.caption('数据来源：东方财富 / 新浪财经（实时行情 + 日线兜底）。')
                if not pnl_df.empty:
                    from modules.visualizer import Visualizer
                    st.markdown('---')
                    fig = Visualizer.portfolio_pnl(pnl_df)
                    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})
                    st.markdown('#### 持仓明细')
                    st.caption(f'📋 持仓明细：共 {len(pnl_df)} 条')
                    display_pnl = pnl_df.copy()
                    if 'name' in display_pnl.columns:
                        display_pnl = display_pnl.drop(columns=['name'])
                    display_pnl['股票'] = display_pnl['ticker'].apply(lambda x: fetcher.get_name_only(x) or fetcher.get_stock_name(x))
                    display_pnl['买入股数'] = display_pnl['shares'].apply(_fmt_int)
                    display_pnl['剩余股数'] = display_pnl['remaining_shares'].apply(_fmt_int)
                    display_pnl['买入价'] = display_pnl['buy_price'].apply(_fmt_money)
                    display_pnl['现价'] = display_pnl['current_price'].apply(_fmt_money)
                    display_pnl['市值'] = display_pnl['market_value'].apply(_fmt_money)
                    display_pnl['已实现盈亏'] = display_pnl['realized_pnl'].apply(_fmt_money)
                    display_pnl['浮动盈亏'] = display_pnl['pnl'].apply(_fmt_money)
                    display_pnl['收益率'] = display_pnl['pnl_pct'].apply(_fmt_signed_pct)
                    if 'buy_date' in display_pnl.columns:
                        display_pnl['建仓时间'] = display_pnl['buy_date'].apply(_fmt_rel)
                    display_pnl = display_pnl.sort_values('pnl_pct', ascending=False, key=lambda s: pd.to_numeric(s, errors='coerce'), ignore_index=True)
                    pnl_cols = ['股票', 'ticker', '建仓时间', '买入价', '买入股数', '剩余股数', '现价', '市值', '已实现盈亏', '浮动盈亏', '收益率']
                    pnl_cols = [c for c in pnl_cols if c in display_pnl.columns]
                    st.dataframe(display_pnl[pnl_cols], width="stretch", hide_index=True, height=400)
                sf_card('🔬 盈亏归因', '按个股拆分盈亏贡献，定位收益的主要来源与拖累项。')
                attribution = pm.pnl_attribution()
                if not attribution.empty:
                    attr_fetcher = StockFetcher()
                    attribution['股票'] = attribution['ticker'].apply(lambda x: fetcher.get_name_only(x) or attr_fetcher.get_stock_name(x))
                    display_attr = attribution[['股票', 'ticker', 'pnl', 'pnl_pct', 'contribution']].copy()
                    st.dataframe(display_attr, width="stretch", hide_index=True, height=400)
                else:
                    _empty_info('暂无盈亏归因数据。需要先有至少一笔卖出记录，系统才能按股票拆分盈亏贡献。')
                st.markdown('---')
                exp_col1, exp_col2 = st.columns([1, 3])
                if exp_col1.button('📥 导出Excel报告'):
                    output = pm.export_excel()
                    with open(output, 'rb') as f:
                        exp_col2.download_button(label='⬇️ 下载报告', data=f, file_name=output.split(os.sep)[-1], mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    xc_success_box(f'报告已生成: {output}')
            except Exception as e:
                xc_handle_error("加载失败", e, hint="请稍后重试")
                if st.button('🔄 重试', key='pnl_retry'):
                    st.rerun()
    else:
        info_banner('请先添加持仓记录。')


def render_portfolio_returns() -> None:
    import streamlit as st
    import pandas as pd
    import plotly.graph_objects as go
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from modules.portfolio import PortfolioManager
    from modules.page_guard import safe_fragment
    from modules.page_utils import render_standard_page, get_fetcher
    from modules.ui_theme import sf_card, sf_metric
    from modules.page_widgets import _empty_info, UP, DOWN, _fig_layout, _section_title
    from modules.chart_cache import cached_fig

    from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, xc_kpi_grid

    dark = render_standard_page(
        title="自选股组合收益跟踪", icon="📊",
        caption="基于「仓位管理」中的持仓，按剩余股数加权构建组合净值曲线，对比沪深300基准。",
        layout="wide",
    )

    fetcher = get_fetcher()
    pm = PortfolioManager()






    def _build_portfolio_series(positions):
        """返回 (portfolio_index: Series, bench_index: Series|None, start_date)。"""
        if positions is None or positions.empty:
            return None, None, None
        positions = positions.copy()
        positions["buy_date"] = pd.to_datetime(positions["buy_date"], errors="coerce")
        positions = positions.dropna(subset=["buy_date"])
        if positions.empty:
            return None, None, None
        start = positions["buy_date"].min()
        start_str = (start - timedelta(days=5)).strftime("%Y-%m-%d")
        end_str = datetime.now().strftime("%Y-%m-%d")

        def _fetch_position_series(ticker, remaining, s_start, s_end):
            """单只持仓的日线价值序列（线程安全：不修改外部可变状态，仅返回结果字典）。"""
            out = {}
            try:
                df = fetcher.get_daily(ticker, start=s_start, end=s_end)
                if df is None or df.empty or "close" not in df.columns:
                    return out
                df = df.copy()
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                    df = df.dropna(subset=["date"])
                    df = df.set_index("date")
                df["close"] = pd.to_numeric(df["close"], errors="coerce")
                for d, c in df["close"].dropna().items():
                    ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                    out[ds] = float(c) * remaining
            except Exception as e:
                print(f"[R-01] 组合收益净值计算 code={code}: {e}")
                pass
            return out

        # 加法式性能优化：原实现按持仓逐只串行拉取日线（持仓多时明显变慢）。
        # 改用线程池并行取数；线程内不共享可变状态，结果在主线程统一 merge，线程安全。
        # series 结构：{date: 组合当日市值}；跨持仓同日期必须累加（不能用 dict.update 覆盖，会丢失其它持仓贡献）。
        series = {}
        _tasks = []
        for _, row in positions.iterrows():
            ticker = str(row["ticker"]).zfill(6)
            remaining = int(row.get("remaining_shares", row.get("shares", 0)) or 0)
            if remaining <= 0:
                continue
            _tasks.append((ticker, remaining))
        if _tasks:
            with ThreadPoolExecutor(max_workers=min(8, len(_tasks))) as _ex:
                _futs = {_ex.submit(_fetch_position_series, t, r, start_str, end_str): t for t, r in _tasks}
                for _fut in as_completed(_futs):
                    for _d, _v in _fut.result().items():
                        series[_d] = series.get(_d, 0.0) + _v

        if not series:
            return None, None, start_str

        # 注意：series 的值已是「跨持仓累加后的当日组合市值」(float)，直接构造时序，勿再对 v 调 .values()。
        pidx = pd.Series(series, name="组合").sort_index()
        pidx = pidx[pidx > 0]
        if len(pidx) < 2:
            return None, None, start_str
        pidx = pidx / pidx.iloc[0] * 100.0

        # 基准：沪深300
        bench = None
        try:
            bdf = fetcher.get_daily("000300", start=start_str, end=end_str)
            if bdf is not None and not bdf.empty and "close" in bdf.columns:
                bdf = bdf.copy()
                if "date" in bdf.columns:
                    bdf["date"] = pd.to_datetime(bdf["date"], errors="coerce")
                    bdf = bdf.dropna(subset=["date"]).set_index("date")
                bdf["close"] = pd.to_numeric(bdf["close"], errors="coerce")
                bser = bdf["close"].dropna()
                bser.index = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in bser.index]
                bser = bser.sort_index()
                bser = bser[bser > 0]
                if len(bser) >= 2:
                    bench = bser / bser.iloc[0] * 100.0
                    bench = bench.reindex(pidx.index).ffill().dropna()
        except Exception:
            bench = None

        return pidx, bench, start_str


    def _max_drawdown(idxs: pd.Series):
        if idxs is None or len(idxs) < 2:
            return 0.0
        peak = idxs.cummax()
        dd = (idxs - peak) / peak * 100.0
        return float(dd.min())


    # ── 图表 figure 构建缓存（性能优化：避免每次脚本重跑/自动刷新时重复 rebuild）──
    @cached_fig(ttl=120)
    def _build_portfolio_nav_fig(pidx, bench, total_ret, dark):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pidx.index, y=pidx.values, name="组合净值",
            line=dict(color=UP if total_ret >= 0 else DOWN, width=2.5),
            hovertemplate="%{x}<br>组合：%{y:.1f}<extra></extra>",
        ))
        if bench is not None and len(bench):
            fig.add_trace(go.Scatter(
                x=bench.index, y=bench.values, name="沪深300",
                line=dict(color="#888888", width=1.8, dash="dot"),
                hovertemplate="%{x}<br>沪深300：%{y:.1f}<extra></extra>",
            ))
        fig.add_hline(y=100, line=dict(color="#999", width=1, dash="dash"))
        fig.update_layout(**_fig_layout(dark), height=380, title="组合净值 vs 沪深300（起点=100）",
                          legend=dict(orientation="h", yanchor="top", y=-0.25, x=0.5, xanchor="center"))
        fig.update_xaxes(tickangle=-45)
        return fig


    @cached_fig(ttl=120)
    def _build_attribution_fig(top, dark):
        fig = go.Figure(go.Bar(
            x=top["name"], y=top["contribution"],
            marker_color=[UP if v >= 0 else DOWN for v in top["contribution"]],
            hovertemplate="%{x}<br>贡献：%{y:.2f}%<extra></extra>",
        ))
        fig.update_layout(**_fig_layout(dark), title="收益贡献 TOP15（%）", height=340)
        fig.update_xaxes(tickangle=-45)
        return fig


    # ───────────────────────── 主体 ─────────────────────────
    @safe_fragment(run_every=300)
    def fragment_portfolio():
        _section_title("💼 组合净值与基准对比")

        positions = pm.get_positions()
        if positions is None or positions.empty:
            _empty_info("暂无持仓。请先在「仓位管理」页添加持仓，再回来查看组合收益跟踪。")
            return

        with st.spinner("计算组合历史净值（拉取各持仓日线）…"):
            pidx, bench, start_str = _build_portfolio_series(positions)

        if pidx is None:
            xc_warn_box("暂无法构建组合净值（持仓缺少可用历史行情）。请检查持仓买入日期与代码。")
            # 仍展示当前盈亏快照（best-effort，失败不影响上方提示）
            try:
                _show_pnl_snapshot()
            except Exception as e:
                xc_handle_error("盈亏快照渲染失败", e, hint="请稍后重试，或检查网络与数据源连接")
            return

        total_ret = float(pidx.iloc[-1] - 100)
        mdd = _max_drawdown(pidx)
        bench_ret = float(bench.iloc[-1] - 100) if bench is not None and len(bench) else None
        xc_kpi_grid([
            {"label": "组合累计收益", "value": f"{total_ret:+.2f}%", "icon": "📈",
             "tone": "up" if total_ret >= 0 else "down", "meta": "净值起点 = 100"},
            {"label": "最大回撤", "value": f"{mdd:.2f}%", "icon": "📉",
             "tone": "down" if mdd < 0 else "flat", "meta": "区间峰值回落"},
            {"label": "沪深300基准", "value": f"{bench_ret:+.2f}%" if bench_ret is not None else "—",
             "icon": "🧭",
             "delta": (f"超额 {total_ret - bench_ret:+.2f}%" if bench_ret is not None else ""),
             "delta_dir": ("up" if (bench_ret is not None and total_ret - bench_ret >= 0) else "down"),
             "meta": "组合收益 − 基准收益"},
            {"label": "区间起始", "value": str(start_str), "icon": "🗓️"},
        ])

        if bench is None:
            st.caption("ℹ️ 沪深300基准暂未展示：未能获取足够历史行情（区间可能过短或接口受限），"
                       "组合收益与回撤结论不受影响。")

        fig = _build_portfolio_nav_fig(pidx, bench, total_ret, dark)
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
        # 加法式小便利（Batch15）：标注净值曲线数据更新时间，便于判断是否为最新行情。
        st.caption(f"🕒 数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}（组合净值基于各持仓历史收盘价加权构建）")

        # 加法式健壮性：summary() / pnl_attribution() 在持仓数据异常时可能抛 KeyError，
        # 原代码无兜底会导致整个 fragment 崩溃、净值曲线也一同消失。这里隔离两个子视图，
        # 任一失败仅提示，净值曲线与另一子视图仍可正常展示。
        try:
            # ── T-231：盈亏快照与「仓位管理」页盈亏统计同源（同调 pm.summary()），收进折叠区；
            #    主区留给净值对比与个股收益贡献。
            with st.expander("💰 当前盈亏快照（与仓位管理页同源）", expanded=False):
                _show_pnl_snapshot()
        except Exception as _e:
            xc_warn_box(f"盈亏快照加载失败：{_e}")
        try:
            _show_attribution()
        except Exception as _e:
            xc_warn_box(f"收益贡献加载失败：{_e}")
        try:
            _show_risk_xray()
        except Exception as _e:
            xc_warn_box(f"组合风险透视加载失败：{_e}")


    def _show_pnl_snapshot():
        _section_title("💰 当前盈亏快照")
        # 加法式字段级兜底：summary() 因版本差异可能缺失个别键，用 .get 降级为 0，
        # 避免单键缺失导致整块盈亏快照崩溃（外层虽有 try，但部分数据仍应可见）。
        s = pm.summary() or {}
        _pnl = s.get('total_pnl', 0)
        _pnl_pct = s.get('total_pnl_pct', 0)
        xc_kpi_grid([
            {"label": "持仓成本", "value": f"{s.get('total_cost', 0):,.0f}", "icon": "🧾"},
            {"label": "市值", "value": f"{s.get('total_market_value', 0):,.0f}", "icon": "💼"},
            {"label": "浮动盈亏", "value": f"{_pnl:,.0f}", "icon": "📊",
             "tone": "up" if _pnl >= 0 else "down",
             "delta": f"{_pnl_pct:+.2f}%", "delta_dir": "up" if _pnl_pct >= 0 else "down"},
            {"label": "持仓数", "value": f"{s.get('position_count', 0)}", "icon": "🔢"},
        ])


    def _show_attribution():
        _section_title("🥧 个股收益贡献")
        attr = pm.pnl_attribution()
        if attr is None or attr.empty:
            _empty_info("暂无收益贡献数据。")
            return
        attr = attr.copy()
        attr["contribution"] = pd.to_numeric(attr["contribution"], errors="coerce")
        # 加法式健壮性：个别版本 pnl_attribution 返回可能缺 pnl/name 列
        if "pnl" not in attr.columns:
            attr["pnl"] = 0.0
        attr = attr.sort_values("pnl", ascending=False)
        if "name" not in attr.columns:
            attr["name"] = attr["ticker"] if "ticker" in attr.columns else ""
        top = attr.head(15).copy()
        fig = _build_attribution_fig(top, dark)
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
        st.dataframe(
            attr, width="stretch", hide_index=True,
            column_config={
                "pnl": st.column_config.NumberColumn("盈亏", format="%.0f"),
                "pnl_pct": st.column_config.NumberColumn("盈亏%", format="%.2f"),
                "contribution": st.column_config.NumberColumn("贡献%", format="%.2f"),
            },
        height=400)
        # 导出收益贡献 CSV（便于离线分析）
        try:
            csv = attr.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("⬇️ 导出收益贡献 CSV", data=csv,
                               file_name="组合收益贡献.csv", mime="text/csv")
        except Exception as e:
            print(f"[R-01] 导出收益贡献 CSV 生成失败: {e}")
            pass


    def _show_risk_xray():
        """H4：组合风险透视 —— 集中度 / 行业暴露 / 相关性 / 情景回放（对标米筐 RQBeta、组合 X-ray）。"""
        from modules.risk_xray import concentration, sector_exposure, correlation_matrix, scenario_pnl
        _section_title("🩻 组合风险透视（X-ray）")
        try:
            pnl_df = pm.calc_pnl()
        except Exception as _e:
            xc_warn_box(f"风险透视取数失败：{_e}")
            return
        if pnl_df is None or pnl_df.empty:
            _empty_info("暂无持仓，无法做组合风险透视。")
            return
        # 权重 = 当前市值（仅取正值）
        w = {}
        for _, r in pnl_df.iterrows():
            try:
                mv = float(r.get("market_value") or 0)
            except Exception:  # noqa: BLE001
                mv = 0.0
            if mv > 0:
                w[str(r.get("ticker"))] = mv
        if len(w) < 1:
            _empty_info("持仓市值为 0，无法计算风险透视。")
            return

        # ── 集中度 ──
        c = concentration(w)
        if c.get("status") == "ok":
            xc_kpi_grid([
                {"label": "持仓数", "value": f"{c['n']}", "icon": "🔢"},
                {"label": "集中度 HHI", "value": f"{c['hhi']:.3f}", "icon": "🎯", "meta": c["level"]},
                {"label": "最大权重", "value": f"{c['max_weight_pct']:.1f}%", "icon": "📌"},
                {"label": "有效持仓数", "value": f"{c['effective_n']:.1f}", "icon": "🧮", "meta": "1/HHI"},
            ])
            st.caption("HHI <0.15 分散 · 0.15–0.25 适中 · >0.25 集中；有效持仓数越低，组合越依赖个别标的。")

        # ── 行业暴露（best-effort，取不到行业如实告警，不编造）──
        try:
            sector_of = {}
            for code in w:
                try:
                    sector_of[code] = (fetcher.get_fundamentals(code) or {}).get("industry")
                except Exception:  # noqa: BLE001
                    sector_of[code] = None
            se = sector_exposure(w, sector_of)
            if se.get("status") == "ok":
                st.markdown("**行业暴露**")
                st.dataframe(pd.DataFrame([{"行业": k, "权重%": v} for k, v in se["exposure"].items()]),
                             width="stretch", hide_index=True, height=200)
                if se.get("warning"):
                    xc_warn_box(se["warning"])
        except Exception as _e:  # noqa: BLE001
            xc_warn_box(f"行业暴露计算失败：{_e}")

        # ── 相关性 + 情景回放（按需触发，避免每次进页都拉行情）──
        with st.expander("🔗 持仓相关性 & 情景压力测试", expanded=False):
            st.caption("基于各持仓近一年日线（最多取权重最大的 8 只）。相关性衡量「是否同涨同跌」；"
                       "情景回放把当前持仓放回最近 1/3/6/12 个月的行情里，看组合会经历多大波动。")
            if st.button("运行相关性 + 情景分析", key="xray_run"):
                top_codes = [k for k, _ in sorted(w.items(), key=lambda kv: -kv[1])][:8]
                hist = {}
                with st.spinner("拉取持仓历史行情…"):
                    for code in top_codes:
                        try:
                            df = fetcher.get_daily(
                                code,
                                start=(datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d"),
                                end=datetime.now().strftime("%Y-%m-%d"),
                            )
                            if df is not None and not df.empty:
                                hist[code] = df
                        except Exception:  # noqa: BLE001
                            continue
                if not hist:
                    xc_warn_box("未能获取任何持仓历史行情，无法计算相关性/情景。")
                    return
                # 相关性热图
                rets = {}
                for code, df in hist.items():
                    try:
                        s = pd.to_numeric(df["close"], errors="coerce").dropna()
                        rets[code] = s.pct_change().dropna().tolist()[-120:]
                    except Exception:  # noqa: BLE001
                        continue
                cm = correlation_matrix(rets)
                if cm.get("status") == "ok":
                    _txt = [[f"{v:.2f}" for v in row] for row in cm["matrix"]]
                    figc = go.Figure(go.Heatmap(z=cm["matrix"], x=cm["codes"], y=cm["codes"],
                                                colorscale="RdBu", zmin=-1, zmax=1,
                                                text=_txt, texttemplate="%{text}"))
                    figc.update_layout(title=f"持仓收益相关性（近 {cm['n_obs']} 日 · 平均 {cm['avg_corr']}）",
                                       height=380,
                                       template="plotly_white" if not dark else "plotly_dark",
                                       margin=dict(l=40, r=20, t=50, b=40))
                    st.plotly_chart(figc, width="stretch",
                                    config={"displaylogo": False, "responsive": True})
                    st.caption("越接近 1 = 越同涨同跌（分散效果差）；接近 0 = 独立；为负 = 互为对冲。")
                else:
                    xc_warn_box(cm.get("reason", "相关性不可用"))

                # 情景回放（历史区间，非虚构事件）
                rows = []
                for label, days in [("近 1 个月", 30), ("近 3 个月", 90), ("近 6 个月", 180), ("近 1 年", 365)]:
                    sr = {}
                    for code, df in hist.items():
                        try:
                            s = pd.to_numeric(df["close"], errors="coerce").dropna()
                            seg = s.tail(days)
                            if len(seg) >= 2 and float(seg.iloc[0]) > 0:
                                sr[code] = float(seg.iloc[-1]) / float(seg.iloc[0]) - 1
                        except Exception:  # noqa: BLE001
                            continue
                    sp = scenario_pnl(w, sr)
                    rows.append({"情景": label,
                                 "组合损益%": sp.get("pnl_pct") if sp.get("status") == "ok" else None,
                                 "覆盖%": sp.get("coverage_pct"), "缺失数": sp.get("n_missing")})
                st.markdown("**历史区间回放（按当前权重静态持有，期末/期初价格模拟）**")
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=200)
                st.caption("⚠️ 回放按当前权重静态持有、未考虑区间内调仓与交易成本，仅作风险量级参考，不构成投资建议。")


    fragment_portfolio()

