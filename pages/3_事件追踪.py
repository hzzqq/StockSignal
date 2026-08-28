"""
页面2：事件追踪
信号评分、事件时间轴、事件管理、新闻挖掘、情感报告

独立性优化（关键）：
- 每个耗时模块用 @safe_fragment 包裹，点击某模块按钮只重跑「该 fragment」，
  不会冻结整页，其它模块保持原样（真正的同页模块独立运行）。
- 各模块结果存入各自独立的 session_state key，fragment 内从 session_state 恢复展示。
- 事件时间轴表单的日期/滑块控件 key 与 session_state 变量同名双向绑定，
  去掉 st.rerun()，避免整页重跑；区间快捷按钮只改 session_state，fragment 自动跟随刷新。
"""
import streamlit as st
import pandas as pd
import html
from datetime import datetime, timedelta
from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page, get_fetcher
from modules.ui_theme import sf_card, sf_metric
from modules.page_widgets import _empty_info
render_standard_page(title='事件追踪', icon='🔔', caption='⚠️ 数据仅供参考，不构成投资建议', layout='wide')

sf_card(
    "事件追踪导读",
    "信号评分、事件时间轴、新闻挖掘与情感报告。各模块独立运行，点击按钮仅刷新对应区块。",
    icon="🔔",
)

lk_p1, lk_p2 = st.columns([1, 1])
with lk_p1:
    if st.button('👁️ 智能盯盘', key='lk_go_k', use_container_width=True):
        st.switch_page('pages/K_智能盯盘.py')
with lk_p2:
    if st.button('🔍 个股研究', key='lk_go_rs', use_container_width=True):
        st.switch_page('pages/个股研究.py')
from modules.signal import SignalEngine
from modules.colors import UP_COLOR, DOWN_COLOR
from modules.search_ui import stock_search_input
from modules.session import api_kline, api_intraday, trading_autorefresh, api_post
trading_autorefresh(key='event_autorefresh')
_FOR_ALL_KEYS = ['sig_scores', 'sig_scores_error', 'live_kw_result', 'tl_existing_events', 'tl_realtime_events', 'tl_df', 'tl_chart_title', 'tl_start_idx', 'tl_n_show', 'tl_start_date', 'tl_end_date', 'mined_result', 'sentiment_report', 'sentiment_report_error', 'sig_ticker_last']
for _k in _FOR_ALL_KEYS:
    if _k not in st.session_state:
        st.session_state[_k] = None
if st.session_state.get('tl_start_idx') is None:
    st.session_state.tl_start_idx = 0
if st.session_state.get('tl_n_show') is None:
    st.session_state.tl_n_show = 60
if st.session_state.get('tl_start_date') is None:
    st.session_state.tl_start_date = (datetime.now() - timedelta(days=180)).date()
if st.session_state.get('tl_end_date') is None:
    st.session_state.tl_end_date = datetime.now().date()
if '_recent_viewed' not in st.session_state:
    st.session_state._recent_viewed = []
if '_fav_set' not in st.session_state:
    st.session_state._fav_set = []

@st.cache_resource
def get_engine():
    return SignalEngine()
engine = get_engine()
fetcher = get_fetcher()

@st.cache_data(show_spinner=False, ttl=60)
def _cached_intraday(ticker):
    """个股分时数据：优先后端 /api/intraday，回退本地 fetcher。返回 (df, prev_close, trade_date) 或 None。"""
    if not ticker:
        return None
    try:
        rec = api_intraday(ticker)
        if rec and isinstance(rec.get('records'), list) and rec['records']:
            return (pd.DataFrame(rec['records']), rec.get('prev_close'), rec.get('trade_date'))
    except Exception:
        pass
    try:
        _df, _pc, _dt = fetcher.get_stock_intraday_sina(ticker)
        if _df is not None and (not _df.empty):
            return (_df, _pc, _dt)
    except Exception:
        pass
    return None

def _news_fallback_url(title: str, source: str='') -> str:
    """原文链接缺失时的兜底：用搜索引擎按标题检索，保证标题始终可点击跳转。"""
    from urllib.parse import quote
    q = title
    return f'https://www.baidu.com/s?wd={quote(q)}'

def _fmt_rel(ts):
    """把绝对时间转换为相对时间：刚刚 / X分钟前 / X小时前 / X天前。"""
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

def _render_news_with_links(df, title_col='title', url_col='url', date_col='date', source_col='source', type_col='type', max_items=50):
    """
    渲染新闻列表，标题可点击跳转至原文。
    使用 st.markdown + unsafe_allow_html 实现 <a> 标签。
    当原文 url 缺失（为空或非 http）时，回退为「按标题搜索」链接，确保标题始终可跳转。
    """
    if df is None or df.empty:
        _empty_info('暂无相关新闻/事件数据（可能该标的暂无公开资讯，或数据源暂不可用）。可换一只股票或稍后重试。')
        return
    for i, (_, row) in enumerate(df.head(max_items).iterrows()):
        title = str(row.get(title_col, '')).strip()
        url = str(row.get(url_col, '')).strip()
        date_raw = row.get(date_col, None)
        if date_raw is None or str(date_raw) in ('', 'NaT', 'nan', 'None'):
            date = ''
        else:
            date = _fmt_rel(date_raw)
        source = str(row.get(source_col, '')).strip()
        etype = str(row.get(type_col, '')).strip()
        if not title:
            continue
        has_direct = bool(url) and url.startswith('http')
        if has_direct:
            link = f'<a href="{html.escape(url)}" target="_blank" style="text-decoration:none;color:inherit;">{html.escape(title)}</a>'
        else:
            fb = _news_fallback_url(title, source)
            link = f'<a href="{html.escape(fb)}" target="_blank" style="text-decoration:none;color:inherit;">{html.escape(title)}</a>'
        badges = []
        if etype == '正面':
            badges.append(f'<span style="color:{UP_COLOR};font-weight:600;">[利好]</span>')
        elif etype == '负面':
            badges.append(f'<span style="color:{DOWN_COLOR};font-weight:600;">[利空]</span>')
        elif etype in ('利好', '利空', '中性'):
            badges.append(f'<span style="color:#95a5a6;">[{html.escape(etype)}]</span>')
        if source:
            badges.append(f'<span style="color:#888;font-size:0.85em;">{html.escape(source)}</span>')
        badge_str = ' '.join(badges) if badges else ''
        cols = st.columns([1, 6, 1])
        with cols[0]:
            st.caption(date)
        with cols[1]:
            st.markdown(f'{badge_str} {link}' if badge_str else link, unsafe_allow_html=True)
        with cols[2]:
            if has_direct:
                st.markdown(f'<a href="{html.escape(url)}" target="_blank" style="font-size:0.8em;color:#3498db;">🔗 原文</a>', unsafe_allow_html=True)
            else:
                st.markdown(f'<a href="{html.escape(fb)}" target="_blank" style="font-size:0.8em;color:#888;">🔍 搜索</a>', unsafe_allow_html=True)

@safe_fragment
def fragment_signal_score():
    """信号评分面板（延迟导入 Visualizer）。"""
    from modules.visualizer import Visualizer
    sf_card('📊 信号评分', "")
    _rv = st.session_state.get('_recent_viewed', [])
    if _rv:
        st.caption('🕘 最近浏览（点击重新填入）')
        _rcs = st.columns(min(len(_rv), 6))
        for _i, _t in enumerate(_rv[:6]):
            with _rcs[_i]:
                if st.button(_t, key=f'recent_chip_{_i}'):
                    st.session_state['sig_ticker'] = _t
                    st.rerun(scope='fragment')
    try:
        with st.form('signal_form'):
            col1, col2 = st.columns(2)
            with col1:
                sig_ticker = stock_search_input(label='股票搜索', key='sig_ticker', default='601088', placeholder='输入代码或名称搜索，如：601088 / 中国神华 / 煤炭')
            with col2:
                sig_date = st.date_input('评估日期', value=datetime.now(), key='sig_date')
            auto_kws = fetcher.get_stock_keywords(sig_ticker, top_k=10)
            default_kws = auto_kws if auto_kws else '煤炭,保供,电厂库存'
            keywords_input = st.text_input('事件关键词（逗号分隔）', value=default_kws, key='sig_keywords', placeholder='如：煤炭,保供,电厂库存（逗号分隔）', help='根据所选股票的行业特征自动匹配高频事件关键词，可手动编辑')
            submitted = st.form_submit_button('开始评分')
        if sig_ticker:
            st.session_state.sig_ticker_last = sig_ticker
        if submitted:
            keywords = [k.strip() for k in keywords_input.split(',') if k.strip()]
            date_str = sig_date.strftime('%Y-%m-%d')
            with st.spinner('📊 正在分析价格趋势、量价关系与事件匹配度…'):
                try:
                    scores = engine.evaluate(sig_ticker, keywords, date_str)
                    st.session_state.sig_scores = scores
                    st.session_state.sig_scores_error = None
                    _rv = st.session_state.get('_recent_viewed', [])
                    if sig_ticker and sig_ticker not in _rv:
                        st.session_state._recent_viewed = ([sig_ticker] + _rv)[:8]
                except Exception as e:
                    st.session_state.sig_scores = None
                    st.session_state.sig_scores_error = str(e)
        if st.session_state.get('sig_scores') is not None:
            scores = st.session_state.sig_scores
            _price = scores.get('price_score', 0) or 0
            _event = scores.get('event_score', 0) or 0
            _macro = scores.get('macro_score', 0) or 0
            _total = scores.get('total', 0) or 0
            _safe_scores = {k: v if v is not None else 0 for k, v in scores.items()}
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric('价格信号', f'{_price}/100')
            with col2:
                st.metric('事件信号', f'{_event}/100')
            with col3:
                st.metric('宏观信号', f'{_macro}/100')
            with col4:
                total = _total
                delta_text = '买入信号' if total >= 70 else '卖出信号' if total <= 40 else '观望'
                st.metric('综合评分', f'{total}/100', delta=delta_text)
            col_radar, col_detail = st.columns([1, 1])
            with col_radar:
                fig = Visualizer.signal_radar(_safe_scores)
                st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True})
            with col_detail:
                st.markdown('#### 评分说明')
                st.markdown(f'\n                - **价格信号 ({_price}）**: 基于均线趋势、动量、量价关系\n                - **事件信号 ({_event}）**: 基于关键词匹配事件库，利好加分/利空减分\n                - **宏观信号 ({_macro}）**: 基于制造业 PMI（>50扩张，<50收缩）\n                - **综合评分 ({total}）**: 加权 = 价格×0.4 + 事件×0.4 + 宏观×0.2\n                - **阈值**: >70 买入 | 40-70 观望 | <40 卖出\n                ')
            st.markdown('---')
            st.caption('数据来源：东方财富 / 新浪财经 / 公开公告')
            st.caption('综合评分 = 价格信号×0.4 + 事件信号×0.4 + 宏观信号×0.2；>70 偏买入，<40 偏卖出，其余观望。')
            if st.button('＋自选', key='sig_add_watch', help='将上方所选股票加入自选股'):
                try:
                    sc, body = api_post('/api/watchlist', payload={'stock_code': sig_ticker})
                    if sc == 200 and isinstance(body, dict) and (body.get('status') == 'ok'):
                        st.toast(f'已加入自选：{sig_ticker}')
                    else:
                        st.info(f'自选操作返回：{sc}')
                except Exception as e:
                    xc_handle_error("加入自选失败", e, hint="请稍后重试，或检查网络与数据源连接")
            _fav = st.session_state.get('_fav_set', [])
            _is_fav = sig_ticker in _fav
            if st.button('⭐ 已收藏' if _is_fav else '☆ 收藏', key='sig_fav_toggle', help='将当前股票加入/移出本地收藏（仅本会话有效）'):
                if _is_fav:
                    st.session_state._fav_set = [x for x in _fav if x != sig_ticker]
                else:
                    st.session_state._fav_set = _fav + [sig_ticker]
                st.rerun(scope='fragment')
        elif st.session_state.get('sig_scores_error'):
            err_msg = st.session_state.sig_scores_error
            if '无法获取' in err_msg or '数据源' in err_msg or '不存在' in err_msg or ('退市' in err_msg):
                st.warning(f'⚠️ {err_msg}')
                st.info('💡 价格信号暂时不可用，事件信号和宏观信号仍可正常评分。建议换用 600519、000858 等活跃股票测试。')
            else:
                st.error(f'评分失败: {err_msg}')
    except Exception as module_err:
        st.error(f'⚠️ 信号评分模块异常: {module_err}')

@safe_fragment
def fragment_live_keywords():
    sf_card('📰 实时关键词提取', "")
    try:
        col_live1, col_live2, col_live_btn = st.columns([3, 1, 1.2])
        with col_live1:
            live_ticker = stock_search_input(label='股票搜索', key='live_kw_ticker', default=st.session_state.get('sig_ticker_last') or '601088', placeholder='选择要提取关键词的股票（默认使用上方已选股票）')
        with col_live2:
            live_limit = st.slider('抓取条数', min_value=10, max_value=50, value=20, key='live_kw_limit')
        with col_live_btn:
            live_submitted = st.button('🔍 提取关键词', type='primary', key='btn_extract_kws', use_container_width=True)
        extract_result = st.container()
        if live_submitted or st.session_state.get('_retry_live_kw'):
            if st.session_state.get('_retry_live_kw'):
                st.session_state['_retry_live_kw'] = False
            with st.spinner('📰 正在抓取最新新闻并提取关键词，预计需要 10-30 秒…'):
                try:
                    stock_name = fetcher._lookup_name_for_code(live_ticker) if live_ticker and live_ticker.isdigit() and (len(live_ticker) == 6) else live_ticker or ''
                    search_keyword = stock_name if stock_name else live_ticker
                    news = engine.event_miner.news_fetcher.fetch(keyword=search_keyword or None, source='auto', limit=live_limit)
                    if not news.empty:
                        kw_df = engine.keyword_extractor.batch_extract(news, topk=5)
                        from collections import Counter
                        all_news_kws = []
                        for kws in kw_df['keywords']:
                            all_news_kws.extend(kws)
                        news_counter = Counter(all_news_kws)
                        top_news = [kw for kw, cnt in news_counter.most_common(15) if len(kw) >= 2]
                        industry_kws = fetcher.get_stock_keywords(live_ticker, top_k=20)
                        industry_set = set(industry_kws.split(',')) if industry_kws else set()
                        final_kws = []
                        seen = set()
                        for kw in industry_kws.split(',') if industry_kws else []:
                            kw = kw.strip()
                            if kw and kw not in seen:
                                final_kws.append(kw)
                                seen.add(kw)
                        for kw in top_news:
                            if kw not in seen:
                                final_kws.append(kw)
                                seen.add(kw)
                        result_str = ','.join(final_kws[:15])
                        st.session_state.live_kw_result = {'news': news.head(5), 'final_kws': final_kws[:15], 'industry_set': industry_set, 'news_counter': news_counter, 'result_str': result_str, 'total': len(news), 'error': None}
                    else:
                        industry_kws = fetcher.get_stock_keywords(live_ticker, top_k=20) or ''
                        st.session_state.live_kw_result = {'news': None, 'final_kws': [], 'industry_set': set(industry_kws.split(',')) if industry_kws else set(), 'news_counter': Counter(), 'result_str': industry_kws, 'total': 0, 'error': 'empty'}
                except Exception as e:
                    st.session_state.live_kw_result = {'news': None, 'final_kws': [], 'industry_set': set(), 'news_counter': Counter(), 'result_str': '', 'total': 0, 'error': str(e)}
        if st.session_state.get('live_kw_result'):
            r = st.session_state.live_kw_result
            with extract_result:
                if r.get('error') and r['error'] != 'empty':
                    st.error(f"提取失败: {r['error']}")
                    if st.button('🔄 重试', key='btn_live_kw_retry'):
                        st.session_state['_retry_live_kw'] = True
                elif r.get('error') == 'empty':
                    st.warning(f"未抓取到与「{live_ticker or '全部'}」相关的新闻。")
                    if r.get('result_str'):
                        st.info('💡 已根据「' + str(live_ticker) + '」的行业特征生成关键词：\n\n`' + str(r.get('result_str', '')) + '`')
                        st.code(r['result_str'], language=None)
                else:
                    st.success(f"✅ 成功从 {r['total']} 条新闻中提取到 {len(r['final_kws'])} 个关键词！")
                    with st.expander('📰 新闻样本（点击标题可跳转原文）', expanded=False):
                        _render_news_with_links(r['news'], title_col='title', url_col='url', date_col='date', source_col='source')
                    cols = st.columns(5)
                    for i, kw in enumerate(r['final_kws']):
                        with cols[i % 5]:
                            is_industry = kw in r['industry_set']
                            st.caption(f"""**{kw}** {('🏭行业' if is_industry else f"📰×{r['news_counter'].get(kw, 0)}")}""")
                    st.code(r['result_str'], language=None)
                    st.info('💡 点击上方代码框右侧的复制按钮，可将关键词粘贴到「事件关键词」输入框中。')
    except Exception as module_err:
        st.error(f'⚠️ 实时关键词模块异常: {module_err}')

@safe_fragment
def fragment_timeline():
    """事件时间轴（延迟导入 Visualizer）。"""
    from modules.visualizer import Visualizer
    sf_card('📅 事件时间轴', "")
    if st.button('🔄 刷新', key='tl_manual_refresh', help='手动局部刷新事件时间轴模块'):
        st.rerun(scope='fragment')
    try:
        with st.form('timeline_form_v2'):
            col1, col2 = st.columns([2, 1])
            with col1:
                tl_ticker = stock_search_input(label='股票搜索', key='tl_ticker_v2', default='601088', placeholder='输入代码或名称搜索，如：601088 / 中国神华')
            with col2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                tl_submitted = st.form_submit_button('生成时间轴', use_container_width=True)
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.date_input('起始日期', value=st.session_state.get('tl_start_date', (datetime.now() - timedelta(days=180)).date()), key='tl_start_date_w', help='选择时间轴起始日期')
            with col_d2:
                st.date_input('截止日期', value=st.session_state.get('tl_end_date', datetime.now().date()), key='tl_end_date_w', help='选择时间轴截止日期')
            col_chk1, col_chk2 = st.columns(2)
            with col_chk1:
                show_existing = st.checkbox('显示现有事件库', value=st.session_state.get('pref_tl_show_existing', True), key='tl_show_existing')
            with col_chk2:
                show_realtime = st.checkbox('实时爬取最新事件', value=st.session_state.get('pref_tl_show_realtime', False), key='tl_show_realtime')
        quick_cols = st.columns([1, 1, 1, 1, 1])

        def _set_tl_range(days):
            st.session_state.tl_end_date = datetime.now().date()
            st.session_state.tl_start_date = (datetime.now() - timedelta(days=days)).date()
            st.session_state.tl_start_idx = 0
        with quick_cols[0]:
            if st.button('近30天', key='tl_q30'):
                _set_tl_range(30)
        with quick_cols[1]:
            if st.button('近90天', key='tl_q90'):
                _set_tl_range(90)
        with quick_cols[2]:
            if st.button('近180天', key='tl_q180'):
                _set_tl_range(180)
        with quick_cols[3]:
            if st.button('近365天', key='tl_q365'):
                _set_tl_range(365)
        with quick_cols[4]:
            if st.button('今年至今', key='tl_qytd'):
                _set_tl_range((datetime.now() - datetime(datetime.now().year, 1, 1)).days)
        if tl_submitted:
            st.session_state.tl_start_date = st.session_state.get('tl_start_date_w', st.session_state.tl_start_date)
            st.session_state.tl_end_date = st.session_state.get('tl_end_date_w', st.session_state.tl_end_date)
            st.session_state.tl_start_idx = 0
            st.session_state['pref_tl_show_existing'] = show_existing
            st.session_state['pref_tl_show_realtime'] = show_realtime
            tl_start = st.session_state.tl_start_date
            tl_end = st.session_state.tl_end_date
            start_str = tl_start.strftime('%Y-%m-%d')
            end_str = tl_end.strftime('%Y-%m-%d')
            timeline_container = st.container()
            with timeline_container:
                if show_existing:
                    st.markdown('#### 📦 现有事件库')
                    with st.spinner('正在加载事件库...'):
                        try:
                            events = engine._load_events()
                            if not events.empty:
                                events['date'] = events['date'].astype(str).str.split(' ').str[0]
                                events['date'] = pd.to_datetime(events['date'], errors='coerce')
                                events = events.dropna(subset=['date'])
                                events = events[(events['date'] >= pd.Timestamp(tl_start)) & (events['date'] <= pd.Timestamp(tl_end))]
                                if tl_ticker:
                                    name_pattern = fetcher._lookup_name_for_code(tl_ticker) or ''
                                    mask = events['ticker'].astype(str).str.contains(tl_ticker, na=False)
                                    if name_pattern:
                                        mask = mask | events['title'].str.contains(name_pattern, na=False)
                                    events = events[mask]
                                st.session_state.tl_existing_events = events.copy()
                            else:
                                st.session_state.tl_existing_events = pd.DataFrame()
                        except Exception as e:
                            st.session_state.tl_existing_events = None
                            xc_handle_error("加载事件库失败", e, hint="请稍后重试，或检查网络与数据源连接")
                if show_realtime:
                    st.markdown('#### 🌐 实时爬取最新事件')
                    with st.spinner('正在实时爬取新闻和公告...'):
                        try:
                            stock_name = ''
                            if tl_ticker:
                                if tl_ticker.isdigit() and len(tl_ticker) == 6:
                                    stock_name = fetcher._lookup_name_for_code(tl_ticker) or ''
                                else:
                                    stock_name = tl_ticker
                            industry_raw = fetcher.get_stock_keywords(tl_ticker, top_k=15) if tl_ticker else ''
                            keywords_list = [k.strip() for k in industry_raw.split(',') if k.strip()] if industry_raw else []
                            stock_code = tl_ticker if tl_ticker and tl_ticker.isdigit() and (len(tl_ticker) == 6) else None
                            events_realtime = engine.event_miner.news_fetcher.fetch_stock_events(stock_code=stock_code, stock_name=stock_name, keywords=keywords_list, limit=50)
                            if not events_realtime.empty:
                                analyzed = engine.event_miner.sentiment_analyzer.batch_analyze(events_realtime)
                                for col in ['sentiment', 'score']:
                                    if col in analyzed.columns:
                                        events_realtime[col] = analyzed[col].values
                                st.session_state.tl_realtime_events = events_realtime.copy()
                                st.session_state.tl_chart_title = f'{stock_name or tl_ticker} 事件时间轴（实时）'
                                try:
                                    _records = api_kline(tl_ticker, start_str, end_str)
                                    if _records is None:
                                        df = fetcher.get_daily(tl_ticker, start_str, end_str)
                                    else:
                                        df = pd.DataFrame(_records)
                                    if df is not None and (not df.empty):
                                        st.session_state.tl_df = df
                                        st.session_state.tl_start_idx = 0
                                        st.session_state.tl_n_show = min(60, len(df))
                                except Exception:
                                    pass
                            else:
                                st.session_state.tl_realtime_events = pd.DataFrame()
                        except Exception as e:
                            st.session_state.tl_realtime_events = None
                            xc_handle_error("实时爬取失败", e, hint="请稍后重试，或检查网络与数据源连接")
        timeline_display = st.container()
        with timeline_display:
            if st.session_state.get('tl_existing_events') is not None:
                st.markdown('#### 📦 现有事件库')
                events = st.session_state.tl_existing_events
                if not events.empty:
                    with st.expander(f'展开查看事件库（共 {len(events)} 条）', expanded=False):
                        events_display = events[['date', 'ticker', 'title', 'type']].sort_values('date', ascending=False).copy()
                        events_display['相对时间'] = events_display['date'].apply(lambda d: _fmt_rel(d))
                        st.dataframe(events_display, use_container_width=True, height=400)
                    st.caption(f'共 {len(events)} 条事件')
                else:
                    st.info('当前筛选条件下事件库为空。可先在上方「股票搜索」选择关注标的并点击「生成时间轴」，或在下方「事件管理」中手动添加事件。')
            if st.session_state.get('tl_realtime_events') is not None:
                st.markdown('#### 🌐 实时爬取最新事件')
                events_realtime = st.session_state.tl_realtime_events
                if not events_realtime.empty:
                    st.success(f'✅ 实时爬取到 {len(events_realtime)} 条事件（含公司公告 + 板块新闻）')
                    with st.expander('展开查看实时事件列表（点击标题可跳转原文）', expanded=False):
                        _render_news_with_links(events_realtime, title_col='title', url_col='url', date_col='date', source_col='source', type_col='sentiment')
                else:
                    st.warning('实时爬取未获取到事件。请检查股票代码是否正确、网络是否可用；也可在「事件管理」中手动添加关注的事件。')
            if 'tl_df' in st.session_state and st.session_state.tl_df is not None and (not st.session_state.tl_df.empty):
                try:
                    df = st.session_state.tl_df
                    events_chart = st.session_state.get('tl_events', st.session_state.get('tl_realtime_events', pd.DataFrame()))
                    title = st.session_state.get('tl_chart_title', '事件时间轴')
                    n_total = len(df)
                    if tl_ticker:
                        _show_intraday = st.checkbox('📈 显示分时图', value=True, key='tl_show_intraday', help='展示该股票当日/最近交易日分时走势（价格线+均价+昨收基准，红涨绿跌）。')
                        if _show_intraday:
                            _intra = _cached_intraday(tl_ticker)
                            if _intra is not None:
                                _idf, _ipc, _idate = _intra
                                _ifig = Visualizer.intraday(_idf, prev_close=_ipc, title=f'{stock_name or tl_ticker} 分时（{_idate}）')
                                st.plotly_chart(_ifig, use_container_width=True, key='tl_intraday_chart', config={"displaylogo": False, "responsive": True})
                                st.caption('📈 分时图：白线为当日价格走势，橙点为均价；虚线为昨收。红涨绿跌（A股惯例）。')
                            else:
                                st.info('📭 暂无分时数据（非交易时段或数据源暂不可用）。')
                    st.markdown('#### 📈 K 线事件时间轴')
                    n_show = max(10, min(int(st.session_state.get('tl_n_show', 60)), n_total))
                    start_idx = max(0, min(int(st.session_state.get('tl_start_idx', 0)), n_total - n_show))
                    nav_cols = st.columns([5, 5])
                    with nav_cols[0]:
                        if n_total > n_show:
                            new_idx = st.slider('显示位置', min_value=0, max_value=n_total - n_show, value=start_idx, key='tl_start_idx_w')
                        else:
                            new_idx = start_idx
                            st.caption('当前区间内 K 线数量已完整显示')
                    with nav_cols[1]:
                        new_n_show = st.slider('显示 K 线数量（缩放）', min_value=10, max_value=min(200, max(10, n_total)), value=n_show, key='tl_n_show_w')
                    st.session_state.tl_start_idx = new_idx
                    st.session_state.tl_n_show = new_n_show
                    st.caption('💡 拖动「显示位置」滑块可左右平移，拖动「显示 K 线数量」滑块可放大/缩小。')
                    st.caption(f'📊 当前显示 {n_show} / 总计 {n_total} 根 K 线')
                    fig = Visualizer.event_timeline(df, events_chart, title=title, start_idx=new_idx, n_show=new_n_show, event_type_col='sentiment', event_title_col='title')
                    st.plotly_chart(fig, use_container_width=True, key='tl_chart', config={"displaylogo": False, "responsive": True})
                except Exception as chart_err:
                    st.error(f'K 线事件时间轴渲染失败: {chart_err}')
                    st.info('💡 请尝试缩短日期区间或切换股票后重试。')
            if not show_existing and (not show_realtime) and (not tl_submitted):
                st.warning('请至少选择一个子模块（现有事件库 / 实时爬取）。')
    except Exception as module_err:
        st.error(f'⚠️ 事件时间轴模块异常: {module_err}')

@safe_fragment
def fragment_event_manage():
    sf_card('📌 事件管理', "")
    try:
        with st.form('add_event_form'):
            col1, col2 = st.columns(2)
            with col1:
                evt_date = st.date_input('事件日期', value=datetime.now(), key='evt_date')
                evt_ticker = stock_search_input(label='关联股票', key='evt_ticker', default='', placeholder='输入代码或名称搜索（可选），如：中国神华')
            with col2:
                evt_type = st.selectbox('事件类型', options=['利好', '利空', '中性'])
                evt_title = st.text_input('事件标题', value='', key='evt_title', placeholder='如：煤炭价格大涨10%')
            add_submitted = st.form_submit_button('添加事件', disabled=not (evt_title or '').strip(), help='填写「事件标题」后方可添加；标题为空时按钮不可用。')
        if not (evt_title or '').strip():
            st.caption('💡 请先在「事件标题」中填写内容，再点击「添加事件」。')
        if add_submitted and evt_title:
            try:
                engine.add_event(evt_date.strftime('%Y-%m-%d'), evt_ticker, evt_title, evt_type)
                st.success('事件添加成功！')
            except Exception as e:
                xc_handle_error("添加失败", e, hint="请稍后重试，或检查网络与数据源连接")
        with st.spinner('⏳ 正在加载全部事件库…'):
            events_all = engine._load_events()
        if not events_all.empty:
            st.markdown('#### 现有事件库（全部）')
            evt_filter = st.text_input('🔍 搜索事件（标题/股票/类型）', value='', key='evt_filter_q', placeholder='如：煤炭 / 601088 / 利好')
            events_display = events_all[['date', 'ticker', 'title', 'type']].sort_values('date', ascending=False).copy()
            events_display['相对时间'] = events_display['date'].apply(lambda d: _fmt_rel(d))
            events_display['股票'] = events_display['ticker'].apply(lambda x: fetcher._lookup_name_for_code(x) if x else '')

            def _is_new_evt(d):
                try:
                    dd = pd.to_datetime(d, errors='coerce')
                    if dd is None or pd.isna(dd):
                        return ''
                    return '🆕新' if (pd.Timestamp(datetime.now()) - pd.Timestamp(dd)).days <= 7 else ''
                except Exception:
                    return ''
            events_display['标记'] = events_display['date'].apply(_is_new_evt)
            if evt_filter.strip():
                q = evt_filter.strip().lower()
                events_display = events_display[events_display.apply(lambda r: q in str(r['title']).lower() or q in str(r['股票']).lower() or q in str(r['ticker']).lower() or (q in str(r['type']).lower()), axis=1)]
            _evt_page_key = 'evt_page_n'
            _evt_last_key = 'evt_filter_last'
            if st.session_state.get(_evt_last_key) != evt_filter:
                st.session_state[_evt_page_key] = 30
                st.session_state[_evt_last_key] = evt_filter
            if _evt_page_key not in st.session_state:
                st.session_state[_evt_page_key] = 30
            _evt_total = len(events_display)
            _evt_show = min(st.session_state[_evt_page_key], _evt_total)
            with st.expander(f'展开查看全部事件库（共 {_evt_total} 条，已显示 {_evt_show} 条）', expanded=False):
                st.dataframe(events_display[['date', '股票', 'ticker', 'title', 'type', '标记', '相对时间']], use_container_width=True, height=400)
            if _evt_show < _evt_total:
                if st.button('显示更多 ▼', key='evt_load_more'):
                    st.session_state[_evt_page_key] = min(st.session_state[_evt_page_key] + 30, _evt_total)
            st.caption('数据来源：东方财富 / 新浪财经 / 公开公告')
    except Exception as module_err:
        st.error(f'⚠️ 事件管理模块异常: {module_err}')

@safe_fragment
def fragment_news_mine():
    try:
        sf_card('⛏️ 新闻事件自动挖掘', "")
        st.caption('一键抓取最新新闻 → jieba 关键词提取 → 金融情感分析 → 自动入库')
        col_mine_input, col_mine_btn, col_mine_limit = st.columns([4, 2, 2])
        with col_mine_input:
            mine_keyword = st.text_input('挖掘关键词（留空抓财经要闻）', value='煤炭', key='mine_keyword', placeholder='如：煤炭 / 中国神华 / 留空抓全部财经要闻', help='如：煤炭 / 中国神华 / 留空则抓取全部财经要闻。')
        with col_mine_limit:
            mine_limit = st.slider('抓取条数', min_value=10, max_value=50, value=20, key='mine_limit_v2')
        with col_mine_btn:
            mine_submitted = st.button('⛏️ 一键挖掘', type='primary', key='btn_mine_news_v2', use_container_width=True)
        mine_output = st.container()
        if mine_submitted:
            with st.spinner('⛏️ 正在抓取新闻并执行 jieba 关键词提取与情感分析，预计需要 30-60 秒…'):
                try:
                    mined = engine.auto_mine_events(keyword=mine_keyword or None, source='auto', limit=mine_limit)
                    if mined is None or mined.empty:
                        st.session_state.mined_result = {'mined': None, 'error': 'empty', 'keyword': mine_keyword}
                    else:
                        st.session_state.mined_result = {'mined': mined, 'error': None, 'keyword': mine_keyword}
                except Exception as e:
                    st.session_state.mined_result = {'mined': None, 'error': str(e), 'keyword': mine_keyword}
        if st.session_state.get('mined_result'):
            mr = st.session_state.mined_result
            with mine_output:
                if mr.get('error') == 'empty':
                    st.warning(f"未抓取到与「{mr.get('keyword') or '全部'}」相关的新闻。")
                    st.info('💡 提示：尝试换一个更通用的关键词，或留空关键词抓取全部财经要闻。')
                elif mr.get('error'):
                    st.error(f"挖掘失败: {mr['error']}")
                else:
                    mined = mr['mined']
                    st.success(f'成功挖掘 {len(mined)} 条事件并入库！')
                    col_s1, col_s2, col_s3 = st.columns(3)
                    if 'type' not in mined.columns:
                        st.warning('⚠️ 挖掘结果缺少「type」字段，无法统计情感分布。')
                        pos_count = neg_count = neu_count = 0
                    else:
                        pos_count = len(mined[mined['type'] == '正面'])
                        neg_count = len(mined[mined['type'] == '负面'])
                        neu_count = len(mined[mined['type'] == '中性'])
                    with col_s1:
                        st.metric('正面事件', f'{pos_count} 条')
                    with col_s2:
                        st.metric('负面事件', f'{neg_count} 条')
                    with col_s3:
                        st.metric('中性事件', f'{neu_count} 条')
                    with st.expander('📰 挖掘结果（点击标题可跳转原文）', expanded=False):
                        _render_news_with_links(mined, title_col='title', url_col='url', date_col='date', source_col='source', type_col='type')
                    display_cols = [c for c in ['date', 'ticker', 'title', 'type', 'keywords', 'sentiment_score'] if c in mined.columns]
                    with st.expander('查看详细数据表格'):
                        _disp = mined[display_cols]
                        if 'date' in display_cols:
                            _disp = _disp.sort_values('date', ascending=False)
                        st.dataframe(_disp, use_container_width=True, height=400)
    except Exception as module_err:
        st.error(f'⚠️ 新闻挖掘模块异常: {module_err}')

@safe_fragment
def fragment_sentiment_report():
    sf_card('📊 新闻情感分析报告', "")
    try:
        report_container = st.container()
        with report_container:
            col_rpt_input, col_rpt_btn = st.columns([3, 1])
            with col_rpt_input:
                report_keyword = st.text_input('分析关键词', value='煤炭', key='report_keyword_v2', placeholder='如：煤炭 / 中国神华 / 留空分析全部财经要闻', help='如：煤炭 / 中国神华 / 留空则分析全部财经要闻。')
            with col_rpt_btn:
                rpt_submitted = st.button('📊 生成报告', type='primary', key='btn_sentiment_report_v2', use_container_width=True)
        if rpt_submitted or st.session_state.get('_retry_sentiment'):
            if st.session_state.get('_retry_sentiment'):
                st.session_state['_retry_sentiment'] = False
            with st.spinner('📊 正在抓取新闻并生成情感分析报告，预计需要 15-45 秒…'):
                try:
                    report = engine.sentiment_report(keyword=report_keyword or None, limit=50)
                    st.session_state.sentiment_report = report
                    st.session_state.sentiment_report_error = None
                except Exception as e:
                    st.session_state.sentiment_report = None
                    st.session_state.sentiment_report_error = str(e)
            if st.session_state.get('sentiment_report'):
                report = st.session_state.sentiment_report
                _total = report.get('total', 0) or 0
                _pos = report.get('positive_pct', 0) or 0
                _neg = report.get('negative_pct', 0) or 0
                _neu = report.get('neutral_pct', 0) or 0
                with report_container:
                    if _total == 0:
                        st.warning('未抓取到新闻。')
                    else:
                        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                        with col_r1:
                            st.metric('新闻总数', f'{_total} 条')
                        with col_r2:
                            st.metric('正面占比', f'{_pos}%')
                        with col_r3:
                            st.metric('负面占比', f'{_neg}%')
                        with col_r4:
                            st.metric('中性占比', f'{_neu}%')
                    import plotly.express as px
                    from modules.visualizer import _is_dark, SF_GRID, SF_BORDER, SF_TXT2
from modules.ui_kit import xc_handle_error
                    _dark = _is_dark()
                    pie_df = pd.DataFrame([{'类型': '正面', '占比': _pos}, {'类型': '负面', '占比': _neg}, {'类型': '中性', '占比': _neu}])
                    color_map = {'正面': UP_COLOR, '负面': DOWN_COLOR, '中性': '#94a3b8'}
                    fig_pie = px.pie(pie_df, values='占比', names='类型', color='类型', color_discrete_map=color_map, title=f'「{report_keyword}」新闻情感分布')
                    if _dark:
                        fig_pie.update_layout(template='starfield_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font={'color': SF_TXT2}, height=350)
                    else:
                        fig_pie.update_layout(template='plotly_white', height=350)
                    st.plotly_chart(fig_pie, use_container_width=True, config={"displaylogo": False, "responsive": True})
                    _top_kws = report.get('top_keywords') or []
                    if _top_kws:
                        st.markdown('#### 热门关键词 TOP15')
                        kw_df = pd.DataFrame(_top_kws, columns=['关键词', '频次'])
                        _maxf = kw_df['频次'].max() if not kw_df.empty else 0
                        kw_df['标记'] = kw_df['频次'].apply(lambda f: '🔥热门' if f >= max(3, _maxf * 0.6) else '')
                        _hot = kw_df[kw_df['标记'] == '🔥热门']['关键词'].tolist()
                        if _hot:
                            st.caption('🔥 热门关键词：' + '、'.join(_hot))
                        fig_kw = px.bar(kw_df, x='频次', y='关键词', orientation='h', title='关键词频次排行', color='频次', color_continuous_scale='Reds')
                        if _dark:
                            fig_kw.update_layout(template='starfield_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font={'color': SF_TXT2}, height=400, yaxis=dict(autorange='reversed', gridcolor=SF_GRID, linecolor=SF_BORDER, tickfont={'color': SF_TXT2}), xaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER, tickfont={'color': SF_TXT2}))
                        else:
                            fig_kw.update_layout(template='plotly_white', height=400, yaxis=dict(autorange='reversed'))
                        st.plotly_chart(fig_kw, use_container_width=True, config={"displaylogo": False, "responsive": True})
                    if report.get('sample_news'):
                        st.markdown('#### 正负面新闻样本（点击标题可跳转原文）')
                        for s in report['sample_news']:
                            title = s.get('title')
                            if not title:
                                continue
                            sentiment = s.get('sentiment', '')
                            color = UP_COLOR if sentiment == '正面' else DOWN_COLOR
                            url = s.get('url', '') or s.get('link', '') or s.get('source_url', '') or s.get('href', '') or ''
                            title_html = html.escape(str(title))
                            score_str = f"<small>(情感分: {s.get('score', '?')})</small>"
                            if url and url.startswith('http'):
                                linked_title = f'<a href="{html.escape(url)}" target="_blank" style="color:{color};text-decoration:underline;font-weight:600;">{title_html}</a>'
                                origin_link = f' <a href="{html.escape(url)}" target="_blank" style="font-size:0.8em;color:#3498db;text-decoration:none;">🔗 原文</a>'
                                st.markdown(f'[{sentiment}] {linked_title} {score_str} {origin_link}', unsafe_allow_html=True)
                            else:
                                st.markdown(f"[{sentiment}] <span style='color:{color};'>{title_html}</span> {score_str}", unsafe_allow_html=True)
        elif st.session_state.get('sentiment_report_error'):
            with report_container:
                st.error(f'生成报告失败: {st.session_state.sentiment_report_error}')
                if st.button('🔄 重试', key='btn_sentiment_retry'):
                    st.session_state['_retry_sentiment'] = True
    except Exception as module_err:
        st.error(f'⚠️ 情感报告模块异常: {module_err}')
fragment_signal_score()
fragment_live_keywords()
fragment_timeline()
fragment_event_manage()
fragment_news_mine()
fragment_sentiment_report()
with st.expander('💡 使用说明', expanded=False):
    st.markdown('\n    **事件追踪使用指引**\n    - **信号评分**：选股票 → 填关键词 → 开始评分，查看价格 / 事件 / 宏观三维度信号。\n    - **实时关键词**：一键提取所选股票的最新新闻关键词。\n    - **事件时间轴**：选标的 + 区间，生成 K 线与事件叠加图。\n    - **事件管理**：手动添加 / 查看事件库。\n    - **新闻挖掘 / 情感报告**：抓取新闻做情感分析与入库。\n    - ⚠️ 所有数据仅供参考，不构成投资建议。\n    ')
with st.expander('🔗 相关事件 / 标的推荐', expanded=False):
    if '_rec_cache' not in st.session_state:
        try:
            st.session_state._rec_cache = engine._load_events()
        except Exception:
            st.session_state._rec_cache = None
    _ev = st.session_state.get('_rec_cache')
    if _ev is not None and (not _ev.empty) and ('ticker' in _ev.columns):
        _top = _ev['ticker'].value_counts().head(8)
        if len(_top) == 0:
            st.caption('暂无推荐数据。')
        else:
            st.caption('📌 事件库中提及最多的标的（点击填入信号评分）')
            _cc = st.columns(len(_top))
            for _j, (_code, _cnt) in enumerate(_top.items()):
                with _cc[_j]:
                    if st.button(f'{_code}\n{_cnt}条', key=f'rec_{_code}'):
                        st.session_state['sig_ticker'] = str(_code)
                        st.rerun()
    else:
        st.caption('暂无推荐数据。')
with st.expander('⌨️ 快捷键', expanded=False):
    st.markdown('\n    本页为 Streamlit Web 应用，未绑定全局快捷键，以下为操作提示：\n    - **回车**：在表单输入框内按回车等效于点击该表单的提交按钮。\n    - **Tab**：在输入控件间切换焦点。\n    - **浏览器 F5 / Cmd·Ctrl+R**：刷新整页（将丢失未保存的会话状态）。\n    - 各模块「🔄 刷新」按钮可局部刷新对应模块。\n    ')
st.markdown('<button onclick="parent.window.scrollTo({top:0,behavior:\'smooth\'});" style="position:fixed;right:24px;bottom:12px;z-index:9999;background:#3498db;color:#fff;border:none;border-radius:20px;padding:8px 14px;font-size:13px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.3);">↑ 回到顶部</button>', unsafe_allow_html=True)