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
import concurrent.futures as _cf

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import (
    require_auth, render_user_badge, safe_switch_page, api_get, trading_autorefresh,
)
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, render_data_degradation_banner
from modules.page_widgets import UP, DOWN

apply_page_config(page_title="消息中心", page_icon="🔔", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
trading_autorefresh(key="message_autorefresh")
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("🔔 消息 / 通知中心")
st.caption("聚合自选股异动、社区动态与系统状态；各模块独立取数，互不干扰。")

FETCHER = StockFetcher()


def _pct(q):
    try:
        if not q or not q.get("prev_close"):
            return 0.0
        return (q["current"] - q["prev_close"]) / q["prev_close"] * 100
    except Exception:
        return 0.0


def _color(pct):
    return UP if pct >= 0 else DOWN


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
        msgs.sort(key=lambda m: abs(float(m["title"].split("%")[0].split(" ")[-1])), reverse=True)
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


msgs = _all_messages()
unread = [m for m in msgs if m["id"] not in st.session_state["msg_read_ids"]]

# ───────────────────────── 顶部操作栏 ─────────────────────────
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    st.metric("未读", len(unread))
with c2:
    st.metric("总消息", len(msgs))
with c3:
    if st.button("✅ 全部标为已读", use_container_width=True, key="mark_all"):
        st.session_state["msg_read_ids"].update(m["id"] for m in msgs)
        st.rerun()

render_data_degradation_banner()

# ───────────────────────── 筛选 ─────────────────────────
TYPES = ["全部", "异动", "社区", "系统"]
_filt = st.radio("类型筛选", TYPES, horizontal=True, label_visibility="collapsed")
shown = msgs if _filt == "全部" else [m for m in msgs if m["type"] == _filt]

if not shown:
    st.info("当前分类暂无消息。💡 异动消息需先添加自选股；社区消息来自股吧发帖；系统消息来自数据源健康度。多使用各功能模块后会逐步产生消息。")
else:
    for m in shown:
        read = m["id"] in st.session_state["msg_read_ids"]
        border_col = _color(float(m["title"].split("%")[0].split(" ")[-1])) if "%" in m["title"] else "#888"
        with st.container(border=True):
            hc1, hc2 = st.columns([11, 1])
            with hc1:
                title_md = m["title"]
                if m["type"] == "异动":
                    try:
                        pct = float(m["title"].split("%")[0].split(" ")[-1])
                        title_md = f"<span style='color:{_color(pct)}'>{m['title']}</span>"
                    except Exception:
                        pass
                st.markdown((f"~~{title_md}~~" if read else title_md), unsafe_allow_html=True)
                st.caption(f"{m['type']}　·　{m['detail']}" + (f"　·　{m['time']}" if m["time"] else ""))
            with hc2:
                if st.button("跳转", key=f"go_{m['id']}", help="前往对应模块"):
                    if m.get("params"):
                        for k, v in m["params"].items():
                            st.query_params[k] = v
                    safe_switch_page(m["target"])
            if not read and st.button("标为已读", key=f"rd_{m['id']}", help="标记为已读"):
                st.session_state["msg_read_ids"].add(m["id"])
                st.rerun()
