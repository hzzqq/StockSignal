"""
pages/7_用户管理.py
------------------
管理员用户管理页面：用户列表 / 创建 / 编辑 / 删除 / 操作日志。
"""
import streamlit as st
from modules.session import init_session_state, require_admin, render_user_badge, get_user
from modules.admin_api import get_users, create_user, update_user, delete_user, get_logs
from modules.page_widgets import _empty_info

init_session_state()
require_admin()

from modules.ui_theme import apply_page_config
apply_page_config(page_title="用户管理", page_icon="👥", layout="wide")
st.session_state["_active_page"] = __file__
st.title("👥 用户管理")
render_user_badge()

# 初始化分页 state
if "user_mgmt_page" not in st.session_state:
    st.session_state["user_mgmt_page"] = 1
if "user_mgmt_keyword" not in st.session_state:
    st.session_state["user_mgmt_keyword"] = ""
if "log_page" not in st.session_state:
    st.session_state["log_page"] = 1

# ================================================================ Tab 布局
tab_users, tab_create, tab_logs = st.tabs(["📋 用户列表", "➕ 创建用户", "📝 操作日志"])

# ----------------------------------------------------------------- 用户列表
with tab_users:
    col_search, col_refresh = st.columns([3, 1])
    with col_search:
        keyword = st.text_input("搜索用户名", value=st.session_state["user_mgmt_keyword"],
                                key="user_search_input", placeholder="输入用户名关键词")
    with col_refresh:
        if st.button("🔄 刷新", width="stretch"):
            st.session_state["user_mgmt_keyword"] = keyword
            st.rerun()

    st.session_state["user_mgmt_keyword"] = keyword
    page = st.session_state["user_mgmt_page"]

    # 加法式健壮性：api_get 返回 (code, body) 元组，body 可能为 None（网络/服务异常）。
    # 直接 resp.get 会抛 AttributeError 导致整页崩溃，先兜底为空字典。
    code, resp = get_users(page=page, per_page=20, keyword=keyword)
    resp = resp or {}
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取用户列表失败: {resp.get('message', '未知错误')}")
    else:
        data = resp["data"]
        items = data["items"]
        total = data["total"]
        pages = data["pages"]

        if not items:
            _empty_info("暂无用户数据。点击「创建用户」标签，填写用户名与密码即可新增账户。")
        else:
            st.caption(f"共 {total} 个用户 · 第 {page}/{pages} 页")
            for u in items:
                with st.container(border=True):
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 2])
                    with col1:
                        role_icon = "🛡️" if u.get("role") == "admin" else "👤"
                        status = "🟢" if u.get("is_active") else "🔴"
                        st.markdown(f"{role_icon} **{u.get('username','')}** {status}")
                    with col2:
                        st.caption(f"ID: {u.get('id','')}")
                        _created = u.get("created_at") or ""
                        st.caption(f"创建: {_created[:10]}")
                    with col3:
                        st.caption(f"角色: `{u.get('role','')}`")
                    with col4:
                        st.caption(f"状态: {'正常' if u.get('is_active') else '停用'}")
                    with col5:
                        col_edit, col_del = st.columns(2)
                        with col_edit:
                            if st.button("✏️ 编辑", key=f"edit_{u.get('id')}"):
                                st.session_state["editing_user"] = u
                                st.rerun()
                        with col_del:
                            current = get_user() or {}
                            if u.get("id") == current.get("id"):
                                st.button("🗑️ 删除", key=f"del_{u.get('id')}", disabled=True, help="不能删除自己")
                            elif u.get("username") == "admin":
                                st.button("🗑️ 删除", key=f"del_{u.get('id')}", disabled=True, help="不能删除初始管理员")
                            else:
                                if st.button("🗑️ 删除", key=f"del_{u.get('id')}", type="secondary"):
                                    st.session_state["deleting_user"] = u
                                    st.rerun()

            # 分页
            col_prev, col_info, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("⬅️ 上一页", disabled=(page <= 1)):
                    st.session_state["user_mgmt_page"] = page - 1
                    st.rerun()
            with col_info:
                st.caption(f"第 {page} / {pages} 页")
            with col_next:
                if st.button("➡️ 下一页", disabled=(page >= pages)):
                    st.session_state["user_mgmt_page"] = page + 1
                    st.rerun()

# ----------------------------------------------------------------- 创建用户
with tab_create:
    st.subheader("创建新用户")
    st.caption("填写用户名与密码创建新账户；管理员可分配 user / admin 角色。")
    with st.form("create_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("用户名", placeholder="2-32位，字母数字下划线中文",
                                        help="登录用户名，2-32 位，支持字母、数字、下划线、中文。")
        with col2:
            new_password = st.text_input("密码", type="password", placeholder="至少6位",
                                        help="登录密码，至少 6 位。")

        new_role = st.selectbox("角色", ["user", "admin"],
                                format_func=lambda x: "👤 普通用户 (user)" if x == "user" else "🛡️ 管理员 (admin)",
                                help="user 仅能管理自己的数据；admin 拥有用户与系统配置管理权限。")

        # 加法式 UX：用户名或密码为空时禁用「创建用户」按钮（前置校验），
        # 避免空提交后才有错误提示；同时保留下方错误分支作为兜底。
        _can_create = bool((new_username or "").strip()) and bool((new_password or "").strip())
        submitted = st.form_submit_button(
            "✅ 创建用户", type="primary",
            disabled=not _can_create,
            help="填写用户名与密码（均不为空）后方可点击创建。",
        )
        if submitted:
            if not _can_create:
                st.error("用户名和密码不能为空")
            else:
                code, resp = create_user(new_username, new_password, new_role)
                resp = resp or {}  # 加法式健壮性：网络/服务异常时 resp 可能为 None，先兜底避免下方 .get 抛 AttributeError
                if code == 200 and resp.get("status") == "ok":
                    st.success(f"✅ 用户 `{new_username}` 创建成功！")
                    st.balloons()
                else:
                    st.error(f"创建失败: {resp.get('message', '未知错误')}")

# ----------------------------------------------------------------- 编辑弹窗
if "editing_user" in st.session_state:
    u = st.session_state["editing_user"]
    with st.dialog(f"编辑用户 - {u.get('username','')}", width="medium"):
        st.caption(f"ID: {u.get('id','')} · 创建于: {str(u.get('created_at') or '')[:10]}")

        edit_role = st.selectbox("角色", ["user", "admin"],
                                 index=0 if u.get("role", "user") == "user" else 1,
                                 format_func=lambda x: "👤 普通用户" if x == "user" else "🛡️ 管理员",
                                 key="edit_role_select",
                                 help="修改该用户的角色权限。")

        edit_active = st.checkbox("账号激活", value=bool(u.get("is_active", False)), key="edit_active_check",
                                 help="取消勾选将停用该账号，停用后无法登录。")

        st.markdown("---")
        st.caption("重置密码（留空则不修改）")
        edit_password = st.text_input("新密码", type="password", placeholder="至少6位", key="edit_pwd_input")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("💾 保存", type="primary", width="stretch"):
                payload = {"role": edit_role, "is_active": edit_active}
                if edit_password:
                    payload["password"] = edit_password
                code, resp = update_user(u.get("id"), **payload)
                resp = resp or {}
                if code == 200 and resp.get("status") == "ok":
                    st.success("更新成功！")
                    del st.session_state["editing_user"]
                    st.rerun()
                else:
                    st.error(f"更新失败: {resp.get('message', '未知错误')}")
        with col_cancel:
            if st.button("取消", width="stretch"):
                del st.session_state["editing_user"]
                st.rerun()

# ----------------------------------------------------------------- 删除确认
if "deleting_user" in st.session_state:
    u = st.session_state["deleting_user"]
    with st.dialog("⚠️ 确认删除", width="small"):
        st.warning(f"确定要删除用户 **{u.get('username', '该用户')}** (ID: {u.get('id', '?')}) 吗？")
        st.caption("此操作不可撤销。")
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("🗑️ 确认删除", type="primary"):
                code, resp = delete_user(u["id"])
                resp = resp or {}
                if code == 200 and resp.get("status") == "ok":
                    st.success("删除成功！")
                    del st.session_state["deleting_user"]
                    st.rerun()
                else:
                    st.error(f"删除失败: {resp.get('message', '未知错误')}")
        with col_cancel:
            if st.button("取消"):
                del st.session_state["deleting_user"]
                st.rerun()

# ----------------------------------------------------------------- 操作日志
with tab_logs:
    # 加法式便利：提供手动刷新按钮，便于后端产生新日志后立即拉取，而无需整页交互触发。
    if st.button("🔄 刷新日志", key="log_refresh_btn",
                 help="重新从后端拉取最新操作日志"):
        st.rerun()
    page = st.session_state["log_page"]
    # 加法式健壮性：与用户列表同理，body 可能为 None，先兜底避免 AttributeError。
    code, resp = get_logs(page=page, per_page=20)
    resp = resp or {}
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取日志失败: {resp.get('message', '未知错误')}")
    else:
        data = resp["data"]
        items = data["items"]
        total = data["total"]
        pages = data["pages"]

        st.caption(f"共 {total} 条日志 · 第 {page}/{pages} 页")

        if not items:
            _empty_info("暂无操作日志。创建、编辑或删除用户后，相关操作会记录在这里。")
        else:
            for log in items:
                action_color = {
                    "create_user": "🟢",
                    "update_user": "🟡",
                    "delete_user": "🔴",
                }.get(log.get("action"), "⚪")
                _ltime = (log.get("created_at") or "")[:19]
                st.markdown(
                    f"{action_color} `{_ltime}` "
                    f"**{log.get('username','')}** → {log.get('action','')} "
                    f"→ `{log.get('target','')}`"
                )
                if log.get("detail"):
                    st.caption(f"   └ {log['detail']}")

            col_prev, col_info, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("⬅️ 上一页", disabled=(page <= 1), key="log_prev"):
                    st.session_state["log_page"] = page - 1
                    st.rerun()
            with col_info:
                st.caption(f"第 {page} / {pages} 页")
            with col_next:
                if st.button("➡️ 下一页", disabled=(page >= pages), key="log_next"):
                    st.session_state["log_page"] = page + 1
                    st.rerun()
