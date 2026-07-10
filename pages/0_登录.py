"""
页面0：登录 / 注册
调 Flask 后端 /api/auth/login 拿 JWT，存到 st.session_state 供各业务页面共享。
登录成功后跳到「行情看板」首页。

注册：POST /api/auth/register，新用户角色固定为 user（后端强制，不可自提权）。
注意：本文件只新增「注册」标签页，登录逻辑完全不变。
"""

import streamlit as st
import requests
from modules.session import init_session_state, is_authenticated, set_auth, clear_auth, safe_switch_page, API_BASE

st.set_page_config(page_title="登录", page_icon="🔐", layout="centered")
init_session_state()

# 已登录用户访问 /登录 时直接跳走（避免重复登录）
if is_authenticated():
    st.success(f"✅ 已登录为 **{st.session_state['auth_user']['username']}**（{st.session_state['auth_user']['role']}）")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📈 进入行情看板", width="stretch"):
            safe_switch_page("pages/1_行情看板.py")
    with col_b:
        if st.button("🚪 退出登录", width="stretch"):
            clear_auth()
            st.rerun()
    st.stop()

st.title("🔐 StockSignal 登录")
st.caption(f"后端 API: `{API_BASE}`")

# 后端健康检查：服务没起时给个明显提示（登录/注册都依赖后端，故置于标签之前）
try:
    health = requests.get(f"{API_BASE}/api/health", timeout=2)
    if health.status_code != 200:
        st.error(f"后端健康检查失败 (HTTP {health.status_code})。请确认 Flask 已启动：")
        st.code("python -m flask --app backend.app:app run --host 127.0.0.1 --port 5050")
        st.stop()
except requests.exceptions.RequestException as e:
    st.error(f"❌ 无法连接后端服务 ({API_BASE})")
    st.code(f"错误: {e}\n\n请先启动 Flask：\npython -m flask --app backend.app:app run --host 127.0.0.1 --port 5050")
    st.stop()

st.markdown("---")

# ── 登录 / 注册 两个标签 ──
login_tab, register_tab = st.tabs(["🔑 登录", "📝 注册"])

# ============================ 登录标签 ============================
with login_tab:
    # 一键填入账号（在表单外，点击后回填表单）
    col_admin, col_demo = st.columns(2)
    with col_admin:
        if st.button("🔧 一键填管理员账号", width="stretch", help="自动填入 admin / Admin@123"):
            st.session_state["_login_username"] = "admin"
            st.session_state["_login_password"] = "Admin@123"
            st.rerun()
    with col_demo:
        if st.button("🧪 一键填演示账号", width="stretch", help="自动填入 demo / Demo@123"):
            st.session_state["_login_username"] = "demo"
            st.session_state["_login_password"] = "Demo@123"
            st.rerun()

    st.caption("点击上方按钮自动填入账号，再点登录即可")

    # 登录表单
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("用户名", placeholder="admin / demo", autocomplete="username",
                                 value=st.session_state.get("_login_username", ""))
        password = st.text_input("密码", type="password", placeholder="Admin@123 / Demo@123", autocomplete="current-password",
                                 value=st.session_state.get("_login_password", ""))
        submit = st.form_submit_button("🔑 登录", width="stretch", type="primary")

        if submit:
            if not username or not password:
                st.error("用户名和密码不能为空")
            else:
                try:
                    resp = requests.post(
                        f"{API_BASE}/api/auth/login",
                        json={"username": username, "password": password},
                        timeout=5,
                    )
                    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    if resp.status_code == 200 and body.get("status") == "ok":
                        token = body["data"]["token"]
                        user = body["data"]["user"]
                        set_auth(token, user)
                        st.success(f"✅ 登录成功！欢迎 {user['username']}")
                        st.balloons()
                        # 跳到第一个业务页
                        safe_switch_page("pages/1_行情看板.py")
                    else:
                        # 统一错误信息（后端已经统一中文，但做一次兜底）
                        msg = body.get("message") or f"HTTP {resp.status_code}"
                        st.error(f"❌ 登录失败：{msg}")
                except requests.exceptions.Timeout:
                    st.error("❌ 登录请求超时，请检查后端服务")
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ 网络错误：{e}")

    # 演示账号提示
    with st.expander("💡 默认演示账号", expanded=False):
        st.markdown("""
        | 用户名 | 密码 | 角色 |
        |---|---|---|
        | `admin` | `Admin@123` | admin（管理员） |
        | `demo` | `Demo@123` | user（普通用户） |

        后端在开发态会预置这两个账号；生产环境请删除并通过管理接口创建。
        """)

# ============================ 注册标签 ============================
with register_tab:
    st.markdown("创建一个新账户（角色自动为 **普通用户**）。")
    with st.form("register_form", clear_on_submit=True):
        new_username = st.text_input(
            "用户名", placeholder="2-32位，字母/数字/下划线/中文",
            autocomplete="username",
        )
        new_password = st.text_input(
            "密码", type="password", placeholder="至少 6 位",
            autocomplete="new-password",
        )
        confirm_password = st.text_input(
            "确认密码", type="password", placeholder="再次输入密码",
            autocomplete="new-password",
        )
        submit_reg = st.form_submit_button("📝 注册", width="stretch", type="primary")

        if submit_reg:
            if not new_username or not new_password or not confirm_password:
                st.error("请填写用户名、密码和确认密码")
            elif new_password != confirm_password:
                st.error("两次输入的密码不一致")
            else:
                try:
                    resp = requests.post(
                        f"{API_BASE}/api/auth/register",
                        json={
                            "username": new_username,
                            "password": new_password,
                            "confirm": confirm_password,
                        },
                        timeout=5,
                    )
                    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    if resp.status_code in (200, 201) and body.get("status") == "ok":
                        reg_name = (body.get("data") or {}).get("username", new_username)
                        st.success(f"✅ 注册成功！欢迎 {reg_name}，请切换到「登录」标签登录。")
                        # 回填登录表单，方便直接登录
                        st.session_state["_login_username"] = reg_name
                        st.session_state["_login_password"] = new_password
                        st.info("已为你填入账号信息，可切回「登录」标签直接登录。")
                    else:
                        msg = body.get("message") or f"HTTP {resp.status_code}"
                        st.error(f"❌ 注册失败：{msg}")
                except requests.exceptions.Timeout:
                    st.error("❌ 注册请求超时，请检查后端服务")
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ 网络错误：{e}")

    st.caption("注册遇到问题？可使用上方「登录」标签的演示账号直接体验。")

# 页脚
st.markdown("---")
st.caption("StockSignal · A股事件驱动投资分析平台 · 需登录后使用")
