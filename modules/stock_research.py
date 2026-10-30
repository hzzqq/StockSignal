"""个股研究渲染主体（P0-1 抽取契约产物，2026-10-30 冻结稿执行）。

承载原 pages/20_个股分析.py 与 pages/11_股票选取.py 的页面语句（docstring 后全部
顶层语句原序搬入，imports 留在函数体内原位；装饰器随调用重建，与原 exec 每次
rerun 重新执行语义一致）。子页文件保留为独立入口 shim，safe_switch_page /
page_link 直跳不受影响。勿在模块级新增其它逻辑。
"""


def render_stock_analysis() -> None:
    import streamlit as st
    import pandas as pd
    from datetime import datetime
    from modules.page_guard import safe_fragment
    from modules.page_utils import render_standard_page, get_fetcher
    from modules.ui_theme import sf_card, sf_metric
    from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner
    dark = render_standard_page(title='个股深度分析 · 决策仪表盘', icon='🔍', layout='wide')
    sf_card("个股分析导读", "输入代码/名称/拼音搜索个股，查看暗色决策仪表盘：K 线、技术面、资金面、情绪与风险铁律。严格遵循绿涨红跌配色；所有外部数据获取失败均友好提示，不抛红错。", icon="🔍")
    from modules.fetcher import StockFetcher
    from modules.cleaner import DataCleaner
    from modules.session import api_kline, api_intraday
    from modules.search_ui import stock_search_input
    from modules.background_tasks import submit_task_with_error, poll_task
    from modules.page_widgets import _empty_info, is_trading_now
    from modules.format_helpers import safe_html_text
    from modules.stock_analysis_helpers import RED, GREEN, AMBER, event_factor_color, _sentiment_tag, _tp_cls, _score_ring_html, _battle_plan_scale, _build_risk_iron_rules, _risk_iron_html, _build_plan_rows, _section_header, _build_rise_fall_factors, _factor_list_html, _build_logic_lists, _logic_list_html
    from modules.fundflow import get_earnings_report, get_earnings_forecast, get_disclosure_calendar
    from modules.financial_report_helpers import (
        fr_fmt as _fr_fmt,
        fr_filter_by_code as _fr_filter_by_code,
        fr_color_yoy as _fr_color_yoy,
        fr_format_financial_df,
        fr_build_history,
        fr_history_metrics,
        fr_expand_rows,
        fr_period_label,
        fr_yoy_column,
        fr_compute_margins,
        fr_fmt_pct,
        _PERF_UP,
        _PERF_DOWN,
        _PERF_FLAT,
    )
    from modules.dark_text_fix import apply_plotly_theme as _apply_plotly_theme
    fetcher = get_fetcher()
    from modules.widgets import sidebar_target
    import modules.scroll_nav as sn
    from modules.chart_cache import cached_fig


    # ── 图表 figure 构建缓存（性能优化：避免 K线/分时图在自动刷新或交互重跑时重复 rebuild）──
    # 注意：保留 Visualizer 延迟导入，避免拖累页面首屏加载（原注释：每页加载约 0.95s）
    @cached_fig(ttl=120)
    def _build_kline_fig(period_df, kline_title, kline_annotations):
        from modules.visualizer import Visualizer
        return Visualizer.candlestick(period_df, title=kline_title, show_volume=True, ma_windows=[5, 10, 20],
                                      annotations=kline_annotations, support=None, resistance=None,
                                      up_color=RED, down_color=GREEN, ma_colors=['#ffa502', '#667eea', '#009e60'])


    @cached_fig(ttl=120)
    def _build_intraday_fig(didf, prev_close, ticker, display_name, dt):
        from modules.visualizer import Visualizer
        return Visualizer.intraday(didf, prev_close=prev_close, title=f'{ticker} {display_name} 分时（{dt}）', up_color=RED, down_color=GREEN)


    @cached_fig(ttl=600)
    def _build_perf_history_fig(hist_df, metric: str = "净利润", dark: bool = False):
        """三年+ 业绩主要指标「柱状 + 折线」横向对比图（参考手机端 F10 常见样式）。

    柱 = 该指标规模（亿元，主轴）；折线 = 同比增速%（副轴，右）。
    配色遵循 A 股铁律：涨/增长 = 红，跌/下滑 = 绿（业绩域走默认红涨绿跌）。

    参数 hist_df 为 modules.financial_report_helpers.fr_build_history 的产物；
    best-effort：数据不足 2 期或字段缺失返回 None，调用方跳过渲染。
    """
        import plotly.graph_objects as go
        x, y, yoy = fr_history_metrics(hist_df, metric)
        if len(x) < 2 or all(v is None for v in y):
            return None
        try:
            y_yi = [None if v is None else v / 1e8 for v in y]          # 元 → 亿元
            # 柱色：正/零红（增长）、负绿（下滑）；本金为负的指标同样按正负着色
            bar_colors = [_PERF_UP if (v is None or v >= 0) else _PERF_DOWN for v in y_yi]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=x, y=y_yi, name=f"{metric}（亿元）",
                marker=dict(color=bar_colors),
                text=[("—" if v is None else f"{v:,.2f}") for v in y_yi],
                textposition="outside", cliponaxis=False,
                hovertemplate="%{x}<br>" + metric + "：%{y:,.2f} 亿元<extra></extra>",
            ))
            # 同比折线（副轴）——仅当存在至少一个有效同比点
            if any(v is not None for v in yoy):
                fig.add_trace(go.Scatter(
                    x=x, y=yoy, name="同比（%）", yaxis="y2",
                    mode="lines+markers",
                    line=dict(color="#f0a020", width=2),
                    marker=dict(size=7, color="#f0a020", line=dict(color="#fff", width=1)),
                    hovertemplate="%{x}<br>同比：%{y:.2f}%<extra></extra>",
                ))
                fig.update_layout(yaxis2=dict(
                    title="同比（%）", overlaying="y", side="right",
                    showgrid=False, zeroline=True, zerolinecolor="rgba(128,128,128,.35)",
                    ticksuffix="%",
                ))
            _pct_metrics = ("ROE%", "毛利率%", "净利率%")
            _yunit = "%" if metric in _pct_metrics else "亿元"
            fig.update_layout(
                height=360, margin=dict(l=56, r=56, t=30, b=44),
                template="plotly_dark" if dark else "plotly_white",
                barmode="group", xaxis_tickangle=0,
                yaxis=dict(title=_yunit, zeroline=True, zerolinecolor="rgba(128,128,128,.35)"),
                legend=dict(orientation="h", y=1.14, x=0),
                bargap=0.42,
                hovermode="x unified",
            )
            _apply_plotly_theme(fig, dark=dark)
            return fig
        except Exception:
            return None


    @cached_fig(ttl=600)
    def _build_financial_trend_fig(code: str, dark: bool = False):
        """利润表多期趋势：营业总收入 / 净利润（单位：亿元），取新浪利润表最新 8 期。

    best-effort：取数失败或字段缺失返回 None，调用方跳过渲染。
    """
        import plotly.graph_objects as go
        try:
            inc = _fr_cached_financial(code, "income")
        except Exception:
            inc = None
        if inc is None or (hasattr(inc, "empty") and inc.empty) or "报告日" not in inc.columns:
            return None
        need = [c for c in ("营业总收入", "净利润") if c in inc.columns]
        if not need:
            return None
        try:
            d = inc[["报告日"] + need].copy()
            for c in need:
                d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.dropna(subset=need, how="all").iloc[::-1]  # 旧→新，左→右
            if d.empty:
                return None
            fig = go.Figure()
            _line_colors = {"营业总收入": "#667eea", "净利润": "#ffa502"}
            for c in need:
                fig.add_trace(go.Scatter(
                    x=d["报告日"].astype(str), y=d[c] / 1e8,
                    mode="lines+markers", name=c,
                    line=dict(color=_line_colors.get(c, "#667eea"), width=2),
                    marker=dict(size=6),
                ))
            fig.update_layout(
                height=320, margin=dict(l=50, r=20, t=34, b=40),
                template="plotly_dark" if dark else "plotly_white",
                xaxis_tickangle=-45, yaxis_title="亿元",
                legend=dict(orientation="h", y=1.12, x=0),
                title=f"{code} 利润表多期趋势（亿元）",
            )
            return fig
        except Exception:
            return None

    with sidebar_target():
        st.header('分析目标')
        # 深链支持：从侧边栏「最近浏览」点击股票时携带 ?pick_stock=CODE，作为初始分析标的
        _qp = st.query_params.get("pick_stock")
        _default_code = str(_qp[0]) if isinstance(_qp, list) and _qp else (str(_qp) if _qp else "600519")
        ticker = stock_search_input(label='股票搜索', key='analysis_stock', default=_default_code, placeholder='输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台')
        st.caption('本页为星辰决策仪表盘，右上角可切换暗夜 / 白天模式。')
    st.markdown('<div class="sf-header"><div class="sf-brand">决策仪表盘 · <b>个股深度分析</b></div><div class="sf-brand">事件驱动 · 多维归因</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="sf-cta-card">', unsafe_allow_html=True)
    st.markdown('<div class="sf-cta-title">🚀 一键生成个股深度分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="sf-cta-sub">输入代码 / 名称 / 拼音，生成暗色决策仪表盘：行情 · 新闻 · 技术 · 评分 · 财报。任务后台并行运行，完成后自动显示。</div>', unsafe_allow_html=True)
    if st.button('🔍 生成分析', type='primary', width="stretch", key='gen_analysis_top'):
        task_id, err = submit_task_with_error('analysis', {'ticker': ticker})
        if task_id:
            st.session_state['analysis_task_id'] = task_id
            st.session_state['analysis_result'] = None
            info_banner('📡 分析任务已提交到后台运行，你可以切到其他页面，完成后会在下方仪表盘自动显示结果。')
        else:
            err = err or '未知错误'
            if '登录' in err or '过期' in err or '凭证' in err:
                xc_handle_error("操作失败", err, hint="请稍后重试，或检查网络与数据源连接")
                if st.button('重新登录', key='anal_relogin_top', width="stretch"):
                    st.session_state.clear()
                    st.switch_page('pages/90_登录.py')
            else:
                xc_handle_error("后台任务提交失败", err, hint="请刷新重试")
    st.markdown('</div>', unsafe_allow_html=True)

    def _analysis_goto(c):
        st.session_state['analysis_stock'] = c
        st.rerun()
    _hist_key2 = '_analysis_recent'
    if _hist_key2 not in st.session_state:
        st.session_state[_hist_key2] = []
    _fav_key2 = '_analysis_favs'
    if _fav_key2 not in st.session_state:
        st.session_state[_fav_key2] = []
    _col_hist, _col_fav = st.columns([0.7, 0.3])
    with _col_hist:
        if st.session_state[_hist_key2]:
            st.markdown('**🕘 最近浏览**')
            _hc = st.columns(min(len(st.session_state[_hist_key2]), 6))
            for i, hc in enumerate(st.session_state[_hist_key2]):
                with _hc[i]:
                    if st.button(hc, key=f'anal_hist_{hc}', width="stretch"):
                        _analysis_goto(hc)
    with _col_fav:
        _is_fav = ticker in st.session_state[_fav_key2]
        if st.button('⭐ 已收藏 ' + ticker if _is_fav else '☆ 收藏当前标的', key='anal_fav_btn', width="stretch"):
            if _is_fav:
                st.session_state[_fav_key2].remove(ticker)
            else:
                st.session_state[_fav_key2].append(ticker)
            st.rerun()

    @st.cache_data(show_spinner=False, ttl=300)
    def _cached_period_kline(ticker: str, start: str, end: str, period: str):
        """#78 周/月 K 线数据（复用 11_股票选取.py 已验证的取数模式）。"""
        recs = api_kline(ticker, start=start, end=end, period=period)
        if recs is None:
            return StockFetcher().get_kline(ticker, start=start, end=end, period=period)
        return pd.DataFrame(recs)

    @st.cache_data(show_spinner=False, ttl=300)
    def _period_end_to_trading_day(ticker, start, end, period_date):
        """周/月线视图下，点击柱子的日期是周期末(可能落在周末/节假日)，
    映射到最近的一个实际交易日，确保双击弹分时能取到数据。"""
        try:
            from modules.calendar_utils import nearest_trading_day
            dd = _cached_period_kline(ticker, start, end, 'daily')
            if dd is None or dd.empty:
                return str(period_date)[:10]
            dts = pd.to_datetime(dd['date']).dt.strftime('%Y-%m-%d').tolist()
            return nearest_trading_day(period_date, dts)
        except Exception:
            pass
        return str(period_date)[:10]

    @st.cache_data(show_spinner=False, ttl=120)
    def _cached_intraday_for_date(ticker, target_date):
        """获取指定交易日的分时数据（用于K线双击回看历史分时）。
    返回 (df, prev_close, trade_date) 或 None。"""
        try:
            _df, _pc, _dt = fetcher.get_stock_intraday_sina(ticker, trade_date=target_date)
            if _df is not None and (not _df.empty):
                return (_df, _pc, _dt)
        except Exception:
            pass
        return None

    @st.cache_data(show_spinner=False, ttl=300)
    def _cached_intraday(ticker):
        """个股分时数据：优先后端 /api/intraday，回退本地 fetcher。返回 (df, prev_close, trade_date) 或 None。
    ttl=300 与交易时段 5 分钟刷新节奏对齐：每 5 分钟重新拉一次真实数据，中间命中缓存。"""
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


    @safe_fragment
    def fragment_kline_card(ticker, display_name, df, ma20v, ma10v, support, trapped):
        """技术指标 K 线卡片：独立 fragment。

    双击 K 线弹分时（on_select='rerun'）/ 切换周期 / 改日期范围，均只重跑本片段，
    不再触发整页（情报面、利好利空清单、板块分析等）重跑。修复此前双击 K 线导致整页 rerun 的性能问题。
    """
        _period_opts = ['daily', 'weekly', 'monthly']
        kline_period = st.radio('K线周期', options=_period_opts,
                                index=_period_opts.index(st.session_state.get(f'kline_period_{ticker}', 'daily')),
                                format_func=lambda p: {'daily': '日 K', 'weekly': '周 K', 'monthly': '月 K'}[p],
                                horizontal=True, key=f'kline_period_radio_{ticker}',
                                help='切换 K 线周期：日线 / 周线 / 月线')
        st.session_state[f'kline_period_{ticker}'] = kline_period
        period_label = {'daily': '日K线', 'weekly': '周K线', 'monthly': '月K线'}[kline_period]
        kline_title = f'{ticker} {display_name} {period_label}'
        _dr_key = f'kline_daterange_{ticker}'
        if _dr_key not in st.session_state:
            st.session_state[_dr_key] = (datetime(2020, 1, 1), datetime.now())
        _dr = st.date_input('K线日期范围（开始 / 结束）', value=st.session_state[_dr_key],
                            max_value=datetime.now(), key=f'kline_daterange_input_{ticker}',
                            help='选定开始与结束日期，按自定义区间查看 K 线（日线直接筛选；周/月线按区间重新拉取）')
        _kstart, _kend = ('2020-01-01', datetime.now().strftime('%Y-%m-%d'))
        if isinstance(_dr, (tuple, list)) and len(_dr) == 2:
            st.session_state[_dr_key] = _dr
            try:
                _kstart = _dr[0].strftime('%Y-%m-%d')
                _kend = _dr[1].strftime('%Y-%m-%d')
            except Exception:
                pass
        if kline_period == 'daily':
            period_df = df
            try:
                _dmask = (pd.to_datetime(period_df['date']) >= _kstart) & (pd.to_datetime(period_df['date']) <= _kend)
                _filtered = period_df[_dmask]
                if not _filtered.empty:
                    period_df = _filtered
            except Exception:
                pass
        else:
            _period_name = {'weekly': '周线', 'monthly': '月线'}.get(kline_period, '')
            with st.spinner(f'正在加载{_period_name} K 线数据…'):
                _kdf = _cached_period_kline(ticker, _kstart, _kend, kline_period)
            if _kdf is not None and (not _kdf.empty):
                period_df = DataCleaner.full_pipeline(_kdf.copy())
            else:
                period_df = df
        _fragment_intraday(ticker, display_name)
        try:
            kline_annotations = [{'price': ma20v, 'label': 'MA20压制', 'color': GREEN, 'dash': 'dash'},
                                 {'price': ma10v, 'label': 'MA10', 'color': '#667eea', 'dash': 'dash'},
                                 {'price': support, 'label': '前低支撑', 'color': RED, 'dash': 'dash'},
                                 {'price': trapped, 'label': '套牢区', 'color': AMBER, 'dash': 'dot'}] if kline_period == 'daily' else None
            fig = _build_kline_fig(period_df, kline_title, kline_annotations)
            _kline_key = f'kline_chart_{ticker}'
            _kline_event = st.plotly_chart(fig, width="stretch", key=_kline_key, on_select='rerun',
                                           config={"displaylogo": False, "responsive": True, 'displayModeBar': 'hover', 'displaylogo': False, 'scrollZoom': True,
                                                   'modeBarButtonsToRemove': ['lasso2d', 'select2d']})
            _dbl_key = f'kline_dbl_{ticker}'
            _now_ms = datetime.now().timestamp()
            _clicked_date = None
            if _kline_event and hasattr(_kline_event, 'selection') and _kline_event.selection.points:
                _pt = _kline_event.selection.points[0]
                _xval = _pt.get('x', _pt.get('pointIndex', None))
                if _xval is not None:
                    try:
                        _idx = int(_xval)
                        if 0 <= _idx < len(period_df):
                            _clicked_date = str(period_df.iloc[_idx]['date'])[:10]
                    except (ValueError, TypeError, IndexError):
                        if isinstance(_xval, str) and len(_xval) >= 10:
                            _clicked_date = _xval[:10]
            if _clicked_date:
                if kline_period != 'daily':
                    _clicked_date = _period_end_to_trading_day(ticker, _kstart, _kend, _clicked_date)
                _prev_click = st.session_state.get(_dbl_key)
                if _prev_click and _now_ms - _prev_click[0] < 0.5 and (_prev_click[1] == _clicked_date):
                    st.session_state[f'intraday_target_{ticker}'] = _clicked_date
                    st.session_state[_dbl_key] = None
                else:
                    st.session_state[_dbl_key] = (_now_ms, _clicked_date)
            _target_dt = st.session_state.get(f'intraday_target_{ticker}')
            if _target_dt:
                with st.expander(f'📈 {_target_dt} 分时走势（双击K线弹出）', expanded=True):
                    st.caption('💡 提示：在上方 K 线图上**双击任意一根柱子**即可切换到该交易日分时。')
                    try:
                        _di = _cached_intraday_for_date(ticker, _target_dt)
                        if _di is not None:
                            _didf, _dipc, _didt = _di
                            _dfig = _build_intraday_fig(_didf, _dipc, ticker, display_name, _didt)
                            st.plotly_chart(_dfig, width="stretch", key=f'dbl_intra_{ticker}_{_target_dt}', config={'displaylogo': False, 'responsive': True})
                        else:
                            info_banner(f'📭 {_target_dt} 暂无分时数据（可能非交易日或数据源不可用）。')
                    except Exception as _die:
                        xc_handle_error("分时图加载失败", str(_die)[:80], hint="请稍后重试，或检查网络与数据源连接")
                    if st.button('✕ 关闭分时图', key=f'close_intra_{ticker}'):
                        del st.session_state[f'intraday_target_{ticker}']
                        st.rerun(scope='fragment')
            st.markdown("<div style='font-size:12px;color:var(--txt2);margin:8px 0 6px;display:flex;align-items:center;gap:8px;'><span>💡</span><span>按住鼠标拖拽可平移；点击工具栏 🔍 后框选区域可放大；点击 🏠 可还原视图（部分浏览器需双击）。</span><span style='margin-left:auto;background:color-mix(in srgb,var(--acc1) 12%,var(--card2));padding:2px 8px;border-radius:4px;font-size:11px;color:var(--acc1);'>🖱️ <b>双击K线柱</b> → 弹出当日分时图</span></div>", unsafe_allow_html=True)
            _date_min = pd.to_datetime(period_df['date']).min().strftime('%Y-%m-%d')
            _date_max = pd.to_datetime(period_df['date']).max().strftime('%Y-%m-%d')
            _cap = "<div style='font-size:12px;color:var(--txt2);margin-top:4px;'>绿柱为上涨、红柱为下跌（参考文档配色）。均线 MA5(橙)/MA10(靛)/MA20(绿)；"
            if kline_period == 'daily':
                _cap += f'标注线：MA20压制 ¥{ma20v:.2f} / MA10 ¥{ma10v:.2f} / 前低支撑 ¥{support:.2f} / 套牢区 ¥{trapped:.2f}。'
            else:
                _cap += f"当前为{('周线' if kline_period == 'weekly' else '月线')}视图，均线为对应周期数值。"
            _cap += f'数据区间 {_date_min} ~ {_date_max}。</div>'
            st.markdown(_cap, unsafe_allow_html=True)
        except Exception as e:
            xc_handle_error("K线图渲染失败", str(e)[:80], hint="请稍后重试")
            if st.button('🔄 重试', key='kline_retry_btn'):
                st.rerun(scope='fragment')
        st.markdown('</div>', unsafe_allow_html=True)


    @safe_fragment(run_every=300)
    def _fragment_intraday(ticker: str, display_name: str) -> None:
        """分时图独立片段：交易时段每 5 分钟自刷新，与整页 1 分钟节奏解耦。"""
        from modules.visualizer import Visualizer

        if is_trading_now():
            _refresh_hint = "<span style='color:#009e60'>● 交易时段，每5分钟自动刷新中</span>"
        else:
            _refresh_hint = "<span style='color:#94a3b8'>● 非交易时段，已暂停刷新</span>"

        _show_intraday = st.checkbox(
            '📈 显示分时图',
            value=True,
            key=f'intraday_chk_{ticker}',
            help='展示该股票当日/最近交易日分时走势（价格线+均价+昨收基准）。',
        )
        if not _show_intraday:
            return

        try:
            _intra = _cached_intraday(ticker)
            if _intra is not None:
                _idf, _ipc, _idate = _intra
                _ifig = _build_intraday_fig(_idf, _ipc, ticker, display_name, _idate)
                st.plotly_chart(_ifig, width="stretch", key=f'intraday_chart_{ticker}', config={'displaylogo': False, 'responsive': True})
                st.markdown(
                    f"<div style='font-size:12px;color:var(--txt2);margin-top:4px;display:flex;justify-content:space-between;'>"
                    f"<span>白线为当日价格走势，橙点为均价；虚线为昨收。绿涨红跌。</span>{_refresh_hint}</div>",
                    unsafe_allow_html=True,
                )
            else:
                info_banner('📭 暂无分时数据（非交易时段或数据源暂不可用）。')
        except Exception as _ie:
            xc_handle_error("分时图加载失败", str(_ie)[:60], hint="请稍后重试，或检查网络与数据源连接")

    def _render_analysis(R: dict):
        """渲染个股分析决策仪表盘（延迟导入 Visualizer，避免每页加载 0.95s）。"""
        from modules.visualizer import Visualizer
        _NUM_FIELDS = ('current_price', 'prev_close', 'change_pct', 'entry_price', 'target_price', 'stop_price', 'atr14', 'support', 'resistance', 'lo52', 'hi52', 'ma5v', 'ma10v', 'ma20v', 'trapped', 'vol_now', 'vol_avg', 'vol_chg', 'q_open', 'q_high', 'q_low', 'q_prev', 'tech_score', 'news_score', 'macro_score', 'vol_score', 'sector_score', 'composite', 'pos_pct', 'neg_pct', 'pos52')
        for _nf in _NUM_FIELDS:
            _v = R.get(_nf)
            if _v is None or (isinstance(_v, float) and pd.isna(_v)):
                R[_nf] = 0.0
        ticker = R['ticker']
        display_name = R['display_name']
        industry = R['industry']
        current_price = R['current_price']
        prev_close = R['prev_close']
        change_pct = R['change_pct']
        df = R['df']
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            _empty_info('分析数据不完整（行情序列缺失），暂无法渲染决策仪表盘。请重新生成分析。')
            return
        trend = R.get('trend') or {}
        momentum = R.get('momentum') or {}
        volume_info = R.get('volume_info') or {}
        tech_score = R['tech_score']
        news_score = R['news_score']
        macro_score = R['macro_score']
        vol_score = R['vol_score']
        composite = R['composite']
        verdict = R['verdict']
        verdict_color = R['verdict_color']
        verdict_cls = R['verdict_cls']
        sector_score = R.get('sector_score', 55)
        sector_analysis = R.get('sector_analysis', {'name': industry, 'change_pct': None, 'label': '—', 'rank': None, 'total': None})
        technical_profile = R.get('technical_profile', {'short': 50, 'mid': 50, 'long': 50, 'trend': 50, 'composite': 50})
        news_rows = R.get('news_rows') or []
        pos_pct = R['pos_pct']
        neg_pct = R['neg_pct']
        support = R['support']
        resistance = R['resistance']
        entry_price = R['entry_price']
        target_price = R['target_price']
        stop_price = R['stop_price']
        atr14 = R['atr14']
        lo52 = R['lo52']
        hi52 = R['hi52']
        pos52 = R['pos52']
        ma5v = R['ma5v']
        ma10v = R['ma10v']
        ma20v = R['ma20v']
        trapped = R['trapped']
        vol_now = R['vol_now']
        vol_avg = R['vol_avg']
        vol_chg = R['vol_chg']
        q_open = R['q_open']
        q_high = R['q_high']
        q_low = R['q_low']
        q_prev = R['q_prev']
        q_amount = R['q_amount']
        board = R['board']
        position_advice = R['position_advice']
        data_src = R['data_src']
        quote_src = R['quote_src']
        last = df.iloc[-1]
        st.markdown('<div class="sf-card">' + _section_header('顶部决策摘要', icon='🎯', level=1), unsafe_allow_html=True)
        chg_txt = f'{change_pct:+.2f}%'
        _close = last['close']
        if _close is None or (isinstance(_close, float) and pd.isna(_close)):
            _close = 0.0
        price_disp = f'¥{current_price:.2f}' if current_price is not None else f'¥{_close:.2f}'
        change_amt = current_price - prev_close if current_price is not None and prev_close is not None else 0.0
        triangle = '▲' if change_pct > 0 else '▼' if change_pct < 0 else '—'
        price_color = RED if change_pct > 0 else GREEN if change_pct < 0 else AMBER
        badge_text = 'BUY' if verdict == '看多' else 'SELL' if verdict == '看空' else 'HOLD'
        badge_class = 'sf-buy-badge' if verdict == '看多' else 'sf-sell-badge' if verdict == '看空' else 'sf-hold-badge'
        today_bits = []
        if q_open is not None:
            today_bits.append(f'今开 ¥{q_open:.2f}')
        if q_high is not None:
            today_bits.append(f'最高 ¥{q_high:.2f}')
        if q_low is not None:
            today_bits.append(f'最低 ¥{q_low:.2f}')
        if q_prev is not None:
            today_bits.append(f'昨收 ¥{q_prev:.2f}')
        if q_amount is not None:
            today_bits.append(f'成交额 {q_amount / 100000000.0:.2f}亿')
        today_bits.append(f"成交量 {df['volume'].iloc[-1] / 10000.0:.1f}万手")
        today_pills = ''.join((f"<span style='display:inline-block;font-size:12px;color:var(--txt2);background:var(--card2);border:1px solid var(--border);border-radius:6px;padding:3px 9px;margin:0 6px 6px 0;'>{b}</span>" for b in today_bits)) if today_bits else '—'
        hdr_left, hdr_right = st.columns([3, 1])
        with hdr_left:
            st.markdown(f"<div style='font-size:23px;font-weight:700;color:var(--txt);'>{display_name}</div><div style='font-size:12.5px;color:var(--txt2);margin-top:3px;'>{ticker} · {board} · {industry}</div><div style='margin-top:10px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;'><span class='sf-price-big' style='color:{price_color}!important;'>{price_disp}</span><span style='font-size:16px;font-weight:600;color:{price_color};'><span class='sf-triangle'>{triangle}</span>{chg_txt} ({change_amt:+.2f})</span></div><div style='margin-top:8px;'>{today_pills}</div>", unsafe_allow_html=True)
        with hdr_right:
            st.markdown(f"<div style='text-align:center;margin-bottom:10px;'><span class='{badge_class}'>{badge_text}</span></div>{_score_ring_html(composite, verdict_color)}<div style='font-size:12px;color:var(--txt2);text-align:center;margin-top:4px;'>{verdict} · {('择机买入' if verdict == '看多' else '逢高减仓' if verdict == '看空' else '区间波段')}<br>({('65~79区间' if 65 <= composite <= 79 else '综合评分区间')})</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='sf-metric-card'><div class='label'>入场价（首仓 / 回踩）</div><div class='value sf-doc-up'>¥{current_price:.1f} / ¥{entry_price:.1f}</div></div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='sf-metric-card'><div class='label'>目标价（一目标 / 压力）</div><div class='value sf-doc-up'>¥{target_price:.1f} / ¥{resistance:.1f}</div></div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='sf-metric-card'><div class='label'>止损价（ATR14 风险位）</div><div class='value sf-doc-down'>¥{stop_price:.1f}</div><div style='font-size:11px;color:var(--txt2);margin-top:4px;'>ATR14=¥{atr14:.2f}</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:14px;border-left:4px solid var(--acc1);background:var(--card2);border-radius:0 12px 12px 0;padding:12px 16px;font-size:13.5px;color:var(--txt2);line-height:1.7;'><b style='color:var(--txt);'>📌 仓位建议：</b>{position_advice}</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="sf-card">' + _section_header('核心结论', 'AI 综合研判 · 多空信号', '💡', level=1), unsafe_allow_html=True)
        trend_label = trend.get('trend_label', '—') if 'error' not in trend else '数据不足'
        mom_label = momentum.get('momentum_label', '—') if 'error' not in momentum else '—'
        vol_label = volume_info.get('volume_price_label', '—') if 'error' not in volume_info else '—'
        one_line = f'{display_name} 现价 ¥{current_price:.2f}（{chg_txt}），技术面「{trend_label}」、动量「{mom_label}」、量能「{vol_label}」；新闻情绪正面占比 {pos_pct:.0f}%，综合研判 <b>{verdict}</b>。'
        st.markdown(f"<div style='border-radius:14px;padding:18px 20px;background:linear-gradient(135deg, {verdict_color}22, {verdict_color}08);border:1px solid {verdict_color}55;'><div style='display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;'><div style='font-size:22px;font-weight:800;color:{verdict_color};'>{verdict} · {display_name}</div><span class='sf-tag {verdict_cls}' style='font-size:13px;padding:5px 14px;'>{badge_text}</span></div><div style='margin-top:10px;font-size:14px;color:var(--txt);line-height:1.8;'>{one_line}</div><div style='margin-top:12px;display:flex;flex-wrap:wrap;gap:8px;'><span class='sf-tag neu'>综合评分 {composite}</span><span class='sf-tag {verdict_cls}'>信号 · {verdict}</span><span class='sf-tag neu'>策略 · {('分批建仓' if verdict == '看多' else '逢高减仓' if verdict == '看空' else '区间波段')}</span><span class='sf-tag neu'>适用 · 事件驱动 / 中短线</span></div></div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="sf-card">' + _section_header('综合信息', '舆情 · 评分 · 五维 · 关联板块', '🧩', level=1), unsafe_allow_html=True)
        _sec = sector_analysis or {}
        _sec_name = _sec.get('name') or industry or '—'
        _sec_chg = _sec.get('change_pct')
        _sec_chg_txt = f'{_sec_chg:+.2f}%' if isinstance(_sec_chg, (int, float)) else '—'
        _sec_rank = _sec.get('rank')
        _sec_total = _sec.get('total')
        _sec_rank_txt = f'{_sec_rank}/{_sec_total}' if isinstance(_sec_rank, (int, float)) and isinstance(_sec_total, (int, float)) else '—'
        st.markdown(f"<div class='sf-grid-4'><div class='sf-perspective-card'><div class='title'>舆情热度（近 {len(news_rows)} 条）</div><div class='body'><span style='color:var(--buy);font-weight:700;'>正面 {pos_pct:.0f}%</span> / <span style='color:var(--sell);font-weight:700;'>负面 {neg_pct:.0f}%</span><div style='margin-top:8px;height:8px;border-radius:4px;background:var(--sell);overflow:hidden;'><div style='height:100%;width:{pos_pct:.0f}%;background:var(--buy);'></div></div></div></div><div class='sf-perspective-card'><div class='title'>综合评分</div><div class='body' style='display:flex;align-items:baseline;gap:8px;'><span style='font-size:30px;font-weight:800;color:{verdict_color};'>{composite}</span><span class='sf-tag {verdict_cls}'>{verdict}</span></div></div><div class='sf-perspective-card'><div class='title'>五维评分拆解</div><div class='body'><span class='sf-pill {_tp_cls(tech_score)}'>技术 {tech_score}</span><span class='sf-pill {_tp_cls(news_score)}'>舆情 {news_score}</span><span class='sf-pill {_tp_cls(vol_score)}'>量能 {vol_score}</span><span class='sf-pill {_tp_cls(macro_score)}'>宏观 {macro_score}</span><span class='sf-pill {_tp_cls(sector_score)}'>板块 {sector_score}</span></div></div><div class='sf-perspective-card'><div class='title'>关联板块 · {board or '—'}</div><div class='body'>{industry or '—'} · {_sec_name}<br>板块涨跌 {_sec_chg_txt} · 排名 {_sec_rank_txt}</div></div></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:12px;font-size:13px;color:var(--txt2);line-height:1.7;'><b style='color:var(--txt);'>📝 股评：</b>技术面 {tech_score} 分、舆情 {news_score} 分、量能 {vol_score} 分、宏观 {macro_score} 分、板块 {sector_score} 分，综合研判 <b>{verdict}</b>，建议{('分批建仓' if verdict == '看多' else '逢高减仓' if verdict == '看空' else '区间波段')}。</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="sf-card">' + _section_header('数据透视', '量价 / 筹码 / 位置 / 乖离', '📊', level=1), unsafe_allow_html=True)
        dev5 = (last['close'] - ma5v) / ma5v * 100 if ma5v else 0.0
        dev10 = (last['close'] - ma10v) / ma10v * 100 if ma10v else 0.0
        dev20 = (last['close'] - ma20v) / ma20v * 100 if ma20v else 0.0
        price_chain = f'价 {current_price:.2f}'
        price_chain += f" {('>' if current_price >= ma5v else '<')} MA5({ma5v:.1f})"
        price_chain += f" {('>' if ma5v >= ma10v else '<')} MA10({ma10v:.1f})"
        if current_price < ma20v:
            price_chain += f" · MA20({ma20v:.1f})<span class='sf-doc-down'>压制</span>"
        else:
            price_chain += f' > MA20({ma20v:.1f})'
        dist_high = (last['close'] / hi52 - 1) * 100 if hi52 else 0.0
        pos_desc = '中下部' if pos52 < 50 else '中上部'
        st.markdown(f"<div class='sf-grid-4'><div class='sf-perspective-card'><div class='title'>技术面 · 多周期（综合 {technical_profile['composite']}）</div><div class='body'><span class='sf-pill {_tp_cls(technical_profile['short'])}'>短期 {technical_profile['short']}</span><span class='sf-pill {_tp_cls(technical_profile['mid'])}'>中期 {technical_profile['mid']}</span><span class='sf-pill {_tp_cls(technical_profile['long'])}'>长期 {technical_profile['long']}</span></div></div><div class='sf-perspective-card'><div class='title'>价格位置（相对关键均线）</div><div class='body'>{price_chain}</div></div><div class='sf-perspective-card'><div class='title'>乖离率（严进标准 &lt;5%）</div><div class='body'>MA5 <b class='sf-doc-up'>{dev5:+.1f}%</b> · MA10 <b class='sf-doc-up'>{dev10:+.1f}%</b> · MA20 <b class='sf-doc-down'>{dev20:+.1f}%</b></div></div><div class='sf-perspective-card'><div class='title'>52周区间</div><div class='body'><b>¥{lo52:.2f} – ¥{hi52:.2f}</b><br>（现处{pos_desc}，距前高 {dist_high:+.0f}%）</div></div></div>", unsafe_allow_html=True)
        _vol_desc = '明显放量' if vol_chg > 30 else '温和放大' if vol_chg > 0 else '缩量' if vol_chg < -15 else '地量企稳'
        _vol_health = '健康换手而非过热' if abs(vol_chg) < 40 else '异常波动需警惕'
        _q_amount_disp = f'{q_amount / 100000000.0:.2f}亿' if q_amount is not None and (not pd.isna(q_amount)) else '—'
        st.markdown(f"<div style='margin-top:12px;font-size:13.5px;color:var(--txt2);line-height:1.7;'><b style='color:var(--txt);'>量能分析：</b>近 20 日均量约 {vol_avg / 10000.0:.1f} 万手；最新一日 {vol_now / 10000.0:.1f} 万手，较前一日 {vol_chg:+.1f}%（{_vol_desc}）；成交额 {_q_amount_disp}（实时行情），当前属{_vol_health}。</div>", unsafe_allow_html=True)
        _drawdown = (last['close'] / trapped - 1) * 100 if trapped > 0 else 0.0
        st.markdown(f"<div style='margin-top:8px;font-size:13.5px;color:var(--txt2);line-height:1.7;'><b style='color:var(--txt);'>筹码结构：</b>近 120 日自 {trapped:.2f} 高点回落至现价 {last['close']:.2f}（约 {_drawdown:+.1f}%），{trapped:.2f}–{hi52:.2f} 区间为近期密集成交<b style='color:{AMBER};'>套牢区</b>，反弹至此抛压显著；前低 <b style='color:{RED};'>¥{support:.2f}</b> 为强支撑，MA5/MA10 为短期依托。</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        fragment_kline_card(ticker, display_name, df, ma20v, ma10v, support, trapped)
        neu_pct = max(0, 100 - pos_pct - neg_pct)
        st.markdown('<div class="sf-card">' + _section_header('情报面', '新闻情绪 · 事件催化 · 风险提示', '📰', level=1), unsafe_allow_html=True)
        st.markdown(f"<div class='sf-intel-header'><div><span class='sf-pill up'>正面 {pos_pct:.0f}%</span><span class='sf-pill mid'>中性 {neu_pct:.0f}%</span><span class='sf-pill down'>负面 {neg_pct:.0f}%</span></div></div><div class='sf-intel-bar'><div class='bar-pos' style='width:{pos_pct:.0f}%'></div><div class='bar-neu' style='width:{neu_pct:.0f}%'></div><div class='bar-neg' style='width:{neg_pct:.0f}%'></div></div>", unsafe_allow_html=True)
        if news_rows:
            _news_q = st.text_input('🔍 搜索相关新闻…', key=f'filter_news_{ticker}', placeholder='输入关键词筛选新闻标题（仅前端过滤，不影响原始数据）')
            _filtered_news = [r for r in news_rows if _news_q.strip().lower() in str(r.get('title') or '').lower()] if _news_q else news_rows
            _news_limit_key = f'news_limit_{ticker}'
            if _news_limit_key not in st.session_state:
                st.session_state[_news_limit_key] = 10
            _show_n = min(st.session_state[_news_limit_key], len(_filtered_news))
            _disp_news = _filtered_news[:_show_n]
            st.caption(f'📰 共获取 {len(news_rows)} 条新闻' + (f'，筛选命中 {len(_filtered_news)} 条' if _news_q else '') + f'，当前显示前 {_show_n} 条（按情绪权重排序）')
            rows_html = ''.join((f"<tr><td class='l'>{safe_html_text(r.get('title'), '—')}</td><td><span class='sf-tag {_sentiment_tag(r.get('sentiment') or '中性')}'>{safe_html_text(r.get('sentiment'), '中性')}</span></td></tr>" for r in _disp_news))
            st.markdown(f"<table class='sf-table'><thead><tr><th class='l'>新闻标题</th><th>情绪</th></tr></thead><tbody>{rows_html}</tbody></table>", unsafe_allow_html=True)
            if _show_n < len(_filtered_news):
                if st.button('显示更多 ▼', key=f'news_more_{ticker}', width="stretch"):
                    st.session_state[_news_limit_key] += 10
        else:
            _empty_info('暂无新闻数据（网络不可用或该标的无公开新闻）')
        if neg_pct >= 30 or verdict == '看空':
            risk_titles = [safe_html_text(r.get('title'), '—') for r in news_rows if r.get('sentiment') == '负面'][:2]
            risk_body = '；'.join(risk_titles) if risk_titles else f'综合研判偏空（{safe_html_text(verdict)}）'
            st.markdown(f"<div class='sf-alert risk'><b>⚠️ 风险警报</b>检测到偏空信号：{risk_body}。建议严格控制仓位并关注止损价 ¥{stop_price:.2f}。</div>", unsafe_allow_html=True)
        if pos_pct >= 40 or verdict == '看多':
            cat_titles = [safe_html_text(r.get('title'), '—') for r in news_rows if r.get('sentiment') == '正面'][:2]
            cat_body = '；'.join(cat_titles) if cat_titles else f'综合研判偏多（{safe_html_text(verdict)}）'
            st.markdown(f"<div class='sf-alert cat'><b>🚀 积极催化</b>检测到正面信号：{cat_body}。可关注突破压力 ¥{target_price:.2f} 后的趋势机会。</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        rise_factors, fall_factors = _build_rise_fall_factors(R)
        col_rise, col_fall = st.columns(2)
        with col_rise:
            st.markdown(_factor_list_html('利好清单（全集）', rise_factors), unsafe_allow_html=True)
        with col_fall:
            st.markdown(_factor_list_html('利空清单（全集）', fall_factors), unsafe_allow_html=True)
        if not rise_factors and (not fall_factors):
            _empty_info('暂未提取到利好 / 利空因素（数据缺失或该标的尚未生成）。可重新生成分析，或检查行情与新闻数据源。')
        rise_logic, fall_logic, fatal_logic = _build_logic_lists(R)
        col_logic_r, col_logic_f = st.columns(2)
        with col_logic_r:
            st.markdown(_logic_list_html('利好逻辑', rise_logic, RED, '🐂'), unsafe_allow_html=True)
        with col_logic_f:
            st.markdown(_logic_list_html('利空逻辑', fall_logic, GREEN, '🐻'), unsafe_allow_html=True)
        if fatal_logic:
            st.markdown(_logic_list_html('致命风险（必须盯死）', fatal_logic, '#ef4444', '⚠️'), unsafe_allow_html=True)
        st.markdown('<div class="sf-card">' + _section_header('板块分析', '主板块定位 · 实时走势 · 同板块对比', '📊', level=1), unsafe_allow_html=True)
        _sa_name = sector_analysis.get('name', '—')
        _sa_full = sector_analysis.get('full_name', _sa_name)
        _sa_chg = sector_analysis.get('change_pct')
        _sa_label = sector_analysis.get('label', '—')
        _sa_rank = sector_analysis.get('rank')
        _sa_total = sector_analysis.get('total')
        _sa_chg_txt = f'{_sa_chg:+.2f}%' if _sa_chg is not None else '—'
        _sa_chg_color = RED if (_sa_chg or 0) > 0 else GREEN if (_sa_chg or 0) < 0 else AMBER
        _sa_rank_txt = f'全市场第 {_sa_rank}/{_sa_total} 强' if _sa_rank and _sa_total else '—'
        if _sa_chg is None:
            _market_verdict = '暂无板块行情数据'
            _market_detail = f'主板块「{_sa_name}」暂无实时涨跌数据，无法判断板块是否有行情。建议结合大盘与五维雷达综合判断。'
        else:
            if _sa_chg >= 2.0:
                _market_strength, _has_boom = ('强势上涨', '板块行情明确')
            elif _sa_chg >= 1.0:
                _market_strength, _has_boom = ('偏强运行', '板块有温和行情')
            elif _sa_chg >= -1.0:
                _market_strength, _has_boom = ('横盘震荡', '板块暂无单边行情')
            elif _sa_chg >= -2.0:
                _market_strength, _has_boom = ('偏弱调整', '板块处于调整')
            else:
                _market_strength, _has_boom = ('弱势下跌', '板块行情较差')
            if _sa_rank and _sa_total:
                _pct = _sa_rank / _sa_total * 100
                if _pct <= 10:
                    _rank_desc = '板块热度处于全市场前 10%（头部）'
                elif _pct <= 30:
                    _rank_desc = '板块热度处于全市场前 30%（中上）'
                elif _pct <= 70:
                    _rank_desc = '板块热度处于全市场中游'
                else:
                    _rank_desc = '板块热度处于全市场后 30%（落后）'
            else:
                _rank_desc = '暂无全市场排名'
            _market_verdict = f'{_has_boom}：{_sa_name} {_market_strength}（{_sa_chg_txt}），{_rank_desc}。'
            _market_detail = f'该主线属于「{_sa_full}」，实时涨跌幅 {_sa_chg_txt}，{_sa_rank_txt}。'
        _peer_rank = sector_analysis.get('peer_rank')
        _peer_total = sector_analysis.get('peer_total')
        _peer_avg = sector_analysis.get('peer_avg_change')
        _peer_median = sector_analysis.get('peer_median_change')
        _is_leader = sector_analysis.get('is_leader', False)
        _top_peers = sector_analysis.get('top_peers', [])
        _better_peers = sector_analysis.get('better_peers', [])
        if _peer_rank and _peer_total:
            _peer_pct = _peer_rank / _peer_total * 100
            if _peer_pct <= 10:
                _position_desc = '板块龙头/前排'
            elif _peer_pct <= 30:
                _position_desc = '板块中上游'
            elif _peer_pct <= 70:
                _position_desc = '板块中游'
            else:
                _position_desc = '板块后排'
            _position_txt = f'{display_name} 在 {_sa_name} 板块 {_peer_total} 只个股中排名第 {_peer_rank}，处于{_position_desc}。'
            if _is_leader:
                _position_txt = f'{display_name} 是 {_sa_name} 板块涨幅龙头，板块内共 {_peer_total} 只个股。'
        else:
            _position_txt = f'暂无 {display_name} 在 {_sa_name} 板块内的排名数据。'
        if _peer_avg is not None:
            _rel = (change_pct or 0) - _peer_avg
            _rel_txt = f'{_rel:+.2f}%'
            if _rel >= 2.0:
                _rel_desc = '明显强于板块'
            elif _rel > 0:
                _rel_desc = '强于板块'
            elif _rel > -2.0:
                _rel_desc = '弱于板块'
            else:
                _rel_desc = '明显弱于板块'
            _position_txt += f' 相对板块平均涨跌幅（{_peer_avg:+.2f}%）{_rel_desc} {_rel_txt}。'
        if _peer_median is not None:
            _position_txt += f' 板块中位数涨跌幅 {_peer_median:+.2f}%。'

        def _fmt_cap(v):
            try:
                v = float(v)
                if v >= 100000000.0:
                    return f'{v / 100000000.0:.1f}亿'
                if v >= 10000.0:
                    return f'{v / 10000.0:.1f}万'
                return f'{v:.0f}'
            except Exception:
                return '—'

        def _peer_row(p, idx=None, show_rank=False):
            code = str(p.get('code', '')).zfill(6)
            name = p.get('name', '')
            chg = p.get('change_pct')
            cap = p.get('market_cap')
            chg_txt = f'{chg:+.2f}%' if chg is not None else '—'
            color = RED if (chg or 0) > 0 else GREEN if (chg or 0) < 0 else AMBER
            cap_txt = _fmt_cap(cap) if cap is not None else '—'
            rank_cell = f"<td style='padding:6px 8px;font-size:13px;color:var(--txt2);text-align:center;width:36px;'>{idx}</td>" if show_rank else ''
            return f"<tr>{rank_cell}<td style='padding:6px 8px;font-size:13px;color:var(--txt);'>{code}</td><td style='padding:6px 8px;font-size:13px;color:var(--txt);'>{name}</td><td style='padding:6px 8px;font-size:13px;font-weight:600;color:{color};'>{chg_txt}</td><td style='padding:6px 8px;font-size:12px;color:var(--txt2);text-align:right;'>{cap_txt}</td></tr>"
        _html = f'<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:12px;"><div style="font-size:18px;font-weight:700;color:var(--txt);">{_sa_name}</div><span class="sf-pill {_tp_cls(sector_score)}">板块强度 {sector_score}</span><span style="font-size:14px;font-weight:600;color:{_sa_chg_color};">{_sa_chg_txt} {_sa_label}</span><span class="sf-pill mid">{_sa_rank_txt}</span></div><div style="font-size:13.5px;color:var(--txt2);line-height:1.7;margin-bottom:12px;"><b style="color:var(--txt);">板块行情：</b>{_market_verdict}<br>{_market_detail}</div><div style="font-size:13.5px;color:var(--txt2);line-height:1.7;margin-bottom:16px;"><b style="color:var(--txt);">个股定位：</b>{_position_txt}</div>'
        if _top_peers:
            rows = ''.join((_peer_row(p, i + 1) for i, p in enumerate(_top_peers[:5])))
            _html += f'<div style="font-size:13px;font-weight:600;color:var(--txt);margin-bottom:8px;">🏆 板块领涨 TOP5</div><table style="width:100%;border-collapse:collapse;margin-bottom:16px;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">代码</th><th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">名称</th><th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">涨跌幅</th><th style="padding:6px 8px;text-align:right;font-size:12px;color:var(--txt2);font-weight:600;">总市值</th></tr></thead><tbody>{rows}</tbody></table>'
        if _better_peers:
            rows = ''.join((_peer_row(p, i + 1, show_rank=True) for i, p in enumerate(_better_peers[:5])))
            _html += f'<div style="font-size:13px;font-weight:600;color:var(--txt);margin-bottom:8px;">⚡ 比 {display_name} 更强的同板块个股</div><table style="width:100%;border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border);"><th style="padding:6px 8px;text-align:center;font-size:12px;color:var(--txt2);font-weight:600;width:36px;">排名</th><th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">代码</th><th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">名称</th><th style="padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;">涨跌幅</th><th style="padding:6px 8px;text-align:right;font-size:12px;color:var(--txt2);font-weight:600;">总市值</th></tr></thead><tbody>{rows}</tbody></table>'
        elif _peer_rank and _peer_rank == 1:
            _html += f'<div style="font-size:13px;color:var(--txt2);margin-top:8px;">✅ {display_name} 当前为该板块涨幅第一，暂无同板块个股比它更强。</div>'
        st.markdown(_html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption('板块内对比表格列说明：代码 / 名称 / 涨跌幅（绿涨红跌，本页配色）/ 总市值（亿元）；数据来自同板块实时行情。')
        st.markdown('<div class="sf-card">' + _section_header('信号归因 · 五维雷达', '技术 / 情绪 / 量能 / 宏观 / 板块', '🎯', level=1), unsafe_allow_html=True)
        try:
            import plotly.graph_objects as go
            radar_fig = go.Figure()
            cats = ['技术指标', '新闻情绪', '资金量能', '市场环境', '板块强度']
            vals = [tech_score, news_score, vol_score, macro_score, sector_score]
            radar_fig.add_trace(go.Scatterpolar(r=vals + [vals[0]], theta=cats + [cats[0]], fill='toself', line=dict(color='#667eea', width=2), fillcolor='rgba(102,126,234,0.25)', name='信号强度'))
            from modules.dark_text_fix import apply_plotly_theme
            apply_plotly_theme(radar_fig, dark=dark)
            radar_fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=440, margin=dict(l=40, r=40, t=20, b=20))
            st.plotly_chart(radar_fig, width="stretch", config={'displaylogo': False, 'responsive': True})
            st.markdown(f"<div style='text-align:center;font-size:14px;font-weight:700;color:var(--txt);margin:6px 0 2px;'>综合信号强度 <b style='color:{verdict_color};'>{composite}</b> · {verdict}（五维加权）</div>", unsafe_allow_html=True)
        except Exception as e:
            xc_handle_error("雷达图渲染失败", str(e)[:80], hint="请稍后重试，或检查网络与数据源连接")
        st.markdown(f"<table class='sf-table'><thead><tr><th class='l'>维度（权重）</th><th>得分</th><th class='l'>研判要点</th></tr></thead><tbody><tr><td class='l'><b>技术指标</b> 25%</td><td>{tech_score:.0f}</td><td class='l'>多周期（短/中/长）趋势 · 动量强弱</td></tr><tr><td class='l'><b>新闻情绪</b> 22%</td><td>{news_score:.0f}</td><td class='l'>事件催化强度 · 正面占比 {pos_pct:.0f}%</td></tr><tr><td class='l'><b>资金量能</b> 18%</td><td>{vol_score:.0f}</td><td class='l'>量价配合 · 换手健康度</td></tr><tr><td class='l'><b>市场环境</b> 15%</td><td>{macro_score:.0f}</td><td class='l'>宏观 PMI · 大盘强弱</td></tr><tr><td class='l'><b>板块强度</b> 20%</td><td>{sector_score:.0f}</td><td class='l'>个股相对所属板块的强弱 · 排名 {sector_analysis.get('rank', '—')}{('/' + str(sector_analysis.get('total')) if sector_analysis.get('total') else '')} 强</td></tr><tr><td class='l'><b>综合评分</b></td><td><b>{composite}</b></td><td class='l'>五维加权汇总</td></tr></tbody></table>", unsafe_allow_html=True)
        with st.expander('📖 评分维度说明', expanded=False):
            st.markdown('• <b>技术指标 25%</b>：多周期（短/中/长）趋势与动量强弱。<br>• <b>新闻情绪 22%</b>：事件催化强度与正面占比。<br>• <b>资金量能 18%</b>：量价配合与换手健康度。<br>• <b>市场环境 15%</b>：宏观 PMI 与大盘强弱。<br>• <b>板块强度 20%</b>：个股相对所属板块的强弱与排名。<br>综合评分 = 五维加权汇总，仅作研究参考，不构成投资建议。', unsafe_allow_html=True)
        bull = []
        bear = []
        if 'error' not in trend:
            if trend.get('arrangement') in ('多头排列', '偏多'):
                bull.append(f"均线「{trend.get('arrangement')}」，站上 {trend.get('above_count', 0)} 条均线")
            if trend.get('arrangement') in ('空头排列', '偏空'):
                bear.append(f"均线「{trend.get('arrangement')}」")
        if 'error' not in momentum:
            if momentum.get('momentum_score', 50) >= 65:
                bull.append(f"动量「{mom_label}」（5日 {momentum.get('returns', {}).get('5日', 0):+.2f}%）")
            elif momentum.get('momentum_score', 50) <= 35:
                bear.append(f'动量「{mom_label}」')
        if 'error' not in volume_info:
            if '升' in vol_label:
                bull.append(f'量能「{vol_label}」')
            if '跌' in vol_label:
                bear.append(f'量能「{vol_label}」')
        if pos_pct >= neg_pct:
            bull.append(f'新闻正面占比 {pos_pct:.0f}% 高于负面 {neg_pct:.0f}%')
        else:
            bear.append(f'新闻负面占比 {neg_pct:.0f}% 高于正面 {pos_pct:.0f}%')
        if verdict == '看多':
            bull.append('综合信号看多')
        elif verdict == '看空':
            bear.append('综合信号看空')
        st.markdown("<div class='sf-vs'>", unsafe_allow_html=True)
        st.markdown(f"<div class='sf-vsbox'><h3 style='color:{RED};'>最强看多信号</h3>" + (''.join((f'<ul><li>{b}</li></ul>' for b in bull)) if bull else '<ul><li>暂无显著看多信号</li></ul>') + '</div>', unsafe_allow_html=True)
        st.markdown(f"<div class='sf-vsbox'><h3 style='color:{GREEN};'>最强看空信号</h3>" + (''.join((f'<ul><li>{b}</li></ul>' for b in bear)) if bear else '<ul><li>暂无显著看空信号</li></ul>') + '</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="sf-card">' + _section_header('作战计划', icon='⚔️', level=1), unsafe_allow_html=True)
        st.markdown(_battle_plan_scale(support, resistance, current_price, target_price, stop_price, entry_price, verdict), unsafe_allow_html=True)
        plan_rows = _build_plan_rows(verdict, current_price, support, resistance, target_price, stop_price, entry_price, ma20v)
        a_tag = 'up' if verdict == '看多' else 'down' if verdict == '看空' else 'mid'
        b_tag = 'neu'
        rows_html = ''.join((f"<tr><td><span class='sf-tag {(a_tag if i == 0 else b_tag)}'>{r[0]}</span></td><td class='l'>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td class='l'>{r[4]}</td></tr>" for i, r in enumerate(plan_rows)))
        st.markdown(f"<table class='sf-table'><thead><tr><th>方案</th><th class='l'>触发条件</th><th>入场</th><th>止损</th><th class='l'>目标</th></tr></thead><tbody>{rows_html}</tbody></table>", unsafe_allow_html=True)
        st.markdown("<div style='color:var(--txt);font-weight:600;margin:14px 0 4px;'>风控清单</div>", unsafe_allow_html=True)
        col_risk, col_iron = st.columns(2)
        with col_risk:
            risk_items = [f'止损价：¥{stop_price:.2f}（破位无条件离场）', f'止盈价：¥{target_price:.2f}（到达分批兑现）', '失效条件：突发利空 / 放量跌穿支撑 / 宏观转弱（PMI<50）', '仓位纪律：单标的 ≤ 总仓位 30%，亏损单不补仓摊平']
            st.markdown("<ul style='color:var(--txt2);font-size:13px;line-height:1.9;'>" + ''.join((f'<li>{x}</li>' for x in risk_items)) + '</ul>', unsafe_allow_html=True)
        with col_iron:
            st.markdown(_risk_iron_html('风险铁律', _build_risk_iron_rules(R)), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(f"<div class='sf-disclaimer'>分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 标的：{display_name}({ticker}) ｜ 数据来源：行情 {data_src}、实时行情 {quote_src}、新闻 东方财富/财新/央视多源聚合、宏观 PMI ｜ 声明：本页所有结论均由程序基于公开数据自动计算，仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。</div>", unsafe_allow_html=True)
        _top_peers = sector_analysis.get('top_peers', []) or []
        _better_peers = sector_analysis.get('better_peers', []) or []
        _recs = []
        for p in _better_peers[:3] + _top_peers[:3]:
            _pc = p.get('code')
            if _pc and _pc not in [r.get('code') for r in _recs]:
                _recs.append(p)
        if _recs:
            st.markdown('<div class="sf-card">' + _section_header('相关标的推荐', '同板块领涨 / 更强个股', '🔗', level=1), unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:13px;color:var(--txt2);line-height:1.7;margin-bottom:10px;'>基于「{_sa_name}」板块内实时表现，为你推荐以下关联标的（涨跌遵循本页绿涨红跌配色）：</div>", unsafe_allow_html=True)
            _rec_rows = ''.join((_peer_row(p) for p in _recs[:6]))
            st.markdown(f"<table style='width:100%;border-collapse:collapse;'><thead><tr style='border-bottom:1px solid var(--border);'><th style='padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;'>代码</th><th style='padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;'>名称</th><th style='padding:6px 8px;text-align:left;font-size:12px;color:var(--txt2);font-weight:600;'>涨跌幅</th><th style='padding:6px 8px;text-align:right;font-size:12px;color:var(--txt2);font-weight:600;'>总市值</th></tr></thead><tbody>{_rec_rows}</tbody></table>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    def _deserialize_analysis_result(result: dict) -> dict:
        """把后台返回的 JSON（DataFrame 已序列化为 records）还原成页面可渲染的 dict。"""
        if not result:
            return result
        if 'df' in result and isinstance(result['df'], list):
            result['df'] = pd.DataFrame(result['df'])
            if 'date' in result['df'].columns:
                result['df']['date'] = pd.to_datetime(result['df']['date'], errors='coerce')
        return result

    st.caption('💡 分析包含行情 / 新闻 / 技术 / 评分等模块，首次生成约需 10–30 秒，后台运行期间可浏览其它页面。')

    @st.cache_data(ttl=1)
    def _poll_analysis_once(task_id: str) -> dict | None:
        """缓存 1 秒：避免同一次 fragment 重跑中多次调用 poll_task 造成请求堆积。"""
        return poll_task(task_id, max_wait=0.5)

    @safe_fragment(run_every=3)
    def fragment_analysis_result():
        """分析结果区：包含轮询、加载中反馈、完成后渲染，独立 fragment 不阻塞整页。"""
        analysis_task_id = st.session_state.get('analysis_task_id')
        if analysis_task_id:
            task = _poll_analysis_once(analysis_task_id)
            if task and task.get('status') == 'success':
                result = _deserialize_analysis_result(task.get('result'))
                _rt = result.get('ticker')
                if _rt:
                    _h2 = st.session_state.setdefault('_analysis_recent', [])
                    if _rt not in _h2:
                        _h2.insert(0, _rt)
                        st.session_state['_analysis_recent'] = _h2[:8]
                for w in result.pop('_warnings', []):
                    xc_warn_box(w)
                st.session_state['analysis_result'] = result
                del st.session_state['analysis_task_id']
                st.toast('✅ 个股分析完成')
            elif task and task.get('status') == 'error':
                st.error(f"分析失败：{task.get('error')}")
                del st.session_state['analysis_task_id']
            elif task and task.get('status') in ('pending', 'running'):
                xc_warn_box('⏳ 分析正在后台并行运行：行情数据 → 新闻舆情 → 技术信号 → 综合评分。完成后会自动显示下方结果，无需切换页面。', icon='⏳')
                st.progress(0.0, text='等待分析结果...')
                # P0-2：轮询改 run_every=3 服务端定时驱动（原 st_autorefresh 在 fragment 内不触发重跑）。
                return
        if st.session_state.get('analysis_result') is not None:
            _render_analysis(st.session_state['analysis_result'])
            _render_event_factor_card(st.session_state['analysis_result'].get('ticker'))

    fragment_analysis_result()


    def _render_event_factor_card(ticker):
        """个股分析页「事件因子」卡片：展示真实 P1 EV 事件因子（适配器接入）。

    仅在有真实信号时占用版面；取不到静默跳过。配色遵循本页「绿涨红跌」惯例。
    """
        if not ticker:
            return
        try:
            from modules.event_factor import get_event_factor
            ef = get_event_factor(ticker, model="ev")
        except Exception as e:  # noqa: BLE401
            xc_handle_error("事件因子加载失败", e)
            return
        if not ef.get("available"):
            return
        _sc = ef.get("score")
        if isinstance(_sc, (int, float)):
            _col = event_factor_color(_sc)  # 本页：绿涨红跌（正分=利好=绿=RED 常量，与价格行 426 一致；锐评 R7）
            _sc_txt = f"{_sc:+.2%}"
        else:
            _col = AMBER
            _sc_txt = "—"
        _rank = ef.get("rank")
        _rank_txt = f"{float(_rank)*100:.1f}" if isinstance(_rank, (int, float)) else "—"
        st.markdown(
            f"🧠 **事件因子（P1 EV，真实信号）**：得分 "
            f"<span style='color:{_col};font-weight:600'>{_sc_txt}</span>"
            f"　信号：**{ef.get('signal')}**　百分位排名：<b>{_rank_txt}</b>　来源：<code>{ef.get('source')}</code>",
            unsafe_allow_html=True)
        st.caption("由 P1-QuantFactor 神经网络产出（并入牧羊人情绪 9 维事件/regime 通道），"
                   "为统计超额收益概率排序，非买卖指令。百分位排名越高越看多。")


    def _video_embed_url(url: str):
        """把常见视频分享链接转换为可嵌入的 iframe src；不支持则返回 None。"""
        import re
        if not url:
            return None
        url = url.strip()
        m = re.search('(?:youtube\\.com/watch\\?v=|youtu\\.be/|youtube\\.com/embed/)([\\w-]{6,})', url)
        if m:
            return f'https://www.youtube.com/embed/{m.group(1)}'
        m = re.search('bilibili\\.com/video/(BV[\\w]+)', url)
        if m:
            return f'https://player.bilibili.com/player.html?bvid={m.group(1)}&autoplay=0&high_quality=1'
        m = re.search('v\\.qq\\.com/x/cover/\\w+/([\\w]+)\\.html', url)
        if m:
            return f'https://v.qq.com/txp/iframe/player.html?vid={m.group(1)}'
        return None

    def _safe_video_markdown(v):
        """PURE, streamlit-free helper：把用户粘贴的视频 raw 链接安全地渲染为 markdown。

    仅当 raw 为 http(s) 链接时才输出可点击的 <a href>，且对链接与文本做 html.escape，
    杜绝 `javascript:` 等存储型 XSS 注入；其余情况（缺失 / 非 http(s) 协议）返回
    转义后的纯文本（无 <a href>），由调用方以 unsafe_allow_html 渲染也不会执行脚本。
    _video_embed_url 的逻辑保持不动，本函数仅负责「安全渲染」这一层。
    """
        import html
        from urllib.parse import urlsplit
        if not isinstance(v, dict):
            return ''
        raw = v.get('raw', '')
        if not raw:
            return ''
        escaped = html.escape(raw)
        scheme = urlsplit(raw).scheme.lower()
        if scheme in ('http', 'https'):
            return f'<a href="{escaped}" target="_blank">{escaped}</a>'
        return escaped

    @safe_fragment
    def fragment_stock_videos(ticker):
        with st.expander('📺 相关视频（把互联网上的股票视频接入项目 · 点击展开/收起）', expanded=False, key='stock_video_exp'):
            try:
                name = StockFetcher().get_stock_name(ticker) or ticker
            except Exception:
                name = ticker
        q = f'{name} 股票分析'
        from urllib.parse import quote
        links = [('🅑️ B站', f'https://search.bilibili.com/all?keyword={quote(q)}'), ('🔍 百度视频', f'https://www.baidu.com/s?tn=baiduvi&wd={quote(q)}'), ('▶️ YouTube', f'https://www.youtube.com/results?search_query={quote(q)}'), ('🎵 抖音', f'https://www.douyin.com/search/{quote(q)}')]
        st.caption(f'「{name}」相关视频聚合（点击在浏览器新标签打开对应平台搜索结果）：')
        _lc = st.columns(len(links))
        for i, (label, href) in enumerate(links):
            with _lc[i]:
                st.markdown(f'<a href="{href}" target="_blank" style="display:block;text-align:center;padding:8px 4px;border:1px solid var(--border);border-radius:10px;text-decoration:none;color:var(--txt);font-weight:600;">{label}</a>', unsafe_allow_html=True)
        st.markdown('---')
        st.markdown('**🔗 粘贴视频地址，内联嵌入播放**（支持 YouTube / B站 / 腾讯视频 分享链接）：')
        vk = f'video_embed_{ticker}'
        if vk not in st.session_state:
            st.session_state[vk] = []
        with st.form(key=f'video_form_{ticker}', clear_on_submit=True):
            video_url = st.text_input('视频链接（如 https://www.bilibili.com/video/BVxxxx 或 YouTube 链接）', '', placeholder='在此粘贴视频地址，例如 B站 / YouTube 分享链接')
            submitted = st.form_submit_button('➕ 添加到本股视频', width="stretch")
            if submitted and video_url:
                emb = _video_embed_url(video_url)
                if emb:
                    st.session_state[vk].append({'src': emb, 'raw': video_url})
                    st.toast('✅ 已添加视频')
                else:
                    xc_warn_box('⚠️ 暂仅支持 YouTube / B站 / 腾讯视频 的嵌入；其它平台已为你保留原链接，可点击观看。')
                    st.session_state[vk].append({'src': None, 'raw': video_url})
        if st.session_state[vk]:
            for idx, v in enumerate(st.session_state[vk]):
                col_player, col_del = st.columns([0.92, 0.08])
                with col_player:
                    if v['src']:
                        st.markdown(f'''<iframe src="{v['src']}" scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true" style="width:100%;height:380px;border-radius:12px;"></iframe>''', unsafe_allow_html=True)
                    else:
                        st.markdown('🔗 ' + _safe_video_markdown(v), unsafe_allow_html=True)
                with col_del:
                    _ck = f'vdel_cfm_{ticker}_{idx}'
                    if st.session_state.get(_ck):
                        if st.button('确认', key=f'vdel_cfm_btn_{ticker}_{idx}', type='primary', width="stretch"):
                            st.session_state[vk].pop(idx)
                            st.session_state.pop(_ck, None)
                        if st.button('取消', key=f'vdel_cancel_{ticker}_{idx}', width="stretch"):
                            st.session_state.pop(_ck, None)
                    elif st.button('✕', key=f'vdel_{ticker}_{idx}', width="stretch", help='移除'):
                        st.session_state[_ck] = True
        else:
            _empty_info('尚未添加视频。粘贴上方链接即可把网络视频「接到」本股票分析页内联播放')
            st.caption('💡 也可以直接点击下方按钮展开「粘贴视频地址」输入框，把 YouTube / B站 / 腾讯视频 接入本页内联播放。')
            if st.button('➕ 展开添加视频', key='video_empty_add'):
                st.session_state['stock_video_exp'] = True

    # ───────────────────────── 个股财报（随搜索框联动，独立于「生成分析」） ─────────────────────────
    def _build_periods_fin() -> dict:
        """动态生成常用报告期选项（当前年 + 前 5 年 × 4 个法定报告期），避免硬编码过时。"""
        from datetime import datetime
        cur = datetime.now().year
        suffix = {"0331": "一季报", "0630": "中报", "0930": "三季报", "1231": "年报"}
        out = {}
        for y in range(cur, cur - 6, -1):
            for mm, lbl in (("0331", "一季报"), ("0630", "中报"), ("0930", "三季报"), ("1231", "年报")):
                # 未来报告期（当年未披露）也保留选项，用户可选；接口会自然返回空
                out[f"{y} {lbl}"] = f"{y}{mm}"
        return out


    PERIODS_FIN = _build_periods_fin()


    def _get_listing_year(code: str) -> int:
        """从东财业绩报表「上市时间」列推断该股上市年份；失败时回退 2010。"""
        import re
        for _p in ("20251231", "20240930", "20240630", "20240331", "20231231",
                   "20230930", "20230630", "20230331", "20221231"):
            try:
                _df = _fr_cached_report(_p)
                _row = _fr_filter_by_code(_df, code)
                if _row is not None and not getattr(_row, "empty", True):
                    _lt = str(_row.iloc[0].get("上市时间", "")).strip()
                    if _lt:
                        _m = re.search(r"(\d{4})", _lt)
                        if _m:
                            return int(_m.group(1))
            except Exception:
                continue
        return 2010

    # 报告期后缀 → 中文标签（pill 按钮回填 session_state 用，与 fr_period_label 同源）
    _QUARTER_SUFFIX_REVERSE = {"0331": "一季报", "0630": "中报", "0930": "三季报", "1231": "年报"}

    # 横向历史对比：默认覆盖的年度（近 4 年 → 每年 4 个法定报告期 = 最多 16 期，满足「≥3 年」）
    _HISTORY_YEARS = ("2023", "2024", "2025", "2026")
    _HISTORY_QUARTERS = ("0331", "0630", "0930", "1231")

    # 横向对比可选指标（东财业绩报表列名 → 展示名）
    _HISTORY_METRICS = {
        "净利润": "净利润",
        "营业总收入": "营业总收入",
        "每股收益": "每股收益",
        "ROE%": "ROE%",
        "毛利率%": "毛利率%",
        "净利率%": "净利率%",
    }


    @st.cache_data(show_spinner=False, ttl=1800)
    def _fr_cached_history(code: str):
        """从该股上市年份（或近 10 年）逐期拉取业绩报表，合并为横向历史对比表。

    东财 stock_yjbb_em 每期只返回「该期全市场」一张表，故需逐期拉取后过滤拼接。
    任一期失败/未披露都会被 fr_build_history 跳过（不补零、不造假）；
    全部失败时返回空 DataFrame，由调用方展示兜底提示。
    返回 DataFrame（列：报告期/报告期标签/每股收益/营业总收入/营收同比%/净利润/净利润同比%/ROE%）。
    """
        from datetime import datetime
        _cur_y = datetime.now().year
        _start_y = max(_get_listing_year(code), _cur_y - 9)
        _years = [str(y) for y in range(_start_y, _cur_y + 1)]
        rows = []
        for _y in _years:
            for _q in _HISTORY_QUARTERS:
                _p = f"{_y}{_q}"
                try:
                    _df = _fr_cached_report(_p)
                except Exception:
                    _df = None
                rows.append((_p, _fr_filter_by_code(_df, code)))
        return fr_build_history(rows)


    @st.cache_data(show_spinner=False, ttl=1800)
    def _fr_cached_report(period: str):
        return get_earnings_report(period)


    @st.cache_data(show_spinner=False, ttl=1800)
    def _fr_cached_forecast(period: str):
        return get_earnings_forecast(period)


    @st.cache_data(show_spinner=False, ttl=1800)
    def _fr_cached_disclosure(market: str, period_str: str):
        return get_disclosure_calendar(market=market, period=period_str)


    @st.cache_data(show_spinner=False, ttl=1800)
    def _fr_cached_financial(code: str, report_type: str):
        """财务三表（利润表/资产负债表/现金流量表），best-effort，失败返回 None。"""
        try:
            df = fetcher.get_financial(code, report_type)
            return df if (df is not None and not getattr(df, "empty", True)) else None
        except Exception:
            return None


    def _build_perf_history_section(code: str, dark: bool = False) -> None:
        """渲染「📈 业绩横向对比」区块：指标切换 + 柱状折线图 + 下方「展开分析」明细表。

    参考手机端 F10「财务分析」常见交互：
      · 顶部一行 pill 切换指标（净利润 / 营业总收入 / 每股收益 / ROE%）；
      · 柱=规模（亿元，主轴）折线=同比%（副轴）；
      · 图下「展开分析」表列出各期明细（最新期在最前，红涨绿跌着色）。
    数据不足 2 期时给出诚实兜底提示，绝不合成假数据。
    """
        st.markdown('<div class="sf-card">' + _section_header("业绩横向对比", "≥3 年主要指标 · 柱状规模 + 折线同比", "📈", level=2), unsafe_allow_html=True)
        _pct_metrics = ("ROE%", "毛利率%", "净利率%")
        # ── 当前指标解析（必须先于下方 caption：T-292 修复——原实现把该块排在 caption 之后，
        #    `_cur` 未赋值先使用 → UnboundLocalError，财报 fragment 首屏渲染全断）──
        _mk = f"fr_hist_metric_{code}"
        _cur = st.session_state.get(_mk, "净利润")
        if _cur not in _HISTORY_METRICS:
            _cur = "净利润"
        if _cur in _pct_metrics:
            st.caption("📊 柱=该指标（%）；红=正值 / 绿=负值。数据来源：东方财富业绩报表（自该股上市年份起，最多近 10 年）。")
        else:
            st.caption("📊 柱=该指标规模（亿元），折线=同比增速（%）；红=增长 / 绿=下滑（业绩域红涨绿跌）。数据来源：东方财富业绩报表（自该股上市年份起，最多近 10 年）。")
        try:
            hist = _fr_cached_history(code)
        except Exception:
            hist = None
        if hist is None or getattr(hist, "empty", True) or len(hist) < 2:
            _empty_info(f"「{code}」暂无可用于横向对比的历史业绩数据（接口受限或披露不足 2 期）。")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        # ── 指标切换（pill）──（_cur 已在上方 caption 前解析）
        _mcols = st.columns(len(_HISTORY_METRICS))
        for _i, (_key, _disp) in enumerate(_HISTORY_METRICS.items()):
            with _mcols[_i]:
                if st.button(_disp, key=f"frhm_{code}_{_key}", width="stretch",
                             type=("primary" if _cur == _key else "secondary")):
                    st.session_state[_mk] = _key
                    st.rerun(scope="fragment")

        # ── 柱状 + 折线图 ──
        _fig = _build_perf_history_fig(hist, metric=_cur, dark=dark)
        if _fig is not None:
            st.plotly_chart(_fig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
        else:
            _empty_info(f"「{_cur}」有效数据点不足，暂不绘图（避免以残缺数据误导判断）。")

        # ── 「展开分析」明细表（与图同源，最新期在前）──
        with st.expander("🔎 展开分析 · 各期明细", expanded=True, key=f"fr_hist_exp_{code}"):
            _rows = fr_expand_rows(hist, _cur)
            if not _rows:
                _empty_info("暂无可展开的明细数据。")
            else:
                _yoy_col = fr_yoy_column(_cur)
                _recs = []
                for _lbl, _val, _yoy in _rows:
                    _c, _t = _fr_color_yoy(_yoy)
                    _recs.append({
                        "报告期": _lbl,
                        _HISTORY_METRICS.get(_cur, _cur): _fr_fmt(_val),
                        "同比": _t if _yoy_col else "—",
                        "_yoy_color": _c,
                    })
                _disp_df = pd.DataFrame(_recs)
                # 明细表：用 st.dataframe 展示数值列，同比着色以 caption 行说明（Streamlit 表格不逐格着色）
                st.dataframe(
                    _disp_df[["报告期", _HISTORY_METRICS.get(_cur, _cur), "同比"]],
                    width="stretch", hide_index=True, height=min(60 + 36 * len(_recs), 420),
                )
                # 同步输出一份「同比着色摘要」，把红涨绿跌语义显式呈现（表格本身不支持逐格着色）
                _chips = "　".join(
                    f"<span style='color:{r['_yoy_color']};font-weight:600;'>{r['报告期']} {r['同比']}</span>"
                    for r in _recs
                )
                st.markdown(
                    "<div style='font-size:12.5px;line-height:2;color:var(--txt2);margin-top:6px;'>"
                    "同比速览（红=增长 / 绿=下滑）：" + _chips + "</div>",
                    unsafe_allow_html=True,
                )
                try:
                    _csv = _disp_df[["报告期", _HISTORY_METRICS.get(_cur, _cur), "同比"]].to_csv(
                        index=False, encoding="utf-8-sig").encode("utf-8-sig")
                    st.download_button(
                        f"⬇️ 导出「{_HISTORY_METRICS.get(_cur, _cur)}」历史明细 CSV", data=_csv,
                        file_name=f"业绩历史_{code}_{_cur}.csv", mime="text/csv",
                        key=f"fr_hist_csv_{code}_{_cur}",
                    )
                except Exception:
                    pass
        st.markdown('</div>', unsafe_allow_html=True)




    def _build_multi_period_table(code: str, periods: list, dark: bool = False) -> None:
        """用户多选报告期后，合并成一个「Excel 式」业绩对比表并支持 CSV 导出。"""
        st.markdown('<div class="sf-card">' + _section_header("多期业绩对比表", "用户自选报告期 · 同一表格", "📊", level=2), unsafe_allow_html=True)
        if not periods:
            _empty_info("请在上方「多期对比」中至少选择一个报告期。")
            st.markdown('</div>', unsafe_allow_html=True)
            return
        _recs = []
        for _p in sorted(set(periods)):
            try:
                _df = _fr_cached_report(_p)
                _row = _fr_filter_by_code(_df, code)
                if _row is None or getattr(_row, "empty", True):
                    continue
                _r = _row.iloc[0]
                _mg = fr_compute_margins(_r)
                _recs.append({
                    "报告期": fr_period_label(_p),
                    "每股收益": _fr_fmt(_r.get("每股收益")),
                    "营业总收入": _fr_fmt(_r.get("营业总收入")),
                    "营收同比%": _fr_fmt(_r.get("营收同比%")),
                    "净利润": _fr_fmt(_r.get("净利润")),
                    "净利润同比%": _fr_fmt(_r.get("净利润同比%")),
                    "ROE%": _fr_fmt(_r.get("ROE%")),
                    "毛利率%": fr_fmt_pct(_mg["毛利率%"]),
                    "净利率%": fr_fmt_pct(_mg["净利率%"]),
                    "披露时间": _r.get("披露时间", "—"),
                })
            except Exception:
                continue
        if not _recs:
            _empty_info("所选报告期暂无该股业绩数据（尚未披露或接口受限）。")
        else:
            _disp = pd.DataFrame(_recs)
            st.dataframe(_disp, width="stretch", hide_index=True, height=min(60 + 36 * len(_recs), 540))
            try:
                _csv = _disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    "⬇️ 导出多期业绩对比表 CSV", data=_csv,
                    file_name=f"多期业绩对比_{code}.csv", mime="text/csv",
                    key=f"fr_multi_csv_{code}",
                )
            except Exception:
                pass
        st.markdown('</div>', unsafe_allow_html=True)

    @safe_fragment
    def fragment_financial_report(ticker):
        """个股财报（随搜索框联动，独立于「生成分析」）：横向历史对比 / 业绩报表 / 业绩预告 / 披露日历 / 财务三表。

    数据层复用 modules.fundflow（东财业绩报表/预告/披露日历）+ fetcher.get_financial（新浪三表）。
    业绩配色：红=同比增长为正（改善）、绿=为负（下滑），与价格「绿涨红跌」不同，已在页内注明。

    v3 改版（2026-09-13）：
      · 报告期选择器由「6 项长下拉」瘦身为**折叠 + 两行 pill 按钮**（默认年报/最新期）；
      · 新增「📈 业绩横向对比」区块：≥3 年主要指标的柱状+折线图 + 下方「展开分析」明细表。
    """
        if not ticker:
            return
        code = str(ticker).zfill(6)
        sf_card("📑 个股财报", "搜索个股后即时展示其横向业绩对比、业绩报表、业绩预告、披露日历与财务三表（利润表/资产负债表/现金流量表）。数据来源：东方财富 / 新浪财经。", icon="📑")

        # ── 📈 业绩横向对比（放在首位：≥3 年主要指标柱状+折线 + 展开分析）──────────
        _build_perf_history_section(code, dark)

        # ── 报告期选择区（折叠 + selectbox，改回之前熟悉的下拉模板）─────────────────
        with st.expander("🗓️ 报告期选择", expanded=True, key=f"fr_sel_exp_{ticker}"):
            st.caption("选择财报报告期查看该股对应期数据；也可多选报告期生成 Excel 式对比表。")
            _period_options = list(PERIODS_FIN.keys())
            # 默认选择最新年报
            _default_idx = 0
            for _i, _k in enumerate(_period_options):
                if "年报" in _k and (_k.startswith(str(datetime.now().year)) or _k.startswith(str(datetime.now().year - 1))):
                    _default_idx = _i
                    break
            period_label = st.selectbox(
                "单期报告期", options=_period_options, index=_default_idx,
                key=f"fr_period_{ticker}",
                help="用于下方「业绩报表 / 业绩预告 / 披露日历」",
            )
            period = PERIODS_FIN[period_label]

            # 多期对比：允许用户勾选多个报告期
            _multi_options = [fr_period_label(f"{y}{q}") for y in range(datetime.now().year, datetime.now().year - 6, -1)
                              for q in ("1231", "0630", "0930", "0331")]
            multi_selected = st.multiselect(
                "多期对比（生成 Excel 式表格）", options=_multi_options, default=[],
                key=f"fr_multi_{ticker}",
                help="选择多个报告期，合并显示该股在所有选中期的业绩数据并支持导出",
            )
            # 把标签转回 period 代码
            _label_to_period = {fr_period_label(f"{y}{q}"): f"{y}{q}"
                                for y in range(datetime.now().year, datetime.now().year - 6, -1)
                                for q in ("1231", "0630", "0930", "0331")}
            multi_periods = [_label_to_period.get(_lbl) for _lbl in multi_selected if _label_to_period.get(_lbl)]

        # ── 业绩报表（东财，按代码过滤）──
        st.markdown('<div class="sf-card">' + _section_header("业绩报表", "每股收益 · 营收 · 净利润 · ROE", "📊", level=2), unsafe_allow_html=True)
        st.caption(f"当前报告期：**{period_label}**")
        try:
            rep_df = _fr_cached_report(period)
        except Exception as e:
            rep_df = None
            xc_handle_error("业绩报表加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
        row = _fr_filter_by_code(rep_df, code)
        if row is None or row.empty:
            _empty_info(f"未查询到「{code}」在「{period_label}」的业绩报表（可能尚未披露或代码不匹配）。")
        else:
            _r = row.iloc[0]
            yoy_col, yoy_txt = _fr_color_yoy(_r.get("净利润同比%"))
            rev_col, rev_txt = _fr_color_yoy(_r.get("营收同比%"))
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1:
                st.metric("每股收益", _fr_fmt(_r.get("每股收益")), delta_color="off")
            with mc2:
                st.metric("营业总收入", _fr_fmt(_r.get("营业总收入")), delta_color="off", help="单位：元")
            with mc3:
                st.metric("净利润", _fr_fmt(_r.get("净利润")), delta_color="off", help="单位：元")
            with mc4:
                st.metric("ROE%", _fr_fmt(_r.get("ROE%")), delta_color="off")
            _mg = fr_compute_margins(_r)
            mc5, mc6 = st.columns(2)
            with mc5:
                st.metric("毛利率", fr_fmt_pct(_mg["毛利率%"]), delta_color="off", help="毛利 / 营业总收入（东财业绩报表）")
            with mc6:
                st.metric("净利率", fr_fmt_pct(_mg["净利率%"]), delta_color="off", help="净利润 / 营业总收入")
            st.markdown(
                f"<div style='font-size:13px;line-height:1.9;color:var(--txt2);margin:6px 0 10px;'>"
                f"净利润同比 <b style='color:{yoy_col};'>净利润 {yoy_txt}</b>　|　"
                f"营收同比 <b style='color:{rev_col};'>营收 {rev_txt}</b>　|　"
                f"披露时间：<b style='color:var(--txt);'>{_r.get('披露时间', '—')}</b></div>",
                unsafe_allow_html=True,
            )
            st.caption("💡 业绩配色：红=同比增长为正（改善），绿=为负（下滑）；与价格「绿涨红跌」不同，仅针对业绩增速。")
            try:
                st.dataframe(row, width="stretch", hide_index=True, height=220)
            except Exception as e:
                xc_warn_box(f"业绩报表明细渲染失败：{e}")
            try:
                _csv = row.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    "⬇️ 导出业绩报表 CSV", data=_csv,
                    file_name=f"业绩报表_{code}_{period}.csv", mime="text/csv",
                    key=f"fr_csv_{ticker}_{period}",
                )
            except Exception:
                pass
        st.markdown('</div>', unsafe_allow_html=True)

        # ── 多期业绩对比表（用户自选多期）──
        _build_multi_period_table(code, multi_periods, dark=dark)

        # ── 业绩预告（best-effort，按代码过滤）──
        with st.expander("🔮 业绩预告（best-effort）", expanded=False, key=f"fr_fc_{ticker}"):
            try:
                fc_df = _fr_cached_forecast(period)
            except Exception:
                fc_df = None
            fc_row = _fr_filter_by_code(fc_df, code)
            if fc_row is None or fc_row.empty:
                _empty_info(f"「{code}」暂无「{period_label}」业绩预告（接口不稳定或尚未发布）。")
            else:
                try:
                    st.dataframe(fc_row, width="stretch", hide_index=True, height=300)
                except Exception as e:
                    xc_warn_box(f"业绩预告渲染失败：{e}")

        # ── 披露日历（best-effort，按代码过滤）──
        with st.expander("🗓️ 披露日历（best-effort）", expanded=False, key=f"fr_dc_{ticker}"):
            mcol1, mcol2 = st.columns(2)
            with mcol1:
                market = st.selectbox("市场", ["沪市", "深市", "沪深京"], index=0, key=f"fr_dc_mkt_{ticker}")
            with mcol2:
                period_str = st.selectbox("报告期（披露）", ["2025年报", "2024年报", "2023年报"], index=0, key=f"fr_dc_per_{ticker}")
            try:
                dc_df = _fr_cached_disclosure(market=market, period_str=period_str)
            except Exception:
                dc_df = None
            dc_row = _fr_filter_by_code(dc_df, code)
            if dc_row is None or dc_row.empty:
                _empty_info(f"「{code}」在「{market}·{period_str}」披露日历中未匹配到记录（接口仅支持年报）。")
            else:
                try:
                    st.dataframe(dc_row, width="stretch", hide_index=True, height=300)
                except Exception as e:
                    xc_warn_box(f"披露日历渲染失败：{e}")

        # ── 财务三表（新浪，best-effort）──
        st.markdown('<div class="sf-card">' + _section_header("财务三表", "利润表 · 资产负债表 · 现金流量表", "🧾", level=2), unsafe_allow_html=True)
        st.caption("数据来源：新浪财经财务三表（取最新 8 期，金额已自动换算为 亿/万）。接口偶发不稳定时单个表会单独提示。")
        # ── 多期趋势（利润表：营业总收入 / 净利润，单位亿元）──
        try:
            _tf = _build_financial_trend_fig(code, dark)
            if _tf is not None:
                st.plotly_chart(_tf, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False})
        except Exception:
            pass
        for _rt, _lbl in (("income", "利润表"), ("balance", "资产负债表"), ("cash", "现金流量表")):
            with st.expander(f"📄 {_lbl}", expanded=False, key=f"fr_tbl_{_rt}_{ticker}"):
                try:
                    _tdf = _fr_cached_financial(code, _rt)
                except Exception:
                    _tdf = None
                if _tdf is None or (hasattr(_tdf, "empty") and _tdf.empty):
                    _empty_info(f"「{code}」{_lbl}暂不可用（接口返回空或网络受限）。可前往「基本面分析」页查看更完整的多期财务分析。")
                    continue
                try:
                    _tdf_disp = fr_format_financial_df(_tdf)
                    st.dataframe(_tdf_disp, width="stretch", hide_index=True, height=360)
                    _csv = _tdf.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                    st.download_button(
                        f"⬇️ 导出{_lbl} CSV", data=_csv,
                        file_name=f"{_lbl}_{code}.csv", mime="text/csv",
                        key=f"fr_tbl_csv_{_rt}_{ticker}",
                    )
                except Exception as e:
                    xc_warn_box(f"{_lbl}渲染失败：{e}")
        st.markdown('</div>', unsafe_allow_html=True)


    fragment_stock_videos(ticker)
    fragment_financial_report(ticker)
    st.markdown('---')
    st.page_link('pages/22_基本面分析.py', label='→ 去 基本面分析（估值/业绩/行业对比）', icon='🏛️')
    st.page_link('pages/24_个股研究.py', label='→ 去 个股研究（K线与技术面）', icon='📈')


def render_stock_picker() -> None:
    import logging
    import streamlit as st
    import pandas as pd
    from datetime import datetime, timedelta

    logger = logging.getLogger(__name__)

    from modules.ui_theme import _theme_is_dark, sf_card, sf_metric
    from modules.page_utils import render_standard_page, get_fetcher
    from modules.ui_theme import sf_card, sf_metric
    from modules.ui_kit import xc_kpi_grid
    from modules.cleaner import DataCleaner
    # K 线图统一交互配置（隐藏工具栏图标、十字光标），与全站规范一致
    from modules.starfield_theme import KLINE_CHART_CONFIG
    # Visualizer 延迟到函数内导入（节省 ~0.95s plotly+matplotlib 链）
    from modules.search_ui import stock_search_input
    from modules.technical import full_analysis as technical_full_analysis
    from modules.signal import SignalEngine
    from modules.linear_trends import plot_normalized_multi
    from modules.session import (
        api_kline, api_intraday,
        api_post, api_add_junk_stock, api_user_score, api_save_user_score,
        get_user, trading_autorefresh,
    )

    from modules.page_guard import safe_fragment
    from modules.page_widgets import UP, is_trading_now

    from modules.ui_kit import xc_error_box, xc_handle_error, xc_info_banner, xc_success_box, xc_warn_box, info_banner
    render_standard_page(title="股票选取", icon="🎯")

    # ── T-230：图表/指标教学说明统一收进折叠区（主区留给参数与图表）──
    with st.expander("📘 图表与指标说明", expanded=False):
        st.markdown(
            "- **K 线图**：含所选 MA 均线；开启「标注事件」后，利好事件标红↑、利空事件标绿↓（A股红涨绿跌惯例）。"
            "可拖动平移或框选缩放；**双击 K 线柱**弹出当日分时图。\n"
            "- **量化指标**：RSI>70 超买 / <30 超卖；MACD 柱>0 多头动能；KDJ J>100 超买、<0 超卖；"
            "BOLL 位置 = 收盘价在布林带内的相对高度。"
        )

    # 支持从龙虎榜/股票池点击跳转：URL ?pick_stock=600519
    _qp_code = st.query_params.get("pick_stock")
    if _qp_code:
        st.session_state["pick_stock_confirmed"] = str(_qp_code)
        st.session_state["pick_stock_query"] = str(_qp_code)
        try:
            del st.query_params["pick_stock"]
        except Exception as e:  # 部分 Streamlit 版本不允许删 query param，可忽略但要留痕
            logger.debug("[11_股票选取] 清理 pick_stock query param 失败: %s", e)

    trading_autorefresh(key="pick_autorefresh")

    fetcher = get_fetcher()
    user = get_user() or {}


    def _fmt_md(d) -> str:
        try:
            return pd.Timestamp(d).strftime("%m-%d")
        except Exception:
            s = str(d)
            if len(s) >= 10:
                return s[:10][5:]
            return s


    def _norm_code(c: str) -> str:
        if not c:
            return ""
        c = str(c).strip().lower()
        for p in ("sh", "sz", "bj"):
            if c.startswith(p):
                c = c[len(p):]
        return c[-6:] if len(c) > 6 else c


    # ── 用户打分组件（Batch8 #271：独立 fragment，交互只重跑本块，提升响应速度）──
    @safe_fragment
    def _render_user_score(ticker: str, stock_label: str) -> None:
        sf_card("⭐ 用户打分", "")
        # 已有分数缓存到 session_state，避免每次交互都回源后端
        _ss_key = f"_score_{ticker}"
        if _ss_key not in st.session_state:
            st.session_state[_ss_key] = api_user_score(ticker)
        existing_score = st.session_state[_ss_key]

        st.caption("评分范围 **0–100**，越高代表越看好。拖动滑块直接选择，无法输入越界值。")

        # 用 slider 做输入：用户只能选 0–100 之间的整数，彻底解决越界输入问题
        with st.form(key=f"score_form_{ticker}"):
            sc1, sc2 = st.columns([0.55, 0.45])
            with sc1:
                score_val = st.slider(
                    "您对该股票的评分（0–100）",
                    min_value=0, max_value=100,
                    value=existing_score if existing_score is not None else 50,
                    step=1,
                    key=f"pick_user_score_{ticker}",
                    help="拖动选择 0–100 之间的整数。",
                )
            with sc2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                submitted = st.form_submit_button("💾 保存评分", width="stretch")

            if submitted:
                # slider 返回值已强制在 [0, 100] 内
                score_val = int(score_val)
                res = api_save_user_score(ticker, score_val, stock_label)
                # ⚠️ 兜底：后端异常时 api_save_user_score 可能返回 None，res.get 会抛 AttributeError
                if isinstance(res, dict) and res.get("status") == "ok":
                    st.session_state[_ss_key] = score_val
                    # 清除旧 slider key，确保下次渲染从已保存值重新初始化（避免残留 50）
                    st.session_state.pop(f"pick_user_score_{ticker}", None)
                    xc_success_box(f"✅ 评分已保存：{score_val} 分")
                else:
                    _msg = res.get("message", "未知错误") if isinstance(res, dict) else "未知错误"
                    xc_error_box(f"保存失败：{_msg}")


    # ═══════════════════════════════════════════════════════════════
    # 参数设置（原行情看板迁入；嵌入合并页时自动改写入主区域，避免覆盖导航）
    # ═══════════════════════════════════════════════════════════════
    from modules.widgets import sidebar_target
    with sidebar_target():
        sf_card("参数设置", "")
        ticker = stock_search_input(
            label="股票搜索",
            key="pick_stock",
            default="600519",
            placeholder="输入代码或名称搜索，如：600519 / 贵州茅台 / GZMT / 茅台",
        )
        _nm = fetcher.get_name_only(ticker)
        if not _nm:
            try:
                _nm = fetcher.get_stock_name(ticker)
            except Exception:
                _nm = None
        stock_label = f"{ticker} {_nm}" if _nm else ticker

        today = datetime.now().date()
        _qc1, _qc2, _qc3, _qc4 = st.columns(4)
        if _qc1.button("近30天", key="pick_q_30", width="stretch"):
            st.session_state["pick_start"] = today - timedelta(days=30)
            st.session_state["pick_end"] = today
            st.rerun()
        if _qc2.button("近90天", key="pick_q_90", width="stretch"):
            st.session_state["pick_start"] = today - timedelta(days=90)
            st.session_state["pick_end"] = today
            st.rerun()
        if _qc3.button("近半年", key="pick_q_180", width="stretch"):
            st.session_state["pick_start"] = today - timedelta(days=180)
            st.session_state["pick_end"] = today
            st.rerun()
        if _qc4.button("近1年", key="pick_q_365", width="stretch"):
            st.session_state["pick_start"] = today - timedelta(days=365)
            st.session_state["pick_end"] = today
            st.rerun()

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input(
                "起始日期",
                value=st.session_state.get("pick_start", today - timedelta(days=180)),
                max_value=today,
                key="pick_start_input",
                help="K 线回测的起始日期，最长可回溯约 1 年；区间越短，长周期指标可能为空。",
            )
        with col_d2:
            end_date = st.date_input(
                "截止日期",
                value=st.session_state.get("pick_end", today),
                max_value=today,
                min_value=start_date,
                key="pick_end_input",
                help="K 线回测的结束日期，默认今天；与起始日期共同决定分析区间。",
            )
        if "pick_start" in st.session_state and st.session_state["pick_start"] != start_date:
            st.session_state["pick_start"] = start_date
        if "pick_end" in st.session_state and st.session_state["pick_end"] != end_date:
            st.session_state["pick_end"] = end_date

        days_span = (end_date - start_date).days
        if days_span < 30:
            st.caption(f"⚠️ 当前区间 {days_span} 天太短，部分长周期指标可能为空")
        elif days_span > 1000:
            st.caption(f"⚠️ 当前区间 {days_span} 天过长，图表可能加载较慢")
        else:
            st.caption(f"📅 已选区间：{start_date} → {end_date}（共 {days_span} 天）")

        kline_period = st.radio(
            "K线周期",
            options=["daily", "weekly", "monthly"],
            format_func=lambda x: {"daily": "日K", "weekly": "周K", "monthly": "月K"}[x],
            index=["daily", "weekly", "monthly"].index(st.session_state.get("pick_period", "daily")),
            key="pick_period",
            horizontal=True,
            help="日K 适合短线研判，周K/月K 更适合观察中长期趋势。",
        )

        ma_select = st.multiselect(
            "均线",
            options=[5, 10, 20, 30, 60, 90, 120, 200, 250],
            default=[5, 20, 60],
            key="pick_ma_select",
            help="勾选需要在 K 线图上叠加显示的移动平均线周期（如 5/20/60 日）。",
        )
        custom_ma = st.text_input("自定义均线（用英文逗号分隔，如 30,90）", placeholder="例如：30,90", key="pick_custom_ma",
                                 help="输入自定义均线周期，逗号分隔，例如 13,34,55；与上方勾选合并生效。")
        custom_windows = []
        _invalid_ma = []
        if custom_ma:
            for x in custom_ma.split(","):
                _tok = x.strip()
                try:
                    val = int(_tok)
                    if val > 0:
                        custom_windows.append(val)
                except ValueError:
                    _invalid_ma.append(_tok)
        if _invalid_ma:
            xc_warn_box(f"⚠️ 已忽略无效均线周期：{', '.join(_invalid_ma)}（仅接受正整数，如 30,90）")
        ma_windows = sorted(set(ma_select + custom_windows))

        st.markdown("---")
        if st.button("🔄", help="强制刷新数据：清除本地缓存，重新拉取最新行情", key="sel_force_refresh"):
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            if kline_period == "daily":
                cache_key = f"daily_{ticker}_{start_str}_{end_str}_qfq"
                pattern = f"daily_{ticker}_%"
            else:
                cache_key = f"kline_{kline_period}_{ticker}_{start_str}_{end_str}_qfq"
                pattern = f"kline_{kline_period}_{ticker}_%"
            # clear_cache 返回实际删除行数；此处只清精确匹配的那条
            deleted = fetcher.clear_cache(table_name="daily_cache", cache_key=cache_key)
            # 再按前缀批量清同标的的其他日期区间缓存。
            # ⚠️ 此处原为 ``except Exception: pass``，失败后仍无条件报"缓存已清除"，
            # 会让用户拿着旧缓存当新数据。改为记录日志 + 向用户明示失败。
            batch_failed = False
            conn = fetcher._get_conn()
            try:
                cur = conn.execute("DELETE FROM daily_cache WHERE cache_key LIKE ?", (pattern,))
                deleted += max(cur.rowcount or 0, 0)
                conn.commit()
            except Exception as e:  # noqa: BLE001 - 需兜底并向用户明示，不能静默
                batch_failed = True
                logger.warning("[11_股票选取] 前缀批量清缓存失败（缓存可能未清空）: %s", e)
            finally:
                conn.close()
            if batch_failed:
                xc_warn_box(
                    "部分缓存未能清除",
                    hint="数据库可能被占用，本次刷新仍可能命中旧缓存，可稍后重试。",
                )
            elif deleted:
                xc_success_box(f"缓存已清除（{deleted} 条），正在刷新...")
            else:
                xc_success_box("本地无对应缓存，正在从数据源拉取...")
            # 击穿 @st.cache_data 内的 _cached_kline（参数变化强制重算并重新取数）
            st.session_state["_pick_kline_nonce"] = int(st.session_state.get("_pick_kline_nonce", 0)) + 1
            st.rerun()

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    period_label = {"daily": "日K线", "weekly": "周K线", "monthly": "月K线"}[kline_period]


    # ═══════════════════════════════════════════════════════════════
    # 标题栏 + 同轴操作按钮
    # ═══════════════════════════════════════════════════════════════
    hc1, hc2, hc3 = st.columns([0.4, 0.3, 0.3])
    with hc1:
        sf_card("🎯 股票选取", "")
    with hc2:
        _ticker_ok = bool(ticker and str(ticker).strip())
        if st.button("➕ 加入自选股", width="stretch", key="pick_add_watch",
                     disabled=not _ticker_ok, help="请先在左侧选择一只股票" if not _ticker_ok else "将当前股票加入自选池"):
            sc, body = api_post("/api/watchlist", {"stock_code": ticker})
            # ⚠️ 兜底：api_post 网络失败时 body 可能为 None，原 else 分支 body.get 会抛 AttributeError
            _msg = body.get("message") if isinstance(body, dict) else ""
            if sc in (200, 201) or "已在" in _msg:
                xc_success_box("✅ 已加入自选股")
            else:
                xc_error_box(f"加入失败：{_msg or '未知错误'}")
    with hc3:
        if st.button("🗑️ 加入垃圾股", width="stretch", key="pick_add_junk",
                     disabled=not _ticker_ok, help="请先在左侧选择一只股票" if not _ticker_ok else "将当前股票标记为垃圾股"):
            body = api_add_junk_stock(ticker)
            # ⚠️ 兜底：api_add_junk_stock 失败时 body 可能为 None，直接 body.get 会抛 AttributeError
            msg = body.get("message", "") if isinstance(body, dict) else ""
            if "成功" in msg or "已在" in msg:
                xc_success_box("✅ 已加入垃圾股")
            else:
                xc_error_box(f"加入失败：{msg or '未知错误'}")


    # ═══════════════════════════════════════════════════════════════
    # K 线图
    # ═══════════════════════════════════════════════════════════════
    st.markdown("---")
    @st.cache_data(show_spinner=False, ttl=300)
    def _cached_kline(ticker, start, end, period, nonce: int = 0):
        # nonce 仅用于「强制刷新」时击穿 @st.cache_data 缓存（参数变化即重算重取数）
        # 1) 优先后端聚合接口（含复权）
        try:
            recs = api_kline(ticker, start=start, end=end, period=period)
        except Exception:
            recs = None
        if recs is not None:
            return pd.DataFrame(recs)
        # 2) 回退本地 fetcher 直连数据源
        try:
            df = fetcher.get_kline(ticker, start=start, end=end, period=period)
        except Exception:
            df = None
        # 统一返回 DataFrame（空则用空表，交由上层「空数据」兜底），绝不在区块内抛未捕获异常
        return df if df is not None else pd.DataFrame()


    @st.cache_data(show_spinner=False, ttl=300)
    def _period_end_to_trading_day(ticker, start, end, period_date):
        """周/月线视图下，点击柱子的日期是周期末(可能落在周末/节假日)，
    映射到最近的一个实际交易日，确保双击弹分时能取到数据。"""
        try:
            from modules.calendar_utils import nearest_trading_day
            dd = _cached_kline(ticker, start, end, "daily")
            if dd is None or dd.empty:
                return str(period_date)[:10]
            dts = pd.to_datetime(dd["date"]).dt.strftime("%Y-%m-%d").tolist()
            return nearest_trading_day(period_date, dts)
        except Exception as e:
            logger.debug("[11_股票选取] 周期末日→交易日映射失败，回退原日期: %s", e)
        return str(period_date)[:10]


    @st.cache_data(show_spinner=False, ttl=120)
    def _cached_intraday_for_date(ticker, target_date):
        """获取指定交易日的分时数据（用于K线双击回看历史分时）。"""
        try:
            _df, _pc, _dt = fetcher.get_stock_intraday_sina(ticker, trade_date=target_date)
            if _df is not None and not _df.empty:
                return _df, _pc, _dt
        except Exception as e:  # 用户双击 K 线却看不到分时 → 必须留下原因
            logger.warning("[11_股票选取] 历史分时拉取失败 %s@%s: %s", ticker, target_date, e)
        return None


    @st.cache_data(show_spinner=False, ttl=300)
    def _cached_intraday(ticker):
        """个股分时数据：优先后端 /api/intraday，回退本地 fetcher。返回 (df, prev_close, trade_date) 或 None。"""
        try:
            rec = api_intraday(ticker)
            if rec and isinstance(rec.get("records"), list) and rec["records"]:
                return pd.DataFrame(rec["records"]), rec.get("prev_close"), rec.get("trade_date")
        except Exception as e:  # 后端不可用时本就走本地回退，属预期，降级 debug
            logger.debug("[11_股票选取] 后端 /api/intraday 不可用，回退本地 fetcher: %s", e)
        try:
            _df, _pc, _dt = fetcher.get_stock_intraday_sina(ticker)
            if _df is not None and not _df.empty:
                return _df, _pc, _dt
        except Exception as e:  # 两条路径都失败 → 界面将显示"无分时"，必须留下原因
            logger.warning("[11_股票选取] 分时数据本地回退亦失败 %s: %s", ticker, e)
        return None


    @safe_fragment
    def fragment_kline_pick(ticker, stock_label, df, kline_period, period_label, start_str, end_str,
                            view_start, view_count, ma_windows, drag_mode, events_df, show_events):
        """行情看板 K 线卡片独立 fragment：双击 K 线弹分时的 on_select="rerun" 只重跑本片段，
    不再触发整页重跑（事件面板 / 区间统计等不受影响）。"""
        from modules.visualizer import Visualizer
        fig = Visualizer.candlestick(df, title=f"{stock_label} {period_label}",
                                     ma_windows=ma_windows, show_volume=True,
                                     start_idx=view_start, n_show=view_count,
                                     dragmode=drag_mode,
                                     events=events_df if show_events else None)
        _pk_event = st.plotly_chart(fig, width="stretch", key="pick_kline_chart",
                                    on_select="rerun", config=KLINE_CHART_CONFIG)
        _pdbl_key = "pick_dblclick"
        _pnow = datetime.now().timestamp()
        _pclick_date = None
        if _pk_event and hasattr(_pk_event, "selection") and _pk_event.selection.points:
            _ppt = _pk_event.selection.points[0]
            _pxval = _ppt.get("x", _ppt.get("pointIndex", None))
            if _pxval is not None:
                try:
                    _pidx = int(_pxval)
                    if 0 <= _pidx < len(df):
                        _pclick_date = str(df.iloc[_pidx]["date"])[:10]
                except (ValueError, TypeError, IndexError):
                    if isinstance(_pxval, str) and len(_pxval) >= 10:
                        _pclick_date = _pxval[:10]
        if _pclick_date:
            if kline_period != "daily":
                _pclick_date = _period_end_to_trading_day(ticker, start_str, end_str, _pclick_date)
            _pprev = st.session_state.get(_pdbl_key)
            if (_pprev and _pnow - _pprev[0] < 0.5 and _pprev[1] == _pclick_date):
                st.session_state["pick_intraday_target"] = _pclick_date
                st.session_state[_pdbl_key] = None
            else:
                st.session_state[_pdbl_key] = (_pnow, _pclick_date)
        _ptgt = st.session_state.get("pick_intraday_target")
        if _ptgt:
            with st.expander(f"📈 {_ptgt} 分时走势（双击K线弹出）", expanded=True):
                st.caption("💡 双击上方 K 线任意柱子可切换到该日分时。")
                try:
                    _pdi = _cached_intraday_for_date(ticker, _ptgt)
                    if _pdi is not None:
                        _pdf, _ppc, _pdt = _pdi
                        _pdfig = Visualizer.intraday(_pdf, prev_close=_ppc,
                                                     title=f"{stock_label} 分时（{_pdt}）")
                        st.plotly_chart(_pdfig, width="stretch", key=f"pick_dbl_intra_{_ptgt}", config={"displaylogo": False, "responsive": True})
                    else:
                        info_banner(f"📭 {_ptgt} 暂无分时数据。")
                except Exception as _pde:
                    xc_handle_error("分时加载失败", str(_pde)[:80], hint="请稍后重试，或检查网络与数据源连接")
                if st.button("✕ 关闭", key="pick_close_intra"):
                    del st.session_state["pick_intraday_target"]
                    st.rerun(scope="fragment")


    @safe_fragment("分时图自动刷新", run_every=300 if is_trading_now() else None)
    def _fragment_intraday(ticker: str, stock_label: str) -> None:
        """分时图区块：独立 fragment，仅在交易时段每 5 分钟自动刷新一次。

    与整页 trading_autorefresh（默认 1 分钟）解耦，避免分时图随整页无意义重算；
    数据走 _cached_intraday（ttl=300，与 5 分钟刷新节奏对齐）。
    """
        show_intraday = st.checkbox("📈 显示分时图", value=True, key="pick_show_intraday",
                                    help="展示该股票当日/最近交易日分时走势（价格线+均价+昨收基准，红涨绿跌）。交易时段每5分钟自动刷新。")
        if not show_intraday:
            return
        _intra = _cached_intraday(ticker)
        if _intra is not None:
            from modules.visualizer import Visualizer  # lazy import: 仅渲染时加载
            _idf, _ipc, _idate = _intra
            _ifig = Visualizer.intraday(_idf, prev_close=_ipc,
                                        title=f"{stock_label} 分时（{_idate}）")
            st.plotly_chart(_ifig, width="stretch", key="pick_intraday_chart", config={"displaylogo": False, "responsive": True})
            _status = "（每5分钟自动刷新中）" if is_trading_now() else "（非交易时段，已暂停刷新）"
            st.caption("📈 分时图：白线为当日价格走势，橙点为均价；基准虚线为昨收。红涨绿跌（A股惯例）。" + _status)
        else:
            info_banner("📭 暂无分时数据（非交易时段或数据源暂不可用）。")


    @st.cache_data(show_spinner=False, ttl=600)
    def _load_stock_events(ticker):
        """加载该股票的事件库（本地 SignalEngine 事件表，按代码过滤）。失败返回空表。"""
        try:
            engine = SignalEngine()
            ev = engine._load_events()
            if ev is None or ev.empty:
                return pd.DataFrame()
            code = str(ticker).zfill(6)
            if "ticker" in ev.columns:
                ev = ev[ev["ticker"].astype(str).str.zfill(6) == code]
            keep = [c for c in ("date", "title", "type") if c in ev.columns]
            return ev[keep] if keep else ev
        except Exception:
            return pd.DataFrame()


    sf_card(f"{stock_label} {period_label}", "")
    df = None
    data_ok = False

    try:
        df = _cached_kline(ticker, start_str, end_str, kline_period,
                           nonce=int(st.session_state.get("_pick_kline_nonce", 0)))
        if df is None or df.empty:
            xc_warn_box("⚠️ 暂未获取到该股票最新数据，正在使用历史快照。请稍后刷新页面。")
        else:
            df = DataCleaner.full_pipeline(df)
            data_ok = True
            st.caption(f"✅ 数据获取成功: {len(df)} 行 {_fmt_md(df['date'].iloc[0])}~{_fmt_md(df['date'].iloc[-1])}")

            latest = df.iloc[-1]
            latest_close = float(latest.get('close') or 0.0)
            # ⚠️ 兜底：change_pct 可能为 None（数据不足），f"{None:.2f}" 会抛 TypeError 致整块 K 线渲染失败
            _chg_pct = latest.get('change_pct')
            _chg_pct = 0.0 if _chg_pct is None else float(_chg_pct)
            total_vol = df['volume'].sum()
            # 加法式数字格式化：成交量按 亿/万 本地化展示（数据不变，仅改显示单位）。
            if total_vol >= 1e8:
                _vol_disp = f"{total_vol/1e8:.2f}亿股"
            elif total_vol >= 1e4:
                _vol_disp = f"{total_vol/1e4:.0f}万股"
            else:
                _vol_disp = f"{total_vol:.0f}股"
            xc_kpi_grid([
                {"label": "最新收盘价", "value": f"¥{latest_close:.2f}",
                 "delta": f"{_chg_pct:.2f}%", "delta_dir": "up" if _chg_pct >= 0 else "down"},
                {"label": "区间最高", "value": f"¥{df['high'].max():.2f}"},
                {"label": "区间最低", "value": f"¥{df['low'].min():.2f}"},
                {"label": "区间总成交量", "value": _vol_disp},
            ])

            n = len(df)
            if n > 20:
                max_count = min(250, n)
                default_count = min(120, n)
                default_start = max(0, n - default_count)
                if "pick_view_count" not in st.session_state:
                    st.session_state["pick_view_count"] = default_count
                if "pick_view_pos" not in st.session_state:
                    st.session_state["pick_view_pos"] = default_start
                if st.session_state["pick_view_count"] > max_count:
                    st.session_state["pick_view_count"] = max_count
                view_count = st.slider("显示 K 线数量", min_value=20, max_value=max_count, step=5,
                                       key="pick_view_count",
                                       help="控制图中展示的 K 线根数；数据量大时可聚焦近期行情。")
                max_start = max(0, n - view_count)
                if st.session_state["pick_view_pos"] > max_start:
                    st.session_state["pick_view_pos"] = max_start
                if max_start >= 1:
                    view_start = st.slider("显示位置（起始）", min_value=0, max_value=max_start, step=1,
                                           key="pick_view_pos")
                else:
                    view_start = 0
            else:
                view_start = 0
                view_count = n

            # 鼠标拖拽：平移 / 区域缩放（控制 K 线图 dragmode）
            drag_mode = st.radio(
                "鼠标拖拽",
                options=["pan", "zoom"],
                format_func=lambda x: {"pan": "平移", "zoom": "区域缩放"}[x],
                index=0, key="pick_dragmode", horizontal=True,
                help="平移：拖动查看不同区间；区域缩放：框选放大某一段。",
            )

            # 事件标注开关（利好↑红 / 利空↓绿），默认开启
            show_events = st.checkbox("📌 标注事件（利好↑红 / 利空↓绿）", value=True, key="pick_show_events",
                                      help="在 K 线上叠加重大事件标注：利好标红、利空标绿。")
            events_df = None
            if show_events:
                with st.spinner("加载事件…"):
                    events_df = _load_stock_events(ticker)

            # 当前可见区间统计
            vis = df.iloc[view_start:view_start + view_count]
            v_high = float(vis["high"].max())
            v_low = float(vis["low"].min())
            v_first = float(vis["close"].iloc[0])
            v_last = float(vis["close"].iloc[-1])
            v_chg = (v_last - v_first) / v_first * 100 if v_first else 0.0
            v_amp = (v_high - v_low) / v_first * 100 if v_first else 0.0
            v_avg = float(vis["close"].mean())
            st.caption(
                f"📊 当前显示区间：最高 ¥{v_high:.2f} / 最低 ¥{v_low:.2f} / "
                f"区间涨幅 {v_chg:+.2f}% / 振幅 {v_amp:.2f}% / 均价 ¥{v_avg:.2f}"
            )

            # 当前可见区间 K 线导出 CSV（新增功能：便于离线分析 / 二次加工）
            v_csv = vis.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "⬇️ 导出当前区间 K 线 CSV",
                data=v_csv,
                file_name=f"{ticker}_{kline_period}_{view_start + 1}-{view_start + view_count}.csv",
                mime="text/csv",
                key="pick_kline_csv",
                help="导出当前「显示位置 / 显示数量」框定区间的 K 线数据（含 OHLCV）",
            )

            # ── 图表渲染区（Visualizer 延迟导入：仅用户选股后执行）──
            from modules.visualizer import Visualizer  # lazy: ~0.95s saved on pages without chart action

            # ── 分时图（独立 fragment，交易时段每 5 分钟自动刷新）──
            _fragment_intraday(ticker, stock_label)

            fragment_kline_pick(ticker, stock_label, df, kline_period, period_label, start_str, end_str,
                                view_start, view_count, ma_windows, drag_mode, events_df, show_events)

            # 事件面板（可折叠）：列出可见区间内事件，便于对照 K 线标注
            if show_events and events_df is not None and not events_df.empty:
                vis_dates = pd.to_datetime(df.iloc[view_start:view_start + view_count]["date"])
                if not vis_dates.empty:
                    lo, hi = vis_dates.min(), vis_dates.max()
                    ev_view = events_df.copy()
                    ev_view["_dt"] = pd.to_datetime(ev_view["date"])
                    ev_view = ev_view[(ev_view["_dt"] >= lo) & (ev_view["_dt"] <= hi)]
                    if not ev_view.empty:
                        with st.expander(f"📌 本区间事件（{len(ev_view)} 条）", expanded=False):
                            disp = ev_view[["date", "title", "type"]].copy() if "type" in ev_view.columns else ev_view[["date", "title"]].copy()
                            disp = disp.sort_values("date")
                            st.dataframe(disp, width="stretch", hide_index=True, height=400)

            # 叠加上证基准对比（归一化多线，可选）
            if st.checkbox("📈 叠加上证基准对比（归一化）", value=False, key="pick_show_bench",
                           help="将个股与上证指数归一化到同一起点（100），直观对比个股相对大盘的强弱。"):
                with st.spinner("加载上证基准…"):
                    idx_df = fetcher.get_index("000001", start=start_str, end=end_str)
                if idx_df is not None and not idx_df.empty:
                    idx_df = idx_df.copy()
                    idx_df["date"] = pd.to_datetime(idx_df["date"]).dt.strftime("%Y-%m-%d")
                    stock_part = df[["date", "close"]].copy()
                    stock_part["date"] = pd.to_datetime(stock_part["date"]).dt.strftime("%Y-%m-%d")
                    merged = stock_part.merge(
                        idx_df[["date", "close"]], on="date", how="inner", suffixes=("_s", "_i"))
                    if len(merged) >= 2:
                        merged = merged.rename(columns={"close_s": stock_label, "close_i": "上证指数"})
                        bfig = plot_normalized_multi(
                            merged, names_map={stock_label: stock_label, "上证指数": "上证指数"},
                            colors_map={stock_label: UP, "上证指数": "#7c5cff"},
                            title="个股 vs 上证基准（归一化起点=100）",
                            dark_mode=_theme_is_dark(), date_range=None, ma_periods=(),
                            selected=None, mode="normalized", show_baseline=True,
                            show_cross=False, show_drawdown=False, ma_type="sma")
                        st.plotly_chart(bfig, width="stretch", config={"displaylogo": False, "responsive": True, "displayModeBar": False},
                                        key="pick_bench")
                    else:
                        info_banner("区间内与上证基准无重合交易日，跳过对比。")
                else:
                    info_banner("上证基准数据获取失败，跳过对比。")
    except Exception as e:
        xc_handle_error("K 线加载异常", str(e)[:80], hint="请稍后刷新页面重试，或切换其它周期 / 区间")


    # ═══════════════════════════════════════════════════════════════
    # 技术面分析 + 用户打分
    # ═══════════════════════════════════════════════════════════════
    if data_ok and df is not None:
        sf_card("🧭 技术面分析", "")
        try:
            profile = SignalEngine().technical_profile(df)
            short, mid, long, composite = profile["short"], profile["mid"], profile["long"], profile["composite"]
            latest = df.iloc[-1]
            r5 = float(latest.get("return_5d", 0.0) or 0.0)
            r20 = float(latest.get("return_20d", 0.0) or 0.0)
            r60 = 0.0
            if len(df) >= 61:
                r60 = (float(df["close"].iloc[-1]) / float(df["close"].iloc[-61]) - 1) * 100

            analysis = technical_full_analysis(df)
            trend = analysis.get("trend", {})
            momentum = analysis.get("momentum", {})
            volume_info = analysis.get("volume", {})
            patterns = analysis.get("patterns", []) or []

            _score_cards = [
                {"label": "① 短期（5日）", "value": f"{'+' if r5 >= 0 else ''}{r5:.2f}%",
                 "delta": f"{short}分", "delta_dir": "up" if r5 >= 0 else "down",
                 "meta": "🟢 强势" if short >= 65 else ("🔴 偏弱" if short <= 40 else "⚪ 中性")},
                {"label": "② 中期（20日）", "value": f"{'+' if r20 >= 0 else ''}{r20:.2f}%",
                 "delta": f"{mid}分", "delta_dir": "up" if r20 >= 0 else "down",
                 "meta": "🟢 强势" if mid >= 65 else ("🔴 偏弱" if mid <= 40 else "⚪ 中性")},
                {"label": "③ 长期（60日）", "value": f"{'+' if r60 >= 0 else ''}{r60:.2f}%",
                 "delta": f"{long}分", "delta_dir": "up" if r60 >= 0 else "down",
                 "meta": "🟢 强势" if long >= 65 else ("🔴 偏弱" if long <= 40 else "⚪ 中性")},
                {"label": "④ 综合评分", "value": f"{composite}/100",
                 "delta": "看多" if composite >= 65 else ("看空" if composite <= 40 else "观望"),
                 "delta_dir": "up" if composite >= 65 else ("down" if composite <= 40 else "flat"),
                 "meta": "短/中/长期加权"},
            ]
            xc_kpi_grid(_score_cards)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown("**均线 / 趋势**")
                if "error" not in trend:
                    st.markdown(f"{'🟢' if trend.get('trend_score', 50) >= 60 else ('🔴' if trend.get('trend_score', 50) <= 40 else '⚪')} **{trend.get('arrangement', '—')}**")
                    st.caption(trend.get("trend_label", ""))
                else:
                    st.caption(trend.get("error", "数据不足"))
            with c2:
                st.markdown("**动量 / 涨跌幅**")
                if "error" not in momentum:
                    rets = momentum.get("returns", {}) or {}
                    # ⚠️ 兜底：returns 内 '5日'/'20日' 可能为 None，直接 f"{None:+.2f}" 抛 TypeError
                    _r5 = rets.get("5日") or 0
                    _r20 = rets.get("20日") or 0
                    st.markdown(f"**{momentum.get('momentum_label', '—')}**")
                    st.metric("5日涨幅", f"{_r5:+.2f}%", delta=f"20日 {_r20:+.2f}%", delta_color="inverse")
                else:
                    st.caption(momentum.get("error", "数据不足"))
            with c3:
                st.markdown("**量能分析**")
                if "error" not in volume_info:
                    # ⚠️ 兜底：vol_ratio/vol_change_pct 可能为 None，避免 f-string 格式化崩溃
                    ratio = volume_info.get("vol_ratio") or 1.0
                    _vol_chg_pct = volume_info.get("vol_change_pct") or 0
                    st.markdown(f"**{volume_info.get('volume_price_label', '—')}**")
                    st.metric("量比(今/5日均)", f"{ratio:.2f}x", delta=f"{_vol_chg_pct:+.1f}%", delta_color="inverse")
                else:
                    st.caption(volume_info.get("error", "数据不足"))
            with c4:
                st.markdown("**K线形态（近10日）**")
                if patterns:
                    for p in patterns[:5]:
                        icon = "🟢" if p.get("bias") == "看涨" else ("🔴" if p.get("bias") == "看跌" else "⚪")
                        # ⚠️ 兜底：pattern 的 date 可能为 None / 坏串，pd.Timestamp(None) 会抛 TypeError
                        _pdate = p.get("date")
                        try:
                            date_str = pd.Timestamp(_pdate).strftime("%m-%d") if _pdate is not None else "—"
                        except Exception:
                            date_str = "—"
                        st.markdown(f"{icon} `{date_str}` {p.get('name', '')}")
                else:
                    st.caption("未识别到明显形态")

            if composite >= 65:
                verdict = "🟢 整体偏多，可关注"
            elif composite >= 40:
                verdict = "⚪ 多空平衡，观望为主"
            else:
                verdict = "🔴 整体偏空，谨慎参与"
            xc_info_banner(f"**综合评分 {composite}/100** · 短期 {short} / 中期 {mid} / 长期 {long} · {verdict}")

            # ── 📊 量化指标（RSI / MACD / KDJ / BOLL） ──
            sf_card("📊 量化指标", "")

            def _calc_quant_indicators(d: pd.DataFrame) -> dict:
                close = pd.to_numeric(d["close"], errors="coerce")
                high = pd.to_numeric(d["high"], errors="coerce")
                low = pd.to_numeric(d["low"], errors="coerce")
                out = {}
                # RSI(14)
                try:
                    delta = close.diff()
                    gain = delta.clip(lower=0).rolling(14).mean()
                    loss = (-delta.clip(upper=0)).rolling(14).mean()
                    rs = gain / loss.replace(0, 1e-9)
                    out["rsi"] = float((100 - 100 / (1 + rs)).iloc[-1])
                except Exception:
                    out["rsi"] = None
                # MACD(12,26,9)
                try:
                    ema12 = close.ewm(span=12, adjust=False).mean()
                    ema26 = close.ewm(span=26, adjust=False).mean()
                    dif = ema12 - ema26
                    dea = dif.ewm(span=9, adjust=False).mean()
                    out["dif"] = float(dif.iloc[-1])
                    out["dea"] = float(dea.iloc[-1])
                    out["macd"] = float((dif.iloc[-1] - dea.iloc[-1]) * 2)
                except Exception:
                    out["dif"] = out["dea"] = out["macd"] = None
                # KDJ(9,3,3)
                try:
                    low9 = low.rolling(9).min()
                    high9 = high.rolling(9).max()
                    rsv = (close - low9) / (high9 - low9).replace(0, 1e-9) * 100
                    k = rsv.ewm(com=2, adjust=False).mean()
                    dd = k.ewm(com=2, adjust=False).mean()
                    out["k"] = float(k.iloc[-1])
                    out["d"] = float(dd.iloc[-1])
                    out["j"] = float(3 * k.iloc[-1] - 2 * dd.iloc[-1])
                except Exception:
                    out["k"] = out["d"] = out["j"] = None
                # BOLL(20,2) 位置
                try:
                    mid_b = close.rolling(20).mean()
                    std_b = close.rolling(20).std()
                    upper_b = mid_b + 2 * std_b
                    lower_b = mid_b - 2 * std_b
                    rng = (upper_b.iloc[-1] - lower_b.iloc[-1]) or 1e-9
                    out["boll_pct"] = float((close.iloc[-1] - lower_b.iloc[-1]) / rng * 100)
                except Exception:
                    out["boll_pct"] = None
                return out

            qi = _calc_quant_indicators(df)
            _qcards = []
            rsi = qi.get("rsi")
            rsi_tag = "超买" if rsi >= 70 else ("超卖" if rsi <= 30 else "中性")
            _qcards.append({"label": "RSI(14)",
                            "value": f"{rsi:.1f}" if rsi is not None else "—",
                            "delta": rsi_tag if rsi is not None else "", "delta_dir": "flat"})
            macd = qi.get("macd")
            _macd_meta = f"DIF {qi['dif']:+.3f} / DEA {qi['dea']:+.3f}" if macd is not None else ""
            _qcards.append({"label": "MACD 柱",
                            "value": f"{macd:+.3f}" if macd is not None else "—",
                            "delta": ("金叉/多头" if macd >= 0 else "死叉/空头") if macd is not None else "",
                            "delta_dir": "flat", "meta": _macd_meta})
            k, d, j = qi.get("k"), qi.get("d"), qi.get("j")
            kdj_tag = "超买" if j >= 100 else ("超卖" if j <= 0 else "中性")
            _qcards.append({"label": "KDJ",
                            "value": f"K{k:.0f} D{d:.0f}" if k is not None else "—",
                            "delta": f"J{j:.0f} · {kdj_tag}" if k is not None else "",
                            "delta_dir": "flat"})
            bp = qi.get("boll_pct")
            pos = "近上轨" if bp >= 80 else ("近下轨" if bp <= 20 else "轨道中部")
            _qcards.append({"label": "BOLL 位置",
                            "value": f"{bp:.0f}%" if bp is not None else "—",
                            "delta": pos if bp is not None else "", "delta_dir": "flat"})
            xc_kpi_grid(_qcards)

            # 用户打分（独立 fragment，交互只重跑本块，提升响应速度）
            _render_user_score(ticker, stock_label)
        except Exception as e:
            xc_handle_error("技术面分析失败", e, hint="请稍后重试，或检查网络与数据源连接")
