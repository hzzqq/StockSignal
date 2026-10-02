"""
页面0：登录 / 注册（T-196a 阿里云登录页改版）
调 Flask 后端 /api/auth/login 拿 JWT，存到 st.session_state 供各业务页面共享。
登录成功后跳到「行情看板」首页。

注册：POST /api/auth/register，新用户角色固定为 user（后端强制，不可自提权）。

T-196a 阿里云化（参考 account.aliyun.com/login）：
  · 大标题区（卡上方居中：渐变强调 + 数据副标题）
  · 白色大卡左右分栏：左品牌价值区 ｜ 右表单区（账号登录 / 注册 Tab）
  · 「立即登录」通栏主色大按钮、忘记密码/演示账号入品牌区
  · 页脚法律声明式链接行
  · 全部配色走风格变量，六套主题自动适配
  · 登录/注册逻辑与旧版逐行一致（仅重排版，不改任何请求/校验行为）
"""

import streamlit as st
import requests
from modules.session import init_session_state, is_authenticated, set_auth, clear_auth, safe_switch_page, API_BASE
from modules.widgets import password_strength

from modules.ui_theme import apply_page_config
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner
apply_page_config(page_title="登录", page_icon="🔐", layout="centered")
st.session_state["_active_page"] = __file__
init_session_state()

# ── 阿里云登录页样式（T-196a，变量驱动六风格适配）──
st.markdown(
    """
    <style>
    .al-hero{text-align:center;margin:6px 0 24px}
    .al-hero h1{font-size:2.3rem;font-weight:900;color:var(--txt);margin:0 0 6px}
    .al-hero h1 .al-grad{background:linear-gradient(90deg,var(--acc1),var(--acc2));
      -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
    .al-hero p{font-size:1.02rem;color:var(--txt2);margin:0}
    .al-hero p b{color:var(--acc1);font-weight:800}
    .al-brand-card{background:var(--card);border:1px solid color-mix(in srgb,var(--acc1) 25%,var(--border));
      border-radius:10px;padding:22px 20px;height:100%}
    .al-brand-card .al-logo{font-size:2rem;margin-bottom:6px}
    .al-brand-card h3{margin:0 0 14px;color:var(--txt);font-size:1.05rem}
    .al-sell{display:flex;gap:8px;align-items:flex-start;margin:10px 0;font-size:.9rem;
      color:var(--txt);line-height:1.5}
    .al-sell .al-check{color:var(--acc1);font-weight:800}
    .al-sell small{display:block;color:var(--txt2);font-size:.78rem}
    .al-badge{display:inline-block;background:color-mix(in srgb,var(--acc1) 12%,transparent);
      color:var(--acc1);border:1px solid color-mix(in srgb,var(--acc1) 35%,transparent);
      border-radius:999px;padding:.4rem .9rem;font-size:.78rem;font-weight:600;margin-top:14px}
    .al-quick{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 2px}
    .al-quick .stButton button{border-radius:6px;font-size:.8rem;padding:.3rem .6rem!important}
    .al-footer{text-align:center;color:var(--txt2);font-size:.78rem;margin-top:26px;
      border-top:1px solid var(--border);padding-top:14px}
    .al-footer a{color:var(--txt2);margin:0 10px;text-decoration:none}
    .al-footer a:hover{color:var(--acc1)}
    </style>
    """,
    unsafe_allow_html=True,
)

# 已登录用户访问 /登录 时直接跳走（避免重复登录）
if is_authenticated():
    xc_success_box(f"✅ 已登录为 **{st.session_state['auth_user']['username']}**（{st.session_state['auth_user']['role']}）")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📈 进入行情看板", width="stretch"):
            safe_switch_page("pages/10_行情看板.py")
    with col_b:
        if st.button("🚪 退出登录", width="stretch"):
            clear_auth()
            st.rerun()
    st.stop()

# ── 大标题区（阿里云式：渐变强调 + 数据副标题）──
st.markdown(
    """
    <div class="al-hero">
      <h1><span class="al-grad">📊 决策</span> 放心交给 StockSignal</h1>
      <p>超过 <b>3,300+</b> 条自动化测试护航 · <b>4,091</b> 日真实回测实证 · 方向命中率 <b>49.1%</b> 严格锚定</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# 后端健康检查：服务没起时给个明显提示（登录/注册都依赖后端，故置于标签之前）
try:
    health = requests.get(f"{API_BASE}/api/health", timeout=2)
    if health.status_code != 200:
        st.error(f"后端健康检查失败 (HTTP {health.status_code})。请确认 Flask 已启动：")
        st.code("python -m flask --app backend.app:app run --host 127.0.0.1 --port 5050")
        st.stop()
except Exception as e:  # noqa: BLE001 - 任何连接/网络异常都降级为友好提示，不抛未捕获异常
    st.error(f"❌ 无法连接后端服务 ({API_BASE})")
    st.code(f"错误: {e}\n\n请先启动 Flask：\npython -m flask --app backend.app:app run --host 127.0.0.1 --port 5050")
    st.stop()

# ── 白色大卡：左品牌价值区 ｜ 右表单区（账号登录 / 注册）──
brand_col, form_col = st.columns([0.38, 0.62], gap="medium")

with brand_col:
    st.markdown(
        """
        <div class="al-brand-card">
          <div class="al-logo">📈</div>
          <h3>StockSignal · A股事件驱动投资分析平台</h3>
          <div class="al-sell"><span class="al-check">✓</span><span><b>四级数据源自动降级</b>
            <small>AKShare / BaoStock / 新浪 / 东财，单点故障不崩</small></span></div>
          <div class="al-sell"><span class="al-check">✓</span><span><b>可解释决策闭环</b>
            <small>每个仓位建议可分解到逐因子贡献，非黑箱</small></span></div>
          <div class="al-sell"><span class="al-check">✓</span><span><b>严格留出评估</b>
            <small>4,091 日真实回测，绝不用数据泄漏刷分</small></span></div>
          <div class="al-badge">🔑 默认演示账号：demo / Demo@123</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # 一键填账号（在品牌区底部，逻辑与旧版一致：点击后回填右侧表单）
    st.markdown('<div class="al-quick">', unsafe_allow_html=True)
    if st.button("🔧 管理员", key="fill_admin", help="自动填入 admin / Admin@123"):
        st.session_state["_login_username"] = "admin"
        st.session_state["_login_password"] = "Admin@123"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("🧪 一键填演示账号", width="stretch", key="fill_demo",
                 help="自动填入 demo / Demo@123"):
        st.session_state["_login_username"] = "demo"
        st.session_state["_login_password"] = "Demo@123"
        st.rerun()
    if st.button("🧹 清空输入", width="stretch", key="clear_login_input",
                 help="清除一键填入的账号与密码，方便手动重新输入。"):
        for _k in ("_login_username", "_login_password"):
            st.session_state.pop(_k, None)
        st.rerun()

with form_col:
    # ── 登录 / 注册 两个标签（阿里云式 Tab：账密登录 / 注册）──
    login_tab, register_tab = st.tabs(["🔑 账号登录", "📝 注册"])

    # ============================ 登录标签 ============================
    with login_tab:
        # 登录表单（逻辑与旧版逐行一致）
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("用户名", placeholder="请输入用户名", autocomplete="username",
                                     value=st.session_state.get("_login_username", ""),
                                     help="输入已注册的用户名；可用左侧「一键填」按钮快速填入示例账号。")
            password = st.text_input("密码", type="password", placeholder="请输入密码",
                                     autocomplete="current-password",
                                     value=st.session_state.get("_login_password", ""),
                                     help="输入账户密码（输入时以掩码显示）。")
            remember = st.checkbox("记住我（关闭浏览器后仍可保持登录）", value=True,
                                   help="token 已保存在地址栏，刷新/重开浏览器无需重新登录")
            submit = st.form_submit_button("立即登录", width="stretch", type="primary",
                                           help="使用左侧一键填入的账号或手动输入的用户名 / 密码登录 StockSignal。")

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
                        # ⚠️ 兜底：content-type 声明 json 但响应体为空/损坏时 resp.json() 会抛 JSONDecodeError
                        try:
                            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                        except ValueError:
                            body = {}
                        if resp.status_code == 200 and body.get("status") == "ok":
                            # ⚠️ 深层守卫：后端可能返回 status=ok 但 data 缺 token/user 字段
                            _data = body.get("data") or {}
                            token = _data.get("token")
                            user = _data.get("user")
                            if not token or not isinstance(user, dict):
                                st.error("❌ 登录成功但服务端返回数据不完整，请重试或联系管理员。")
                            else:
                                set_auth(token, user)
                                st.session_state["_remember_me"] = remember
                                xc_success_box(f"✅ 登录成功！欢迎 {user.get('username', '用户')}")
                                st.balloons()
                                # 跳到第一个业务页
                                safe_switch_page("pages/10_行情看板.py")
                        elif resp.status_code == 429:
                            # 后端已做 60s/5 次限流
                            st.error("⏳ 登录尝试过于频繁，请 60 秒后再试（防爆破保护已启用）")
                        else:
                            # 前端尝试计数提示
                            tries = st.session_state.get("_login_tries", 0) + 1
                            st.session_state["_login_tries"] = tries
                            remain = max(0, 5 - tries)
                            msg = body.get("message") or f"HTTP {resp.status_code}"
                            suffix = f"（剩余尝试次数约 {remain} 次，过多将临时锁定）" if remain > 0 else ""
                            st.error(f"❌ 登录失败：{msg}{suffix}")
                    except requests.exceptions.Timeout:
                        st.error("❌ 登录请求超时，请检查后端服务")
                    except requests.exceptions.RequestException as e:
                        xc_handle_error("网络错误", e, hint="请稍后重试，或检查网络与数据源连接")

        # 忘记密码（离线环境无邮件服务，提供引导）
        with st.expander("❓ 忘记密码？", expanded=False):
            st.info(
                "当前为离线演示环境，未接入邮件/短信服务，暂不支持在线重置密码。\n\n"
                "**处理方式：**\n"
                "1. 可使用左侧「演示账号」一键登录体验；\n"
                "2. 管理员可在「用户管理」中为该账号重置密码；\n"
                "3. 生产环境可接入邮件服务后开放自助重置。"
            )

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
        new_username = st.text_input(
            "用户名", key="reg_username", placeholder="2-32位，字母/数字/下划线/中文",
            autocomplete="username",
            help="用户名长度 2-32 位，仅支持字母、数字、下划线或中文。",
        )
        new_password = st.text_input(
            "密码", type="password", key="reg_password", placeholder="至少 6 位",
            autocomplete="new-password",
            help="密码至少 6 位；下方实时显示强度，建议包含大小写字母与数字。",
        )
        # 实时密码强度
        if new_password:
            score, level = password_strength(new_password)
            st.progress(score / 4.0, text=f"密码强度：{level}")
        confirm_password = st.text_input(
            "确认密码", type="password", key="reg_confirm", placeholder="再次输入密码",
            autocomplete="new-password",
            help="请再次输入相同密码以完成注册校验。",
        )
        agree = st.checkbox(
            "我已阅读并同意《用户协议》与《隐私政策》",
            key="reg_agree",
            help="注册即表示你同意平台的服务条款与隐私声明",
        )

        if st.button("📝 注册", width="stretch", type="primary", key="reg_submit"):
            if not agree:
                st.error("请先勾选同意《用户协议》与《隐私政策》")
            elif not new_username or not new_password or not confirm_password:
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
                    # ⚠️ 兜底：同登录分支，content-type 为 json 但响应体损坏时 resp.json() 抛异常
                    try:
                        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    except ValueError:
                        body = {}
                    if resp.status_code in (200, 201) and body.get("status") == "ok":
                        reg_name = (body.get("data") or {}).get("username", new_username)
                        xc_success_box(f"✅ 注册成功！欢迎 {reg_name}，请切换到「登录」标签登录。")
                        # 回填登录表单，方便直接登录
                        st.session_state["_login_username"] = reg_name
                        st.session_state["_login_password"] = new_password
                        info_banner("已为你填入账号信息，可切回「登录」标签直接登录。")
                    else:
                        msg = body.get("message") or f"HTTP {resp.status_code}"
                        st.error(f"❌ 注册失败：{msg}")
                except requests.exceptions.Timeout:
                    st.error("❌ 注册请求超时，请检查后端服务")
                except requests.exceptions.RequestException as e:
                    xc_handle_error("网络错误", e, hint="请稍后重试，或检查网络与数据源连接")

        st.caption("注册遇到问题？可使用「账号登录」标签的演示账号直接体验。")

# ── 页脚（阿里云式法律声明链接行）──
st.markdown(
    """
    <div class="al-footer">
      <a href="https://github.com/hzzqq/StockSignal" target="_blank">开源仓库</a>
      <a href="/新手教程">使用教程</a>
      <span>仅供学习与研究所用 · 不构成任何投资建议</span>
      <span>StockSignal · A股事件驱动投资分析平台</span>
    </div>
    """,
    unsafe_allow_html=True,
)
