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
import streamlit as st
import requests

from .ui_theme import FONT_DEFAULT

# 后端 API 基地址。
# 本地开发默认 http://127.0.0.1:5050；容器化部署（docker-compose）下由
# STOCKSIGNAL_API_BASE=http://backend:5050 注入，前端容器借此跨容器访问后端。
API_BASE = os.environ.get("STOCKSIGNAL_API_BASE", "http://127.0.0.1:5050")

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
            u_str = json.dumps(user, ensure_ascii=False)
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


def persist_prefs() -> None:
    """偏好变更后调用：写入浏览器 localStorage（关闭浏览器兜底）+ 回写 URL query_params。"""
    try:
        from .prefs_persist import save_prefs
        save_prefs(_current_prefs())
    except Exception as e:
        print(f"[session] persist_prefs localStorage error: {e}")
    _sync_prefs_query_params()


def get_token() -> str | None:
    return st.session_state.get(KEY_TOKEN)


def get_user() -> dict | None:
    return st.session_state.get(KEY_USER)


def is_authenticated() -> bool:
    return bool(st.session_state.get(KEY_TOKEN))


def auth_headers() -> dict:
    """返回带 Authorization 的 requests headers dict。"""
    token = get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def require_auth() -> None:
    """
    业务页面门禁：未登录 → 显示提示 + 跳转按钮 + st.stop()
    """
    init_session_state()

    if is_authenticated():
        # 注入所有页面通用组件：右上角主题开关 + 侧边栏全局 AI 咨询
        from modules.widgets import inject_global_widgets
        inject_global_widgets()
        return

    st.warning("🔐 该功能需要登录后才能使用")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔑 去登录", type="primary"):
            safe_switch_page("pages/0_登录.py")
    with col2:
        st.caption("提示：默认演示账号 `demo` / `Demo@123`")
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
    """保存用户头像到本地，返回路径。会先清除旧头像。"""
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


def render_user_badge(sidebar: bool = True) -> None:
    """在侧边栏/顶栏渲染当前用户头像 + 用户名 + 退出登录按钮。"""
    user = get_user() or {}
    username = user.get("username", "?")
    role_cn = "管理员" if user.get("role") == "admin" else "普通用户"
    target = st.sidebar if sidebar else st
    avatar = get_avatar_path(username)
    if avatar:
        try:
            target.image(avatar, width=64)
        except Exception:
            pass
    target.markdown(f"**👤 {username} · {role_cn}**")
    if target.button("🚪 退出登录", key="logout_btn"):
        clear_auth()
        safe_switch_page("pages/0_登录.py")


def is_admin() -> bool:
    user = get_user() or {}
    return user.get("role") == "admin"


def require_admin() -> None:
    require_auth()
    if not is_admin():
        st.error("⛔ 该页面仅管理员可访问")
        st.caption("请联系管理员提升权限")
        st.stop()
