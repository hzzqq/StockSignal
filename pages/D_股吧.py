"""
页面 D：股吧
────────────
用户社区：发表言论 / 文章，其他用户可查看、评论、点赞。
- 帖子可选关联某只股票，点击可跳转「股票选取」查看该股。
- 列表 / 详情两态切换（session_state），纯前端聚合，走后端 /api/forum。
"""
import streamlit as st

from modules.ui_theme import apply_page_config, dashboard_sf_css
from modules.session import (
    require_auth, render_user_badge, get_user, safe_switch_page,
    api_get, api_post, api_delete,
)

apply_page_config(page_title="股吧", page_icon="💬", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

user = get_user() or {}


def _fmt_time(s: str) -> str:
    if not s:
        return ""
    return s[:19].replace("T", " ").replace("Z", "")


def _go_list():
    st.session_state.pop("forum_view_post", None)
    st.rerun()


def _open_post(pid: int):
    st.session_state["forum_view_post"] = int(pid)
    st.rerun()


st.title("💬 股吧 · 社区讨论")
st.caption("发表你的观点或文章，与其他投资者交流。可关联具体股票，点击帖子里的股票直达「股票选取」。")

_view_pid = st.session_state.get("forum_view_post")

# ══════════════════════════════════════════════════════════════
# 详情态
# ══════════════════════════════════════════════════════════════
if _view_pid:
    if st.button("← 返回列表", key="forum_back"):
        _go_list()

    sc, body = api_get(f"/api/forum/posts/{_view_pid}")
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("帖子加载失败或已被删除。")
        if st.button("返回", key="forum_back2"):
            _go_list()
        st.stop()

    post = body.get("data") or {}
    st.markdown(f"## {post.get('title', '（无标题）')}")
    meta = f"👤 {post.get('username', '?')} · 🕘 {_fmt_time(post.get('created_at', ''))} · 👀 {post.get('views', 0)} · 👍 {post.get('likes', 0)}"
    st.caption(meta)

    if post.get("stock_code"):
        cst1, cst2 = st.columns([0.3, 0.7])
        with cst1:
            label = f"📈 {post.get('stock_name') or post['stock_code']}（{post['stock_code']}）"
            if st.button(label, key="forum_jump_stock", use_container_width=True):
                st.query_params["pick_stock"] = post["stock_code"]
                safe_switch_page("pages/1_股票选取.py")

    st.markdown("---")
    st.markdown(post.get("content", ""))
    st.markdown("---")

    ca1, ca2, _ = st.columns([0.2, 0.2, 0.6])
    with ca1:
        if st.button(f"👍 点赞 ({post.get('likes', 0)})", key="forum_like", use_container_width=True):
            api_post(f"/api/forum/posts/{_view_pid}/like", {})
            st.rerun()
    with ca2:
        can_del = post.get("user_id") == user.get("id") or user.get("role") == "admin"
        if can_del and st.button("🗑️ 删除帖子", key="forum_del", use_container_width=True):
            api_delete(f"/api/forum/posts/{_view_pid}")
            st.success("已删除")
            _go_list()

    # ── 评论区 ──
    comments = post.get("comments") or []
    st.subheader(f"💭 评论（{len(comments)}）")
    for c in comments:
        st.markdown(
            f"<div style='padding:8px 12px;margin-bottom:6px;border-left:3px solid #B8860B;'>"
            f"<b>{c.get('username', '?')}</b> "
            f"<span style='opacity:.6;font-size:12px;'>{_fmt_time(c.get('created_at', ''))}</span><br>"
            f"{c.get('content', '')}</div>",
            unsafe_allow_html=True,
        )
    if not comments:
        st.info("还没有评论，来抢沙发～")

    with st.form("forum_comment_form", clear_on_submit=True):
        new_comment = st.text_area("发表评论", key="forum_new_comment", height=90,
                                   placeholder="友善交流，理性发言…")
        if st.form_submit_button("💬 提交评论", use_container_width=True):
            if new_comment.strip():
                sc, cb = api_post(f"/api/forum/posts/{_view_pid}/comments", {"content": new_comment.strip()})
                if sc in (200, 201):
                    st.success("评论成功")
                    st.rerun()
                else:
                    st.error(cb.get("message", "评论失败") if isinstance(cb, dict) else "评论失败")
            else:
                st.warning("评论内容不能为空")
    st.stop()

# ══════════════════════════════════════════════════════════════
# 列表态
# ══════════════════════════════════════════════════════════════
with st.expander("✍️ 发表新帖 / 文章", expanded=False):
    with st.form("forum_new_post", clear_on_submit=True):
        title = st.text_input("标题", key="forum_title", placeholder="一句话说清你的观点")
        content = st.text_area("正文（支持 Markdown）", key="forum_content", height=180,
                               placeholder="展开你的分析、逻辑或提问…")
        cc1, cc2 = st.columns(2)
        with cc1:
            stock_code = st.text_input("关联股票代码（可选）", key="forum_code",
                                       placeholder="如 600519，可留空")
        with cc2:
            stock_name = st.text_input("关联股票名称（可选）", key="forum_name",
                                       placeholder="如 贵州茅台，可留空")
        if st.form_submit_button("🚀 发布", type="primary", use_container_width=True):
            if not title.strip() or not content.strip():
                st.warning("标题和正文都不能为空")
            else:
                payload = {"title": title.strip(), "content": content.strip()}
                if stock_code.strip():
                    payload["stock_code"] = stock_code.strip()
                    payload["stock_name"] = stock_name.strip()
                sc, cb = api_post("/api/forum/posts", payload)
                if sc in (200, 201):
                    st.success("发布成功！")
                    st.rerun()
                else:
                    st.error(cb.get("message", "发布失败") if isinstance(cb, dict) else "发布失败")

# 过滤
fc1, fc2 = st.columns([0.4, 0.6])
with fc1:
    filter_code = st.text_input("🔍 按股票代码筛选（可选）", key="forum_filter_code",
                                placeholder="如 600519，留空看全部")
st.markdown("---")

path = "/api/forum/posts"
if filter_code.strip():
    path += f"?stock_code={filter_code.strip()}"
sc, body = api_get(path)
posts = body.get("data", []) if (sc == 200 and isinstance(body, dict)) else []

if not posts:
    st.info("还没有帖子，来发第一帖吧！")
else:
    st.markdown(f"#### 📋 共 {len(posts)} 帖")
    for p in posts:
        with st.container(border=True):
            top1, top2 = st.columns([0.75, 0.25])
            with top1:
                if st.button(f"📌 {p.get('title', '（无标题）')}", key=f"forum_open_{p['id']}",
                             use_container_width=True):
                    _open_post(p["id"])
                excerpt = p.get("excerpt", "")
                if excerpt:
                    st.caption(excerpt + ("…" if len(excerpt) >= 80 else ""))
            with top2:
                tag = ""
                if p.get("stock_code"):
                    tag = f"📈 {p.get('stock_name') or p['stock_code']}"
                st.markdown(
                    f"<div style='text-align:right;font-size:12px;opacity:.75;'>"
                    f"{tag}<br>👤 {p.get('username', '?')}<br>"
                    f"💬 {p.get('comment_count', 0)} · 👍 {p.get('likes', 0)} · 👀 {p.get('views', 0)}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            st.caption(f"🕘 {_fmt_time(p.get('created_at', ''))}")
