"""
modules/session.py
-----------------
Streamlit 跨页面 / 跨刷新持久化登录态。

核心机制：token 始终存于 URL query_params（浏览器地址栏）
- 登录成功 → token 写入 session_state + URL query_params
- 每次页面加载 → init_session_state() 先从 session_state 取；没有则从 URL query_params 恢复
  （F5 刷新时浏览器保留 URL，token 仍在 query_params 中 → 直接恢复，无需网络）
- 加载后立即把 token「回写」到 URL query_params，保证刷新瞬间 URL 一定带 token
- 退出登录 → 清除 query_params + session_state

为什么用 query_params 而不是 cookie / session_state / localStorage？
- session_state 在浏览器「完全刷新(F5)」且服务端 session 被 GC 时会丢，不可靠
- localStorage 兜底方案依赖 component iframe 注入 JS 跳转，但 Streamlit component iframe
  是 sandboxed 的（无 allow-top-navigation），window.parent.location 跳转会静默失败，不可靠
- query_params 随 URL 永远存在，刷新后仍然保留，是唯一可靠的「刷新保持登录」方案
- 注意：st.switch_page 默认会清空 query 参数！所以所有跳转必须用 safe_switch_page()
  带上 token，且每次页面加载都要 _sync_query_params() 重新补回

注意：
- init_session_state() 必须在每个页面最开头调用（除 st.set_page_config 外的第一个 st 调用）
- 写入 query_params 仅在值变化时触发 rerun，幂等，不会死循环
"""

from __future__ import annotations
import os
import json
import time
import jwt
import streamlit as st
import requests
from datetime import datetime

from .ui_theme import FONT_DEFAULT
from .page_guard import safe_fragment

# 后端 API 基地址。
# 本地开发默认 http://127.0.0.1:5050；容器化部署（docker-compose）下由
# STOCKSIGNAL_API_BASE=http://backend:5050 注入，前端容器借此跨容器访问后端。
API_BASE = os.environ.get("STOCKSIGNAL_API_BASE", "http://127.0.0.1:5050")


def trading_autorefresh(interval_ms: int = 60000, key: str = "auto_refresh"):
    """交易时段（工作日 09:30-11:30 / 13:00-15:00）自动刷新当前页面数据，避免数据陈旧。

    非交易时段（午休 / 收盘 / 周末）不刷新，避免无意义请求与界面闪烁。
    统一替换各页散落的 `from streamlit_autorefresh import st_autorefresh` + 交易时段判断。
    """
    try:
        from streamlit_autorefresh import st_autorefresh
    except Exception:
        return
    now = datetime.now()
    if now.weekday() >= 5:  # 周六 / 周日
        return
    t = now.time()
    morning = datetime.strptime("09:30", "%H:%M").time() <= t <= datetime.strptime("11:30", "%H:%M").time()
    afternoon = datetime.strptime("13:00", "%H:%M").time() <= t <= datetime.strptime("15:00", "%H:%M").time()
    if morning or afternoon:
        st_autorefresh(interval=interval_ms, limit=400, key=key)

KEY_TOKEN = "auth_token"
KEY_USER = "auth_user"
QP_TOKEN = "token"
QP_USER = "u"
QP_PREFS = "prefs"  # 用户偏好（主题/字体）持久化参数


def init_session_state() -> None:
    """
    在每个页面入口先调一次，从 session_state / query_params 恢复登录态。
    必须在页面最开头调用（任何其它 st.xxx 之前，st.set_page_config 之后）。

    刷新「保持登录」的根本机制：
    1) 登录成功 → token 写入 session_state + URL query_params
    2) 每次页面加载 → 先从 session_state 取；没有则从 URL query_params 恢复
       （F5 刷新时浏览器保留 URL，token 仍在 query_params 中 → 直接恢复，无需网络）
    3) 立刻把 token「回写」到 URL query_params，保证刷新瞬间 URL 一定带 token。
       （st.switch_page 默认会清空 query 参数，所以每次加载都要补回，
        否则导航后再刷新就会掉登录。）
    """
    if KEY_TOKEN not in st.session_state:
        st.session_state[KEY_TOKEN] = None
    if KEY_USER not in st.session_state:
        st.session_state[KEY_USER] = None

    # 1) session_state 里已有 → 直接用；否则 2) 从 URL query_params 恢复
    if not st.session_state[KEY_TOKEN]:
        _restore_from_query_params()

    # 3) 关键：把登录态回写到 URL，确保「刷新后状态和刷新前一模一样」
    _sync_query_params()

    # 4) 恢复用户偏好（主题 / 字体）：先试 URL query_params（刷新/导航可靠）；
    #    若 URL 无偏好但 localStorage 有（浏览器关闭后再打开），则从 localStorage 兜底恢复。
    _prefs = _restore_prefs_from_query_params()
    if _prefs:
        st.session_state.setdefault("theme_mode", _prefs.get("theme_mode", "light"))
        st.session_state.setdefault("font_size", _prefs.get("font_size", FONT_DEFAULT))
    else:
        try:
            from .prefs_persist import restore_prefs_from_local_storage
            restore_prefs_from_local_storage()
        except Exception as e:
            print(f"[session] restore_prefs error: {e}")
    _sync_prefs_query_params()

    # 记录当前页面作用域（供「个股分析」强制暗色等按页面生效的逻辑使用，
    # 不改写全局 theme_mode，避免访问该页后其它页面被意外变暗）。
    # _active_page 由各页面在顶部用 __file__ 设置，这里仅做兜底默认值。
    st.session_state.setdefault("_active_page", "")

    # 清理旧版侧边栏/嵌入相关缓存键，避免旧状态影响新导航（闪一下旧侧边栏）
    for _old_key in ("_embed_active", "_sidebar_collapsed", "_old_nav", "_nav_cache"):
        st.session_state.pop(_old_key, None)

    # 注入金融级 UI 主题（仅视觉，不影响任何功能逻辑）
    from .ui_theme import apply_theme
    apply_theme()


def _restore_from_query_params() -> None:
    """从 URL query_params 读取 token，恢复到 session_state。

    快速路径：URL 里直接带 user JSON，无需网络请求即可瞬时恢复（刷新立即生效）。
    兜底：调 /api/auth/me 校验 token 并取回 user。
    """
    try:
        qp = st.query_params
        token = qp.get(QP_TOKEN)
        if not token:
            return

        # 快速路径：直接还原 user（刷新无网络依赖）
        user = None
        raw_user = qp.get(QP_USER)
        if raw_user:
            try:
                user = json.loads(raw_user)
            except Exception:
                user = None

        # 兜底：URL 无 user 或解析失败 → 校验 token 取回
        if not isinstance(user, dict):
            user = _verify_token(token)

        if user:
            st.session_state[KEY_TOKEN] = token
            st.session_state[KEY_USER] = user
        else:
            # token 无效（过期/伪造）→ 清掉，避免反复校验
            _clear_query_params()
    except Exception as e:
        print(f"[session] _restore_from_query_params error: {e}")


def _sync_query_params() -> None:
    """
    把当前 session 里的 token/user 回写到 URL query_params。
    这是「刷新保持登录」的根本保障：无论怎样导航，页面加载后 URL 都会补回 token，
    下次 F5 时 query_params 直接恢复登录态，状态与刷新前完全一致。
    仅在值变化时写入，避免无意义的 rerun 死循环。
    """
    token = st.session_state.get(KEY_TOKEN)
    if not token:
        return
    try:
        qp = st.query_params
        if qp.get(QP_TOKEN) != token:
            qp[QP_TOKEN] = token
        user = st.session_state.get(KEY_USER)
        if user is not None:
            # 头像体积大（base64），不写进 URL，避免地址栏爆掉；
            # 刷新后由 /api/auth/me 重新拉取（见 get_avatar_data_url）。
            u_safe = {k: v for k, v in user.items() if k != "avatar"}
            u_str = json.dumps(u_safe, ensure_ascii=False)
            if qp.get(QP_USER) != u_str:
                qp[QP_USER] = u_str
    except Exception as e:
        print(f"[session] _sync_query_params error: {e}")


def safe_switch_page(page: str, **kwargs) -> None:
    """
    带登录态的页面跳转：在 query_params 里带上 token/user，
    避免 st.switch_page 默认清空 query 参数导致「导航后再刷新掉登录」。
    未登录时与普通 st.switch_page 行为一致（清空查询参数）。
    """
    token = st.session_state.get(KEY_TOKEN)
    user = st.session_state.get(KEY_USER)
    qp = {}
    # 保留当前所有 query 参数（主题/字体偏好等），避免导航后丢失
    try:
        for k, v in st.query_params.items():
            qp[k] = v
    except Exception:
        pass
    if token:
        qp[QP_TOKEN] = token
        if user is not None:
            qp[QP_USER] = json.dumps(user, ensure_ascii=False)
    if qp:
        st.switch_page(page, query_params=qp, **kwargs)
    else:
        st.switch_page(page, **kwargs)


def _verify_token(token: str) -> dict | None:
    """调 /api/auth/me 验证 token 是否有效，返回 user dict（有效）或 None（无效）。"""
    try:
        resp = requests.get(
            f"{API_BASE}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") == "ok":
                data = body.get("data") or {}
                # /api/auth/me 返回 data 即为 user 对象（扁平结构）
                if isinstance(data, dict) and "username" in data:
                    return data
                # 兼容：若 data 内仍嵌套 user 键
                if isinstance(data, dict) and isinstance(data.get("user"), dict):
                    return data["user"]
    except Exception:
        pass
    return None


def set_auth(token: str, user: dict) -> None:
    """登录 / 注册成功时调用：写入 session_state + URL query_params + 浏览器 localStorage。"""
    st.session_state[KEY_TOKEN] = token
    st.session_state[KEY_USER] = user
    # 应用后端保存的偏好（按账号），覆盖默认值，实现「换设备也不丢设置」
    _apply_user_settings(user)
    try:
        st.query_params[QP_TOKEN] = token
        st.query_params[QP_USER] = json.dumps(user, ensure_ascii=False)
    except Exception as e:
        print(f"[session] set_auth query_params error: {e}")
    # 双保险：写入浏览器 localStorage，F5 整页刷新后也能自动恢复
    try:
        from .auth_persist import save_to_local_storage
        save_to_local_storage(token, user)
    except Exception as e:
        print(f"[session] set_auth localStorage error: {e}")


def clear_auth() -> None:
    """退出登录时调用：清除 session_state + URL query_params + 浏览器 localStorage。"""
    st.session_state[KEY_TOKEN] = None
    st.session_state[KEY_USER] = None
    _clear_query_params()
    try:
        from .auth_persist import clear_local_storage
        clear_local_storage()
    except Exception as e:
        print(f"[session] clear_auth localStorage error: {e}")


def _clear_query_params() -> None:
    try:
        qp = st.query_params
        for k in (QP_TOKEN, QP_USER):
            if k in qp:
                del qp[k]
    except Exception as e:
        print(f"[session] _clear_query_params error: {e}")


# ══════════════════════════════════════════════════════════════
# 用户偏好（主题 / 字体大小）持久化：与登录态同源机制，保证刷新 / 跨页 / 关闭浏览器后恢复
# ══════════════════════════════════════════════════════════════
def _current_prefs() -> dict:
    """从 session_state 收集当前偏好。"""
    return {
        "theme_mode": st.session_state.get("theme_mode", "light"),
        "font_size": st.session_state.get("font_size", FONT_DEFAULT),
    }


def _restore_prefs_from_query_params() -> dict:
    """从 URL query_params 读取 prefs JSON，返回 dict（无则空）。"""
    try:
        raw = st.query_params.get(QP_PREFS)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


def _sync_prefs_query_params() -> None:
    """把当前偏好回写到 URL query_params，保证刷新 / 导航后偏好不丢（仅在变化时写，避免重跑死循环）。"""
    try:
        prefs = _current_prefs()
        cur = st.query_params.get(QP_PREFS)
        new = json.dumps(prefs, ensure_ascii=False)
        if cur != new:
            st.query_params[QP_PREFS] = new
    except Exception as e:
        print(f"[session] _sync_prefs_query_params error: {e}")


def _apply_user_settings(user: dict | None) -> None:
    """把后端返回的用户偏好（theme_mode / font_size）应用到当前会话，覆盖默认值。"""
    settings = (user or {}).get("settings")
    if not isinstance(settings, dict):
        return
    if settings.get("theme_mode") in ("dark", "light"):
        st.session_state["theme_mode"] = settings["theme_mode"]
    if settings.get("font_size"):
        st.session_state["font_size"] = settings["font_size"]


def push_settings_to_backend() -> None:
    """把当前偏好（主题/字号）按账号推到后端。失败静默忽略（用裸 requests，不触发自动登出）。"""
    token = get_token()
    if not token:
        return
    try:
        prefs = _current_prefs()
        requests.post(
            f"{API_BASE}/api/auth/settings",
            json={"settings": prefs},
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
    except Exception:
        pass


def get_user_setting(key, default=None):
    """读取当前登录用户的自定义设置项（后端 settings JSON 中的任意 key）。"""
    user = get_user()
    settings = (user or {}).get("settings")
    if isinstance(settings, dict) and key in settings:
        return settings[key]
    return default


def save_user_setting(key, value) -> None:
    """把用户自定义设置项（如扫描池）按账号持久化到后端 settings JSON。失败静默忽略。"""
    token = get_token()
    if not token:
        return
    try:
        user = get_user() or {}
        settings = dict(user.get("settings") or {})
        settings[key] = value
        user["settings"] = settings
        st.session_state[KEY_USER] = user
        requests.post(
            f"{API_BASE}/api/auth/settings",
            json={"settings": settings},
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
    except Exception:
        pass


def persist_prefs() -> None:
    """偏好变更后调用：写入浏览器 localStorage（关闭浏览器兜底）+ 回写 URL query_params + 同步后端。"""
    try:
        from .prefs_persist import save_prefs
        save_prefs(_current_prefs())
    except Exception as e:
        print(f"[session] persist_prefs localStorage error: {e}")
    _sync_prefs_query_params()
    # 按账号持久化到后端（换设备/清缓存也不丢）；失败静默忽略
    if is_authenticated():
        try:
            push_settings_to_backend()
        except Exception:
            pass


def get_token() -> str | None:
    return st.session_state.get(KEY_TOKEN)


def get_user() -> dict | None:
    return st.session_state.get(KEY_USER)


def is_authenticated() -> bool:
    """检查是否已登录，并在本地校验 JWT 是否过期。

    仅检查 token 存在会导致「token 已过期但前端仍显示登录」的不一致。
    这里用 PyJWT 无签名验证地解析 exp，过期则统一清理登录态。
    """
    token = st.session_state.get(KEY_TOKEN)
    if not token:
        return False
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        if exp and isinstance(exp, (int, float)) and int(exp) < int(time.time()):
            clear_auth()
            return False
        return True
    except Exception:
        return False


def auth_headers() -> dict:
    """返回带 Authorization 的 requests headers dict。"""
    token = get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _logo_base64() -> str:
    """加载项目 logo 并转为 base64 data URL，失败返回空字符串。"""
    try:
        import base64
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon-256.png")
        with open(logo_path, "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
    except Exception:
        return ""


def _render_login_gate() -> None:
    """未登录门禁页：项目品牌 + 金融风登录引导。整卡片纯 HTML，避免 SVG 内联泄露。"""
    logo_b64 = _logo_base64()
    logo_html = f'<img src="{logo_b64}" class="ss-login-logo" alt="StockSignal">' if logo_b64 else ""

    st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(135deg, #0b0f1f 0%, #131a35 50%, #0b1120 100%) !important;
    }}
    .block-container {{
        padding: 0 !important;
        max-width: 100% !important;
    }}
    .ss-login-card {{
        max-width: 420px;
        margin: 5rem auto 0 auto;
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 28px;
        padding: 2.5rem 2rem 2.25rem 2rem;
        text-align: center;
        box-shadow: 0 32px 80px rgba(0, 0, 0, 0.45),
                    0 0 0 1px rgba(255, 255, 255, 0.05),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(12px);
    }}
    .ss-login-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 4px;
        background: linear-gradient(90deg, #f59e0b 0%, #3b82f6 50%, #6366f1 100%);
    }}
    .ss-login-card::after {{
        content: "";
        position: absolute;
        top: -60px; right: -60px;
        width: 140px; height: 140px;
        background: radial-gradient(circle, rgba(59, 130, 246, 0.18) 0%, transparent 70%);
        pointer-events: none;
    }}
    .ss-login-logo {{
        width: 96px;
        height: 96px;
        border-radius: 22px;
        box-shadow: 0 10px 32px rgba(59, 130, 246, 0.28);
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .ss-login-title {{
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(90deg, #fbbf24 0%, #60a5fa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.35rem;
        letter-spacing: -0.5px;
    }}
    .ss-login-subtitle {{
        color: #e2e8f0;
        font-size: 1.05rem;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }}
    .ss-login-desc {{
        color: #94a3b8;
        font-size: 0.9rem;
        margin-bottom: 1.25rem;
        line-height: 1.5;
    }}
    .ss-login-badge {{
        display: inline-block;
        background: rgba(245, 158, 11, 0.13);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.35);
        border-radius: 999px;
        padding: 0.45rem 1rem;
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 1.5rem;
    }}
    .ss-login-btn {{
        display: block;
        width: 100%;
        padding: 0.75rem 1rem;
        background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%);
        color: #fff !important;
        font-size: 1rem;
        font-weight: 700;
        text-align: center;
        text-decoration: none;
        border-radius: 12px;
        border: none;
        box-shadow: 0 8px 24px rgba(245, 158, 11, 0.35);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        cursor: pointer;
    }}
    .ss-login-btn:hover {{
        transform: translateY(-2px);
        box-shadow: 0 12px 32px rgba(245, 158, 11, 0.45);
    }}
    .ss-login-footer {{
        text-align: center;
        color: #64748b;
        font-size: 0.75rem;
        margin-top: 2rem;
    }}
    </style>
    <div class="ss-login-card">
        {logo_html}
        <div class="ss-login-title">StockSignal</div>
        <div class="ss-login-subtitle">A股事件驱动投资分析平台</div>
        <div class="ss-login-desc">登录后解锁行情看板、个股分析、形态选股等全部功能</div>
        <div class="ss-login-badge">🔑 默认演示账号：demo / Demo@123</div>
        <a class="ss-login-btn" href="/登录">🔑 去登录</a>
    </div>
    <div class="ss-login-footer">StockSignal · 仅供学习与研究所用，不构成投资建议</div>
    """, unsafe_allow_html=True)


def require_auth() -> None:
    """
    业务页面门禁：未登录 → 显示品牌登录引导 + 跳转按钮 + st.stop()
    """
    init_session_state()

    if is_authenticated():
        # 注入所有页面通用组件：右上角主题开关 + 侧边栏全局 AI 咨询
        from modules.widgets import inject_global_widgets, render_sidebar_nav
        inject_global_widgets()
        # 自定义分组侧边栏导航（替代原生平铺页面列表）。
        # 始终渲染，确保合并页嵌入子页时侧边栏导航也不丢失（#360）。
        render_sidebar_nav()
        return

    _render_login_gate()
    st.stop()


def api_get(path: str, timeout: int = 5, **kwargs):
    try:
        resp = requests.get(f"{API_BASE}{path}", headers=auth_headers(), timeout=timeout, **kwargs)
    except requests.exceptions.RequestException as e:
        return -1, {"message": f"网络错误: {e}"}
    if resp.status_code == 401:
        clear_auth()
        safe_switch_page("pages/0_登录.py")
    return resp.status_code, _safe_json(resp)


def api_post(path: str, payload: dict | None = None, timeout: int = 5, **kwargs):
    try:
        resp = requests.post(
            f"{API_BASE}{path}", json=payload or {}, headers=auth_headers(), timeout=timeout, **kwargs
        )
    except requests.exceptions.RequestException as e:
        return -1, {"message": f"网络错误: {e}"}
    if resp.status_code == 401:
        clear_auth()
        safe_switch_page("pages/0_登录.py")
    return resp.status_code, _safe_json(resp)


def api_put(path: str, payload: dict | None = None, timeout: int = 5, **kwargs):
    try:
        resp = requests.put(
            f"{API_BASE}{path}", json=payload or {}, headers=auth_headers(), timeout=timeout, **kwargs
        )
    except requests.exceptions.RequestException as e:
        return -1, {"message": f"网络错误: {e}"}
    if resp.status_code == 401:
        clear_auth()
        safe_switch_page("pages/0_登录.py")
    return resp.status_code, _safe_json(resp)


def api_delete(path: str, timeout: int = 5, **kwargs):
    try:
        resp = requests.delete(
            f"{API_BASE}{path}", headers=auth_headers(), timeout=timeout, **kwargs
        )
    except requests.exceptions.RequestException as e:
        return -1, {"message": f"网络错误: {e}"}
    if resp.status_code == 401:
        clear_auth()
        safe_switch_page("pages/0_登录.py")
    return resp.status_code, _safe_json(resp)


# ──────────────────────────────────────────────────────────────
# 市场指标异动提醒（后端 /api/market-alerts）
# ──────────────────────────────────────────────────────────────
def api_market_alerts(limit: int = 50, offset: int = 0) -> dict:
    """返回 {items, unread_count, total, last_seen}；失败返回空 dict。"""
    code, body = api_get(f"/api/market-alerts?limit={limit}&offset={offset}", timeout=8)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return {}


def api_mark_alert_read(alert_id: int) -> tuple:
    return api_post(f"/api/market-alerts/{int(alert_id)}/read", timeout=8)


def api_mark_all_alerts_read() -> tuple:
    return api_post("/api/market-alerts/read-all", timeout=8)


def api_quote(ticker: str, timeout: int = 5) -> dict | None:
    """
    实时五档行情（后端 GET /api/quote?ticker=）。

    优先走后端；失败（网络错误 / 非 200 / 响应非 ok / data 非 dict）时返回 None，
    由调用方回退到本地 fetcher.get_realtime_quote。
    成功判定键为响应信封的 status=="ok"（见 backend/utils/response.py）。
    """
    if not ticker:
        return None
    code, body = api_get(f"/api/quote?ticker={ticker}", timeout=timeout)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return None


def api_kline(symbol: str, start: str | None = None, end: str | None = None,
              period: str = "daily", adjust: str = "qfq", timeout: int = 5) -> list | None:
    """
    历史 K 线（后端 GET /api/kline?symbol=...）。支持 daily/weekly/monthly。

    返回 records 列表（与 StockFetcher.get_kline 的 df.to_dict("records") 一致），
    调用方需用 pd.DataFrame(records) 还原 DataFrame 用法。
    失败（网络错误 / 非 200 / 响应非 ok / data 非 list）时返回 None，
    由调用方回退到本地 fetcher.get_kline。
    """
    if not symbol:
        return None
    params = f"symbol={symbol}&start={start or '2024-01-01'}&period={period}&adjust={adjust}"
    if end:
        params += f"&end={end}"
    code, body = api_get(f"/api/kline?{params}", timeout=timeout)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, list):
            return data
    return None


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"message": f"非 JSON 响应 (HTTP {resp.status_code})"}


def api_junk_stocks() -> list:
    """GET /api/junk-stocks，返回当前用户的垃圾股列表。"""
    code, body = api_get("/api/junk-stocks", timeout=5)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, list):
            return data
    return []


def api_add_junk_stock(code: str, note: str = "") -> dict:
    """POST /api/junk-stocks"""
    code, body = api_post("/api/junk-stocks", {"stock_code": code, "note": note}, timeout=5)
    return body if isinstance(body, dict) else {}


def api_remove_junk_stock(item_id: int) -> dict:
    """DELETE /api/junk-stocks/{id}"""
    code, body = api_delete(f"/api/junk-stocks/{item_id}", timeout=5)
    return body if isinstance(body, dict) else {}


def api_user_score(code: str) -> int | None:
    """GET /api/user-scores/{code}，返回用户打分或 None。"""
    code, body = api_get(f"/api/user-scores/{code}", timeout=5)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return int(data.get("score", 0))
    return None


def api_save_user_score(code: str, score: int, name: str = "") -> dict:
    """POST /api/user-scores"""
    code, body = api_post("/api/user-scores", {"stock_code": code, "stock_name": name, "score": score}, timeout=5)
    return body if isinstance(body, dict) else {}


def _avatar_dir() -> str:
    """头像本地存储目录：<项目根>/data/avatars。"""
    d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "avatars")
    os.makedirs(d, exist_ok=True)
    return d


def get_avatar_path(username: str | None = None) -> str | None:
    """返回当前用户的头像文件路径（存在则返回，否则 None）。"""
    if username is None:
        username = (get_user() or {}).get("username")
    if not username:
        return None
    import glob
    safe = "".join(c for c in str(username) if c.isalnum() or c in "_-")
    matches = glob.glob(os.path.join(_avatar_dir(), f"{safe}.*"))
    return matches[0] if matches else None


def save_avatar(username: str, file_bytes: bytes, ext: str = "png") -> str:
    """保存用户头像到本地，返回路径。会先清除旧头像。

    注：自 Batch（头像持久化）起，头像的权威存储是后端 users.avatar 列；
    本地文件仅作为「后端不可用时」的离线兜底。
    """
    import glob
    safe = "".join(c for c in str(username) if c.isalnum() or c in "_-")
    for old in glob.glob(os.path.join(_avatar_dir(), f"{safe}.*")):
        try:
            os.remove(old)
        except Exception:
            pass
    path = os.path.join(_avatar_dir(), f"{safe}.{ext.lstrip('.')}")
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


def render_avatar(target, avatar_value, width: int = 64) -> None:
    """
    渲染头像：优先 base64 data URL（后端按账号存储），回退本地文件路径。
    target 为 st.sidebar / st。失败静默跳过，避免一个坏图炸掉整页。
    """
    try:
        if isinstance(avatar_value, str) and avatar_value.startswith("data:image/"):
            import base64
            import io
            _, b64 = avatar_value.split(",", 1)
            target.image(io.BytesIO(base64.b64decode(b64)), width=width)
        elif avatar_value:
            target.image(avatar_value, width=width)
    except Exception:
        pass


def get_avatar_data_url() -> str | None:
    """返回当前用户头像的 base64 data URL（来自后端，按账号持久化）。

    会话内若暂无头像（如刷新后 URL 未带 avatar 字段），则向后端 /api/auth/me
    补拉一次并缓存，保证「刷新 / 跨页」后头像不丢失。无头像返回 None。
    """
    user = get_user() or {}
    avatar = user.get("avatar")
    if avatar:
        return avatar
    # 本次会话已确认过无头像 / 已拉取过，避免每帧重复请求后端
    if st.session_state.get("_avatar_checked"):
        return None
    if is_authenticated():
        refreshed = _refresh_user_from_backend()
        st.session_state["_avatar_checked"] = True
        if refreshed and refreshed.get("avatar"):
            return refreshed["avatar"]
    return None


def set_avatar_data_url(data_url: str) -> None:
    """把后端返回的头像 data URL 写回当前会话（含 URL 回写，但不写 avatar 进 URL）。"""
    user = st.session_state.get(KEY_USER)
    if isinstance(user, dict):
        user["avatar"] = data_url
    st.session_state["_avatar_checked"] = True
    _sync_query_params()


def save_avatar_to_backend(data_url: str, timeout: int = 5) -> dict:
    """把头像 base64 data URL 保存到后端（按账号持久化）。返回后端响应 dict。"""
    return api_post("/api/auth/avatar", {"avatar": data_url}, timeout=timeout)


def _refresh_user_from_backend() -> dict | None:
    """调 /api/auth/me 重新拉取最新 user（含 avatar）。"""
    return _verify_token(get_token())


def render_user_badge(sidebar: bool = True) -> None:
    """在侧边栏/顶栏渲染当前用户头像 + 用户名 + 退出登录按钮 + 市场异动铃铛。"""
    user = get_user() or {}
    username = user.get("username", "?")
    role_cn = "管理员" if user.get("role") == "admin" else "普通用户"
    target = st.sidebar if sidebar else st
    _avatar = get_avatar_data_url() or get_avatar_path(username)
    if _avatar:
        render_avatar(target, _avatar, width=64)
    target.markdown(f"**👤 {username} · {role_cn}**")
    if target.button("🚪 退出登录", key="logout_btn"):
        clear_auth()
        safe_switch_page("pages/0_登录.py")
    # 市场异动铃铛（全局，挂用户区下方）
    try:
        render_market_alert_bell(target)
    except Exception as e:  # noqa: BLE001
        target.caption(f"提醒加载失败：{str(e)[:40]}")


@st.cache_data(ttl=30, show_spinner=False)
def _cached_alert_summary(token: str, nonce: int) -> dict:
    """缓存市场异动摘要（未读数 + 最近 5 条），nonce 变化即击穿重取。"""
    try:
        code, body = api_get("/api/market-alerts?limit=5", timeout=8)
        if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
            data = body.get("data")
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def render_market_alert_bell(target=st.sidebar) -> None:
    """侧边栏市场异动铃铛：常驻侧边栏，点击展开 popover 显示未读摘要 + 最近异动 + 全部已读。"""
    nonce = int(st.session_state.get("_alert_nonce", 0))
    data = _cached_alert_summary(get_token() or "", nonce)
    unread = int(data.get("unread_count", 0) or 0)
    items = data.get("items", []) or []

    badge = f" 🔴{unread}" if unread else ""
    with target.popover(f"🔔 市场异动{badge}", use_container_width=True):
        _sev_icon = {"danger": "⛔", "warning": "⚠️", "info": "ℹ️"}
        if items:
            for it in items[:5]:
                sev = it.get("severity", "info")
                icon = _sev_icon.get(sev, "ℹ️")
                ts = (it.get("created_at") or "")[:16].replace("T", " ")
                st.caption(f"{icon} {it.get('metric_name')}：{it.get('message')}")
                st.caption(f"　└ {ts}")
        else:
            st.caption("暂无异动提醒")

        if st.button("✅ 全部标为已读", key="alert_mark_all_btn"):
            code, _ = api_mark_all_alerts_read()
            if code == 200:
                st.session_state["_alert_nonce"] = nonce + 1


@st.cache_data(ttl=20, show_spinner=False)
def _cached_alerts_panel(token: str, nonce: int) -> dict:
    """缓存市场异动列表（共享面板用，nonce 变化即击穿重取）。"""
    return api_market_alerts(limit=20, offset=0)


@safe_fragment("市场异动提醒面板")
def fragment_market_alerts_panel() -> None:
    """共享市场异动面板：可在任意页面末尾挂载，风格与 P 页统一。"""
    from modules.page_widgets import _section_title
    _section_title("🔔 近期异动提醒（自动扫描 · 后台调度）", accent="#ee2a2a")
    nonce = int(st.session_state.get("_alert_panel_nonce", 0))
    data = _cached_alerts_panel(get_token() or "", nonce)
    items = data.get("items", []) or []
    unread = int(data.get("unread_count", 0) or 0)

    if unread:
        st.markdown(f"未读 **{unread}** 条")
    if st.button("✅ 全部标为已读", key="panel_mark_all"):
        code, _ = api_mark_all_alerts_read()
        if code == 200:
            st.session_state["_alert_panel_nonce"] = nonce + 1

    if not items:
        st.info("暂无异动提醒。后台调度器会在交易时段扫描广度/情绪/估值指标越界并推送。")
        return

    _sev_icon = {"danger": "⛔", "warning": "⚠️", "info": "ℹ️"}
    for it in items:
        sev = it.get("severity", "info")
        icon = _sev_icon.get(sev, "ℹ️")
        ts = (it.get("created_at") or "")[:16].replace("T", " ")
        c1, c2 = st.columns([0.88, 0.12])
        with c1:
            st.markdown(f"{icon} **{it.get('metric_name')}**：{it.get('message')}")
            st.caption(f"　└ {ts}　值 {it.get('value')}　阈值 {it.get('threshold')}")
        with c2:
            if st.button("✓", key=f"panel_read_{it.get('id')}", help="标为已读"):
                code, _ = api_mark_alert_read(it.get("id"))
                if code == 200:
                    st.session_state["_alert_panel_nonce"] = nonce + 1


def is_admin() -> bool:
    user = get_user() or {}
    return user.get("role") == "admin"


def require_admin() -> None:
    require_auth()
    if not is_admin():
        st.error("⛔ 该页面仅管理员可访问")
        st.caption("请联系管理员提升权限")
        st.stop()
