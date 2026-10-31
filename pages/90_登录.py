"""
页面0：登录 / 注册（T-196a 改版 + T-367 登录页行情台）

调 Flask 后端 /api/auth/login 拿 JWT，存到 st.session_state 供各业务页面共享。
登录成功后跳到「行情看板」首页。

注册：POST /api/auth/register，新用户角色固定为 user（后端强制，不可自提权）。

T-196a：阿里云式分栏登录（左品牌价值区 ｜ 右表单区），六风格变量适配，逻辑逐行一致。
T-367：登录前即可见「今日市场实时变化」——左栏升级为行情台（资金温度 / 今日市场广度 /
      AI 信号 + 真实上证指数抓取），数据零网络优先用 daily_snapshot.json，真实上证指数
      走内联 2.5s 超时抓取、失败优雅降级为快照广度（绝不编造数字）。

诚实红线：验证码登录 Tab 在离线演示环境未接入短信网关，明确标注不可用，不做假功能。
"""

import streamlit as st
import requests
from modules.session import init_session_state, is_authenticated, set_auth, clear_auth, safe_switch_page, API_BASE
from modules.widgets import password_strength
from modules import decision as _decision

from modules.ui_theme import apply_page_config
from modules.ui_kit import xc_handle_error, xc_success_box, xc_warn_box, info_banner, xc_error_box
apply_page_config(page_title="登录", page_icon="🔐", layout="wide")
st.session_state["_active_page"] = __file__
init_session_state()


# ── 登录页行情台数据（T-367）：零网络优先 + 真实上证指数短超时抓取 ──
@st.cache_data(ttl=60, show_spinner=False)
def _login_market_pulse() -> dict:
    """登录页市场行情台数据。

    - 主体来自本地 daily_snapshot.json（零网络、永远可用，是「今日」的单一真理源）。
    - 真实上证指数走内联 urllib 抓取（新浪，2.5s 超时）；失败/离线返回 None，
      此时左栏用快照广度兜底并显式标注「今日快照」，绝不回填伪造的指数数字。
    """
    snap = {}
    try:
        snap = _decision.load_snapshot() or {}
    except Exception:  # noqa: BLE001
        snap = {}
    ind = snap.get("indicators") or {}
    ef = snap.get("event_factor") or {}
    return {
        "date": snap.get("date") or "—",
        "temperature": snap.get("temperature"),
        "cycle": snap.get("cycle") or "—",
        "bias": snap.get("bias") or "—",
        "long_count": ef.get("long_count"),
        "up": ind.get("up_count"),
        "down": ind.get("down_count"),
        "limit_up": ind.get("limit_up"),
        "limit_down": ind.get("limit_down"),
        "red_ratio": ind.get("red_ratio"),
        "median_chg": ind.get("median_chg"),
        "index": _fetch_sh_index(),
    }


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_sh_index() -> dict | None:
    """真实上证指数（sh000001）实时报价。2.5s 超时，任何失败返回 None。"""
    try:
        import urllib.request
        url = "https://hq.sinajs.cn/list=sh000001"
        req = urllib.request.Request(
            url,
            headers={
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=2.5) as r:
            text = r.read().decode("gbk", "replace")
        s = text.find('"')
        e = text.find('"', s + 1)
        if s == -1 or e == -1:
            return None
        parts = text[s + 1:e].split(",")
        if len(parts) < 32:
            return None
        current = float(parts[3])
        prev = float(parts[2])
        chg = current - prev
        pct = chg / prev * 100 if prev else 0.0
        return {
            "name": parts[0],
            "current": current,
            "prev_close": prev,
            "chg": chg,
            "pct": pct,
            "time": parts[30] if len(parts) > 30 else "",
        }
    except Exception:  # noqa: BLE001 - 离线/超时/解析失败一律降级
        return None


def _render_market_desk(m: dict) -> None:
    """左侧行情台面板（T-367）：资金温度 + 今日市场 + AI 信号。"""
    temp = m.get("temperature")
    temp_val = f"{temp:.0f}" if isinstance(temp, (int, float)) else "—"
    temp_w = max(0, min(100, temp)) if isinstance(temp, (int, float)) else 0
    idx = m.get("index")
    if isinstance(idx, dict):
        _ic = "lg-up" if idx.get("chg", 0) >= 0 else "lg-down"
        _iv = f"{idx.get('current', 0):.2f}"
        _ichg = f"{idx.get('chg', 0):+.2f}　({idx.get('pct', 0):+.2f}%)"
        _itag = f"实时 · {idx.get('time', '')[:5]}"
    else:
        _ic = ""
        _iv = "—"
        _ichg = "实时行情获取中"
        _itag = "今日快照（离线）"
    up = m.get("up"); down = m.get("down")
    lu = m.get("limit_up"); ld = m.get("limit_down")
    rr = m.get("red_ratio"); mc = m.get("median_chg")
    lc = m.get("long_count")
    _rr_s = f"{rr:.1f}" if isinstance(rr, (int, float)) else "—"
    _mc_s = f"{mc:+.2f}" if isinstance(mc, (int, float)) else "—"
    st.markdown(
        f"""
        <div class="lg-desk">
          <div class="lg-desk-brand">
            <div class="lg-logo">📊</div>
            <div>
              <div class="lg-brand-name">StockSignal</div>
              <div class="lg-brand-sub">A股事件驱动投资分析平台</div>
            </div>
          </div>
          <p class="lg-desk-desc">登录前先一览今日市场温度与信号，决策不盲从。</p>

          <div class="lg-card">
            <div class="lg-card-h">🔥 资金温度</div>
            <div class="lg-gauge">
              <div class="lg-gauge-val">{temp_val}</div>
              <div class="lg-gauge-bar"><span style="width:{temp_w}%"></span></div>
            </div>
            <div class="lg-card-meta">情绪周期 · {m.get('cycle')}　|　次日方向 · {m.get('bias')}</div>
          </div>

          <div class="lg-card">
            <div class="lg-card-h">📈 今日市场 <span class="lg-tag">{m.get('date')}</span></div>
            <div class="lg-idx">
              <div class="lg-idx-name">上证指数 <span class="lg-tag">{_itag}</span></div>
              <div class="lg-idx-val {_ic}">{_iv}</div>
              <div class="lg-idx-chg {_ic}">{_ichg}</div>
            </div>
            <div class="lg-breadth">
              <div><span class="lg-up">▲ {up if up is not None else '—'}</span> 涨　/　<span class="lg-down">▼ {down if down is not None else '—'}</span> 跌</div>
              <div>涨停 <b>{lu if lu is not None else '—'}</b>　跌停 <b>{ld if ld is not None else '—'}</b></div>
              <div>红绿比 <b>{_rr_s}%</b>　中位 <b>{_mc_s}%</b></div>
            </div>
          </div>

          <div class="lg-card">
            <div class="lg-card-h">🤖 AI 信号</div>
            <div class="lg-ai">情绪周期 <b>{m.get('cycle')}</b>　·　方向 <b>{m.get('bias')}</b></div>
            <div class="lg-ai-clue">📡 {lc if lc is not None else '—'} 条事件线索在看板中生效</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── 登录页样式（T-196a + T-367 行情台，变量驱动六风格适配）──
st.markdown(
    """
    <style>
    .lg-wrap{max-width:1160px;margin:0 auto;padding-top:1.2rem}
    .lg-title{text-align:center;margin:0 0 22px}
    .lg-title h1{font-size:2.1rem;font-weight:900;color:var(--txt);margin:0 0 6px}
    .lg-title h1 .lg-grad{background:linear-gradient(90deg,var(--acc1),var(--acc2));
      -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
    .lg-title p{font-size:1rem;color:var(--txt2);margin:0}
    .lg-title p b{color:var(--acc1);font-weight:800}
    .lg-desk{background:linear-gradient(160deg,color-mix(in srgb,var(--acc1) 10%,var(--card)) 0%,var(--card) 100%);
      border:1px solid color-mix(in srgb,var(--acc1) 28%,var(--border));
      border-radius:18px;padding:1.5rem 1.4rem;height:100%}
    .lg-desk-brand{display:flex;align-items:center;gap:.7rem;margin-bottom:.6rem}
    .lg-logo{font-size:2rem}
    .lg-brand-name{font-size:1.25rem;font-weight:800;color:var(--txt)}
    .lg-brand-sub{font-size:.82rem;color:var(--txt2)}
    .lg-desk-desc{font-size:.86rem;color:var(--txt2);line-height:1.6;margin:0 0 1.1rem}
    .lg-card{background:color-mix(in srgb,var(--acc1) 5%,var(--card));
      border:1px solid var(--border);border-radius:14px;padding:.95rem 1rem;margin-bottom:.85rem}
    .lg-card-h{font-size:.92rem;font-weight:700;color:var(--txt);margin-bottom:.6rem;
      display:flex;align-items:center;gap:.4rem}
    .lg-tag{font-size:.66rem;font-weight:600;color:var(--acc1);
      background:color-mix(in srgb,var(--acc1) 12%,transparent);
      border:1px solid color-mix(in srgb,var(--acc1) 30%,transparent);
      border-radius:999px;padding:.1rem .5rem;margin-left:.3rem}
    .lg-gauge{display:flex;align-items:center;gap:.8rem}
    .lg-gauge-val{font-size:2rem;font-weight:900;color:var(--acc1);min-width:62px;text-align:center}
    .lg-gauge-bar{flex:1;height:10px;border-radius:999px;background:color-mix(in srgb,var(--acc1) 14%,var(--border));overflow:hidden}
    .lg-gauge-bar span{display:block;height:100%;border-radius:999px;
      background:linear-gradient(90deg,var(--acc1),var(--acc2))}
    .lg-card-meta{font-size:.76rem;color:var(--txt2);margin-top:.6rem}
    .lg-idx{display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap;margin-bottom:.6rem}
    .lg-idx-name{font-size:.82rem;color:var(--txt2)}
    .lg-idx-val{font-size:1.6rem;font-weight:900;color:var(--txt)}
    .lg-idx-chg{font-size:.92rem;font-weight:700}
    .lg-up{color:#ee2a2a!important}   /* A股惯例：涨红 */
    .lg-down{color:#00b96b!important} /* A股惯例：跌绿 */
    .lg-breadth{font-size:.8rem;color:var(--txt2);line-height:1.7}
    .lg-breadth b{color:var(--txt)}
    .lg-ai{font-size:.86rem;color:var(--txt);margin-bottom:.4rem}
    .lg-ai b{color:var(--acc1)}
    .lg-ai-clue{font-size:.78rem;color:var(--txt2)}
    .lg-form{max-width:420px;margin:0 auto}
    .lg-quick{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0 2px}
    .lg-quick .stButton button{border-radius:6px;font-size:.8rem;padding:.3rem .6rem!important}
    .lg-footer{text-align:center;color:var(--txt2);font-size:.78rem;margin-top:26px;
      border-top:1px solid var(--border);padding-top:14px}
    .lg-footer a{color:var(--txt2);margin:0 10px;text-decoration:none}
    .lg-footer a:hover{color:var(--acc1)}
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
    <div class="lg-title">
      <h1><span class="lg-grad">📊 决策</span> 放心交给 StockSignal</h1>
      <p>超过 <b>3,300+</b> 条自动化测试护航 · <b>4,091</b> 日真实回测实证 · 方向命中率 <b>49.1%</b> 严格锚定</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# 后端健康检查：服务没起时给个明显提示（登录/注册都依赖后端，故置于标签之前）
FLASK_CMD = "python -m flask --app backend.app:app run --host 127.0.0.1 --port 5050"
try:
    health = requests.get(
        f"{API_BASE}/api/health", timeout=2,
        proxies={"http": None, "https": None},
    )
    if health.status_code != 200:
        xc_error_box(
            f"❌ 后端健康检查失败 (HTTP {health.status_code})",
            hint="请确认 Flask 后端已启动，然后刷新本页。启动命令已附在下方，可一键复制。",
        )
        st.code(FLASK_CMD, language="bash")
        st.stop()
except Exception as e:  # noqa: BLE001
    xc_handle_error(
        f"❌ 无法连接后端服务 ({API_BASE})",
        exc=e,
        hint="请先启动 Flask 后端，再刷新本页。启动命令已附在下方，可一键复制。",
    )
    st.code(FLASK_CMD, language="bash")
    st.stop()

# ── 分栏：左行情台 ｜ 右登录表单 ──
_mkt = _login_market_pulse()
desk_col, form_col = st.columns([0.46, 0.54], gap="large")

with desk_col:
    _render_market_desk(_mkt)

with form_col:
    st.markdown('<div class="lg-form">', unsafe_allow_html=True)
    # ── 登录方式 Tab：密码登录 / 验证码登录 / 注册 ──
    # 验证码登录在离线演示环境未接入短信网关，Tab 内明确标注不可用（诚实红线，不做假功能）。
    tab_pwd, tab_sms, tab_reg = st.tabs(["🔑 密码登录", "📲 验证码登录", "📝 注册"])

    # ============================ 密码登录 ============================
    with tab_pwd:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("用户名", placeholder="请输入用户名", autocomplete="username",
                                     value=st.session_state.get("_login_username", ""),
                                     help="输入已注册的用户名；可用下方「一键填」按钮快速填入示例账号。")
            password = st.text_input("密码", type="password", placeholder="请输入密码",
                                     autocomplete="current-password",
                                     value=st.session_state.get("_login_password", ""),
                                     help="输入账户密码（输入时以掩码显示）。")
            remember = st.checkbox("记住我（关闭浏览器后仍可保持登录）", value=True,
                                   help="token 已保存在地址栏，刷新/重开浏览器无需重新登录")
            submit = st.form_submit_button("立即登录", width="stretch", type="primary",
                                           help="使用一键填入的账号或手动输入的用户名 / 密码登录 StockSignal。")

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
                        try:
                            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                        except ValueError:
                            body = {}
                        if resp.status_code == 200 and body.get("status") == "ok":
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
                                safe_switch_page("pages/10_行情看板.py")
                        elif resp.status_code == 429:
                            st.error("⏳ 登录尝试过于频繁，请 60 秒后再试（防爆破保护已启用）")
                        else:
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

        with st.expander("❓ 忘记密码？", expanded=False):
            st.info(
                "当前为离线演示环境，未接入邮件/短信服务，暂不支持在线重置密码。\n\n"
                "**处理方式：**\n"
                "1. 可使用下方「演示账号」一键登录体验；\n"
                "2. 管理员可在「用户管理」中为该账号重置密码；\n"
                "3. 生产环境可接入邮件服务后开放自助重置。"
            )
        with st.expander("💡 默认演示账号", expanded=False):
            st.markdown("""
            | 用户名 | 密码 | 角色 |
            |---|---|---|
            | `admin` | `Admin@123` | admin（管理员） |
            | `demo` | `Demo@123` | user（普通用户） |

            后端在开发态会预置这两个账号；生产环境请删除并通过管理接口创建。
            """)

    # ============================ 验证码登录（离线未接入） ============================
    with tab_sms:
        st.info("📲 **验证码登录**（演示环境说明）\n\n"
                 "当前为离线演示环境，**未接入短信网关**，验证码登录暂不可用。\n\n"
                 "请使用左侧「密码登录」Tab 输入账号密码，或一键填入下方演示账号登录体验。")
        sms_phone = st.text_input("手机号", placeholder="请输入注册手机号", key="sms_phone",
                                  help="离线演示环境不发送短信，此处仅作界面演示")
        if st.button("获取验证码", width="stretch", key="sms_get", disabled=True,
                     help="离线演示环境未接入短信网关，按钮已禁用"):
            pass

    # ============================ 注册 ============================
    with tab_reg:
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
                    try:
                        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    except ValueError:
                        body = {}
                    if resp.status_code in (200, 201) and body.get("status") == "ok":
                        reg_name = (body.get("data") or {}).get("username", new_username)
                        xc_success_box(f"✅ 注册成功！欢迎 {reg_name}，请切换到「密码登录」标签登录。")
                        st.session_state["_login_username"] = reg_name
                        st.session_state["_login_password"] = new_password
                        info_banner("已为你填入账号信息，可切回「密码登录」标签直接登录。")
                    else:
                        msg = body.get("message") or f"HTTP {resp.status_code}"
                        st.error(f"❌ 注册失败：{msg}")
                except requests.exceptions.Timeout:
                    st.error("❌ 注册请求超时，请检查后端服务")
                except requests.exceptions.RequestException as e:
                    xc_handle_error("网络错误", e, hint="请稍后重试，或检查网络与数据源连接")
        st.caption("注册遇到问题？可使用「密码登录」标签的演示账号直接体验。")

    # 一键填账号（表单底部，逻辑与旧版一致：点击后回填表单并重跑）
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="lg-quick">', unsafe_allow_html=True)
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

# ── 页脚（阿里云式法律声明链接行）──
st.markdown(
    """
    <div class="lg-footer">
      <a href="https://github.com/hzzqq/StockSignal" target="_blank">开源仓库</a>
      <a href="/新手教程">使用教程</a>
      <span>仅供学习与研究所用 · 不构成任何投资建议</span>
      <span>StockSignal · A股事件驱动投资分析平台</span>
    </div>
    """,
    unsafe_allow_html=True,
)
