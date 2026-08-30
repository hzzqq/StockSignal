"""
页面 D：股吧
────────────
用户社区：发表言论 / 文章，其他用户可查看、评论、点赞。
- 帖子可选关联某只股票，点击可跳转「股票选取」查看该股。
- 列表 / 详情两态切换（session_state），纯前端聚合，走后端 /api/forum。
- 详情 / 列表拆为独立 @safe_fragment，交互只重跑本区块，避免整页 st.rerun（#543-8）。
"""
import streamlit as st
from datetime import date

from modules.session import (
    get_user, safe_switch_page,
    api_get, api_post, api_delete, trading_autorefresh, _rel_time,
)
from modules.page_widgets import _empty_info, _toast
from modules.page_guard import safe_fragment
from modules.page_utils import render_standard_page
from modules.ui_theme import sf_card, sf_metric
from modules.format_helpers import safe_int, safe_html_text
import modules.scroll_nav as sn

from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box
render_standard_page(
    title="股吧 · 社区讨论", icon="💬",
    caption="发表你的观点或文章，与其他投资者交流。可关联具体股票，点击帖子里的股票直达「股票选取」。",
    layout="wide",
)
sf_card("💬 股吧 · 社区讨论", "发表观点或文章，与其他投资者交流；可关联具体股票，点击帖子内股票直达「股票选取」。社区内容由用户生成，请理性判断、风险自担。", icon="💬")
st.caption("⚠️ 社区内容由用户生成，数据仅供参考，不构成投资建议；请理性判断，风险自担。")
trading_autorefresh(key="forum_autorefresh")

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
        # ⚠️ 安全：avatar_data_url 是用户可控字段，未转义会从 src="…" 属性里逃逸
        #    （形如 `" onerror="…`）注入事件处理器 → XSS。
        return (
            f'<img src="{safe_html_text(avatar_data_url)}" width="{size}" height="{size}" '
            f'style="border-radius:50%;object-fit:cover;vertical-align:middle;'
            f'flex:0 0 auto;">'
        )
    initial = safe_html_text((username or "?").strip()[:1], "?")
    color = _AVATAR_COLORS[(hash(username or "x")) % len(_AVATAR_COLORS)]
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:{color};color:#fff;display:flex;align-items:center;'
        f'justify-content:center;font-weight:700;font-size:{int(size * 0.45)}px;'
        f'flex:0 0 auto;line-height:1;">{initial}</div>'
    )


# 收藏 / 星标切换（#Batch20-3）：纯前端维护 session_state 收藏集合
def _toggle_fav(x):
    s = st.session_state.setdefault("forum_fav_set", set())
    if x in s:
        s.discard(x)
    else:
        s.add(x)


# 视图切换：只改 session_state，fragment 自然重跑（不调 st.rerun，#543-8）
def _go_list():
    st.session_state.pop("forum_view_post", None)


def _open_post(pid: int):
    st.session_state["forum_view_post"] = int(pid)


# 页面间快捷跳转（#Batch19-5）：相关页面一键直达
_pl1, _pl2 = st.columns(2)
with _pl1:
    st.page_link("pages/24_个股研究.py", label="📈 去个股研究", icon="📈")
with _pl2:
    st.page_link("pages/46_自选股监控.py", label="⭐ 去自选股监控", icon="⭐")

# 可折叠使用说明 / 快捷键提示（#Batch20-5 / #Batch20-9）：集合式帮助，纯前端折叠
with st.expander("💡 使用说明 / 常见问题"):
    st.markdown(
        "- **浏览帖子**：点击列表中的主题标题即可展开详情，含楼主信息、点赞与评论。\n"
        "- **发表内容**：展开「✍️ 发表新帖」填写标题、正文，可关联一只股票代码。\n"
        "- **收藏与历史**：帖子可「⭐ 收藏」，查看过的主题会出现在「最近浏览」。\n"
        "- **筛选与排序**：顶部可按股票代码 / 关键字过滤，并切换最新 / 最热 / 最多评论。\n"
        "- **风险提示**：社区内容由用户生成，仅供参考，不构成投资建议。"
    )
with st.expander("⌨️ 快捷键提示"):
    st.markdown(
        "- 本页以鼠标 / 触控操作为主，无全局键盘快捷键。\n"
        "- 长列表滚动后点击「↑ 回到顶部」可一键回顶。\n"
        "- 帖子详情页点击「← 返回列表」返回社区列表。"
    )

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

    with st.spinner("加载帖子详情…"):
        sc, body = api_get(f"/api/forum/posts/{_view_pid}")
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("帖子加载失败或已被删除。")
        if st.button("返回", key="forum_back2", on_click=_go_list):
            pass
        if st.button("🔄 重试", key="forum_retry_detail"):
            pass  # 点击即重跑本 fragment，重新加载帖子详情
        return

    post = body.get("data") or {}
    # 最近浏览历史（#Batch20-2）：记录最近查看主题，纯前端
    _pid = post.get("id")
    _ptitle = post.get("title", "（无标题）")
    if _pid is not None:
        _recent = st.session_state.setdefault("forum_recent", [])
        _recent = [r for r in _recent if r[0] != _pid]
        _recent.insert(0, (_pid, _ptitle))
        st.session_state["forum_recent"] = _recent[:6]
    _op_name = post.get("username", "")
    st.markdown(f"## {post.get('title', '（无标题）')}")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:8px;'>"
        f"{render_forum_avatar(post.get('avatar', ''), _op_name, size=32)}"
        f"<span style='font-weight:600;'>{safe_html_text(_op_name)}</span>"
        f"<span style='font-size:11px;padding:1px 6px;border-radius:8px;"
        f"background:#2b8aef;color:#fff;'>楼主</span></div>",
        unsafe_allow_html=True,
    )
    _total_likes = safe_int(post.get("likes", 0), 0)
    meta = (f"🕘 {_fmt_time(post.get('created_at', ''))} · 👀 {safe_int(post.get('views'), 0)}"
            f" · 👍 {_total_likes}（点赞汇总）")
    st.caption(meta)

    if post.get("stock_code"):
        cst1, cst2 = st.columns([0.3, 0.7])
        with cst1:
            label = f"📈 {post.get('stock_name') or post['stock_code']}（{post['stock_code']}）"
            if st.button(label, key="forum_jump_stock", use_container_width=True):
                st.query_params["pick_stock"] = post["stock_code"]
                safe_switch_page("pages/24_个股研究.py")

    st.markdown("---")
    st.markdown(post.get("content", ""))
    if not (post.get("content") or "").strip():
        _empty_info("这条主题暂无正文内容。点击左上角「← 返回列表」浏览其他讨论，"
                    "或到列表顶部用「标题 + 正文」发布你的主题。")
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
    if not isinstance(comments, list):
        # 二级嵌套兜底：comments 字段偶发非 list（如 {} / null），避免迭代崩溃中断详情页
        comments = []
    sf_card(f"💭 评论（{len(comments)}）", "")
    for c in comments:
        if not isinstance(c, dict):
            # 列表元素兜底：单条评论 schema 漂移时跳过，不影响其余评论渲染
            continue
        _is_cop = (c.get("username") == _op_name)
        _cop_badge = (" <span style='font-size:11px;padding:1px 6px;border-radius:8px;"
                      "background:#2b8aef;color:#fff;'>楼主</span>") if _is_cop else ""
        st.markdown(
            f"<div style='display:flex;gap:8px;padding:8px 12px;margin-bottom:6px;"
            f"border-left:3px solid #B8860B;'>"
            f"<div style='flex:0 0 auto;'>{render_forum_avatar(c.get('avatar', ''), c.get('username', '?'), size=28)}</div>"
            # ⚠️ 安全：评论用户名与正文是外部输入，必须转义后再拼 HTML。
            f"<div><b>{safe_html_text(c.get('username'), '?')}</b>{_cop_badge} "
            f"<span style='opacity:.6;font-size:12px;'>{_fmt_time(c.get('created_at', ''))}</span><br>"
            f"{safe_html_text(c.get('content'))}</div></div>",
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
            xc_warn_box("评论内容不能为空")


@safe_fragment
def fragment_list():
    if st.session_state.get("forum_view_post"):
        return

    # 手动刷新（#Batch20-1）：fragment 内用 scope="fragment" 显式重跑本区块
    if st.button("🔄 刷新帖子", key="forum_manual_refresh"):
        st.rerun(scope="fragment")
    # 偏好记忆（#Batch20-10）：session 内记住上次排序 / 筛选，下次自动套用
    if "forum_sort" not in st.session_state and st.session_state.get("forum_remembered_sort"):
        st.session_state["forum_sort"] = st.session_state["forum_remembered_sort"]
    if "forum_filter_code" not in st.session_state and st.session_state.get("forum_remembered_filter"):
        st.session_state["forum_filter_code"] = st.session_state["forum_remembered_filter"]
    # 最近浏览（#Batch20-2）：chips 展示最近查看的主题，点击直达
    _recent = st.session_state.get("forum_recent", [])
    if _recent:
        st.caption("🕘 最近浏览：")
        _rc = st.columns(min(len(_recent), 6))
        for _i, (rpid, rtitle) in enumerate(_recent[:6]):
            with _rc[_i]:
                if st.button(f"• {rtitle[:10]}", key=f"forum_recent_{rpid}",
                             use_container_width=True, on_click=_open_post, args=(rpid,)):
                    pass

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
                        xc_warn_box("标题和正文都不能为空")
                    elif stock_code.strip() and not (stock_code.strip().isdigit() and len(stock_code.strip()) == 6):
                        xc_warn_box("关联股票代码需为 6 位数字（如 600519），请检查后重试")
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
        # 输入内联校验（#Batch20-7）：股票代码筛选实时校验，错误时 st.warning
        if filter_code.strip() and not (filter_code.strip().isdigit() and len(filter_code.strip()) == 6):
            xc_warn_box("⚠️ 股票代码须为 6 位数字（如 600519），当前输入可能不完整。")
    with fc2:
        _sort = st.radio("排序", ["最新", "最热(点赞)", "最多评论"], horizontal=True, key="forum_sort")
        # 记忆当前排序偏好（#Batch20-10）
        st.session_state["forum_remembered_sort"] = _sort
        st.session_state["forum_remembered_filter"] = filter_code.strip()
    if st.button("🔄 清空筛选", key="forum_clear", help="清空股票代码筛选条件，查看全部帖子"):
        st.session_state["forum_filter_code"] = ""
    # 列表内搜索/筛选框（#Batch19-3）：标题关键字，纯前端过滤，不动既有后端筛选
    forum_kw = st.text_input("🔍 帖子标题关键字搜索（可选，纯前端过滤）", key="forum_kw_search")
    st.markdown("---")

    path = "/api/forum/posts"
    if filter_code.strip():
        path += f"?stock_code={filter_code.strip()}"
    # 加载态 + 错误隔离（#543-9）：失败只影响本区块，不拖垮整页
    with st.spinner("加载帖子…"):
        try:
            sc, body = api_get(path)
        except Exception as e:
            xc_handle_error("📡 帖子加载失败", e, hint="请稍后重试，或检查网络与数据源连接")
            return
    if sc != 200 or not isinstance(body, dict):
        st.error("📡 帖子加载失败，请稍后重试。")
        if st.button("🔄 重试", key="forum_retry_list"):
            pass  # 点击即重跑本 fragment，重新拉取帖子列表
        return
    posts = body.get("data", []) or []
    # 排序（#543-6）
    if _sort == "最热(点赞)":
        posts = sorted(posts, key=lambda p: safe_int(p.get("likes", 0), 0), reverse=True)
    elif _sort == "最多评论":
        posts = sorted(posts, key=lambda p: safe_int(p.get("comment_count", 0), 0), reverse=True)
    else:
        posts = sorted(posts, key=lambda p: str(p.get("created_at", "")), reverse=True)

    # 列表内搜索：标题关键字纯前端过滤（#Batch19-3）
    if forum_kw.strip():
        posts = [p for p in posts if forum_kw.strip().lower() in str(p.get("title", "")).lower()]

    # 分页 / 加载更多（#Batch19-4）：默认只显示前 N 条，按钮累加计数
    _show_key = "forum_show_n"
    if _show_key not in st.session_state:
        st.session_state[_show_key] = 8
    _visible = posts[: st.session_state[_show_key]]

    if not posts:
        if filter_code.strip():
            _empty_info(f"没有与股票「{filter_code.strip()}」相关的帖子。换个代码试试，或发布第一条相关讨论～")
        else:
            _empty_info("还没有帖子，来发第一帖吧！用上方标题 + 内容输入框发布你的第一条帖子，社区即刻可见。")
            # 示例数据预览（#Batch19-9）：无数据时只读展示示例讨论
            if st.button("👀 查看示例讨论", key="forum_sample"):
                with st.container(border=True):
                    st.markdown("#### 示例：白酒板块是否见底？")
                    st.caption("📈 600519 贵州茅台")
                    st.markdown("> 个人观点：估值回到近五年中枢下沿，分红率提升，长期配置价值渐显，仅供参考。")
                    st.caption("🔥 热门 · 👍 12 · 💬 8 · 👀 230")
    else:
        st.markdown(f"#### 📋 共 {len(posts)} 帖")
        # 指标/字段说明 tooltip（#Batch19-6）：关键聚合指标的含义说明
        st.caption("ℹ️ 指标说明：👍 点赞数 / 💬 评论数 / 👀 浏览量，均由社区实时聚合；🔥 热门(点赞或评论≥10) / 🆕 新(当日发布)。")
        for p in _visible:
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
                        tag = f"📈 {safe_html_text(p.get('stock_name') or p['stock_code'])}"
                    st.markdown(
                        f"<div style='text-align:right;font-size:12px;opacity:.75;'>"
                        f"{tag}<br>"
                        f"<span style='display:inline-flex;align-items:center;gap:6px;"
                        f"justify-content:flex-end;'>"
                        f"{render_forum_avatar(p.get('avatar', ''), p.get('username', '?'), size=20)}"
                        f"👤 {safe_html_text(p.get('username'), '?')}</span><br>"
                        f"💬 {p.get('comment_count') or 0} · 👍 {p.get('likes') or 0} · 👀 {p.get('views') or 0}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                # 结果标记/徽章（#Batch19-10）：中性色标签，不动红涨绿跌配色
                _badges = []
                if (safe_int(p.get("likes", 0), 0) >= 10) or (safe_int(p.get("comment_count", 0), 0) >= 10):
                    _badges.append("🔥 热门")
                if str(p.get("created_at", ""))[:10] == date.today().isoformat():
                    _badges.append("🆕 新")
                if _badges:
                    st.caption("　".join(_badges))
                st.caption(f"🕘 {_fmt_time(p.get('created_at', ''))}")
                # 收藏 / 批量选择（#Batch20-3 / #Batch20-6）：纯前端星标 + 勾选
                if pid is not None:
                    _favs = st.session_state.setdefault("forum_fav_set", set())
                    _is_fav = pid in _favs
                    scc1, scc2 = st.columns([0.2, 0.8])
                    with scc1:
                        if st.button("⭐" if _is_fav else "☆ 收藏", key=f"forum_fav_{pid}",
                                     use_container_width=True, on_click=_toggle_fav, args=(pid,)):
                            pass
                    with scc2:
                        st.checkbox("选择", key=f"forum_sel_{pid}", value=False)

        # 分页 / 加载更多（#Batch19-4）：列表还有更多时展示累加按钮
        if len(posts) > st.session_state[_show_key]:
            if st.button("显示更多 ▼", key="forum_more"):
                st.session_state[_show_key] += 8

        # 批量选择操作（#Batch20-6）：底部批量按钮，纯前端星标 + 清空选择
        _sel_ids = [p.get("id") for p in _visible
                    if p.get("id") is not None
                    and st.session_state.get(f"forum_sel_{p.get('id')}", False)]
        if _sel_ids:
            st.markdown(f"#### ✅ 已选择 {len(_sel_ids)} 个主题")
            b1, b2 = st.columns([0.3, 0.7])
            with b1:
                if st.button("⭐ 批量收藏", key="forum_batch_fav", use_container_width=True):
                    st.session_state.setdefault("forum_fav_set", set()).update(_sel_ids)
            with b2:
                if st.button("🧹 清空选择", key="forum_batch_clear", use_container_width=True):
                    for _id in _sel_ids:
                        st.session_state[f"forum_sel_{_id}"] = False

        # 相关推荐块（#Batch20-4）：底部热门主题推荐，点击直达
        _rec = sorted(posts, key=lambda p: safe_int(p.get("likes", 0), 0), reverse=True)[:3]
        if _rec:
            sf_card("🔥 热门主题推荐", "")
            _rcs = st.columns(len(_rec))
            for _i, rp in enumerate(_rec):
                rpid = rp.get("id")
                if rpid is None:
                    continue
                with _rcs[_i]:
                    if st.button(f"📌 {rp.get('title', '（无标题）')[:12]}",
                                 key=f"forum_rec_{rpid}", use_container_width=True,
                                 on_click=_open_post, args=(rpid,)):
                        pass


fragment_detail()
fragment_list()

# 快捷回到顶部（#Batch18-6）：长列表滚动后一键回顶。
# 原 st.markdown 注入 <script> 会被 Streamlit 过滤导致点击无效，改用 components.html（#MCP-2026）。
if st.button("↑ 回到顶部", key="forum_back_to_top"):
    sn.back_to_top_button()
