import logging
logger = logging.getLogger(__name__)
"""
股票搜索UI组件模块 v6
后端 API 搜索 + 本地 fetcher 降级 + 防抖优化

交互流程：
1. 用户在输入框输入关键词（代码/名称/拼音首字母/全拼/首字）
2. 优先调用后端 /api/stocks/search 实时搜索
3. 后端不可用时降级到本地 fetcher.lookup_code()
4. 下方下拉框展示匹配结果（代码 + 名称 + 市场）
5. 用户选择 → 返回纯代码

v6 改进：
- 接入后端搜索 API（拼音首字母 + 全拼 + 首字模糊匹配）
- 防抖：输入长度 < 1 不搜索；结果缓存避免重复请求
- 搜索结果展示市场信息（SH/SZ）
- 降级链：后端 API → 本地 fetcher → 原始输入
"""
import streamlit as st
import streamlit.components.v1 as components
import time
import re
import html as _html
from modules.fetcher import StockFetcher
from modules.ui_theme import _theme_is_dark
try:
    from modules.session import is_authenticated, api_get
    _HAS_SESSION = True
except ImportError:
    _HAS_SESSION = False

def _search_via_backend(query: str, limit: int=15):
    """通过后端 API 搜索，返回 [(code, name, market), ...] 或 None。"""
    if not _HAS_SESSION or not is_authenticated():
        return None
    try:
        code, resp = api_get(f'/api/stocks/search?q={query}&limit={limit}', timeout=3)
        if code == 200 and resp.get('status') == 'ok':
            data = resp.get('data', [])
            return [(d['code'], d['name'], d.get('market', '')) for d in data]
    except Exception as e:
        logger.warning(f"[search_ui] 处理异常: {e}")
        pass
    return None

def _search_via_local(query: str, limit: int=15):
    """通过本地 fetcher 搜索，返回 [(code, name, market), ...]。"""
    fetcher = StockFetcher()
    results = fetcher.lookup_code(query, limit=limit)
    return [(code, name, _guess_market(code)) for code, name in results]

def _guess_market(code: str) -> str:
    from modules.market_utils import guess_exchange
    return guess_exchange(code)
_MATCH_LABELS = {'code_exact': '精确代码', 'name_exact': '精确名称', 'code_prefix': '代码前缀', 'name_prefix': '名称前缀', 'pinyin_init': '拼音首字母', 'pinyin_full': '拼音全拼', 'name_contains': '名称包含', 'dispersed': '名称分散'}

def _match_label(query: str, code: str, name: str) -> str:
    """判定查询与结果的匹配方式（纯函数，可离线测试）。

    优先级与 dad 项目 search_stock 一致：
    精确代码 > 精确名称 > 代码前缀 > 名称前缀 > 拼音首字母 > 拼音全拼
    > 名称包含 > 名称分散。命中返回中文标签，否则返回「市场」标签兜底。
    """
    if not query:
        return _derive_tag(code)
    q = query.strip()
    if not q:
        return _derive_tag(code)
    q_up = q.upper()
    q_low = q.lower()
    has_chinese = any(('一' <= ch <= '鿿' for ch in q))
    c = str(code).strip().zfill(6)
    n = str(name)
    if c == q and len(q) == 6:
        return _MATCH_LABELS['code_exact']
    if n == q:
        return _MATCH_LABELS['name_exact']
    if len(q) >= 3 and c.startswith(q):
        return _MATCH_LABELS['code_prefix']
    if n.startswith(q):
        return _MATCH_LABELS['name_prefix']
    if not has_chinese:
        initials = StockFetcher._pinyin_initials(n)
        if initials and q_up == initials:
            return _MATCH_LABELS['pinyin_init']
        variants = StockFetcher._pinyin_initials_variants(n)
        if variants and q_up in variants:
            return _MATCH_LABELS['pinyin_init']
    if not has_chinese:
        full = StockFetcher._pinyin_full(n)
        if full and q_low == full:
            return _MATCH_LABELS['pinyin_full']
    if q in n:
        return _MATCH_LABELS['name_contains']
    if has_chinese and len(q) >= 2 and all((ch in n for ch in q)):
        return _MATCH_LABELS['dispersed']
    return _derive_tag(code)

def _code_exists(code: str) -> bool:
    """本地股票库精确校验 6 位代码是否存在。"""
    try:
        fetcher = StockFetcher()
        _, name = fetcher.get_stock_basic(str(code).strip().zfill(6))
        return bool(name) and name != str(code).strip().zfill(6)
    except Exception as e:
        logger.warning(f"[search_ui] 处理异常: {e}")
        return False

def resolve_stock_codes(raw_text: str, max_rows: int=8):
    """
    把多行/逗号/空格分隔的原始输入解析为股票代码列表。
    支持 6 位代码、中文名称、拼音首字母。返回 (codes, labels, unresolved)。
    codes: 解析成功的 6 位代码列表
    labels: 解析成功的 "名称(代码)" 列表，用于 chip 展示
    unresolved: 未识别或无效的原始输入列表
    """
    if not raw_text:
        return ([], [], [])
    parts = [p.strip() for p in re.split('[\\n,，;\\s]+', raw_text) if p.strip()]
    parts = parts[:max_rows]
    fetcher = StockFetcher()
    codes = []
    labels = []
    unresolved = []
    for raw in parts:
        if raw.isdigit():
            if len(raw) != 6:
                unresolved.append(f'{raw}（须6位）')
                continue
            try:
                _, name = fetcher.get_stock_basic(raw)
            except Exception as e:
                logger.warning(f"[search_ui] 处理异常: {e}")
                name = None
            if not name or name == raw:
                results = _cached_search(raw, limit=1)
                if results:
                    code, name, _ = results[0]
                    if code == raw.zfill(6):
                        codes.append(code)
                        labels.append(f'{name}({code})')
                        continue
                unresolved.append(f'{raw}（代码不存在）')
                continue
            codes.append(raw)
            labels.append(f'{name}({raw})')
        else:
            results = _cached_search(raw, limit=1)
            if results:
                code, name, _ = results[0]
                codes.append(code)
                labels.append(f'{name}({code})')
            else:
                unresolved.append(f'{raw}（未识别）')
    return (codes, labels, unresolved)
_search_cache = {}
_CACHE_TTL = 30

def _cached_search(query: str, limit: int=10):
    """带缓存的搜索，后端 + 本地合并，确保拼音首字母等匹配更全面。"""
    cache_key = f'{query}:{limit}'
    now = time.time()
    if cache_key in _search_cache:
        ts, results = _search_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return results
    seen = set()
    merged = []
    backend_results = _search_via_backend(query, limit)
    if backend_results:
        for code, name, market in backend_results:
            if code not in seen:
                merged.append((code, name, market))
                seen.add(code)
    local_results = _search_via_local(query, limit * 2)
    if local_results:
        for code, name, market in local_results:
            if code not in seen:
                merged.append((code, name, market))
                seen.add(code)
    results = merged[:limit]
    _search_cache[cache_key] = (now, results)
    return results

def _derive_tag(code: str) -> str:
    """由代码前缀推导市场/板块标签（用于匹配结果下拉的「标签」列）。

    委托统一判定 modules.market_utils.short_tag（DRY，避免多份规则漂移）。
    """
    from modules.market_utils import short_tag
    return short_tag(code)

def _render_match_dropdown(key: str, raw_input: str, results, active_code: str, dark: bool):
    """渲染「匹配结果 N 条」选择列表（胶囊风格，对齐 dad 项目搜索前端），
    返回被选中（点击）的代码或 None。

    交互载体用 Streamlit 原生 ``st.pills``（1.58+ 胶囊单选控件）：
    - 视觉贴近 dad 项目 `trade_ui.html` 的 drop-tag chip（圆角胶囊）；
    - ``st.button`` 在 ``st.form`` 内会抛 ``StreamlitAPIException``
      （5_仓位管理 等页面把搜索框放在 form 里，导致整页崩溃）；
    - ``streamlit.components.v1.html()`` 内 JS 的 ``setComponentValue()``
      只对 ``components.declare()`` 自定义组件有效，对静态 iframe 无效，
      点击结果行完全无响应（最初“点不了”的根因）；
    - ``st.pills`` 是受支持的输入控件，form 内外都能正常选中并回传值，
      点击即选中、非 form 页面会触发 rerun 立即生效。
    - 浅色/深色模式由 st.pills 原生适配（无需手工配色）。

    label 展示 dad 式三要素：``名称 ★ 代码 匹配方式``（★ 标注最优匹配，
    匹配方式来自 _match_label：拼音首字母/拼音全拼/精确代码/名称包含等）。

    pills key 带 ``mkpills_`` 前缀；key 中含 ``raw_input`` 保证换搜索词后
    重新挂载、不残留旧选中态。Streamlit < 1.36（无 pills）时回退 st.radio。
    """
    st.caption(f'🔍 匹配结果（{len(results)} 条）')
    token = ''.join((ch if ch.isalnum() and ch.isascii() else str(ord(ch)) for ch in raw_input))[:24]
    labels = []
    code_by_label = {}
    default_idx = 0
    best_code = results[0][0] if results else None
    for i, (code, name, market) in enumerate(results):
        star = ' ★' if code == best_code else ''
        mlabel = _match_label(raw_input, code, name)
        label = f'{name}{star}\u3000{code}\u3000{mlabel}'
        labels.append(label)
        code_by_label[label] = code
        if code == active_code:
            default_idx = i
    pick_key = f'mkpills_{key}_{token}'
    if hasattr(st, 'pills'):
        picked_label = st.pills('选择匹配的股票', options=labels, selection_mode='single', default=labels[default_idx] if labels else None, key=pick_key, label_visibility='collapsed')
    else:
        picked_label = st.radio('选择匹配的股票', options=labels, index=default_idx, key=pick_key, label_visibility='collapsed', horizontal=False)
    if picked_label and picked_label in code_by_label:
        return code_by_label[picked_label]
    return None

def stock_search_input(label='股票搜索', key='stock_search', default='600519', placeholder='输入代码/名称/拼音首字母，如：600519 / 贵州茅台 / gzmt / 茅台', help_text='支持：6位代码、中文名称、拼音首字母(gzmt)、全拼(maotai)、首字模糊(茅)'):
    """
    统一的股票搜索组件 —— 后端 API + 本地降级 + 防抖缓存。
    返回选中的纯股票代码（如 "600519"）。
    """
    confirmed_key = f'{key}_confirmed'
    query_key = f'{key}_query'
    base_select_key = f'{key}_select'
    if confirmed_key not in st.session_state:
        st.session_state[confirmed_key] = default
    if query_key not in st.session_state:
        st.session_state[query_key] = default
    query = st.text_input(label, placeholder=placeholder, help=help_text, key=query_key)
    if not query or not query.strip():
        return st.session_state[confirmed_key]
    raw_input = query.strip()
    if raw_input.isdigit():
        if len(raw_input) != 6:
            st.error(f'⚠️ 股票代码须为 6 位数字，当前输入 {len(raw_input)} 位，请输入完整代码（如 600519）')
            return st.session_state[confirmed_key]
        if not _code_exists(raw_input):
            st.error(f'⚠️ 未找到代码 {raw_input} 对应的股票，请检查代码是否正确')
            return st.session_state[confirmed_key]
    results = _cached_search(raw_input, limit=10)
    if not results:
        st.error('⚠️ 未找到匹配的股票，请检查代码或名称是否正确')
        if any(('一' <= ch <= '鿿' for ch in raw_input)):
            try:
                pinyin_hint = StockFetcher._pinyin_full(raw_input)
                if pinyin_hint and pinyin_hint.lower() != raw_input.lower():
                    st.info(f'💡 尝试用拼音搜索: **{pinyin_hint}**')
            except Exception as e:
                logger.warning(f"[search_ui] 处理异常: {e}")
                pass
        return st.session_state[confirmed_key]
    confirmed = st.session_state[confirmed_key]
    codes_in = [c for c, _, _ in results]
    active = confirmed if confirmed in codes_in else results[0][0]
    picked = _render_match_dropdown(key, raw_input, results, active, _theme_is_dark())
    if picked and picked in codes_in:
        st.session_state[confirmed_key] = picked
        active = picked
    return active

def _add_item(key: str, max_rows: int):
    """多股输入：增加一行空输入框。"""
    items_key = f'{key}_items'
    items = st.session_state[items_key]
    if len(items) < max_rows:
        new_id = max((it['id'] for it in items), default=-1) + 1
        items.append({'id': new_id, 'value': '', 'code': None, 'name': None})

def _remove_item(key: str, item_id: int):
    """多股输入：删除指定行。"""
    items_key = f'{key}_items'
    st.session_state[items_key] = [it for it in st.session_state[items_key] if it['id'] != item_id]

def multi_stock_search_input(label='输入多只股票', key='multi_stock_search', default='600519,000858,601088,600036', placeholder='代码 / 名称 / 拼音', max_rows=8):
    """
    多股票搜索组件（动态行版）。
    每行一只，支持代码、中文名称、拼音；可添加/删除，已解析的股票以 chip 展示。
    返回 list[str] 股票代码列表。
    """
    items_key = f'{key}_items'
    fetcher = StockFetcher()
    if items_key not in st.session_state:
        defaults = [p.strip() for p in str(default).split(',') if p.strip()]
        st.session_state[items_key] = [{'id': i, 'value': val, 'code': None, 'name': None} for i, val in enumerate(defaults)]
    st.markdown(f"<div style='font-size:14px;font-weight:600;margin-bottom:6px;'>{label}</div>", unsafe_allow_html=True)
    st.caption('每行一只，支持代码 / 中文名 / 拼音；点击 🗑️ 删除，➕ 添加。')
    items = st.session_state[items_key]
    _need_split = False
    new_items = []
    max_id = max((it['id'] for it in items), default=-1)
    for item in items:
        val = item.get('value', '')
        if val and any((sep in val for sep in [',', '，', ';', ' ', '\n', '\t'])):
            parts = [p.strip() for p in re.split('[\\n,，;\\s]+', val) if p.strip()]
            if len(parts) > 1:
                _need_split = True
                for p in parts:
                    max_id += 1
                    new_items.append({'id': max_id, 'value': p, 'code': None, 'name': None})
                continue
        new_items.append(item)
    if _need_split:
        seen = set()
        deduped = []
        for it in new_items:
            v = it['value'].strip()
            if v not in seen:
                seen.add(v)
                deduped.append({'id': len(deduped), 'value': v, 'code': None, 'name': None})
        st.session_state[items_key] = deduped[:max_rows]
        st.rerun()
    if len(items) < max_rows:
        st.button('➕ 添加股票', key=f'{key}_add', on_click=_add_item, args=(key, max_rows), use_container_width=True)
    resolved_codes = []
    resolved_labels = []
    unresolved = []
    for idx, item in enumerate(items):
        cols = st.columns([5, 1])
        with cols[0]:
            val = st.text_input(f'股票 {idx + 1}', value=item['value'], key=f"{key}_input_{item['id']}", placeholder=placeholder, label_visibility='collapsed')
        with cols[1]:
            st.button('🗑️', key=f"{key}_del_{item['id']}", on_click=_remove_item, args=(key, item['id']), help='删除')
        item['value'] = val
        if val and val.strip():
            raw = val.strip()
            if raw.isdigit():
                if len(raw) != 6:
                    item['code'] = None
                    item['name'] = None
                    unresolved.append(f'{raw}（代码须为6位）')
                    continue
                code = raw
                try:
                    name = fetcher.get_stock_basic(code)[1] or code
                except Exception as e:
                    logger.warning(f"[search_ui] 处理异常: {e}")
                    name = code
                if name == code:
                    results = _cached_search(code, limit=1)
                    if results:
                        code, name, _ = results[0]
                        if code != raw.zfill(6):
                            code = None
                            name = None
                    else:
                        code = None
                        name = None
                if name == raw or not code:
                    item['code'] = None
                    item['name'] = None
                    unresolved.append(f'{raw}（代码不存在）')
                    continue
            else:
                results = _cached_search(raw, limit=1)
                if results:
                    code, name, _ = results[0]
                else:
                    code = None
                    name = None
            item['code'] = code
            item['name'] = name
            if code:
                resolved_codes.append(code)
                resolved_labels.append(f'{name or code}({code})')
            else:
                unresolved.append(raw)
        else:
            item['code'] = None
            item['name'] = None
    if resolved_labels:
        if _theme_is_dark():
            chip_bg, chip_border, chip_color = ('#1a1a2e', '#2d2d44', '#e2e8f0')
        else:
            chip_bg, chip_border, chip_color = ('#ffffff', '#e2e8f0', '#1e293b')
        chips_html = ''.join((f'<span style="display:inline-block;background:{chip_bg};border:1px solid {chip_border};border-radius:12px;padding:4px 10px;margin:3px 3px 3px 0;font-size:12px;color:{chip_color};">{lab}</span>' for lab in resolved_labels))
        st.markdown(f"<div style='margin-top:8px;'>{chips_html}</div>", unsafe_allow_html=True)
    if unresolved:
        st.error(f"⚠️ 未识别或无效: {', '.join(unresolved)}")
    return resolved_codes