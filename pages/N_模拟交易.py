"""
模拟交易组合（Paper Trading）
--------------------------------
一个完全自包含的模拟交易模块：用虚拟资金买卖 A 股，跟踪持仓、盈亏与净值曲线。

  • 持仓 / 成交记录持久化到本地 data/paper_{user}.json（刷新不丢失，模块独立运行）
  • 现价取自实时行情，失败降级到日线收盘价
  • 支持买入 / 卖出 / 重置账户，展示总资产、累计盈亏、胜率与净值曲线

不接入真实券商，仅用于策略演练与学习。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime
import streamlit.components.v1 as components
from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric
import modules.scroll_nav as sn
from modules.session import get_user, trading_autorefresh
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, safe_fragment
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast, UP, DOWN
dark = render_standard_page(title='模拟交易组合', icon='🎮', caption='虚拟资金练习；持仓持久化到本地，模块独立运行，不影响真实账户。')

sf_card("🎮 模拟交易组合", "用虚拟资金买卖 A 股，跟踪持仓、盈亏与净值曲线；持仓持久化到本地，不接入真实券商，仅供策略演练。", icon="💡")
st.caption('⚠️ 模拟交易，仅供学习，不构成任何投资建议。')

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
FETCHER = StockFetcher()
INIT_CASH = 1000000.0
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def _book_path(user):
    return os.path.join(DATA_DIR, f'paper_{user}.json')

def _load_book(user):
    p = _book_path(user)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return {'init_cash': INIT_CASH, 'cash': INIT_CASH, 'positions': {}, 'trades': [], 'equity': []}

def _save_book(user, book):
    json.dump(book, open(_book_path(user), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

def _snapshot(book, assets):
    """记录一个净值快照（按分钟去重），用于绘制净值曲线。"""
    t = datetime.now().strftime('%Y-%m-%d %H:%M')
    eq = book.setdefault('equity', [])
    if eq and eq[-1][0] == t:
        eq[-1] = (t, round(assets, 2))
    else:
        eq.append((t, round(assets, 2)))
    if len(eq) > 500:
        eq[:] = eq[-500:]

@st.cache_data(ttl=20, show_spinner=False)
def _price(code):
    try:
        q = FETCHER.get_realtime_quote(code)
        if q and q.get('current'):
            return (float(q['current']), q.get('name') or code)
    except Exception:
        pass
    try:
        d = FETCHER.get_daily(code, start='2024-01-01')
        if d is not None and (not d.empty):
            return (float(d.iloc[-1]['close']), FETCHER.get_name_only(code))
    except Exception:
        pass
    return (None, code)

def _recompute(book):
    total_mv = 0.0
    rows = []
    for code, pos in book['positions'].items():
        if not isinstance(pos, dict) or 'qty' not in pos or 'avg_cost' not in pos:
            continue
        price, name = _price(code)
        price = price if price is not None else pos['avg_cost']
        qty = pos['qty']
        mv = price * qty
        cost = pos['avg_cost'] * qty
        pnl = mv - cost
        total_mv += mv
        rows.append({'代码': code, '名称': name, '持仓(股)': qty, '成本价': round(pos['avg_cost'], 2), '现价': round(price, 2), '市值': round(mv, 2), '盈亏': round(pnl, 2), '盈亏%': round((price / pos['avg_cost'] - 1) * 100, 2) if pos['avg_cost'] else 0.0})
    assets = book['cash'] + total_mv
    return (rows, assets, total_mv)

@safe_fragment('模拟交易')
def fragment_paper():
    trading_autorefresh(key='paper_autorefresh')
    user = (get_user() or {}).get('username', 'guest')
    book = _load_book(user)
    st.caption(f'🕒 最近刷新：{datetime.now():%Y-%m-%d %H:%M:%S}')
    if st.button('🔄 刷新', key='pt_manual_refresh', help='手动刷新行情与持仓快照'):
        st.rerun(scope='fragment')
    st.session_state.setdefault('_pt_recent', [])
    if st.session_state['_pt_recent']:
        st.caption('🕘 最近浏览：' + '  '.join((f'`{c}`' for c in st.session_state['_pt_recent'][-6:][::-1])))
    st.session_state.setdefault('_pt_fav', [])
    with safe_section('账户概览'):
        with st.spinner('加载持仓行情中…'):
            rows, assets, mv = _recompute(book)
        pnl_total = assets - book['init_cash']
        pnl_pct = pnl_total / book['init_cash'] * 100
        c1, c2, c3, c4 = st.columns(4)
        c1.metric('总资产', f'¥{assets:,.0f}')
        c2.metric('可用现金', f"¥{book['cash']:,.0f}")
        c3.metric('持仓市值', f'¥{mv:,.0f}')
        c4.metric('累计盈亏', f'¥{pnl_total:,.0f}', delta=f'{pnl_pct:+.2f}%')
        st.caption('ℹ️ 累计盈亏 = 总资产 − 初始资金；净值曲线基于每笔成交后的总资产快照绘制。')
    st.markdown('---')
    st.subheader('💱 交易')
    col_b, col_s = st.columns(2)
    with col_b:
        st.markdown('**买入**')
        bcode = stock_search_input('买入标的', key='pt_buy')
        bqty = st.number_input('买入股数', min_value=100, step=100, value=st.session_state.get('_pt_def_bqty', 100), key='pt_bqty', placeholder='如 100（100 股的整数倍）')
        if bqty < 100 or bqty % 100 != 0:
            st.warning('⚠️ 买入股数需为 100 股的整数倍（A 股最小交易单位）。')
        _braw = (bcode or '').strip()
        _bok = len(_braw) == 6 and _braw.isdigit()
        if st.button('确认买入', type='primary', key='pt_buy_btn', use_container_width=True, disabled=not _bok, help='请先在上方输入有效的 6 位股票代码' if not _bok else '按当前设置的数量买入'):
            code = (bcode or '').strip().zfill(6)
            if len(code) != 6 or not code.isdigit():
                st.error('请输入有效的 6 位股票代码。')
            else:
                with st.spinner('获取现价中…'):
                    price, name = _price(code)
                if price is None:
                    st.error('无法获取现价，买入失败。')
                else:
                    cost = price * bqty
                    if cost > book['cash']:
                        st.error(f"现金不足：需要 ¥{cost:,.0f}，可用 ¥{book['cash']:,.0f}。")
                    else:
                        book['cash'] -= cost
                        pos = book['positions'].get(code)
                        if pos:
                            tot_qty = pos['qty'] + bqty
                            pos['avg_cost'] = (pos['avg_cost'] * pos['qty'] + cost) / tot_qty
                            pos['qty'] = tot_qty
                        else:
                            book['positions'][code] = {'name': name, 'qty': bqty, 'avg_cost': price}
                        book['trades'].append({'time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'code': code, 'name': name, 'side': '买', 'price': round(price, 2), 'qty': bqty, 'amount': round(cost, 2)})
                        rows, assets, mv = _recompute(book)
                        _snapshot(book, assets)
                        _save_book(user, book)
                        _toast(f'已买入 {name}({code}) {bqty} 股 @ ¥{price:.2f}')
                        st.session_state['_pt_def_bqty'] = bqty
                        if code not in st.session_state['_pt_recent']:
                            st.session_state['_pt_recent'] = (st.session_state['_pt_recent'] + [code])[-10:]
        if st.button('⭐ 收藏该标的', key='pt_fav_add', use_container_width=True):
            _fc = (bcode or '').strip().zfill(6)
            if len(_fc) == 6 and _fc.isdigit() and (_fc not in st.session_state['_pt_fav']):
                st.session_state['_pt_fav'].append(_fc)
                _toast(f'已收藏 {_fc}')
            else:
                st.warning('请输入有效代码后再收藏。')
    with col_s:
        st.markdown('**卖出**')
        scode = stock_search_input('卖出标的', key='pt_sell')
        sqty = st.number_input('卖出股数', min_value=100, step=100, value=st.session_state.get('_pt_def_sqty', 100), key='pt_sqty', placeholder='如 100（100 股的整数倍）')
        if sqty < 100 or sqty % 100 != 0:
            st.warning('⚠️ 卖出股数需为 100 股的整数倍。')
        _sraw = (scode or '').strip()
        _sok = len(_sraw) == 6 and _sraw.isdigit()
        _skey = _sraw.zfill(6)
        _shas = bool(book['positions'].get(_skey)) if _sok else False
        _sell_disabled = not (_sok and _shas)
        _sell_help = '请先输入有效代码，且当前持有该标的' if _sell_disabled else '按当前设置的数量卖出'
        if st.button('确认卖出', key='pt_sell_btn', use_container_width=True, disabled=_sell_disabled, help=_sell_help):
            if st.confirm('确定卖出该持仓？此操作不可撤销。', key='pt_sell_confirm'):
                code = (scode or '').strip().zfill(6)
                pos = book['positions'].get(code)
                if not pos:
                    st.error('当前未持有该标的。')
                elif sqty > pos['qty']:
                    st.error(f"持仓不足：持有 {pos['qty']} 股。")
                else:
                    with st.spinner('获取现价中…'):
                        price, name = _price(code)
                    if price is None:
                        st.error('无法获取现价，卖出失败。')
                    else:
                        proceeds = price * sqty
                        book['cash'] += proceeds
                        pos['qty'] -= sqty
                        if pos['qty'] <= 0:
                            del book['positions'][code]
                        book['trades'].append({'time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'code': code, 'name': name, 'side': '卖', 'price': round(price, 2), 'qty': sqty, 'amount': round(proceeds, 2)})
                        rows, assets, mv = _recompute(book)
                        _snapshot(book, assets)
                        _save_book(user, book)
                        _toast(f'已卖出 {name}({code}) {sqty} 股 @ ¥{price:.2f}')
                        st.session_state['_pt_def_sqty'] = sqty
                        if code not in st.session_state['_pt_recent']:
                            st.session_state['_pt_recent'] = (st.session_state['_pt_recent'] + [code])[-10:]
    st.markdown('---')
    tab_p, tab_t, tab_e = st.tabs(['📦 当前持仓', '🧾 成交记录', '📈 净值曲线'])
    with tab_p:
        st.caption(f'📦 当前持仓：共 {len(rows)} 条')
        if rows:
            dfp = pd.DataFrame(rows)
            dfp = dfp.sort_values('盈亏', ascending=False, ignore_index=True)

            def _color_row(r):
                c = UP if r['盈亏'] >= 0 else DOWN
                return [f'color:{c}'] * len(r)
            st.dataframe(dfp.style.apply(_color_row, axis=1), use_container_width=True, hide_index=True, height=400)
            st.markdown('**批量操作**')
            _pt_sel = [r['代码'] for r in rows if st.checkbox(f"选择 {r['名称']}({r['代码']})", key=f"pt_sel_{r['代码']}")]
            if _pt_sel:
                _b1, _b2 = st.columns(2)
                with _b1:
                    if st.button('⭐ 批量加自选', key='pt_batch_fav', use_container_width=True):
                        try:
                            from modules.admin_api import add_watchlist
                            for _c in _pt_sel:
                                add_watchlist(_c)
                            _toast(f"已加自选：{', '.join(_pt_sel)}")
                        except Exception as _e:
                            st.error(f'批量加自选失败：{_e}')
                with _b2:
                    if st.button('📤 批量平仓', key='pt_batch_close', use_container_width=True):
                        with st.spinner('批量平仓中…'):
                            for _c in _pt_sel:
                                _pos = book['positions'].get(_c)
                                if _pos:
                                    _pr, _nm = _price(_c)
                                    if _pr is None:
                                        _pr = _pos['avg_cost']
                                    _proceeds = _pr * _pos['qty']
                                    book['cash'] += _proceeds
                                    book['trades'].append({'time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'code': _c, 'name': _nm, 'side': '卖', 'price': round(_pr, 2), 'qty': _pos['qty'], 'amount': round(_proceeds, 2)})
                                    del book['positions'][_c]
                            rows, assets, mv = _recompute(book)
                            _snapshot(book, assets)
                            _save_book(user, book)
                        _toast('已批量平仓所选持仓')
                        st.rerun(scope='fragment')
        else:
            _empty_info('暂无持仓。先在上方搜索框输入代码（如 600519 贵州茅台），设置数量后点「买入」开始你的第一笔模拟交易。')
    with tab_t:
        st.caption(f"🧾 成交记录：共 {len(book['trades'])} 条")
        if book['trades']:
            dft = pd.DataFrame(book['trades'])
            dft['成交时间'] = dft['time'].apply(_fmt_rel)
            dft = dft.drop(columns=['time'])
            _kw = st.text_input('🔍 搜索成交（代码 / 名称 / 方向）', key='pt_trade_filter')
            if _kw and _kw.strip():
                _kw = _kw.strip()
                _mask = dft.astype(str).apply(lambda col: col.str.contains(_kw, case=False, na=False)).any(axis=1)
                dft = dft[_mask]
                if dft.empty:
                    st.caption('🔍 未找到匹配的成交记录。')
            _show_key = 'pt_trade_show'
            _show_n = st.session_state.get(_show_key, 10)
            st.dataframe(dft.head(_show_n), use_container_width=True, hide_index=True, height=400)
            if len(dft) > _show_n:
                if st.button('显示更多 ▼', key='pt_trade_more', use_container_width=True):
                    st.session_state[_show_key] = min(_show_n + 10, len(dft))
        else:
            _empty_info('暂无成交记录。买入成功后，这里会逐笔显示你的成交明细。')
    with tab_e:
        eq = [('起始', book['init_cash'])] + list(book.get('equity', []) or [])
        _clean_eq = []
        for e in eq:
            if isinstance(e, (list, tuple)) and len(e) >= 2 and isinstance(e[1], (int, float)) and (e[1] == e[1]):
                _clean_eq.append((e[0], float(e[1])))
        eq = _clean_eq
        if len(eq) >= 2:
            xs = [e[0] for e in eq]
            ys = [e[1] for e in eq]
            _pt_types = ['线', '柱', '面积']
            _pt_ct = st.radio('图表类型', _pt_types, index=_pt_types.index(st.session_state.get('_pt_eq_type', '线')), horizontal=True, key='pt_eq_type', help='切换净值曲线展示样式，不改变底层数据。')
            fig = go.Figure()
            _pt_color = UP if ys[-1] >= book['init_cash'] else DOWN
            if _pt_ct == '柱':
                fig.add_trace(go.Bar(x=xs, y=ys, name='总资产', marker_color=_pt_color))
            elif _pt_ct == '面积':
                fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='总资产', fill='tozeroy', line=dict(color=_pt_color, width=2), fillcolor=_pt_color))
            else:
                fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines+markers', name='总资产', line=dict(color=_pt_color, width=2)))
            fig.add_hline(y=book['init_cash'], line_dash='dot', line_color='#888', annotation_text='初始资金', annotation_position='bottom right')
            fig.update_layout(height=360, template='plotly_dark' if dark else 'plotly_white', xaxis_title='时间', yaxis_title='总资产(元)', margin=dict(t=20, l=60, r=20, b=40))
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True})
        else:
            _empty_info('完成至少一笔交易后生成净值曲线。')
        st.caption('💡 在上方「💱 交易」买入或卖出后，这里会基于每笔成交后的总资产快照绘制净值曲线。')
        st.caption('数据来源：东方财富 / 新浪财经（实时行情，失败降级日线收盘价）。')
    st.markdown('---')
    st.subheader('🔗 相关标的推荐')
    import random as _rnd
    _cand = ['600519', '000858', '601318', '000333', '600036', '601012', '300750', '002594', '600276', '000001']
    _rec = _rnd.sample(_cand, 5)
    st.caption('📌 ' + '  '.join((f'`{c}`' for c in _rec)))
    with st.expander('💡 使用说明'):
        st.markdown('• 本页为模拟交易，使用虚拟资金，不影响真实账户。\n• 买入/卖出需输入 6 位代码，并设置 100 股整数倍的数量。\n• 持仓与成交持久化到本地文件，刷新不丢失。\n• 净值曲线基于每笔成交后的总资产快照绘制。\n• 点击「🔄 刷新」可手动刷新行情；可收藏标的、查看最近浏览。')
    with st.expander('⌨️ 快捷键'):
        st.markdown('• 当前页面以内联按钮/表单交互为主，无全局键盘快捷键。\n• 行情每 20 秒自动刷新（见账户概览上方提示）。\n• 可用「⭐ 收藏该标的」与「最近浏览」快速回到关注的股票。')
    with st.expander('⭐ 我的收藏'):
        _pt_favs = st.session_state.get('_pt_fav', [])
        if _pt_favs:
            for _f in list(_pt_favs):
                _fc1, _fc2 = st.columns([4, 1])
                _fc1.caption(f'`{_f}`')
                if _fc2.button('移除', key=f'pt_fav_del_{_f}'):
                    st.session_state['_pt_fav'].remove(_f)
        else:
            st.caption('暂无收藏。在「买入」区点「⭐ 收藏该标的」即可添加。')
    st.markdown('---')
    if st.button('🗑️ 重置模拟账户', key='pt_reset', help='清空持仓与成交，恢复初始资金'):
        if st.confirm('确定重置？此操作不可撤销。'):
            book = {'init_cash': INIT_CASH, 'cash': INIT_CASH, 'positions': {}, 'trades': [], 'equity': []}
            _save_book(user, book)
            _toast('账户已重置。')
    st.divider()
    if st.button('↑ 回到顶部', key='pt_back_top', use_container_width=True):
        st.session_state['_pt_scroll_top'] = True
    if st.session_state.get('_pt_scroll_top'):
        sn.back_to_top_button()
        st.session_state['_pt_scroll_top'] = False
fragment_paper()