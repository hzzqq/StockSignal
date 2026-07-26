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
    # 委托统一判定，避免多份前缀规则漂移（DRY）
    from modules.market_utils import guess_exchange
    return guess_exchange(code)


def _code_exists(code: str) -> bool:
    """本地股票库精确校验 6 位代码是否存在。"""
    try:
        fetcher = StockFetcher()
        _, name = fetcher.get_stock_basic(str(code).strip().zfill(6))
        return bool(name) and name != str(code).strip().zfill(6)
    except Exception:
        return False


def resolve_stock_codes(raw_text: str, max_rows: int = 8):
    """
    把多行/逗号/空格分隔的原始输入解析为股票代码列表。
    支持 6 位代码、中文名称、拼音首字母。返回 (codes, labels, unresolved)。
    codes: 解析成功的 6 位代码列表
    labels: 解析成功的 "名称(代码)" 列表，用于 chip 展示
    unresolved: 未识别或无效的原始输入列表
    """
    if not raw_text:
        return [], [], []
    parts = [p.strip() for p in re.split(r"[\n,，;\s]+", raw_text) if p.strip()]
    parts = parts[:max_rows]
    fetcher = StockFetcher()
    codes = []
    labels = []
    unresolved = []
    for raw in parts:
        if raw.isdigit():
            if len(raw) != 6:
                unresolved.append(f"{raw}（须6位）")
                continue
            try:
                _, name = fetcher.get_stock_basic(raw)
            except Exception:
                name = None
            if not name or name == raw:
                # fallback：后端/本地搜索按代码精确匹配（补全本地库缺失的深市/创业板代码）
                results = _cached_search(raw, limit=1)
                if results:
                    code, name, _ = results[0]
                    if code == raw.zfill(6):
                        codes.append(code)
                        labels.append(f"{name}({code})")
                        continue
                unresolved.append(f"{raw}（代码不存在）")
                continue
            codes.append(raw)
            labels.append(f"{name}({raw})")
        else:
            results = _cached_search(raw, limit=1)
            if results:
                code, name, _ = results[0]
                codes.append(code)
                labels.append(f"{name}({code})")
            else:
                unresolved.append(f"{raw}（未识别）")
    return codes, labels, unresolved



# 搜索结果缓存（query → (timestamp, results)）
_search_cache = {}
_CACHE_TTL = 30  # 30 秒缓存


def _cached_search(query: str, limit: int = 10):
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


def _derive_tag(code: str) -> str:
    """由代码前缀推导市场/板块标签（用于匹配结果下拉的「标签」列）。

    委托统一判定 modules.market_utils.short_tag（DRY，避免多份规则漂移）。
    """
    from modules.market_utils import short_tag
    return short_tag(code)


def _render_match_dropdown(key: str, raw_input: str, results, active_code: str, dark: bool):
    """渲染「匹配结果 N 条」内联下拉（HTML + 可点击行），返回点击的代码或 None。

    直接显示在输入框下方，每行含 名称 / 代码 / 标签，点击即选中（点击由组件的
    setComponentValue 触发重跑，fragment 内只重跑片段，无需手动 st.rerun）。
    key 随输入词变化以确保换词后组件重新挂载、不残留旧选中值。
    """
    rows = []
    for code, name, market in results:
        tag = _derive_tag(code)
        cls = " mk-active" if code == active_code else ""
        # HTML 转义：股票名/代码虽来自交易所可信源，仍防御含 < & " 的异常值破坏下拉标记
        safe_code = _html.escape(str(code), quote=True)
        safe_name = _html.escape(str(name), quote=True)
        safe_tag = _html.escape(str(tag), quote=True)
        rows.append(
            f'<div class="mk-row{cls}" data-code="{safe_code}">'
            f'<span class="mk-name">{safe_name}</span>'
            f'<span class="mk-code">{safe_code}</span>'
            f'<span class="mk-tag">{safe_tag}</span>'
            f'</div>'
        )
    rows_html = "".join(rows)

    if dark:
        bg, border = "#16161e", "#2d2d44"
        head_color, row_color = "#cbd5e1", "#e2e8f0"
        code_color, tag_bg, tag_color = "#8b95a8", "#2d2d44", "#a5b4fc"
        hover, active_bg = "#23233a", "#2a2a44"
    else:
        bg, border = "#ffffff", "#e2e8f0"
        head_color, row_color = "#475569", "#1e293b"
        code_color, tag_bg, tag_color = "#64748b", "#eef2ff", "#4f46e5"
        hover, active_bg = "#f1f5f9", "#eef2ff"

    css = f"""
    <style>
    .mk-wrap{{background:{bg};border:1px solid {border};border-radius:8px;
      margin-top:4px;overflow:hidden;font-family:inherit;}}
    .mk-head{{padding:6px 10px;font-size:12px;color:{head_color};font-weight:600;
      border-bottom:1px solid {border};}}
    .mk-row{{display:flex;align-items:center;gap:8px;padding:7px 10px;cursor:pointer;
      color:{row_color};font-size:13px;}}
    .mk-row:hover{{background:{hover};}}
    .mk-active{{background:{active_bg};font-weight:600;}}
    .mk-name{{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
    .mk-code{{color:{code_color};font-size:12px;font-variant-numeric:tabular-nums;}}
    .mk-tag{{background:{tag_bg};color:{tag_color};font-size:11px;padding:1px 7px;
      border-radius:10px;white-space:nowrap;}}
    </style>
    """
    html = (
        css
        + f'<div class="mk-wrap"><div class="mk-head">🔍 匹配结果 ({len(results)} 条)</div>'
        + f'{rows_html}</div>'
        + '<script>'
        + 'var rows=document.querySelectorAll(".mk-row");'
        + 'for(var i=0;i<rows.length;i++){'
        + 'rows[i].onclick=function(){'
        + 'var s=window.parent&&window.parent.Streamlit;'
        + 'if(s&&s.setComponentValue){s.setComponentValue(this.getAttribute("data-code"));}'
        + '};}'
        + '</script>'
    )
    height = min(38 + len(results) * 36, 460)
    # key 随输入词变化 → 换词重新挂载组件，避免残留上一次点击的选中值
    return components.html(html, height=height, key=f"{key}_match_{hash(raw_input)}")


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

    # ── 严格 6 位代码校验 ──
    if raw_input.isdigit():
        if len(raw_input) != 6:
            st.error(
                f"⚠️ 股票代码须为 6 位数字，当前输入 {len(raw_input)} 位，"
                f"请输入完整代码（如 600519）"
            )
            return st.session_state[confirmed_key]
        if not _code_exists(raw_input):
            st.error(f"⚠️ 未找到代码 {raw_input} 对应的股票，请检查代码是否正确")
            return st.session_state[confirmed_key]

    # ── 防抖：单字符也搜索（首字模糊匹配）──
    results = _cached_search(raw_input, limit=10)

    if not results:
        st.error("⚠️ 未找到匹配的股票，请检查代码或名称是否正确")
        # 拼音提示
        if any('\u4e00' <= ch <= '\u9fff' for ch in raw_input):
            try:
                pinyin_hint = StockFetcher._pinyin_full(raw_input)
                if pinyin_hint and pinyin_hint.lower() != raw_input.lower():
                    st.info(f"💡 尝试用拼音搜索: **{pinyin_hint}**")
            except Exception:
                pass
        return st.session_state[confirmed_key]

    # ── 内联「匹配结果」下拉（模仿图片：直接显示在输入框下方，含 名称/代码/标签）──
    confirmed = st.session_state[confirmed_key]
    codes_in = [c for c, _, _ in results]
    # 保持旧行为：输入即选中结果首位（若已确认项不在当前结果则回退到首位）
    active = confirmed if confirmed in codes_in else results[0][0]

    picked = _render_match_dropdown(key, raw_input, results, active, _theme_is_dark())
    if picked and picked in codes_in:
        st.session_state[confirmed_key] = picked
        active = picked

    return active


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

    # 检测单行输入里是否粘贴了逗号/中文逗号/分号/空格/换行分隔的多只股票，
    # 如果是则自动拆成多行，避免用户把“深科技，太极实业...”整段贴进一个框导致全部未识别。
    _need_split = False
    new_items = []
    max_id = max((it["id"] for it in items), default=-1)
    for item in items:
        val = item.get("value", "")
        if val and any(sep in val for sep in [",", "，", ";", " ", "\n", "\t"]):
            parts = [p.strip() for p in re.split(r"[\n,，;\s]+", val) if p.strip()]
            if len(parts) > 1:
                _need_split = True
                for p in parts:
                    max_id += 1
                    new_items.append({"id": max_id, "value": p, "code": None, "name": None})
                continue
        new_items.append(item)
    if _need_split:
        # 去重并限制 max_rows
        seen = set()
        deduped = []
        for it in new_items:
            v = it["value"].strip()
            if v not in seen:
                seen.add(v)
                deduped.append({"id": len(deduped), "value": v, "code": None, "name": None})
        st.session_state[items_key] = deduped[:max_rows]
        st.rerun()

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
            if raw.isdigit():
                if len(raw) != 6:
                    item["code"] = None
                    item["name"] = None
                    unresolved.append(f"{raw}（代码须为6位）")
                    continue
                code = raw
                try:
                    name = fetcher.get_stock_basic(code)[1] or code
                except Exception:
                    name = code
                if name == code:  # 本地库无此代码 -> fallback 搜索
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
                    item["code"] = None
                    item["name"] = None
                    unresolved.append(f"{raw}（代码不存在）")
                    continue
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

    # 已解析股票 chip 展示（跟随全局亮/暗主题）
    if resolved_labels:
        if _theme_is_dark():
            chip_bg, chip_border, chip_color = "#1a1a2e", "#2d2d44", "#e2e8f0"
        else:
            chip_bg, chip_border, chip_color = "#ffffff", "#e2e8f0", "#1e293b"
        chips_html = "".join(
            f'<span style="display:inline-block;background:{chip_bg};border:1px solid {chip_border};'
            f'border-radius:12px;padding:4px 10px;margin:3px 3px 3px 0;font-size:12px;color:{chip_color};"'
            f'>{lab}</span>'
            for lab in resolved_labels
        )
        st.markdown(f"<div style='margin-top:8px;'>{chips_html}</div>", unsafe_allow_html=True)

    if unresolved:
        st.error(f"⚠️ 未识别或无效: {', '.join(unresolved)}")

    return resolved_codes
