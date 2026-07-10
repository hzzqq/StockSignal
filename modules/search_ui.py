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


def multi_stock_search_input(
    label="输入多只股票（逗号分隔）",
    key="multi_stock_search",
    default="600519,000858,601088,600036",
    placeholder="输入代码/名称/拼音，逗号分隔，如：600519,茅台,gzmt",
):
    """
    多股票搜索组件，每只股票支持代码或中文名称或拼音。
    返回 list[str] 股票代码列表。
    """
    raw_key = f"{key}_raw"

    if raw_key not in st.session_state:
        st.session_state[raw_key] = default

    raw = st.text_input(
        label,
        key=raw_key,
        placeholder=placeholder,
        help="支持股票代码、中文名称、拼音首字母，逗号分隔",
    )

    if not raw or not raw.strip():
        return []

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    resolved = []
    unresolved = []

    for part in parts:
        if part.isdigit() and len(part) == 6:
            resolved.append(part)
        else:
            results = _cached_search(part, limit=1)
            if results:
                resolved.append(results[0][0])
            else:
                unresolved.append(part)

    if resolved:
        fetcher = StockFetcher()
        labels = [fetcher._lookup_name_for_code(c) for c in resolved]
        st.caption(f"📌 已解析: {', '.join(labels)}")

    if unresolved:
        st.caption(f"⚠️ 未识别: {', '.join(unresolved)}")

    return resolved
