"""
消息 / 通知中心（聚合页）
----------------------------
把分散在各模块的「提醒」汇成一条统一信息流：

  🔔 异动  —— 自选股当日涨跌异动（基于实时行情计算）
  💬 社区  —— 股吧最新帖子 / 评论动态
  🛡️ 系统  —— 数据源健康度、使用提示

每个区块独立取数（safe_section 隔离），单源失败不影响其它模块。
支持按类型筛选、标记已读、点击跳转到对应模块。
"""
import streamlit as st
from datetime import datetime
import math
import concurrent.futures as _cf

from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric
from modules.session import safe_switch_page, api_get, trading_autorefresh
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, render_data_degradation_banner
from modules.page_widgets import UP, DOWN
from modules.format_helpers import extract_pct

dark = render_standard_page(
    title="消息 / 通知中心", icon="🔔",
    caption="聚合自选股异动、社区动态与系统状态；各模块独立取数，互不干扰。",
)
sf_card("🔔 消息 / 通知中心", "把分散在各模块的提醒汇成统一信息流：自选股异动、股吧社区动态、系统健康度。支持按类型筛选、标记已读、点击跳转对应模块。", icon="📬")
trading_autorefresh(key="message_autorefresh")

FETCHER = StockFetcher()


def _pct(q):
    try:
        if not q or not q.get("prev_close"):
            return 0.0
        cur = q.get("current")
        prev = q.get("prev_close")
        if cur is None or prev in (None, 0):
            return 0.0
        return (float(cur) - float(prev)) / float(prev) * 100
    except Exception:
        return 0.0


def _color(pct):
    return UP if pct >= 0 else DOWN


def _safe_title_html(title, read=False):
    """转义消息标题中的 HTML，防止存储型 XSS；已读消息加删除线。

    纯函数：仅依赖标准库 html.escape，不访问 st / 网络 / 会话状态。
    """
    import html
    t = html.escape(str(title or ""))
    return f"~~{t}~~" if read else t


def _fmt_rel(ts):
    """绝对时间 -> 相对时间：刚刚/X分钟前/X小时前/X天前。"""
    from datetime import datetime
    try:
        if isinstance(ts, str):
            s = ts.replace("Z", "")
            if "." in s:
                s = s[: s.index(".")]
            s = s.replace("T", " ")
            try:
                ts = datetime.fromisoformat(s)
            except Exception:
                ts = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        elif hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        sec = (datetime.now() - ts).total_seconds()
        if sec < 0:
            return "刚刚"
        if sec < 60:
            return "刚刚"
        if sec < 3600:
            return f"{int(sec // 60)}分钟前"
        if sec < 86400:
            return f"{int(sec // 3600)}小时前"
        return f"{int(sec // 86400)}天前"
    except Exception:
        return str(ts) if ts else ""


# ───────────────────────── 数据区块 ─────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _load_watchlist():
    try:
        sc, body = api_get("/api/watchlist", timeout=5)
        if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
            return body.get("data") or []
    except Exception:
        pass
    return []


@st.cache_data(ttl=30, show_spinner=False)
def _load_forum(limit=15):
    try:
        sc, body = api_get(f"/api/forum/posts?limit={limit}", timeout=5)
        if sc == 200 and isinstance(body, dict):
            return body.get("data") or []
    except Exception:
        pass
    return []


def _build_movers():
    """自选股当日异动通知。"""
    items = _load_watchlist()
    if not items:
        return []
    codes = [it.get("stock_code") for it in items if it.get("stock_code")]
    msgs = []
    with _cf.ThreadPoolExecutor(max_workers=6) as ex:
        fut = {ex.submit(FETCHER.get_realtime_quote, c): c for c in codes}
        for f in _cf.as_completed(fut):
            code = fut[f]
            try:
                q = f.result()
            except Exception:
                q = None
            if not q or not isinstance(q, dict):
                continue
            pct = _pct(q)
            if abs(pct) >= 3.0:
                try:
                    name = q.get("name") or code
                    try:
                        cur_s = f"¥{float(q.get('current') or 0):.2f}"
                    except Exception:
                        cur_s = "—"
                    try:
                        high_s = f"¥{float(q.get('high') or 0):.2f}"
                    except Exception:
                        high_s = "—"
                    try:
                        low_s = f"¥{float(q.get('low') or 0):.2f}"
                    except Exception:
                        low_s = "—"
                    msgs.append({
                        "id": f"mv_{code}",
                        "type": "异动",
                        "title": f"{name}({code}) {'大涨' if pct >= 0 else '大跌'} {pct:+.2f}%",
                        "detail": f"现价 {cur_s}　高 {high_s}　低 {low_s}",
                        "time": q.get("datetime", ""),
                        "target": "pages/个股研究.py",
                        "params": {"pick_stock": code},
                    })
                except Exception:
                    # 单只行情异常不应拖垮整个异动区块（safe_section 会整体降级）
                    continue
    try:
        # extract_pct 永不抛异常：无 "%" 的标题返回 -inf，abs 后沉底，
        # 不再因任意一条非数字标题就让整个排序静默失效
        msgs.sort(key=lambda m: abs(extract_pct(m["title"])), reverse=True)
    except Exception:
        pass
    return msgs


def _build_forum():
    posts = _load_forum(15)
    msgs = []
    for p in posts:
        msgs.append({
            "id": f"fm_{p.get('id')}",
            "type": "社区",
            "title": f"💬 {p.get('title', '无标题')}",
            "detail": f"由 {p.get('username', '匿名')} 发布 · {p.get('comment_count', 0)} 条评论"
                      + (f" · 关联 {p.get('stock_name')}" if p.get("stock_name") else ""),
            "time": p.get("created_at", ""),
            "target": "pages/D_股吧.py",
            "params": {},
        })
    return msgs


def _build_system():
    from modules.page_guard import get_data_source_health
    msgs = []
    h = get_data_source_health()
    if h["status"] == "down":
        msgs.append({
            "id": "sys_down", "type": "系统",
            "title": "⚠️ 部分数据源不可用",
            "detail": f"受影响源：{', '.join(h['down'])}；相关模块已自动降级或展示缓存数据。",
            "time": "", "target": "pages/1_行情看板.py", "params": {},
        })
    elif h["status"] == "degraded":
        msgs.append({
            "id": "sys_deg", "type": "系统",
            "title": "📡 部分数据源不稳定",
            "detail": f"受影响源：{', '.join(h['degraded'])}；部分数据可能延迟或为估算值。",
            "time": "", "target": "pages/1_行情看板.py", "params": {},
        })
    msgs.append({
        "id": "sys_tip", "type": "系统",
        "title": "🛡️ 数据安全提示",
        "detail": "本平台为课程设计的分析工具，所有信号仅供参考，不构成投资建议。",
        "time": "", "target": "app.py", "params": {},
    })
    return msgs


# 已读状态（session 级）
if "msg_read_ids" not in st.session_state:
    st.session_state["msg_read_ids"] = set()

# 加法式收藏/星标（session 级，不接后端）
if "msg_starred" not in st.session_state:
    st.session_state["msg_starred"] = set()


def _all_messages():
    msgs = []
    with safe_section("自选股异动"):
        msgs += _build_movers()
    with safe_section("社区动态"):
        msgs += _build_forum()
    with safe_section("系统状态"):
        msgs += _build_system()
    # 解析时间排序（能解析的排前）
    def _ts(m):
        try:
            return datetime.strptime(m["time"][:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min
    msgs.sort(key=_ts, reverse=True)
    return msgs


# 加法式加载态反馈：聚合三类消息涉及多次后台请求 / 行情计算
with st.spinner("加载中…"):
    msgs = _all_messages()
unread = [m for m in msgs if m["id"] not in st.session_state["msg_read_ids"]]

# session_state 清理防膨胀：已读集合只保留当前仍存在消息的 id，并对集合设上限，
# 避免随使用时间无限增长（历史消息消失后其已读标记不再有意义）。
_current_ids = {m["id"] for m in msgs}
_read_set = st.session_state["msg_read_ids"]
_read_set &= _current_ids
if len(_read_set) > 500:
    st.session_state["msg_read_ids"] = set(list(_read_set)[-500:])

# 加法式操作成功反馈：标记已读 / 清除已读后给出成功提示
if st.session_state.get("_msg_marked_toast"):
    st.session_state.pop("_msg_marked_toast", None)
    st.success("✅ 已全部标记为已读")
if st.session_state.get("_msg_cleared_toast"):
    st.session_state.pop("_msg_cleared_toast", None)
    st.success("✅ 已清除已读标记")

# ───────────────────────── 顶部操作栏 ─────────────────────────
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    st.metric("未读", len(unread))
with c2:
    st.metric("总消息", len(msgs))
with c3:
    if st.button("✅ 全部标为已读", use_container_width=True, key="mark_all",
                 disabled=len(unread) == 0,
                 help="一键将当前所有未读消息标记为已读（无未读时禁用）。"):
        st.session_state["msg_read_ids"].update(m["id"] for m in msgs)
        st.session_state["_msg_marked_toast"] = True
        st.rerun()

render_data_degradation_banner()

# 加法式 UX：清空已读标记，重新将全部消息标为未读（仅清理本会话 session_state，不改后台数据）
if st.button("🧹 清除已读标记", key="clear_read_marks", use_container_width=False,
             help="将当前所有已读消息重新标记为未读（仅本会话生效，不影响后台数据）。"):
    st.session_state["msg_read_ids"] = set()
    st.session_state["_msg_cleared_toast"] = True
    st.rerun()

# 加法式失败重试：聚合取数经 safe_section 已降级，此处提供手动重新加载入口，
# 清掉本页缓存后整页重跑重新向各数据源拉取最新消息。
if st.button("🔄 重新加载", key="msg_reload", use_container_width=False):
    try:
        _load_watchlist.clear()
        _load_forum.clear()
    except Exception:
        pass
    st.rerun()

# ───────────────────────── 筛选 ─────────────────────────
TYPES = ["全部", "异动", "社区", "系统"]
# 加法式偏好记忆：用 key 将上次选择的类型筛选项存入 session_state，
# 下次进入本页自动套用（仅 session 级，不落库）。
_filt = st.radio("类型筛选", TYPES, horizontal=True, label_visibility="collapsed",
                 index=TYPES.index(st.session_state.get("msg_type_filter", "全部")),
                 key="msg_type_filter",
                 help="按消息类型过滤：异动（自选股涨跌）、社区（股吧动态）、系统（数据源与健康提示）。")
shown = msgs if _filt == "全部" else [m for m in msgs if m["type"] == _filt]

# 加法式列表内搜索/筛选：纯前端关键词过滤（不改后端、不改原有数据获取）
_search_kw = st.text_input(
    "🔍 搜索消息…", key="msg_search",
    help="按标题或详情关键词过滤当前消息（仅前端显示过滤，不影响后台数据）。",
)
if _search_kw and _search_kw.strip():
    _kw = _search_kw.strip().lower()
    shown = [m for m in shown if _kw in (str(m.get("title", "")) + str(m.get("detail", ""))).lower()]

# 加法式分页/加载更多：长列表只显示前 N 条，下方提供「显示更多 ▼」
_MSG_STEP = 10
if "msg_show_n" not in st.session_state:
    st.session_state["msg_show_n"] = _MSG_STEP
_visible = shown[: st.session_state["msg_show_n"]]

# 加法式结果计数/摘要：当前筛选下的显示条数与总条数
st.caption(f"当前显示 {len(_visible)} / 总计 {len(msgs)} 条消息")

if not shown:
    st.info("当前分类暂无消息。💡 异动消息需先添加自选股；社区消息来自股吧发帖；系统消息来自数据源健康度。多使用各功能模块后会逐步产生消息。")
else:
    for m in _visible:
        read = m["id"] in st.session_state["msg_read_ids"]
        border_col = "#888"
        if "%" in m["title"]:
            _p = extract_pct(m["title"])
            # 含 "%" 但解析不出合法涨跌幅（如社区消息 "35% 折扣"）→ 灰色边框而非错误上色
            border_col = _color(_p) if math.isfinite(_p) else "#888"
        with st.container(border=True):
            # 加法式批量选择+操作：每行加勾选框（纯前端 session_state）
            hc0, hc1, hc2, hc3 = st.columns([1, 9, 1, 1])
            with hc0:
                st.checkbox("", key=f"sel_{m['id']}", label_visibility="collapsed",
                            help="勾选后可在下方批量操作")
            with hc1:
                title_md = _safe_title_html(m["title"], read=read)
                if m["type"] == "异动":
                    _p = extract_pct(m["title"])
                    if math.isfinite(_p):
                        title_md = f"<span style='color:{_color(_p)}'>{_safe_title_html(m['title'], read=read)}</span>"
                st.markdown(title_md, unsafe_allow_html=True)
                st.caption(f"{m['type']}　·　{m['detail']}" + (f"　·　{_fmt_rel(m['time'])}" if m["time"] else ""))
                if not read and st.button("标为已读", key=f"rd_{m['id']}", help="标记为已读"):
                    st.session_state["msg_read_ids"].add(m["id"])
                    st.rerun()
            with hc2:
                if st.button("跳转", key=f"go_{m['id']}", help="前往对应模块"):
                    if m.get("params"):
                        for k, v in m["params"].items():
                            st.query_params[k] = v
                    safe_switch_page(m["target"])
            with hc3:
                # 加法式收藏/星标：星标当前消息（纯前端 session_state，不接后端）
                _starred = m["id"] in st.session_state["msg_starred"]
                if st.button("⭐" if _starred else "☆", key=f"star_{m['id']}",
                             help="收藏 / 取消收藏该消息"):
                    if _starred:
                        st.session_state["msg_starred"].discard(m["id"])
                    else:
                        st.session_state["msg_starred"].add(m["id"])
                    st.rerun()
    # 加法式加载更多：仅前端分页，不删原数据
    if st.session_state["msg_show_n"] < len(shown):
        if st.button("显示更多 ▼", key="msg_more", use_container_width=False,
                     help="每次多显示 10 条消息（仅前端分页）。"):
            st.session_state["msg_show_n"] += _MSG_STEP
            st.rerun()

# 加法式批量选择+操作：对勾选的消息执行批量标为已读 / 批量取消收藏
_sel_ids = [m["id"] for m in shown if st.session_state.get(f"sel_{m['id']}", False)]
if _sel_ids:
    st.markdown("---")
    _bc1, _bc2 = st.columns(2)
    with _bc1:
        if st.button("✅ 批量标为已读", key="msg_batch_read", use_container_width=True,
                     help="将当前勾选的消息全部标记为已读（仅本会话生效）。"):
            st.session_state["msg_read_ids"].update(_sel_ids)
            for _id in _sel_ids:
                st.session_state.pop(f"sel_{_id}", None)
            st.rerun()
    with _bc2:
        if st.button("🗑️ 批量取消收藏", key="msg_batch_unstar", use_container_width=True,
                     help="取消勾选消息的收藏标记（仅本会话生效）。"):
            st.session_state["msg_starred"] -= set(_sel_ids)
            for _id in _sel_ids:
                st.session_state.pop(f"sel_{_id}", None)
            st.rerun()

# 加法式收藏/星标：展示用户收藏的消息（纯前端 session，不接后端）
_msg_starred_ids = st.session_state.get("msg_starred", set())
if _msg_starred_ids:
    st.markdown("---")
    st.markdown("**⭐ 我的收藏**")
    for _sm in [m for m in msgs if m["id"] in _msg_starred_ids]:
        with st.container(border=True):
            st.markdown(_safe_title_html(_sm["title"]), unsafe_allow_html=True)
            st.caption(f"{_sm['type']}　·　{_sm['detail']}")

# 加法式数据来源标注
st.caption("📡 数据来源：自选股实时行情（东方财富 / 新浪财经）、股吧社区动态、系统数据源健康度监控")
