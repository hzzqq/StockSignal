"""
页面：仓位管理
持仓记录、卖出交易、盈亏统计、Excel导出
"""
import os
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner
render_standard_page(title='仓位管理', icon='💰', caption='⚠️ 本页为模拟/历史持仓管理，仅供学习，不构成投资建议。', layout='wide')

sf_card("仓位管理导读", "记录持仓、卖出交易、盈亏统计与 Excel 导出。本页为模拟/历史持仓管理，仅供学习，不构成投资建议。", icon="💰")

_c1, _c2 = st.columns(2)
with _c1:
    st.page_link('pages/N_模拟交易.py', label='🎮 前往模拟交易', icon='🎮')
with _c2:
    st.page_link('pages/H_组合收益.py', label='📈 前往组合收益', icon='📈')
if st.button('🔄 刷新', key='pm_refresh_top', help='重新加载本页持仓与行情'):
    st.rerun()
st.session_state.setdefault('_pm_recent', [])
if st.session_state['_pm_recent']:
    st.caption('🕘 最近浏览：' + '  '.join((f'`{c}`' for c in st.session_state['_pm_recent'][-6:][::-1])))
_PM_PREF_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pm_prefs.json')

def _load_pm_pref(k, d):
    try:
        if os.path.exists(_PM_PREF_PATH):
            return json.load(open(_PM_PREF_PATH, encoding='utf-8')).get(k, d)
    except Exception:
        pass
    return d

def _save_pm_pref(k, v):
    try:
        _d = {}
        if os.path.exists(_PM_PREF_PATH):
            _d = json.load(open(_PM_PREF_PATH, encoding='utf-8'))
        _d[k] = v
        json.dump(_d, open(_PM_PREF_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception:
        pass
from modules.portfolio import PortfolioManager
from modules.search_ui import stock_search_input
import modules.scroll_nav as sn
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
    st.dataframe(display_pos[show_cols].head(_pshow_n), use_container_width=True, hide_index=True, height=400)
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
            if st.button('⭐ 批量加自选', key='pm_batch_fav', use_container_width=True):
                try:
                    from modules.admin_api import add_watchlist
                    for _t in _pm_sel:
                        add_watchlist(_t)
                    _toast(f"已加自选：{', '.join(_pm_sel)}")
                except Exception as e:
                    xc_handle_error("批量加自选失败", e, hint="请稍后重试，或检查网络与数据源连接")
        with _pb2:
            if st.button('📤 批量平仓', key='pm_batch_close', use_container_width=True):
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
    if col.button(f'{qv:,} 股', use_container_width=True, key=f'buy_quick_{qv}'):
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
                        st.dataframe(_qdf, use_container_width=True, hide_index=True, height=400)
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
if st.button('⭐ ＋自选（当前买入标的）', key='pm_add_watch', use_container_width=True):
    try:
        from modules.admin_api import add_watchlist
        add_watchlist(buy_ticker)
        _toast(f'已加入自选：{buy_label} ({buy_ticker})')
    except Exception as e:
        xc_handle_error("加入自选失败", e, hint="请稍后重试，或检查网络与数据源连接")
if st.button('⭐ 收藏（本地星标）', key='pm_fav_add', use_container_width=True):
    st.session_state.setdefault('_pm_fav', [])
    _ft = (buy_ticker or '').strip()
    if _ft and _ft not in st.session_state['_pm_fav']:
        st.session_state['_pm_fav'].append(_ft)
        _toast(f'已收藏（星标）：{_ft}')
    else:
        xc_warn_box('该标的已收藏或代码为空。')
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
            st.metric('可卖股数', f'{sellable_shares:,} 股')
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
                        st.dataframe(_qdf, use_container_width=True, hide_index=True, height=400)
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
    st.dataframe(display_trades[show_cols], use_container_width=True, hide_index=True, height=400)
sf_card('📈 盈亏统计', '汇总总成本、总市值、总盈亏与收益率，并绘制盈亏曲线与持仓明细。')
positions = pm.get_positions()
if not positions.empty:
    with st.spinner('正在获取行情并计算盈亏...'):
        try:
            pnl_df = pm.calc_pnl()
            summary = pm.summary()
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric('总成本', f"¥{summary.get('total_cost', 0):,.2f}")
            with col2:
                st.metric('总市值', f"¥{summary.get('total_market_value', 0):,.2f}")
            with col3:
                delta_pnl = summary.get('delta_pnl', 0)
                st.metric('总盈亏', f"¥{summary.get('total_pnl', 0):,.2f}", delta=f"{summary.get('delta_pnl', 0):+.2f}" if abs(delta_pnl or 0) > 0.01 else None)
            with col4:
                st.metric('总收益率', f"{summary.get('total_pnl_pct', 0):+.2f}%")
            st.caption('数据来源：东方财富 / 新浪财经（实时行情 + 日线兜底）。')
            if not pnl_df.empty:
                from modules.visualizer import Visualizer
                st.markdown('---')
                fig = Visualizer.portfolio_pnl(pnl_df)
                st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True})
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
                st.dataframe(display_pnl[pnl_cols], use_container_width=True, hide_index=True, height=400)
            sf_card('🔬 盈亏归因', '按个股拆分盈亏贡献，定位收益的主要来源与拖累项。')
            attribution = pm.pnl_attribution()
            if not attribution.empty:
                attr_fetcher = StockFetcher()
                attribution['股票'] = attribution['ticker'].apply(lambda x: fetcher.get_name_only(x) or attr_fetcher.get_stock_name(x))
                display_attr = attribution[['股票', 'ticker', 'pnl', 'pnl_pct', 'contribution']].copy()
                st.dataframe(display_attr, use_container_width=True, hide_index=True, height=400)
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
st.divider()
if st.button('↑ 回到顶部', key='cang_mgr_top', use_container_width=True):
    sn.back_to_top_button()
    st.session_state['_mgr_scroll_top'] = False