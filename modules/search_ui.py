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
import time
from modules.fetcher import StockFetcher

try:
    from modules.session import is_authenticated, api_get
    _HAS_SESSION = True
except ImportError:
    _HAS_SESSION = False


def _search_via_backend(query: str, limit: int = 15):
    """通过后端 API 搜索，返回 [(code, name, market), ...] 或 None。"""
    if not _HAS_SESSION or not is_authenticated():
        return None
    try:
        code, resp = api_get(f"/api/stocks/search?q={query}&limit={limit}", timeout=3)
        if code == 200 and resp.get("status") == "ok":
            data = resp.get("data", [])
            return [(d["code"], d["name"], d.get("market", "")) for d in data]
    except Exception:
        pass
    return None


def _search_via_local(query: str, limit: int = 15):
    """通过本地 fetcher 搜索，返回 [(code, name, market), ...]。"""
    fetcher = StockFetcher()
    results = fetcher.lookup_code(query, limit=limit)
    # fetcher 返回 [(code, name), ...]，补上 market
    return [(code, name, _guess_market(code)) for code, name in results]


def _guess_market(code: str) -> str:
    if code.startswith("6"):
        return "SH"
    elif code.startswith("0") or code.startswith("3"):
        return "SZ"
    return ""


# 搜索结果缓存（query → (timestamp, results)）
_search_cache = {}
_CACHE_TTL = 30  # 30 秒缓存


def _cached_search(query: str, limit: int = 15):
    """带缓存的搜索，后端 + 本地合并，确保拼音首字母等匹配更全面。"""
    cache_key = f"{query}:{limit}"
    now = time.time()
    if cache_key in _search_cache:
        ts, results = _search_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return results

    seen = set()
    merged = []

    # 优先后端 API
    backend_results = _search_via_backend(query, limit)
    if backend_results:
        for code, name, market in backend_results:
            if code not in seen:
                merged.append((code, name, market))
                seen.add(code)

    # 再查本地，补充后端可能遗漏的结果（如拼音大小写、本地缓存差异）
    local_results = _search_via_local(query, limit * 2)
    if local_results:
        for code, name, market in local_results:
            if code not in seen:
                merged.append((code, name, market))
                seen.add(code)

    results = merged[:limit]
    _search_cache[cache_key] = (now, results)
    return results


def stock_search_input(
    label="股票搜索",
    key="stock_search",
    default="600519",
    placeholder="输入代码/名称/拼音首字母，如：600519 / 贵州茅台 / gzmt / 茅台",
    help_text="支持：6位代码、中文名称、拼音首字母(gzmt)、全拼(maotai)、首字模糊(茅)",
):
    """
    统一的股票搜索组件 —— 后端 API + 本地降级 + 防抖缓存。
    返回选中的纯股票代码（如 "600519"）。
    """
    # ── session_state 初始化 ──
    confirmed_key = f"{key}_confirmed"
    query_key = f"{key}_query"
    base_select_key = f"{key}_select"

    if confirmed_key not in st.session_state:
        st.session_state[confirmed_key] = default
    if query_key not in st.session_state:
        st.session_state[query_key] = default

    # ── 搜索输入框 ──
    query = st.text_input(
        label,
        placeholder=placeholder,
        help=help_text,
        key=query_key,
    )

    # ── 空输入 → 返回已确认的代码 ──
    if not query or not query.strip():
        return st.session_state[confirmed_key]

    raw_input = query.strip()

    # ── 防抖：单字符也搜索（首字模糊匹配）──
    results = _cached_search(raw_input, limit=15)

    if not results:
        st.caption("🔍 未找到匹配结果，请检查输入")
        # 拼音提示
        if any('\u4e00' <= ch <= '\u9fff' for ch in raw_input):
            try:
                pinyin_hint = StockFetcher._pinyin_full(raw_input)
                if pinyin_hint and pinyin_hint.lower() != raw_input.lower():
                    st.info(f"💡 尝试用拼音搜索: **{pinyin_hint}**")
            except Exception:
                pass
        return raw_input

    # ── 构建下拉选项（代码 + 名称 + 市场）──
    options = []
    codes_map = {}

    for code, name, market in results:
        market_tag = f"[{market}]" if market else ""
        display = f"{code} {name} {market_tag}"
        options.append(display)
        codes_map[display] = code

    # selectbox key 包含查询词哈希，确保选项随输入变化而刷新
    dynamic_select_key = f"{base_select_key}_{hash(raw_input)}"

    selected_display = st.selectbox(
        f"🔍 匹配结果 ({len(results)} 条)",
        options=options,
        index=0,
        key=dynamic_select_key,
        label_visibility="visible",
    )

    chosen_code = codes_map.get(selected_display, raw_input)

    # 用户选了新股票 → 同步更新
    if chosen_code != st.session_state[confirmed_key]:
        st.session_state[confirmed_key] = chosen_code
        st.rerun()

    return chosen_code


def _add_item(key: str, max_rows: int):
    """多股输入：增加一行空输入框。"""
    items_key = f"{key}_items"
    items = st.session_state[items_key]
    if len(items) < max_rows:
        new_id = max((it["id"] for it in items), default=-1) + 1
        items.append({"id": new_id, "value": "", "code": None, "name": None})


def _remove_item(key: str, item_id: int):
    """多股输入：删除指定行。"""
    items_key = f"{key}_items"
    st.session_state[items_key] = [it for it in st.session_state[items_key] if it["id"] != item_id]


def multi_stock_search_input(
    label="输入多只股票",
    key="multi_stock_search",
    default="600519,000858,601088,600036",
    placeholder="代码 / 名称 / 拼音",
    max_rows=8,
):
    """
    多股票搜索组件（动态行版）。
    每行一只，支持代码、中文名称、拼音；可添加/删除，已解析的股票以 chip 展示。
    返回 list[str] 股票代码列表。
    """
    items_key = f"{key}_items"
    fetcher = StockFetcher()

    # 初始化：把逗号分隔的 default 拆成多行
    if items_key not in st.session_state:
        defaults = [p.strip() for p in str(default).split(",") if p.strip()]
        st.session_state[items_key] = [
            {"id": i, "value": val, "code": None, "name": None}
            for i, val in enumerate(defaults)
        ]

    st.markdown(
        f"<div style='font-size:14px;font-weight:600;margin-bottom:6px;'>{label}</div>",
        unsafe_allow_html=True,
    )
    st.caption("每行一只，支持代码 / 中文名 / 拼音；点击 🗑️ 删除，➕ 添加。")

    items = st.session_state[items_key]

    # 添加按钮
    if len(items) < max_rows:
        st.button(
            "➕ 添加股票",
            key=f"{key}_add",
            on_click=_add_item,
            args=(key, max_rows),
            use_container_width=True,
        )

    resolved_codes = []
    resolved_labels = []
    unresolved = []

    for idx, item in enumerate(items):
        cols = st.columns([5, 1])
        with cols[0]:
            val = st.text_input(
                f"股票 {idx + 1}",
                value=item["value"],
                key=f"{key}_input_{item['id']}",
                placeholder=placeholder,
                label_visibility="collapsed",
            )
        with cols[1]:
            st.button(
                "🗑️",
                key=f"{key}_del_{item['id']}",
                on_click=_remove_item,
                args=(key, item["id"]),
                help="删除",
            )

        # 解析当前行
        item["value"] = val
        if val and val.strip():
            raw = val.strip()
            if raw.isdigit() and len(raw) == 6:
                code = raw
                try:
                    name = fetcher.get_stock_basic(code)[1] or code
                except Exception:
                    name = code
            else:
                results = _cached_search(raw, limit=1)
                if results:
                    code, name, _ = results[0]
                else:
                    code = None
                    name = None
            item["code"] = code
            item["name"] = name
            if code:
                resolved_codes.append(code)
                resolved_labels.append(f"{name or code}({code})")
            else:
                unresolved.append(raw)
        else:
            item["code"] = None
            item["name"] = None

    # 已解析股票 chip 展示
    if resolved_labels:
        chips_html = "".join(
            f'<span style="display:inline-block;background:#1a1a2e;border:1px solid #2d2d44;'
            f'border-radius:12px;padding:4px 10px;margin:3px 3px 3px 0;font-size:12px;color:#e2e8f0;">'
            f'{lab}</span>'
            for lab in resolved_labels
        )
        st.markdown(f"<div style='margin-top:8px;'>{chips_html}</div>", unsafe_allow_html=True)

    if unresolved:
        st.warning(f"⚠️ 未识别: {', '.join(unresolved)}")

    return resolved_codes
