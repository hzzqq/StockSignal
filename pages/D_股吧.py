"""
页面 D：股吧
────────────
用户社区：发表言论 / 文章，其他用户可查看、评论、点赞。
- 帖子可选关联某只股票，点击可跳转「股票选取」查看该股。
- 列表 / 详情两态切换（session_state），纯前端聚合，走后端 /api/forum。
- 详情 / 列表拆为独立 @safe_fragment，交互只重跑本区块，避免整页 st.rerun（#543-8）。
"""
import streamlit as st

from modules.ui_theme import apply_page_config, dashboard_sf_css
from modules.session import (
    require_auth, render_user_badge, get_user, safe_switch_page,
    api_get, api_post, api_delete, trading_autorefresh, _rel_time,
)
from modules.page_widgets import _empty_info, _toast
from modules.page_guard import safe_fragment

apply_page_config(page_title="股吧", page_icon="💬", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
trading_autorefresh(key="forum_autorefresh")
render_user_badge(sidebar=True)

st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

user = get_user() or {}


def _fmt_time(s: str) -> str:
    if not s:
        return ""
    rel = _rel_time(s)
    return rel if rel else s[:19].replace("T", " ").replace("Z", "")


# 头像配色（按用户名稳定取色）
_AVATAR_COLORS = [
    "#E57373", "#F06292", "#BA68C8", "#9575CD", "#7986CB",
    "#64B5F6", "#4FC3F7", "#4DD0E1", "#4DB6AC", "#81C784",
    "#FFB74D", "#FF8A65", "#A1887F", "#90A4AE",
]


def render_forum_avatar(avatar_data_url, username, size: int = 32) -> str:
    """返回头像 HTML：有头像用 <img>，否则用首字母彩色圆。"""
    if avatar_data_url:
        return (
            f'<img src="{avatar_data_url}" width="{size}" height="{size}" '
            f'style="border-radius:50%;object-fit:cover;vertical-align:middle;'
            f'flex:0 0 auto;">'
        )
    initial = (username or "?").strip()[:1] or "?"
    color = _AVATAR_COLORS[(hash(username or "x")) % len(_AVATAR_COLORS)]
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:{color};color:#fff;display:flex;align-items:center;'
        f'justify-content:center;font-weight:700;font-size:{int(size * 0.45)}px;'
        f'flex:0 0 auto;line-height:1;">{initial}</div>'
    )


# 视图切换：只改 session_state，fragment 自然重跑（不调 st.rerun，#543-8）
def _go_list():
    st.session_state.pop("forum_view_post", None)


def _open_post(pid: int):
    st.session_state["forum_view_post"] = int(pid)


st.title("💬 股吧 · 社区讨论")
st.caption("发表你的观点或文章，与其他投资者交流。可关联具体股票，点击帖子里的股票直达「股票选取」。")

_EMOJIS = [
    "😂", "🚀", "📈", "📉", "💰", "🎯", "✅", "❌", "👍", "💎",
    "🤦", "(╯°□°）╯︵ ┻━┻", "¯\\_(ツ)_/¯", "(◕‿◕)", "(╥﹏╥)", "(╬⊙﹏⊙)",
]


@safe_fragment
def fragment_detail():
    _view_pid = st.session_state.get("forum_view_post")
    if not _view_pid:
        return

    if st.button("← 返回列表", key="forum_back", on_click=_go_list):
        pass

    sc, body = api_get(f"/api/forum/posts/{_view_pid}")
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("帖子加载失败或已被删除。")
        if st.button("返回", key="forum_back2", on_click=_go_list):
            pass
        return

    post = body.get("data") or {}
    _op_name = post.get("username", "")
    st.markdown(f"## {post.get('title', '（无标题）')}")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:8px;'>"
        f"{render_forum_avatar(post.get('avatar', ''), _op_name, size=32)}"
        f"<span style='font-weight:600;'>{_op_name}</span>"
        f"<span style='font-size:11px;padding:1px 6px;border-radius:8px;"
        f"background:#2b8aef;color:#fff;'>楼主</span></div>",
        unsafe_allow_html=True,
    )
    _total_likes = int(post.get("likes", 0) or 0)
    meta = (f"🕘 {_fmt_time(post.get('created_at', ''))} · 👀 {post.get('views', 0)}"
            f" · 👍 {_total_likes}（点赞汇总）")
    st.caption(meta)

    if post.get("stock_code"):
        cst1, cst2 = st.columns([0.3, 0.7])
        with cst1:
            label = f"📈 {post.get('stock_name') or post['stock_code']}（{post['stock_code']}）"
            if st.button(label, key="forum_jump_stock", use_container_width=True):
                st.query_params["pick_stock"] = post["stock_code"]
                safe_switch_page("pages/个股研究.py")

    st.markdown("---")
    st.markdown(post.get("content", ""))
    st.markdown("---")

    ca1, ca2, _ = st.columns([0.2, 0.2, 0.6])
    with ca1:
        # 点赞：只写后端，fragment 自然重跑后拉到最新点赞数（不调 st.rerun，#543-8）
        if st.button(f"👍 点赞 ({post.get('likes', 0)})", key="forum_like", use_container_width=True):
            api_post(f"/api/forum/posts/{_view_pid}/like", {})
    with ca2:
        can_del = post.get("user_id") == user.get("id") or user.get("role") == "admin"
        _ck = f"forum_del_{_view_pid}"
        if can_del:
            if st.session_state.get(_ck):
                if st.button("确认删除帖子", key="forum_del_cfm", type="primary", use_container_width=True):
                    api_delete(f"/api/forum/posts/{_view_pid}")
                    _toast("已删除")
                    st.session_state.pop("forum_view_post", None)
                    st.session_state.pop(_ck, None)
                if st.button("取消", key="forum_del_cancel", use_container_width=True):
                    st.session_state.pop(_ck, None)
            else:
                if st.button("🗑️ 删除帖子", key="forum_del", use_container_width=True):
                    st.session_state[_ck] = True

    # ── 评论区 ──
    comments = post.get("comments") or []
    st.subheader(f"💭 评论（{len(comments)}）")
    for c in comments:
        _is_cop = (c.get("username") == _op_name)
        _cop_badge = (" <span style='font-size:11px;padding:1px 6px;border-radius:8px;"
                      "background:#2b8aef;color:#fff;'>楼主</span>") if _is_cop else ""
        st.markdown(
            f"<div style='display:flex;gap:8px;padding:8px 12px;margin-bottom:6px;"
            f"border-left:3px solid #B8860B;'>"
            f"<div style='flex:0 0 auto;'>{render_forum_avatar(c.get('avatar', ''), c.get('username', '?'), size=28)}</div>"
            f"<div><b>{c.get('username', '?')}</b>{_cop_badge} "
            f"<span style='opacity:.6;font-size:12px;'>{_fmt_time(c.get('created_at', ''))}</span><br>"
            f"{c.get('content', '')}</div></div>",
            unsafe_allow_html=True,
        )
    if not comments:
        _empty_info("还没有评论，来抢沙发～ 在下方输入框写下你的看法，发布后即显示在这里。")

    # ── 发表评论（含表情包 / 颜文字快捷插入）──
    st.caption("😀 快捷表情 / 颜文字：点击可插入到评论末尾")
    if "forum_new_comment" not in st.session_state:
        st.session_state["forum_new_comment"] = ""

    def _append_emoji(emo: str):
        st.session_state["forum_new_comment"] = st.session_state["forum_new_comment"] + emo

    _n_cols = 8
    for _start in range(0, len(_EMOJIS), _n_cols):
        _row = _EMOJIS[_start:_start + _n_cols]
        _cols = st.columns(len(_row))
        for _i, _emo in enumerate(_row):
            with _cols[_i]:
                st.button(_emo, key=f"forum_emo_{_start}_{_i}", on_click=_append_emoji, args=(_emo,))

    new_comment = st.text_area("发表评论", key="forum_new_comment", height=90, placeholder="友善交流，理性发言…")
    if st.button("💬 提交评论", type="primary", use_container_width=True):
        if new_comment.strip():
            sc, cb = api_post(f"/api/forum/posts/{_view_pid}/comments", {"content": new_comment.strip()})
            if sc in (200, 201):
                _toast("评论成功")
                st.session_state["forum_new_comment"] = ""
            else:
                st.error(cb.get("message", "评论失败") if isinstance(cb, dict) else "评论失败")
        else:
            st.warning("评论内容不能为空")


@safe_fragment
def fragment_list():
    if st.session_state.get("forum_view_post"):
        return

    with st.expander("✍️ 发表新帖 / 文章", expanded=False):
        with st.container(border=True):
            st.markdown("### 📝 发布到股吧")
            st.caption("分享你的观点或文章，与社区交流。")
            with st.form("forum_new_post", clear_on_submit=True):
                title = st.text_input("**标题** *", key="forum_title",
                                      placeholder="一句话说清你的观点（例如：白酒板块是否见底？）")
                content = st.text_area("**正文（支持 Markdown）** *", key="forum_content", height=180,
                                       placeholder="展开你的分析、逻辑或提问… 支持 Markdown 语法")
                cc1, cc2 = st.columns(2)
                with cc1:
                    stock_code = st.text_input("关联股票代码（可选）", key="forum_code", placeholder="如 600519，可留空")
                with cc2:
                    stock_name = st.text_input("关联股票名称（可选）", key="forum_name", placeholder="如 贵州茅台，可留空")
                st.caption("💡 正文支持 Markdown 语法。关联股票为可选项，留空则作为普通帖子发布。")
                if st.form_submit_button("🚀 发布帖子", type="primary", use_container_width=True):
                    if not title.strip() or not content.strip():
                        st.warning("标题和正文都不能为空")
                    else:
                        payload = {"title": title.strip(), "content": content.strip()}
                        if stock_code.strip():
                            payload["stock_code"] = stock_code.strip()
                            payload["stock_name"] = stock_name.strip()
                        sc, cb = api_post("/api/forum/posts", payload)
                        if sc in (200, 201):
                            _toast("发布成功！")
                        else:
                            st.error(cb.get("message", "发布失败") if isinstance(cb, dict) else "发布失败")

    fc1, fc2 = st.columns([0.4, 0.6])
    with fc1:
        filter_code = st.text_input("🔍 按股票代码筛选（可选）", key="forum_filter_code", placeholder="如 600519，留空看全部")
    with fc2:
        _sort = st.radio("排序", ["最新", "最热(点赞)", "最多评论"], horizontal=True, key="forum_sort")
    st.markdown("---")

    path = "/api/forum/posts"
    if filter_code.strip():
        path += f"?stock_code={filter_code.strip()}"
    # 加载态 + 错误隔离（#543-9）：失败只影响本区块，不拖垮整页
    with st.spinner("加载帖子…"):
        try:
            sc, body = api_get(path)
        except Exception as e:
            st.error(f"📡 帖子加载失败：{e}")
            return
    if sc != 200 or not isinstance(body, dict):
        st.error("📡 帖子加载失败，请稍后重试。")
        return
    posts = body.get("data", []) or []
    # 排序（#543-6）
    if _sort == "最热(点赞)":
        posts = sorted(posts, key=lambda p: int(p.get("likes", 0) or 0), reverse=True)
    elif _sort == "最多评论":
        posts = sorted(posts, key=lambda p: int(p.get("comment_count", 0) or 0), reverse=True)
    else:
        posts = sorted(posts, key=lambda p: str(p.get("created_at", "")), reverse=True)

    if not posts:
        _empty_info("还没有帖子，来发第一帖吧！用上方标题 + 内容输入框发布你的第一条帖子，社区即刻可见。")
    else:
        st.markdown(f"#### 📋 共 {len(posts)} 帖")
        for p in posts:
            with st.container(border=True):
                top1, top2 = st.columns([0.75, 0.25])
                with top1:
                    pid = p.get("id")
                    if pid is None:
                        # 帖子缺 id（上游 schema 漂移）时禁用打开按钮，避免 key 非法/args 崩溃
                        st.button(f"📌 {p.get('title', '（无标题）')}", disabled=True,
                                  use_container_width=True, help="该帖子缺少 id，暂无法打开")
                    else:
                        if st.button(f"📌 {p.get('title', '（无标题）')}", key=f"forum_open_{pid}",
                                     use_container_width=True, on_click=_open_post, args=(pid,)):
                            pass
                    excerpt = p.get("excerpt", "")
                    if excerpt:
                        st.caption(excerpt + ("…" if len(excerpt) >= 80 else ""))
                with top2:
                    tag = ""
                    if p.get("stock_code"):
                        tag = f"📈 {p.get('stock_name') or p['stock_code']}"
                    st.markdown(
                        f"<div style='text-align:right;font-size:12px;opacity:.75;'>"
                        f"{tag}<br>"
                        f"<span style='display:inline-flex;align-items:center;gap:6px;"
                        f"justify-content:flex-end;'>"
                        f"{render_forum_avatar(p.get('avatar', ''), p.get('username', '?'), size=20)}"
                        f"👤 {p.get('username', '?')}</span><br>"
                        f"💬 {p.get('comment_count') or 0} · 👍 {p.get('likes') or 0} · 👀 {p.get('views') or 0}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                st.caption(f"🕘 {_fmt_time(p.get('created_at', ''))}")


fragment_detail()
fragment_list()
