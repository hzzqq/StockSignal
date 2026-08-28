"""
页面1：行情看板
指数迷你卡、行业板块涨跌榜（含涨跌排行/分布折叠区）、龙虎榜、个股相关性矩阵。
K 线、参数设置、技术面分析已迁移至「股票选取」模块。
"""
import logging
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import concurrent.futures as _cf
from datetime import datetime, timedelta, time
from modules.colors import UP_COLOR, DOWN_COLOR
from modules.search_ui import multi_stock_search_input, stock_search_input
from modules.session import api_kline, safe_switch_page, fragment_market_alerts_panel, api_get, api_post, api_delete, get_token, clear_auth
from modules.format_helpers import safe_int
from modules.widgets import render_index_compact
from modules.page_guard import safe_fragment
from modules.chart_cache import cached_fig
from modules.page_utils import render_standard_page, get_fetcher
from modules.ui_theme import sf_card, sf_metric
from modules.page_widgets import _empty_info, _fmt_yi, _toast, is_trading_now
from modules.fundamental_helpers import fund_one

from modules.ui_kit import xc_error_box, xc_handle_error, xc_success_box, xc_warn_box, info_banner
logger = logging.getLogger(__name__)
dark = render_standard_page(title='行情看板', icon='📈', layout='wide')
render_index_compact(cols_per_row=5)
sf_card("页面导读", "上方为市场指数迷你卡；下方输入代码 / 名称 / 拼音首字母搜索股票，点击结果即选中，可一键加入自选股，自选行情实时同步。K 线、技术面分析请前往「股票选取」。", icon="📈")
sf_card('🔍 搜索股票 · 加入自选', "")
st.caption('输入代码 / 名称 / 拼音首字母，匹配结果直接显示在输入框下方（含市场标签），点击结果即选中；选中后可一键加入自选股，下方「自选行情」会实时同步。')
_wb_code = stock_search_input(label='输入代码 / 名称 / 拼音', key='wb_search', default='600519')
_wb_c1, _wb_c2 = st.columns([1, 3])
with _wb_c1:
    if st.button('☆ 加入自选股', key='wb_add_wl', use_container_width=True):
        if _wb_code:
            _sc, _body = api_post('/api/watchlist', {'stock_code': _wb_code}, timeout=5)
            if _sc == 200 and isinstance(_body, dict) and (_body.get('status') == 'ok'):
                _toast(f'✅ 已加入自选股 {_wb_code}')
                st.rerun()
            else:
                _msg = _body.get('message', '添加失败') if isinstance(_body, dict) else '添加失败'
                xc_warn_box(f'⚠️ {_msg}')
fetcher = get_fetcher()

@st.cache_data(ttl=3600, show_spinner=False)
def _get_stock_concept(code: str) -> str:
    """获取个股所属概念/行业（用于龙虎榜表格）。

    优先尝试 fetcher.get_stock_concept；不存在或失败时，用 akshare 个股信息
    里的「行业」兜底；若仍失败则填充「—」但保留列。

    行业/概念属低频变化数据，@st.cache_data(ttl=3600) 缓存 1 小时，
    避免龙虎榜表格每只股票每次刷新都发起网络请求（交易时段每 60s 刷新的 N+1 问题）。
    """
    try:
        f = get_fetcher()
        if hasattr(f, 'get_stock_concept'):
            res = f.get_stock_concept(code)
            if res:
                if isinstance(res, (list, tuple, set)):
                    return '、'.join((str(x) for x in res)) if res else '—'
                return str(res)
    except Exception:
        pass
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=str(code))
        if info is not None and (not info.empty) and ('item' in info.columns):
            rec = info[info['item'] == '行业']
            if not rec.empty:
                val = rec['value'].iloc[0]
                if val:
                    return str(val)
    except Exception:
        pass
    return '—'

def _render_sector_cards(df, top_n=24):
    show = df.head(top_n) if top_n else df
    cards = []
    for _, row in show.iterrows():
        name = str(row.get('sector', ''))
        try:
            pct = float(row.get('change_pct', 0))
        except Exception:
            pct = 0.0
        up = pct >= 0
        color = UP_COLOR if up else DOWN_COLOR
        bg = '#fde8e6' if up else '#e8f9ef'
        arrow = '▲' if up else '▼'
        cards.append(f'<div class="xc-sector-card" style="border-left-color:{color};"><div class="xc-sector-name">{name}</div><div class="xc-sector-pct" style="color:{color};">{arrow} {pct:+.2f}%</div></div>')
    grid = ''.join(cards)
    st.markdown(
        f'<div class="ss-chart" style="margin-top:0">'
        f'<div class="xc-sector-grid">{grid}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if top_n and len(df) > top_n:
        st.caption(f'仅显示涨幅前 {top_n} 名（共 {len(df)} 个行业）。')

def _get_market_status():
    now = datetime.now()
    t = now.time()
    weekday = now.weekday()
    if weekday >= 5:
        return (False, '⚪ 已休市（周末），展示最后一交易日数据', 0)
    am_start, am_end = (time(9, 30), time(11, 30))
    pm_start, pm_end = (time(13, 0), time(15, 0))
    after_close = time(16, 0)
    if am_start <= t <= am_end:
        return (True, '🟢 上午交易中（实时数据）', 60 * 1000)
    elif am_end < t < pm_start:
        return (False, '🟡 午间休市，展示上午收盘数据', 60 * 1000)
    elif pm_start <= t <= pm_end:
        return (True, '🟢 下午交易中（实时数据）', 60 * 1000)
    elif pm_end < t <= after_close:
        return (False, '🔵 已收盘，展示今日全天数据', 0)
    else:
        if t < am_start:
            return (False, '⚪ 尚未开盘，展示上一交易日数据', 0)
        return (False, '⚪ 已休市，展示最后一交易日数据', 0)

@cached_fig(ttl=120)
def _build_sector_heatmap_fig(detail_df):
    """板块涨跌分布热力图（缓存未命中时才延迟导入 Visualizer，避免每轮刷新前页加载 0.95s）。"""
    from modules.visualizer import Visualizer
    return Visualizer.sector_heatmap(detail_df, title='全部行业板块涨跌幅')


@cached_fig(ttl=120)
def _build_correlation_fig(daily_dict):
    """个股相关性矩阵（缓存未命中时才延迟导入 Visualizer）。"""
    from modules.visualizer import Visualizer
    return Visualizer.correlation_matrix(daily_dict)


@safe_fragment('行业板块涨跌榜')
def fragment_sector_board():
    """行业板块涨跌榜（板块图构建已迁移至模块级 _build_sector_heatmap_fig，延迟导入 Visualizer 仅缓存未命中时触发）。"""
    sf_card('🏭 行业板块涨跌榜', "")
    try:
        from modules.autorefresh import st_autorefresh
        is_open, status_text, refresh_ms = _get_market_status()
        if refresh_ms > 0:
            st_autorefresh(interval=refresh_ms, key='sector_autorefresh')
    except Exception:
        is_open, status_text, _ = _get_market_status()
    st.caption(status_text)
    try:
        sector_df = fetcher.get_sector_list()
    except Exception as e:
        sector_df = None
        logger.warning("获取板块数据失败: %s", e)
        xc_error_box("获取板块数据失败", hint="请稍后重试，或检查网络/数据源连接")
    if sector_df is not None and (not sector_df.empty):
        _sec_col = next((c for c in sector_df.columns if c in ('sector', '板块', '行业', '名称')), None)
        if _sec_col and _sec_col != 'sector':
            sector_df = sector_df.rename(columns={_sec_col: 'sector'})
        _chg_col = next((c for c in sector_df.columns if c in ('change_pct', '涨跌幅', '涨跌幅(%)')), None)
        if _chg_col and _chg_col != 'change_pct':
            sector_df = sector_df.rename(columns={_chg_col: 'change_pct'})
        if 'sector' not in sector_df.columns:
            sector_df['sector'] = ''
        if 'change_pct' not in sector_df.columns:
            sector_df['change_pct'] = 0.0
            xc_warn_box('⚠️ 板块涨跌幅字段缺失，已按 0 处理；数据源可能已变更字段名。')
        sector_df['change_pct'] = pd.to_numeric(sector_df['change_pct'], errors='coerce').fillna(0)
        sector_df = sector_df.sort_values('change_pct', ascending=False).reset_index(drop=True)
        if sector_df['change_pct'].abs().max() < 0.01:
            xc_warn_box('⚠️ 当前数据源未返回板块涨跌幅，仅展示行业列表。交易时间或网络恢复后会自动获取真实数据。')
        _render_sector_cards(sector_df, top_n=24)
    else:
        xc_warn_box('未获取到板块数据。可能处于非交易时段、数据源暂不可用或网络波动；交易时段会自动刷新，也可手动刷新页面重试。')
    with st.expander('📊 板块涨跌详情（点击展开）', expanded=False):
        if sector_df is not None and (not sector_df.empty):
            try:
                detail_df = sector_df.copy()
                detail_df['排名'] = range(1, len(detail_df) + 1)
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.markdown('#### 涨跌排行表格')
                    display_cols = ['排名', 'sector', 'change_pct']
                    st.dataframe(detail_df[display_cols].rename(columns={'sector': '板块', 'change_pct': '涨跌幅'}), use_container_width=True, column_config={'涨跌幅': st.column_config.NumberColumn(format='%.2f%%')}, height=700)
                with col2:
                    st.markdown('#### 涨跌分布')
                    fig = _build_sector_heatmap_fig(detail_df)
                    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True})
            except Exception as e:
                xc_handle_error("获取板块详情失败", e, hint="请稍后重试，或检查网络与数据源连接")
        else:
            xc_warn_box('未获取到板块数据。可能处于非交易时段、数据源暂不可用或网络波动；交易时段会自动刷新，也可手动刷新页面重试。')
fragment_sector_board()

def _load_lhb(date_str: str):
    """获取龙虎榜数据。优先东方财富，其次新浪；失败返回 None。

    SSL 校验通过 ssl_bypass() 上下文管理器局部关闭，退出即恢复，
    不再污染进程全局 requests（历史隐患已修，#401/#404）。
    """
    import akshare as ak
    import concurrent.futures as _cf
    from modules.ssl_helper import ssl_bypass

    def _fetch_em():
        with ssl_bypass():
            start = (datetime.now().date() - timedelta(days=7)).strftime('%Y%m%d')
            end = datetime.now().date().strftime('%Y%m%d')
            return ak.stock_lhb_detail_em(start_date=start, end_date=end)
    from modules.timeout_exec import run_with_timeout
    em_raw = run_with_timeout(_fetch_em, timeout=12)
    if em_raw is not None and hasattr(em_raw, 'empty') and (not em_raw.empty):
        df = em_raw.rename(columns=lambda x: str(x).strip())
        if '上榜日' in df.columns:
            df['上榜日'] = df['上榜日'].astype(str).str.replace('-', '')
            filtered = df[df['上榜日'] <= date_str].sort_values('上榜日', ascending=False)
            if not filtered.empty:
                latest_date = filtered['上榜日'].iloc[0]
                df = df[df['上榜日'] == latest_date].copy()
        col_map = {'代码': '股票代码', '名称': '股票名称', '上榜原因': '上榜原因', '龙虎榜买入额': '龙虎榜买入额', '龙虎榜卖出额': '龙虎榜卖出额', '龙虎榜净买额': '龙虎榜净买额', '涨跌幅': '涨跌幅', '收盘价': '收盘价'}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if '股票代码' in df.columns:
            df['股票代码'] = df['股票代码'].astype(str).str.replace('[^0-9]', '', regex=True).str[-6:]
            df = df[df['股票代码'].str.len() == 6]
        return df
    try:
        for offset in range(0, 4):
            d = (datetime.now().date() - timedelta(days=offset)).strftime('%Y%m%d')
            try:
                df = ak.stock_lhb_detail_daily_sina(date=d)
                if df is not None and (not df.empty):
                    df = df.rename(columns=lambda x: str(x).strip())
                    return df
            except Exception:
                continue
    except Exception:
        pass
    return None

@safe_fragment('龙虎榜')
def fragment_lhb():
    st.markdown('---')
    try:
        from modules.autorefresh import st_autorefresh
        is_open, _, _ = _get_market_status()
        if is_open:
            st_autorefresh(interval=60000, key='lhb_autorefresh')
    except Exception:
        pass
    with st.expander('🐉 龙虎榜（点击展开/收起）', expanded=True):
        st.caption('当日机构/游资活跃个股（数据来源：东方财富龙虎榜）')
        lhb_date = (datetime.now().date() - timedelta(days=0 if datetime.now().weekday() < 5 else 1)).strftime('%Y%m%d')
        lhb_df = _load_lhb(lhb_date)
        if lhb_df is not None and (not lhb_df.empty):
            cols = list(lhb_df.columns)
            code_col = next((c for c in cols if '代码' in c), None) or cols[0]
            name_col = next((c for c in cols if '名称' in c or '简称' in c), None)
            reason_col = next((c for c in cols if '原因' in c or '上榜' in c), None)
            buy_col = next((c for c in cols if '买入' in c and '额' in c), None)
            sell_col = next((c for c in cols if '卖出' in c and '额' in c), None)
            net_col = next((c for c in cols if '净买' in c or '净额' in c), None)
            chg_col = next((c for c in cols if '涨跌幅' in c or '涨幅' in c), None)
            lhb_df['_code'] = lhb_df[code_col].astype(str).str.replace('[^0-9]', '', regex=True).str[-6:]
            if name_col is None:
                lhb_df['股票名称'] = lhb_df[code_col].map(lambda c: fetcher.get_name_only(c))
            else:
                lhb_df['股票名称'] = lhb_df[name_col].astype(str)
            if net_col and net_col in lhb_df.columns:
                lhb_df['_net'] = pd.to_numeric(lhb_df[net_col], errors='coerce').fillna(0)
                lhb_df['_score'] = lhb_df['_net'].abs()
            else:
                lhb_df['_score'] = pd.Series(range(len(lhb_df)), index=lhb_df.index, dtype=float)
            lhb_df = lhb_df.reset_index(drop=True)
            lhb_df['_orig'] = range(len(lhb_df))
            lhb_df = lhb_df.sort_values(['_code', '_score'], ascending=[True, False]).drop_duplicates('_code', keep='first').sort_values('_orig').reset_index(drop=True)
            lhb_df['股票代码'] = lhb_df['_code']
            if buy_col:
                lhb_df['买方金额'] = lhb_df[buy_col]
            if sell_col:
                lhb_df['卖方金额'] = lhb_df[sell_col]
            if net_col:
                lhb_df['龙虎榜净买额'] = lhb_df[net_col]
            if chg_col:
                lhb_df['涨跌幅'] = lhb_df[chg_col]
            for _amt_c in ('买方金额', '卖方金额', '龙虎榜净买额'):
                if _amt_c in lhb_df.columns:
                    lhb_df[_amt_c + '(亿)'] = lhb_df[_amt_c].apply(lambda v: _fmt_yi(v) if pd.notna(v) else '—')
            with st.spinner('正在获取个股所属概念 / 行业...'):
                lhb_df['所属概念'] = [_get_stock_concept(c) for c in lhb_df['股票代码']]
            display_cols = ['股票代码', '股票名称', '所属概念']
            for c in ('涨跌幅', '买方金额', '卖方金额', '龙虎榜净买额'):
                if c in lhb_df.columns:
                    display_cols.append(c + '(亿)')
            if reason_col:
                display_cols.append(reason_col)
            _tmp_cols = [c for c in lhb_df.columns if c.startswith('_')]
            st.dataframe(lhb_df[[c for c in display_cols if c in lhb_df.columns]].drop(columns=_tmp_cols, errors='ignore'), use_container_width=True, height=420)
            with st.expander('📋 复制龙虎榜代码', expanded=False):
                _lhb_codes = '\n'.join((str(c) for c in lhb_df['股票代码'].tolist() if str(c)))
                st.code(_lhb_codes or '—', language='text')
            opts = [f"{row['股票代码']} {row['股票名称']}" for _, row in lhb_df.iterrows() if len(str(row['股票代码'])) == 6]
            sel = st.selectbox('选择龙虎榜股票查看 K 线', ['— 请选择 —'] + opts, key='lhb_jump_select', help='选择一个标的后跳转到「股票选取」页查看其 K 线与详情。')
            if sel and sel != '— 请选择 —':
                code = sel.split()[0]
                st.query_params['pick_stock'] = code
                safe_switch_page('pages/1_股票选取.py')
            with st.expander('🔥 热股榜', expanded=False):
                _n = len(lhb_df)
                _amounts = []
                _chgs = []
                for _, _r in lhb_df.iterrows():
                    try:
                        _buy = float(pd.to_numeric(_r.get('买方金额'), errors='coerce') or 0)
                    except Exception:
                        _buy = 0.0
                    try:
                        _sell = float(pd.to_numeric(_r.get('卖方金额'), errors='coerce') or 0)
                    except Exception:
                        _sell = 0.0
                    try:
                        _chg = abs(float(pd.to_numeric(_r.get('涨跌幅'), errors='coerce') or 0))
                    except Exception:
                        _chg = 0.0
                    _amounts.append(abs(_buy) + abs(_sell))
                    _chgs.append(_chg)
                _amounts = pd.Series(_amounts, dtype=float)
                _amax = _amounts.max() if _n else 0.0
                _anorm = _amounts / _amax if _amax > 0 else pd.Series([0.0] * _n, dtype=float)
                _heat = _anorm + 0.3 * pd.Series(_chgs, dtype=float)
                heat_df = pd.DataFrame({'股票代码': lhb_df['股票代码'].values, '股票名称': lhb_df['股票名称'].values, '热度': [round(float(x), 2) for x in _heat], '买方金额': lhb_df['买方金额'].values if '买方金额' in lhb_df.columns else [0] * _n, '卖方金额': lhb_df['卖方金额'].values if '卖方金额' in lhb_df.columns else [0] * _n, '涨跌幅': lhb_df['涨跌幅'].values if '涨跌幅' in lhb_df.columns else [0] * _n})
                heat_df = heat_df.sort_values('热度', ascending=False).reset_index(drop=True)
                st.dataframe(heat_df, use_container_width=True, column_config={'热度': st.column_config.NumberColumn(format='%.2f')}, height=400)
                heat_opts = [f"{row['股票代码']} {row['股票名称']}" for _, row in heat_df.iterrows() if len(str(row['股票代码'])) == 6]
                hsel = st.selectbox('选择热股榜股票查看 K 线', ['— 请选择 —'] + heat_opts, key='heat_jump_select', help='选择热股榜中的标的后跳转到「股票选取」页查看其 K 线与详情。')
                if hsel and hsel != '— 请选择 —':
                    code = hsel.split()[0]
                    st.query_params['pick_stock'] = code
                    safe_switch_page('pages/1_股票选取.py')
        else:
            _empty_info('暂无龙虎榜数据（非交易日晚间或数据源暂不可用）。可先到「📡 股票选取」查看个股 K 线，交易时段会自动刷新。')
fragment_lhb()
sf_card('个股收益率相关性矩阵', "")
st.caption('💡 解释：数值越接近 1（深红）表示两只股票走势高度同向；越接近 -1（深绿）表示反向；接近 0 表示关系不大。可用于判断持仓是否过于集中、分散风险。')
with st.expander('📖 怎么看这张图？', expanded=False):
    st.markdown('- **颜色**：红=正相关（同涨同跌），绿=负相关（你涨我跌），白=无关。\n- **对角线**恒为 1（自己和自己完全相关）。\n- **用法**：如果组合里多只股票相关性都接近 1，说明风险没有分散；可适当加入低相关或负相关的标的平衡。\n- **注意**：仅基于近期（默认 180 天）日收益率计算，长期关系可能变化。')

def _today_str():
    return datetime.now().date().strftime('%Y-%m-%d')
_corr_tickers = multi_stock_search_input(label='输入多只股票（逗号分隔）', key='corr_stocks', default='600519,000858,601088,600036', placeholder='输入代码或名称，逗号分隔')
_ticker_list = [t.strip() for t in (_corr_tickers if isinstance(_corr_tickers, list) else []) if t.strip()]
if not _ticker_list and _corr_tickers:
    _ticker_list = [t.strip() for t in str(_corr_tickers).split(',') if t.strip()]
if not _ticker_list:
    info_banner('💡 请输入至少 2 只股票代码/名称（逗号分隔）后点击「计算相关性」。已默认预填 4 只示例，直接点击即可。')

def _fetch_one_corr(t, start, end):
    """单只股票取数（带超时兜底），返回 (label, df)。"""
    try:
        _records = api_kline(t, start=start, end=end)
        if _records is None:
            d = fetcher.get_daily(t, start=start, end=end)
        else:
            d = pd.DataFrame(_records)
        if d is None or d.empty:
            return None
        _nm = fetcher.get_name_only(t) or fetcher.get_stock_name(t)
        label = f'{t} {_nm}' if _nm else t
        return (label, d)
    except Exception:
        return None
if st.button('计算相关性', key='calc_corr', use_container_width=True, disabled=len(_ticker_list) < 2, help='请至少输入 2 只股票（逗号分隔）后再计算相关性'):
    with st.spinner('正在并行获取行情并计算相关性（最多约 12 秒）...'):
        _end = _today_str()
        _start = (datetime.now().date() - timedelta(days=180)).strftime('%Y-%m-%d')
        daily_dict = {}
        try:
            from modules.fetch_parallel import fetch_many as _fm
            _tasks = [(t, lambda tt=t: _fetch_one_corr(tt, _start, _end)) for t in _ticker_list]
            _res = _fm(_tasks, max_workers=8, timeout=15)
            for _item in _res.values():
                if isinstance(_item, tuple) and len(_item) == 2 and (_item[0] is not None):
                    daily_dict[_item[0]] = _item[1]
        except Exception:
            pass
        if len(daily_dict) >= 2:
            try:
                fig = _build_correlation_fig(daily_dict)
                st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "responsive": True})
            except Exception as e:
                xc_handle_error("相关性矩阵渲染失败", str(e)[:80], hint="请检查输入代码或网络后重试")
        else:
            xc_warn_box('需要至少 2 只有效股票代码。请检查输入或网络后重试。')

def _wl_quote_batch(codes, token):
    """R90：优先批量接口（1 次网络往返替代 N 次 /api/quote）。

    返回 (quotes_dict, has_auth_error)。批量接口失败的代码走本地 fetcher 回退。
    每只失败返回 None，由调用方统一渲染空态。
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
            for code, q in ex.map(lambda c: (c, _wl_quote_local(c)), missing):
                if q is not None:
                    quotes[code] = q
    return (quotes, has_auth_error)

def _wl_extra_uncached(code: str):
    """R90 拆分：未装饰底层（可在线程池并行调用）。返回 总股本/流通股。"""
    try:
        import akshare as ak
        from modules.ssl_helper import ssl_bypass
        with ssl_bypass():
            info = ak.stock_individual_info_em(symbol=str(code))
        if info is None or info.empty:
            return None
        d = dict(zip(info['item'], info['value']))

        def _f(k):
            try:
                return float(str(d.get(k)).replace(',', '').replace('%', '').replace('亿', '').replace('万', ''))
            except Exception:
                return None
        return {'total_shares': _f('总股本'), 'float_shares': _f('流通股')}
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def _wl_extra(code: str):
    """缓存 1h：返回 总股本/流通股（股），用于计算 总市值 与 换手率。失败返回 None。"""
    return _wl_extra_uncached(code)

def _wl_pe_uncached(code: str):
    """R90 拆分：未装饰底层（可在线程池并行调用）。取市盈率(TTM)。"""
    try:
        _, pe, _ = fund_one(code, fetcher)
        return pe
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def _wl_pe(code: str):
    """缓存 1h：取市盈率(TTM)。"""
    return _wl_pe_uncached(code)

def _wl_render_table_html(rows, dark: bool):
    """渲染自选行情 HTML 表（深色/浅色自适应），操作列可点击看 K 线。返回 height。"""
    if dark:
        bg, border = ('#16161e', '#2d2d44')
        head_bg, head_color = ('#1f1f2e', '#cbd5e1')
        row_color, hover = ('#e2e8f0', '#23233a')
        code_color = '#8b95a8'
        op_bg, op_color = ('#2a2a44', '#a5b4fc')
    else:
        bg, border = ('#ffffff', '#e2e8f0')
        head_bg, head_color = ('#f8fafc', '#475569')
        row_color, hover = ('#1e293b', '#f1f5f9')
        code_color = '#64748b'
        op_bg, op_color = ('#eef2ff', '#4f46e5')
    up, down = (UP_COLOR, DOWN_COLOR)
    cols = ['名称', '代码', '现价', '涨跌幅', '涨跌额', '今开', '最高', '最低', '换手率', '市盈率', '总市值(亿)', '操作']
    head = ''.join((f'<th style="padding:7px 8px;white-space:nowrap;">{c}</th>' for c in cols))
    body = ''
    for r in rows:
        chg = r.get('chg')
        camt = r.get('change_amt')
        col = up if chg is not None and chg > 0 else down if chg is not None and chg < 0 else '#9aa0a6'
        chg_s = f'{chg:+.2f}%' if isinstance(chg, (int, float)) else '—'
        camt_s = f'{camt:+.2f}' if isinstance(camt, (int, float)) else '—'
        cur_s = f"{r['cur']:.2f}" if isinstance(r.get('cur'), (int, float)) else '—'
        open_s = f"{r['open']:.2f}" if isinstance(r.get('open'), (int, float)) else '—'
        high_s = f"{r['high']:.2f}" if isinstance(r.get('high'), (int, float)) else '—'
        low_s = f"{r['low']:.2f}" if isinstance(r.get('low'), (int, float)) else '—'
        turn_s = r.get('turnover') if r.get('turnover') is not None else '—'
        pe_s = r.get('pe') if r.get('pe') is not None else '—'
        mv_s = r.get('mv_yi') if r.get('mv_yi') is not None else '—'
        body += f'''<tr style="color:{row_color};"><td style="padding:6px 8px;white-space:nowrap;">{r['name']}</td><td style="padding:6px 8px;color:{code_color};font-variant-numeric:tabular-nums;">{r['code']}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{cur_s}</td><td style="padding:6px 8px;color:{col};font-weight:600;font-variant-numeric:tabular-nums;">{chg_s}</td><td style="padding:6px 8px;color:{col};font-variant-numeric:tabular-nums;">{camt_s}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{open_s}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{high_s}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{low_s}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{turn_s}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{pe_s}</td><td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{mv_s}</td><td style="padding:6px 8px;"><span class="wl-op" data-code="{r['code']}" style="cursor:pointer;background:{op_bg};color:{op_color};font-size:12px;padding:2px 8px;border-radius:10px;white-space:nowrap;">📈 看K线</span></td></tr>'''
    css = f'\n    <style>\n    .wl-table{{width:100%;border-collapse:collapse;background:{bg};\n      border:1px solid {border};border-radius:8px;font-size:13px;font-family:inherit;}}\n    .wl-table th{{background:{head_bg};color:{head_color};text-align:right;font-weight:600;\n      border-bottom:1px solid {border};position:sticky;top:0;}}\n    .wl-table th:nth-child(1),.wl-table th:nth-child(2){{text-align:left;}}\n    .wl-table td{{text-align:right;border-bottom:1px solid {border};}}\n    .wl-table td:nth-child(1),.wl-table td:nth-child(2){{text-align:left;}}\n    .wl-table tr:hover td{{background:{hover};}}\n    </style>\n    '
    html = css + f'<div style="max-height:520px;overflow:auto;"><table class="wl-table">' + f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>' + '<script>' + 'var ops=document.querySelectorAll(".wl-op");' + 'for(var i=0;i<ops.length;i++){ops[i].onclick=function(){' + 'var s=window.parent&&window.parent.Streamlit;' + 'if(s&&s.setComponentValue){s.setComponentValue(this.getAttribute("data-code"));}' + '};}' + '</script>'
    return html

@safe_fragment('自选行情')
def fragment_watchlist_quotes():
    sf_card('📌 自选行情', "")
    st.caption('实时跟踪自选股现价与涨跌（A股红涨绿跌）；行情接口异常时自动回退本地源。点击操作列「📈 看K线」跳转个股 K 线；跳转后可在「股票选取」页调节 K 线显示数量与起始位置。')
    try:
        from modules.autorefresh import st_autorefresh
        if is_trading_now():
            st_autorefresh(interval=60 * 1000, key='wl_quotes_autorefresh')
    except Exception:
        pass
    sc, body = api_get('/api/watchlist', timeout=10)
    if sc != 200 or not isinstance(body, dict) or body.get('status') != 'ok':
        st.error('⚠️ 加载自选股失败，请稍后重试')
        return
    items = body.get('data', []) or []
    if not items:
        _empty_info('自选股为空。可在上方「🔍 搜索股票 · 加入自选」搜索后点击 ☆ 加入，或前往「📡 自选股监控」管理。')
        return
    codes = [it.get('stock_code') for it in items if isinstance(it, dict) and it.get('stock_code')]
    name_by_code = {it.get('stock_code'): it.get('stock_name') for it in items}
    id_by_code = {it.get('stock_code'): it.get('id') for it in items}
    names = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        _fut_map = {ex.submit(fetcher.get_name_only, c): c for c in codes}
        for _fut in _cf.as_completed(_fut_map):
            _c = _fut_map[_fut]
            try:
                names[_c] = _fut.result() or _c
            except Exception:
                names[_c] = _c
    _tok = get_token()
    with st.spinner(f'并行获取 {len(codes)} 只自选股实时行情…'):
        quotes, _has_auth_err = _wl_quote_batch(codes, _tok)
    if _has_auth_err or any((isinstance(q, dict) and q.get('__auth_error') for q in quotes.values())):
        clear_auth()
        xc_warn_box('🔐 登录已过期，请重新登录')
        return
    try:
        from modules.fetch_parallel import fetch_many as _fetch_many
        _fin_tasks = []
        for code in codes:
            _fin_tasks.append((f'pe_{code}', lambda c=code: _wl_pe_uncached(c)))
            _fin_tasks.append((f'ex_{code}', lambda c=code: _wl_extra_uncached(c)))
        _fin_res = _fetch_many(_fin_tasks, max_workers=6)
    except Exception:
        _fin_res = {}
    rows = []
    for code in codes:
        q = quotes.get(code)
        name = (q.get('name') if isinstance(q, dict) and q.get('name') else None) or names.get(code) or code
        if q and q.get('current'):
            cur = float(q['current'])
            prev = float(q.get('prev_close') or 0)
            high = float(q.get('high') or 0)
            low = float(q.get('low') or 0)
            open_ = float(q.get('open') or 0)
            volume = safe_int(q.get('volume'), 0)
            chg = (cur - prev) / prev * 100 if prev else 0.0
            change_amt = cur - prev if prev else 0.0
        else:
            cur = open_ = high = low = chg = change_amt = None
            volume = 0
        pe = _fin_res.get(f'pe_{code}')
        extra = _fin_res.get(f'ex_{code}')
        total_shares = extra.get('total_shares') if extra else None
        float_shares = extra.get('float_shares') if extra else None
        mv_yi = cur * total_shares / 100000000.0 if cur and total_shares else None
        turnover = None
        if volume and float_shares:
            _t = volume / float_shares * 100
            turnover = f'{_t:.2f}%' if 0 <= _t <= 100 else '—'
        rows.append({'code': code, 'name': name, 'cur': cur, 'chg': chg, 'change_amt': change_amt, 'open': open_, 'high': high, 'low': low, 'turnover': turnover, 'pe': f'{pe:.2f}' if isinstance(pe, (int, float)) and (not pd.isna(pe)) else None, 'mv_yi': f'{mv_yi:.2f}' if mv_yi is not None else None})
    up_n = sum((1 for r in rows if r['chg'] is not None and r['chg'] >= 0))
    down_n = sum((1 for r in rows if r['chg'] is not None and r['chg'] < 0))
    st.markdown(f"#### 共 {len(rows)} 只自选股 ｜ <span style='color:{UP_COLOR};font-weight:600;'>▲ {up_n}</span> ／ <span style='color:{DOWN_COLOR};font-weight:600;'>▼ {down_n}</span>", unsafe_allow_html=True)
    picks = _wl_render_table_html(rows, dark)
    picked = st.markdown(picks, unsafe_allow_html=True)
    if picked and picked in codes:
        st.query_params['pick_stock'] = picked
        safe_switch_page('pages/1_股票选取.py')
    opts = [f"{r['code']} {r['name']}" for r in rows]
    _kc1, _kc2 = st.columns(2)
    with _kc1:
        sel = st.selectbox('选择股票查看 K 线', ['— 请选择 —'] + opts, key='wl_kline_jump')
        if sel and sel != '— 请选择 —':
            c = sel.split()[0]
            st.query_params['pick_stock'] = c
            safe_switch_page('pages/1_股票选取.py')
    with _kc2:
        rsel = st.selectbox('移除自选', ['— 请选择 —'] + opts, key='wl_remove_sel')
        if st.button('🗑 移除', key='wl_remove_btn', use_container_width=True):
            if rsel and rsel != '— 请选择 —':
                rc = rsel.split()[0]
                rid = id_by_code.get(rc)
                if rid is not None:
                    dsc, dbody = api_delete(f'/api/watchlist/{rid}', timeout=5)
                    if dsc == 200:
                        _toast(f'🗑 已移除 {rc}')
                        st.rerun(scope='fragment')
                    else:
                        xc_warn_box('⚠️ 移除失败，请重试')
fragment_watchlist_quotes()
fragment_market_alerts_panel()