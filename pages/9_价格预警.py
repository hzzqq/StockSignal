"""
页面9：自选股多维预警
支持四类预警：
  - 价格（price）：涨破/跌破目标价（实时比价）
  - 技术形态（pattern）：个股出现指定技术形态时触发
  - 成交量异动（volume）：当日量比 ≥ 阈值时触发
  - 公告（announcement）：近期新闻/公告含指定关键词时触发
触发检查在页面访问时于前端执行（与原有价格预警一致）；数据不足时标记为「待验证」。
"""
import json
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time as _time
from threading import Lock as _Lock
from concurrent.futures import ThreadPoolExecutor
import logging
logger = logging.getLogger(__name__)
from modules.page_utils import render_standard_page, get_fetcher
import modules.scroll_nav as sn
from modules.session import api_get, api_post, api_put, api_delete, api_quote, api_kline, trading_autorefresh, safe_switch_page
from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast
from modules.page_guard import safe_fragment
from modules.format_helpers import safe_float, to_float
import streamlit.components.v1 as components
from modules.fundflow import _ensure_proxy_and_ssl
_ensure_proxy_and_ssl()

def _fmt_rel(ts):
    """把绝对时间戳转成相对时间（刚刚 / X分钟前 / X小时前 / X天前）。"""
    from datetime import datetime as _dt
    try:
        if isinstance(ts, str):
            s = ts.strip().replace('Z', '')
            for _fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y-%m-%dT%H:%M'):
                try:
                    ts = _dt.strptime(s, _fmt)
                    break
                except ValueError:
                    continue
            else:
                return s
        elif hasattr(ts, 'to_pydatetime'):
            ts = ts.to_pydatetime()
        sec = (_dt.now() - ts).total_seconds()
        if sec < 60:
            return '刚刚'
        if sec < 3600:
            return f'{int(sec // 60)}分钟前'
        if sec < 86400:
            return f'{int(sec // 3600)}小时前'
        return f'{int(sec // 86400)}天前'
    except Exception:
        return str(ts) if ts is not None else ''

def validate_alert_condition(kind, value, value2=None):
    """纯函数：校验预警条件输入，返回 (ok, error)。

    支持类型（与页面实际数值输入对应）：
      - 'threshold'：数值阈值，必须可解析为数字且 > 0
        （对应价格预警目标价 / 成交量异动量比阈值）。
      - 'percent'：百分比，必须可解析为数字且落在 0~100 之间。
      - 'cross'：需要 value 与 value2 两个数值，任一缺失或非数字即拒绝。
    统一使用 safe_float 做安全解析，避免非数字输入导致页面崩溃。
    """

    def _num(x):
        if x is None:
            return None
        s = str(x).strip()
        if s == '':
            return None
        return safe_float(s, default=None)
    if kind == 'threshold':
        v = _num(value)
        if v is None:
            return (False, '阈值必须为大于 0 的数字')
        if v <= 0:
            return (False, '阈值必须大于 0')
        return (True, None)
    elif kind == 'percent':
        v = _num(value)
        if v is None:
            return (False, '百分比必须为数字')
        if v < 0 or v > 100:
            return (False, '百分比须落在 0~100 之间')
        return (True, None)
    elif kind == 'cross':
        if value2 is None:
            return (False, '需要第二个数值')
        a = _num(value)
        b = _num(value2)
        if a is None or b is None:
            return (False, '两个数值都必须为有效数字')
        return (True, None)
    return (False, f'不支持的预警类型：{kind}')
dark = render_standard_page(title='自选股多维预警', icon='🔔', caption='价格 / 技术形态 / 成交量异动 / 公告 四类预警；触发状态为页面访问时实时比价与扫描结果。')
st.caption('⚠️ 数据仅供参考，不构成投资建议')
with st.expander('💡 使用说明', expanded=False, key='alert_help_exp'):
    st.markdown('**四类预警怎么用？**\n- 💲 **价格预警**：设置目标价与「涨破/跌破」条件，页面访问时实时比价触发。\n- 📐 **技术形态预警**：选择形态后，页面扫描该股日线，命中即触发。\n- 📊 **成交量异动预警**：当日量比 ≥ 设定阈值时触发（放量信号）。\n- 📢 **公告预警**：近 20 条新闻/公告出现关键词时触发。\n\n**常见问题**\n- *触发是准实时的吗？* 触发在页面访问时于前端检测，保持本页打开并定期刷新可更快捕捉异动。\n- *为什么显示「待验证」？* 行情或日线数据不足时无法判定，稍后刷新重试。\n- *如何持续盯盘？* 关注右上角「🔔 市场异动」铃铛，并保持本页在浏览器中打开。')
fetcher = get_fetcher()
PATTERN_OPTIONS = ['均线金叉', '均线死叉', 'MACD金叉', 'MACD死叉', 'KDJ金叉', 'KDJ死叉', '底背离', '顶背离', '放量突破', '缩量回调', '一阳穿多线', '十字星', '红三兵', '乌云盖顶', '锤头线', '倒锤头']
ALERT_TYPE_LABEL = {'price': '💲 价格', 'pattern': '📐 技术形态', 'volume': '📊 成交量异动', 'announcement': '📢 公告'}

def _current_price(code: str):
    rt = api_quote(code)
    if isinstance(rt, dict):
        v = to_float(rt.get('current'))
        if v is not None:
            return v
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict):
            v = to_float(q.get('current'))
            if v is not None:
                return v
    except Exception:
        pass
    return None

def _norm(s):
    return ''.join(str(s).lower().split())
_EVAL_TTL = 120.0
_eval_cache = {}
_eval_cache_lock = _Lock()

def _eval_pattern(code, pattern_name):
    """扫描个股日线，判断是否出现指定形态。返回 (triggered, detail)。
    结果按 (code, pattern_name) 记忆体缓存 2 分钟（跨自动刷新复用），降低重复网络请求。"""
    _key = ('pat', code, pattern_name)
    _now = _time.time()
    with _eval_cache_lock:
        _hit = _eval_cache.get(_key)
    if _hit and _now - _hit[0] < _EVAL_TTL:
        return _hit[1]
    _trig, _detail = (False, '日线数据不足')
    try:
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        recs = api_kline(code, start=start, end=end)
        if not recs:
            recs = fetcher.get_daily(code, start=start, end=end)
        df = pd.DataFrame(recs) if recs else None
        df = DataCleaner.full_pipeline(df)
        if df is None or df.empty or len(df) < 20:
            _trig, _detail = (False, '日线数据不足')
        else:
            pats = full_analysis(df).get('patterns', []) or []
            names = [_norm(p.get('name', '')) for p in pats]
            chosen = _norm(pattern_name)
            hit = [n for n in names if chosen in n or n in chosen]
            if hit:
                _trig, _detail = (True, f'检测到：{hit[0]}')
            else:
                _trig, _detail = (False, '未出现该形态')
    except Exception as e:
        _trig, _detail = (False, f'扫描失败：{e}')
    _res = (_trig, _detail)
    with _eval_cache_lock:
        _eval_cache[_key] = (_now, _res)
    return _res

def _eval_volume(code, threshold):
    """当日量比 ≥ 阈值触发。返回 (triggered, detail)。
    结果按 (code, threshold) 记忆体缓存 2 分钟（跨自动刷新复用），避免重复计算。"""
    _key = ('vol', code, threshold)
    _now = _time.time()
    with _eval_cache_lock:
        _hit = _eval_cache.get(_key)
    if _hit and _now - _hit[0] < _EVAL_TTL:
        return _hit[1]
    _trig, _detail = (False, '成交量数据不足')
    try:
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        recs = api_kline(code, start=start, end=end)
        if not recs:
            recs = fetcher.get_daily(code, start=start, end=end)
        df = pd.DataFrame(recs) if recs else None
        df = DataCleaner.full_pipeline(df)
        if df is None or df.empty or 'volume' not in df.columns or (len(df) < 6):
            _trig, _detail = (False, '成交量数据不足')
        else:
            vols = pd.to_numeric(df['volume'], errors='coerce').dropna()
            if len(vols) < 6:
                _trig, _detail = (False, '成交量数据不足')
            else:
                today = float(vols.iloc[-1])
                prev = vols.iloc[:-1].tail(5)
                ma5 = float(prev.mean()) if len(prev) else float(vols.iloc[-2])
                if ma5 <= 0:
                    _trig, _detail = (False, '基准量为0')
                else:
                    ratio = today / ma5
                    _trig, _detail = (ratio >= threshold, f'量比 {ratio:.2f}×（阈值 {threshold:.2f}×）')
    except Exception as e:
        _trig, _detail = (False, f'计算失败：{e}')
    _res = (_trig, _detail)
    with _eval_cache_lock:
        _eval_cache[_key] = (_now, _res)
    return _res

def _eval_announcement(code, keyword):
    """近期新闻/公告含关键词触发。返回 (triggered, detail)。"""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return (False, '新闻源暂无数据')
        text_cols = [c for c in df.columns if any((k in str(c) for k in ('标题', '内容', '新闻', '摘要')))]
        if not text_cols:
            text_cols = list(df.columns)
        text = ' '.join((str(df[c].iloc[i]) for c in text_cols for i in range(min(len(df), 20))))
        if keyword in text:
            return (True, f'新闻中出现「{keyword}」')
        return (False, f'近 {min(len(df), 20)} 条新闻未出现「{keyword}」')
    except Exception:
        return (False, '新闻源不可用')

def _eval_alert(a):
    """按类型评估预警。返回 (triggered_bool, detail_text)。"""
    atype = a.get('alert_type', 'price')
    code = a['stock_code']
    if atype == 'price':
        price = _current_price(code)
        if price is None:
            return (None, '行情不可用')
        tp = float(a.get('target_price') or 0)
        cond = a.get('condition', 'above')
        triggered = price >= tp if cond == 'above' else price <= tp
        return (triggered, f'现价 {price:.2f} / 目标 {tp:.2f}')
    elif atype == 'pattern':
        pname = ''
        try:
            pname = json.loads(a.get('params') or '{}').get('pattern_name', '')
        except Exception:
            pass
        if not pname:
            return (None, '未配置形态')
        return _eval_pattern(code, pname)
    elif atype == 'volume':
        vr = 2.0
        try:
            vr = float(json.loads(a.get('params') or '{}').get('volume_ratio', 2.0))
        except Exception:
            pass
        return _eval_volume(code, vr)
    elif atype == 'announcement':
        kw = ''
        try:
            kw = json.loads(a.get('params') or '{}').get('keyword', '')
        except Exception:
            pass
        if not kw:
            return (None, '未配置关键词')
        return _eval_announcement(code, kw)
    return (None, '未知类型')

def _eval_alert_parallel(alerts):
    """并行评估多条预警，避免串行网络请求阻塞页面。

    走共享有界池（modules.fetch_parallel），整批带硬边界。
    ⚠️ 不可用 `with ThreadPoolExecutor(...)` + result(timeout=)：退出 with 时的
    shutdown(wait=True) 会阻塞等慢任务跑完，超时保护被完全抵消——某条公告类
    预警卡住就会拖死整页 fragment（历史 bug）。
    """
    if not alerts:
        return []
    from modules.fetch_parallel import fetch_many
    n_workers = min(8, max(1, len(alerts)))
    raw = fetch_many([(i, lambda a=a: _eval_alert(a)) for i, a in enumerate(alerts)], max_workers=n_workers, timeout=15)
    return [raw.get(i) if raw.get(i) is not None else (False, '评估超时或失败') for i in range(len(alerts))]
with st.expander('➕ 新建预警', expanded=False, key='new_alert_exp'):
    atype = st.radio('预警类型', options=list(ALERT_TYPE_LABEL.keys()), format_func=lambda x: ALERT_TYPE_LABEL[x], horizontal=True, key='new_atype')
    code = stock_search_input(label='选择股票', key='alert_stock', default='600519')
    params = {}
    if atype == 'price':
        c1, c2 = st.columns(2)
        with c1:
            condition = st.selectbox('触发条件', ['above', 'below'], format_func=lambda x: '涨破 ▲' if x == 'above' else '跌破 ▼', help='涨破 ▲：现价 ≥ 目标价时触发；跌破 ▼：现价 ≤ 目标价时触发。')
        with c2:
            target = st.number_input('目标价格 (元)', min_value=0.0, step=0.01, value=0.0, help='触发比价的参考价位；价格涨破或跌破该值即触发预警。')
    elif atype == 'pattern':
        pattern_name = st.selectbox('技术形态', PATTERN_OPTIONS, index=0)
        params = {'pattern_name': pattern_name}
        st.caption('页面访问时扫描该股日线，若检测到所选形态即标记触发。')
    elif atype == 'volume':
        vr = st.number_input('量比阈值（当日成交量 / 近5日均量）', min_value=0.1, step=0.1, value=2.0)
        params = {'volume_ratio': float(vr)}
        st.caption('当日量比 ≥ 阈值时触发（如 2.0 表示放量一倍）。')
    elif atype == 'announcement':
        kw = st.text_input('关键词（如：增持、回购、中标、减持）', placeholder='输入触发关键词，如：增持、回购、中标、减持')
        params = {'keyword': kw}
        st.caption('近期新闻/公告标题或内容包含该关键词即触发。')
    submitted = st.button('保存预警', type='primary', use_container_width=True)
    if submitted:
        _price_ok, _price_err = validate_alert_condition('threshold', target) if atype == 'price' else (True, None)
        _vol_ok, _vol_err = validate_alert_condition('threshold', vr) if atype == 'volume' else (True, None)
        if not code:
            st.error('请选择股票')
        elif atype == 'price' and (not _price_ok):
            st.error(_price_err or '目标价格必须大于 0')
        elif atype == 'volume' and (not _vol_ok):
            st.error(_vol_err or '量比阈值必须大于 0')
        elif atype == 'announcement' and (not kw):
            st.error('请填写关键词')
        else:
            name = fetcher.get_name_only(code)
            body_payload = {'stock_code': code, 'stock_name': name, 'alert_type': atype, 'params': params}
            if atype == 'price':
                body_payload['condition'] = condition
                body_payload['target_price'] = float(target)
            sc, body = api_post('/api/price-alerts', body_payload)
            if sc == 200 and isinstance(body, dict) and (body.get('status') == 'ok'):
                _toast('预警已创建')
                _rec = st.session_state.setdefault('_alert_recent_codes', [])
                if code not in _rec:
                    _rec.insert(0, code)
                st.session_state['_alert_recent_codes'] = _rec[:8]
                st.rerun()
            else:
                msg = body.get('message', '创建失败') if isinstance(body, dict) else '创建失败'
                st.error(f'❌ {msg}')
_recent = st.session_state.get('_alert_recent_codes', [])
if _recent:
    st.markdown('**🕘 最近浏览**')
    _rc_cols = st.columns(min(len(_recent), 6))
    for _i, _rc in enumerate(_recent[:6]):
        with _rc_cols[_i]:
            if st.button(f'📈 {_rc}', key=f'alert_recent_{_rc}', use_container_width=True):
                st.session_state['pick_stock_confirmed'] = _rc
                st.session_state['pick_stock_query'] = _rc
                safe_switch_page('pages/个股研究.py')

@safe_fragment('预警列表')
def fragment_alerts():
    trading_autorefresh(key='alert_autorefresh')
    try:
        sc, body = api_get('/api/price-alerts')
    except Exception as _e:
        st.error(f'⚠️ 加载失败，请稍后重试（{_e}）')
        if st.button('🔄 重试', key='alert_list_retry'):
            st.rerun(scope='fragment')
        return
    if sc != 200 or not isinstance(body, dict) or body.get('status') != 'ok':
        st.error('⚠️ 加载失败，请稍后重试')
        if st.button('🔄 重试', key='alert_list_retry'):
            st.rerun(scope='fragment')
        return
    alerts = body.get('data', []) or []
    if not alerts:
        _empty_info('暂无预警。点击上方「新建预警」添加（支持价格 / 技术形态 / 成交量异动 / 公告）。')
        st.caption('💡 小提示：先把想盯的标的加进「自选股监控」，再回来建预警更顺手。')
        if st.button('➕ 立即新建预警', key='alert_empty_new'):
            st.session_state['new_alert_exp'] = True
            st.rerun(scope='app')
        st.info('🔔 通知机制：触发检测在**页面访问时**于前端实时比价/扫描；若要持续接收异动，可关注右上角「🔔 市场异动」铃铛（系统级异动提醒），并保持本页或持仓页在浏览器中打开。')
    else:
        st.markdown(f'#### 共 {len(alerts)} 条预警（页面访问时实时检测）')
        st.caption('数据来源：实时行情（新浪财经 / 东方财富）、新闻公告（东方财富）')
        _filter = st.text_input('🔍 搜索预警（代码 / 名称 / 类型）', key='filter_alerts', help='按代码、名称或预警类型（price/pattern/volume/announcement）纯前端过滤。')
        if _filter:
            _fk = _norm(_filter)
            alerts = [a for a in alerts if _fk in _norm(f"{a.get('stock_code', '')} {a.get('stock_name', '')} {a.get('alert_type', '')} {a.get('params', '')}")]
        _alert_fav_set = st.session_state.get('_alert_fav_set', set())
        _show_fav_only = st.checkbox('⭐ 只看收藏', key='alert_fav_only', help='仅显示已加星标的预警。')
        if _show_fav_only:
            alerts = [a for i, a in enumerate(alerts) if (a.get('id') or f'idx{i}') in _alert_fav_set]
        with st.spinner('正在检测预警触发状态…'):
            eval_results = _eval_alert_parallel(alerts)
        _notified_ids = st.session_state.setdefault('_alert_notified_ids', set())
        _notify_msgs = []
    for idx, a in enumerate(alerts):
        aid = a.get('id') or f'idx{idx}'
        atype = a.get('alert_type', 'price')
        triggered, detail = eval_results[idx] if idx < len(eval_results) else (False, '评估异常')
        code = a.get('stock_code', '') or ''
        try:
            _fname = fetcher.get_name_only(code)
        except Exception:
            _fname = ''
        display_name = _fname or a.get('stock_name') or code
        if atype == 'price':
            cond_txt = '涨破 ▲' if a.get('condition') == 'above' else '跌破 ▼'
            try:
                _tp = float(a.get('target_price') or 0)
                desc = f'当{cond_txt} **{_tp:.2f}**'
            except (TypeError, ValueError):
                desc = f"当{cond_txt} **{a.get('target_price', '—')}**"
        elif atype == 'pattern':
            pname = ''
            try:
                pname = json.loads(a.get('params') or '{}').get('pattern_name', '')
            except Exception:
                pass
            desc = f'出现形态 **{pname}**'
        elif atype == 'volume':
            vr = 2.0
            try:
                vr = float(json.loads(a.get('params') or '{}').get('volume_ratio', 2.0))
            except Exception:
                pass
            desc = f'量比 ≥ **{vr:.2f}×**'
        elif atype == 'announcement':
            kw = ''
            try:
                kw = json.loads(a.get('params') or '{}').get('keyword', '')
            except Exception:
                pass
            desc = f'新闻含「**{kw}**」'
        else:
            desc = ''
        if triggered is None:
            status_txt = '待验证'
            status_cls = 'sf-pill mid'
        elif triggered:
            status_txt = '🔥 已触发'
            status_cls = 'sf-pill down'
        else:
            status_txt = '监测中'
            status_cls = 'sf-pill mid'
        if st.session_state.get('alert_browser_notify') and triggered:
            _aid = aid
            if _aid is not None and _aid not in _notified_ids:
                _notified_ids.add(_aid)
                _notify_msgs.append(f'{display_name} ({code})：{detail}')
        elif triggered is False and a.get('id') in _notified_ids:
            _notified_ids.discard(a.get('id'))
        col_star, col_info, col_status, col_toggle, col_del = st.columns([1, 3.5, 2, 1.2, 1.2])
        with col_star:
            _is_fav = aid in st.session_state.get('_alert_fav_set', set())
            if st.button('⭐' if _is_fav else '☆', key=f'fav_{aid}', use_container_width=True, help='收藏/取消收藏该预警'):
                _fs = st.session_state.setdefault('_alert_fav_set', set())
                if aid in _fs:
                    _fs.discard(aid)
                else:
                    _fs.add(aid)
                st.rerun(scope='fragment')
        with col_info:
            st.markdown(f'{ALERT_TYPE_LABEL.get(atype, atype)} **{display_name}** `{code}` ｜ {desc}', help=f"创建于 {_fmt_rel(a.get('created_at'))}\n检测：{detail}")
        with col_status:
            st.markdown(f'<span class="{status_cls}">{status_txt}</span>', unsafe_allow_html=True)
            st.caption(detail)
        with col_toggle:
            label = '停用' if a.get('active', False) else '启用'
            if st.button(label, key=f'tog_{aid}', use_container_width=True):
                api_put(f'/api/price-alerts/{aid}/toggle')
        with col_del:
            _ck = f'alert_del_{aid}'
            if st.session_state.get(_ck):
                if st.button('确认删除', key=f'del_cfm_{aid}', type='primary', use_container_width=True):
                    api_delete(f'/api/price-alerts/{aid}')
                    _toast('预警已删除')
                    st.session_state.pop(_ck, None)
                if st.button('取消', key=f'del_cancel_{aid}', use_container_width=True):
                    st.session_state.pop(_ck, None)
            elif st.button('删除', key=f'del_{aid}', use_container_width=True):
                st.session_state[_ck] = True
        if _notify_msgs:
            try:
                _noti_body = '\n'.join(_notify_msgs)
                _js = "<script>(function(){if(!('Notification' in window))return;function fire(){if(Notification.permission==='granted'){new Notification('🔔 StockSignal 预警触发',{body:MSG});}}if(Notification.permission==='default'){Notification.requestPermission().then(function(p){if(p==='granted')fire();});}else{fire();}})();</script>".replace('MSG', json.dumps(_noti_body))
                st.markdown(_js, unsafe_allow_html=True)
            except Exception as _e:
                logger.warning(f'[alerts] 浏览器通知注入失败: {_e}')
        st.caption('提示：触发检测在页面访问时于前端执行（价格实时比价、形态/量比扫描日线、公告检索新闻）。如需持续监控，可在本页保持打开或定时刷新。')
        st.info('🔔 通知机制：触发检测在**页面访问时**于前端执行；若要持续接收异动提醒，可关注右上角「🔔 市场异动」铃铛，并保持本页在浏览器中打开。')
st.checkbox('🔔 启用浏览器桌面通知', value=st.session_state.get('alert_browser_notify', False), key='alert_browser_notify', help='开启后，本页预警触发时会向操作系统弹出桌面通知（需浏览器授予通知权限）。')
if st.button('🧹 清空通知记录', key='alert_clear_notified', help='清除已触发通知的去重记录，下次触发将再次弹出桌面通知。'):
    st.session_state['_alert_notified_ids'] = set()
    st.rerun()
fragment_alerts()
if st.button('↑ 回到顶部', key='alert_back_to_top'):
    sn.back_to_top_button()