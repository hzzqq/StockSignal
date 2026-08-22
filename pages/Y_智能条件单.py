"""
页面 Y：智能条件单
────────────────
新增两类筛选 / 触发条件（用户需求）：
  1. 融资买入额达到多少 → 买入 / 卖出
       - 单只股票融资买入额 ≥ 阈值（万元）
       - 全市场合计融资买入额 ≥ 阈值（亿元）
  2. 沿 5 日均线上涨 / 下跌的破位
       - ma5_break_up  ：现价上穿 5 日均线（沿 MA5 上涨突破）→ 触发动作
       - ma5_break_down：现价跌破 5 日均线（沿 MA5 下跌破位）→ 触发动作

触发后由后端统一下单（经 broker.execute_order，含风控 + live 护栏），
并写 real_orders 流水。调度器在交易时段后台扫描；也可手动触发一轮扫描。
"""
import json
from datetime import datetime, timedelta
import streamlit as st
from modules.page_utils import render_standard_page
from modules.session import api_get, api_post, api_put, api_delete, trading_autorefresh
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast
from modules.page_guard import safe_fragment
dark = render_standard_page(title='智能条件单', icon='🤖', caption='融资买入额阈值 / 5 日均线突破破位 → 自动下单（交易时段后台扫描 + 可手动触发）')
st.caption('⚠️ 数据仅供参考，不构成投资建议；触发后按账户实盘/模拟模式真实下单')
try:
    from modules.fundflow import _ensure_proxy_and_ssl
    _ensure_proxy_and_ssl()
except Exception:
    pass
TRIGGER_LABELS = {'margin_stock': '💰 单股融资买入额 ≥ 阈值（万元）', 'margin_market': '🌐 全市场融资买入额 ≥ 阈值（亿元）', 'ma5_break_up': '📈 沿 5 日均线上涨突破（上穿 MA5）', 'ma5_break_down': '📉 沿 5 日均线下跌破位（跌破 MA5）'}
STATUS_LABELS = {'pending': '⏳ 待触发', 'triggered': '⚡ 已触发待成交', 'filled': '✅ 已成交', 'failed': '❌ 触发失败', 'cancelled': '🚫 已撤销', 'expired': '⌛ 已过期'}
with st.expander('💡 触发类型说明', expanded=False, key='cond_help'):
    st.markdown('- **单股融资买入额**：抓该股最近披露日的融资买入额，达到设定「万元」阈值即触发（融资余额高 = 资金做多意愿强）。\n- **全市场融资买入额**：沪+深两市融资买入额合计，达到设定「亿元」阈值即触发（衡量全市场杠杆资金热度）。\n- **5 日均线突破 / 破位**：昨收 ≤ 昨 MA5 且现价上穿今日 MA5 → 上涨突破；昨收 ≥ 昨 MA5 且现价跌破今日 MA5 → 下跌破位。`确认幅度%`=0 表示只要穿越即触发。\n\n**触发后做什么？** 按你设定的「动作（买/卖）+ 数量」，经账户的风控与券商通道真实下单，并写入订单流水。')
with st.expander('➕ 新建条件单', expanded=True, key='new_cond_exp'):
    c1, c2 = st.columns([1.4, 1])
    with c1:
        cond_code = stock_search_input(label='触发后交易的股票', key='cond_stock', default='600519')
        st.caption('注意：即使选「全市场融资」类型，也需指定触发后买入/卖出的具体股票。')
    with c2:
        trigger_type = st.selectbox('触发条件', list(TRIGGER_LABELS.keys()), format_func=lambda x: TRIGGER_LABELS[x])
        action = st.selectbox('触发动作', ['buy', 'sell'], format_func=lambda x: '买入 ▲' if x == 'buy' else '卖出 ▼')
    p1, p2, p3 = st.columns(3)
    params = {}
    with p1:
        if trigger_type in ('margin_stock', 'margin_market'):
            unit = '万元' if trigger_type == 'margin_stock' else '亿元'
            threshold = st.number_input(f'融资买入额阈值（{unit}）', min_value=0.0, step=0.1, value=5000.0 if trigger_type == 'margin_stock' else 1000.0, help='达到该阈值即触发')
            params['threshold'] = float(threshold)
        else:
            confirm_pct = st.number_input('突破确认幅度 (%)', min_value=0.0, max_value=10.0, step=0.1, value=0.0, help='0 = 只要穿越即触发；>0 需突破该幅度才确认')
            params['confirm_pct'] = float(confirm_pct)
    with p2:
        quantity = st.number_input('下单数量 (股)', min_value=100, step=100, value=100, help='须为 100 的整数倍')
    with p3:
        default_expire = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        expire_date = st.date_input('到期日（可选）', value=datetime.strptime(default_expire, '%Y-%m-%d'), help='超过该日期未触发则自动失效')
        expire_str = expire_date.strftime('%Y-%m-%d') if expire_date else None
    if st.button('🚀 创建条件单', type='primary', use_container_width=True, key='cond_create'):
        if not cond_code:
            st.error('请选择股票')
        elif quantity <= 0 or quantity % 100 != 0:
            st.error('数量须为 100 的整数倍')
        else:
            name = ''
            try:
                from modules.fetcher import StockFetcher
                name = StockFetcher().get_name_only(cond_code) or ''
            except Exception:
                pass
            payload = {'stock_code': cond_code, 'stock_name': name, 'trigger_type': trigger_type, 'action': action, 'trigger_params': params, 'quantity': int(quantity), 'expire_date': expire_str}
            sc, body = api_post('/api/cond-orders', payload)
            if sc == 200 and isinstance(body, dict) and (body.get('status') == 'ok'):
                _toast('条件单已创建')
                st.rerun()
            else:
                msg = body.get('message', '创建失败') if isinstance(body, dict) else '创建失败'
                st.error(f'❌ {msg}')
st.divider()
col_scan, col_info = st.columns([1, 2])
with col_scan:
    if st.button('🔍 立即扫描一轮', type='primary', use_container_width=True, key='cond_scan'):
        sc, body = api_post('/api/cond-orders/scan')
        if sc == 200 and isinstance(body, dict):
            stats = body.get('data') or {} if body.get('status') == 'ok' else {}
            st.success(f"扫描完成：检查 {stats.get('checked', 0)} · 触发 {stats.get('triggered', 0)} · 成交 {stats.get('filled', 0)} · 失败 {stats.get('failed', 0)} · 过期 {stats.get('expired', 0)}")
        else:
            st.error('扫描失败')
with col_info:
    st.caption('调度器会在交易时段（周一至周五 9:15-11:35 / 12:55-15:05）自动扫描；此按钮可手动触发全量扫描。')

@st.fragment
def fragment_cond_list():
    trading_autorefresh(key='cond_list_autorefresh')
    sc, body = api_get('/api/cond-orders')
    if sc != 200 or not isinstance(body, dict) or body.get('status') != 'ok':
        st.error('⚠️ 条件单加载失败')
        if st.button('🔄 重试', key='cond_retry'):
            st.rerun(scope='fragment')
        return
    rows = body.get('data', []) or []
    st.markdown(f'#### 📋 条件单列表（{len(rows)}）')
    if not rows:
        _empty_info('暂无条件单。点击上方「新建条件单」添加（融资阈值 / 5 日均线破位）。')
        return
    _only_active = st.checkbox('只看生效中', key='cond_only_active', help='仅显示 pending 且 active=True 的条件单')
    if _only_active:
        rows = [r for r in rows if r.get('status') == 'pending' and r.get('active')]
    for idx, c in enumerate(rows):
        cid = c.get('id') or f'idx{idx}'
        code = c.get('stock_code', '')
        name = c.get('stock_name') or code
        ttype = c.get('trigger_type', '')
        tparams = c.get('trigger_params') or {}
        action = c.get('action', 'buy')
        status = c.get('status', 'pending')
        active = bool(c.get('active'))
        if ttype in ('margin_stock', 'margin_market'):
            unit = '万元' if ttype == 'margin_stock' else '亿元'
            desc = f"融资买入额 ≥ **{float(tparams.get('threshold', 0)):g} {unit}**"
        else:
            cp = float(tparams.get('confirm_pct', 0) or 0)
            desc = f"{('上穿' if ttype == 'ma5_break_up' else '跌破')} 5 日均线（确认 {cp:g}%）"
        status_txt = STATUS_LABELS.get(status, status)
        status_cls = {'pending': 'sf-pill mid', 'triggered': 'sf-pill up', 'filled': 'sf-pill up', 'failed': 'sf-pill down', 'cancelled': 'sf-pill down', 'expired': 'sf-pill mid'}.get(status, 'sf-pill mid')
        with st.container(border=True):
            cm1, cm2, cm3, cm4, cm5 = st.columns([1.5, 2.2, 1, 0.9, 0.9])
            with cm1:
                st.markdown(f'**{name}** `{code}`')
                st.caption(f'{TRIGGER_LABELS.get(ttype, ttype)}')
            with cm2:
                st.markdown(f'{desc}')
                st.caption(f"触发后：{('买入▲' if action == 'buy' else '卖出▼')} {int(c.get('quantity') or 0)} 股" + (f" · 到期 {c.get('expire_date')}" if c.get('expire_date') else ''))
            with cm3:
                st.markdown(f"<span class='{status_cls}'>{status_txt}</span>", unsafe_allow_html=True)
                if c.get('triggered_info'):
                    st.caption(f"ℹ️ {c.get('triggered_info')}")
            with cm4:
                if status == 'pending':
                    label = '停用' if active else '启用'
                    if st.button(label, key=f'cond_tog_{cid}', use_container_width=True):
                        api_put(f'/api/cond-orders/{cid}', {'active': not active})
                        st.rerun(scope='fragment')
                else:
                    st.caption('—')
            with cm5:
                if st.button('🗑️', key=f'cond_del_{cid}', use_container_width=True):
                    api_delete(f'/api/cond-orders/{cid}')
                    _toast('已删除')
                    st.rerun(scope='fragment')
fragment_cond_list()
if st.button('↑ 回到顶部', key='cond_back_to_top'):
    st.markdown("<script>window.scrollTo({top:0,behavior:'smooth'});</script>", unsafe_allow_html=True)