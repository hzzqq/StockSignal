"""
"""
from __future__ import annotations

import json
import logging
import os
import time

import jwt
import streamlit as st
from datetime import datetime

from modules.request_utils import http_get, http_post
from modules.site_config import API_BASE
from modules.time_utils import now_cst_naive
from modules.ui_kit import xc_info_banner, xc_success_box, xc_warn_box

from .page_guard import safe_fragment
from .ui_theme import FONT_DEFAULT

# 子模块 re-export：对外 ``from modules.session import ...`` 全部保持可用
from modules.session_api import (  # noqa: F401
    _api_request,
    _safe_json,
    api_add_junk_stock,
    api_delete,
    api_get,
    api_intraday,
    api_junk_stocks,
    api_kline,
    api_mark_alert_read,
    api_mark_all_alerts_read,
    api_market_alerts,
    api_post,
    api_put,
    api_quote,
    api_remove_junk_stock,
    api_save_user_score,
    api_user_score,
    get_watchlist,
    save_avatar_to_backend,
)
from modules.session_user import (  # noqa: F401
    _avatar_dir,
    _cached_alert_summary,
    _cached_alerts_panel,
    _confirm_logout_dialog,
    _parse_alert_summary,
    _parse_iso,
    _parse_ts,
    _refresh_user_from_backend,
    _rel_time,
    fragment_market_alerts_panel,
    get_avatar_data_url,
    get_avatar_path,
    render_avatar,
    render_market_alert_bell,
    render_user_badge,
    save_avatar,
    set_avatar_data_url,
)

# 与子模块共用同名 logger（同一实例）：test_exception_logging 等按名注入继续生效
logger = logging.getLogger("modules.session")


KEY_TOKEN = "auth_token"
KEY_USER = "auth_user"
QP_TOKEN = "token"
QP_USER = "u"
QP_PREFS = "prefs"  # 用户偏好（主题/字体）持久化参数
_TOKEN_INVALID = "___token_invalid_sentinel___"
_TOKEN_EXPIRED = "___token_expired_sentinel___"
_REFRESH_REJECTED = "___refresh_rejected_sentinel___"

def trading_autorefresh(interval_ms: int = 60000, key: str = "auto_refresh",
                        limit: int = 400, only_trading: bool = True):
    """自动刷新当前页面数据，避免数据陈旧（默认仅交易时段）。

    默认非交易时段（午休 / 收盘 / 周末）不刷新，避免无意义请求与界面闪烁。
    `only_trading=False` 时不限交易时段——供「产物文件变化即重载」类页面复用
    （如 P1 信号页：文件 mtime 变化就该重载，与开收盘无关）。

    P0-2 迁移（T-350）：由第三方 st_autorefresh 改为 Streamlit 原生 fragment 驱动。
    - 整页刷新语义：fragment(run_every=间隔秒) 触发后调用 st.rerun(scope="app")；
    - 防首帧循环：session_state 标记「首帧只置位不 rerun」，仅 run_every 触发的
      后续重跑才整页刷新（裸用 st.rerun(scope="app") 会在首帧即无限循环）；
    - limit 限次与「非交易时段不刷新」语义保留（limit 无原生对应物，
      用 session_state 计数器复刻）。
    """
    if only_trading:
        from modules.page_widgets import is_trading_now
        if not is_trading_now():
            return
    _interval_s = max(1, int(interval_ms) // 1000)
    _tick_key = f"_ta_tick_{key}"
    _cnt_key = f"_ta_cnt_{key}"
    _limit = max(1, int(limit))

    @st.fragment(run_every=_interval_s)
    def _auto_tick():
        # 首帧只置位不 rerun（防无限循环）；run_every 触发后的后续重跑才整页刷新。
        if not st.session_state.get(_tick_key):
            st.session_state[_tick_key] = True
            return
        _cnt = int(st.session_state.get(_cnt_key, 0))
        if _cnt >= _limit:
            return
        st.session_state[_cnt_key] = _cnt + 1
        st.session_state[_tick_key] = False
        st.rerun(scope="app")

    _auto_tick()



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
    # 2.5) T-206：localStorage 兜底已废弃删除。原 auth_persist 用 st.markdown 注入
    #      <script>，被 Streamlit 剥离（从未生效）；且其「补回 URL 并跳转父页」依赖
    #      component iframe 导航父窗口，被 sandbox（无 allow-top-navigation）拦截——
    #      架构上不可行，勿再引入。登录态持久化现由 URL query_params 承载：登录写、
    #      导航 href 带 token（session.nav_query_string）、每帧 _sync_query_params 回写。

    # 3) 把已恢复的 token「回写」到 URL query_params（刷新保持登录的根本保障）。
    # 原实现漏了这一步，导致仅凭 localStorage 兜底恢复的 token 始终未同步回 URL，
    # 一旦 localStorage 也被清空便直接掉登录，且违背本模块「URL 为登录态主存储」的契约。
    # _sync_query_params 仅在值变化时写入，幂等、不会触发 rerun 死循环。
    if st.session_state.get(KEY_TOKEN):
        _sync_query_params()

    # 4) 恢复用户偏好（主题 / 字体）：先试 URL query_params（刷新/导航可靠）；
    #    若 URL 无偏好但 localStorage 有（浏览器关闭后再打开），则从 localStorage 兜底恢复。
    _prefs = _restore_prefs_from_query_params()
    if _prefs:
        st.session_state.setdefault("theme_mode", _prefs.get("theme_mode", "dark"))
        st.session_state.setdefault("font_size", _prefs.get("font_size", FONT_DEFAULT))
        st.session_state.setdefault("ui_style", _prefs.get("ui_style", "classic"))
    else:
        try:
            from .prefs_persist import restore_prefs_from_local_storage
            restore_prefs_from_local_storage()
        except Exception as e:
            logger.warning(f"[session] restore_prefs error: {e}")
    _sync_prefs_query_params()

    # 记录当前页面作用域（供「个股分析」强制暗色等按页面生效的逻辑使用，
    # 不改写全局 theme_mode，避免访问该页后其它页面被意外变暗）。
    # _active_page 由各页面在顶部用 __file__ 设置，这里仅做兜底默认值。
    st.session_state.setdefault("_active_page", "")

    # 清理旧版侧边栏/嵌入相关缓存键，避免旧状态影响新导航（闪一下旧侧边栏）
    for _old_key in ("_embed_active", "_sidebar_collapsed", "_old_nav", "_nav_cache"):
        st.session_state.pop(_old_key, None)

    # 注入金融级 UI 主题（仅视觉，不影响任何功能逻辑）
    # T-194b：风格切换器防重入改时间窗（ui_theme 侧），此处不再清标记——
    # apply_page_config 比 init_session_state 更早调 apply_theme，帧首清除反而制造二次渲染
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
            except Exception as e:
                logger.warning(f"[session] 处理异常: {e}")
                user = None

        # 兜底：URL 无 user 或解析失败 → 校验 token 取回
        if not isinstance(user, dict):
            user = _verify_token(token)

        if isinstance(user, dict):
            st.session_state[KEY_TOKEN] = token
            st.session_state[KEY_USER] = user
        elif user is _TOKEN_EXPIRED:
            # T-158：过期先静默续期——成功即恢复登录（_try_refresh 内部已 set_auth
            # 更新三层存储）；后端明确拒绝才走失效清理；网络瞬态保留现有登录态
            # （与下方「校验网络异常保留登录态」同语义，避免后端抖动误踢）。
            r = _try_refresh()
            if r is True:
                return
            if r is _REFRESH_REJECTED:
                _clear_query_params()
        elif user is _TOKEN_INVALID:
            # token 明确失效（过期/伪造）→ 清掉 URL 参数（T-206：localStorage 兜底
            # 已删除，无需再同步清理）。
            _clear_query_params()
        else:
            # None = 网络/服务端瞬态错误：保留现有 token 与登录态，后端恢复后自动恢复
            logger.warning("[session] token 校验网络异常，保留现有登录态，待后端恢复")
    except Exception as e:
        logger.warning(f"[session] _restore_from_query_params error: {e}")



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
        logger.warning(f"[session] _sync_query_params error: {e}")



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
    except Exception as e:
        logger.warning(f"[session] 读取 query_params 失败: {e}")
    if token:
        qp[QP_TOKEN] = token
        if user is not None:
            qp[QP_USER] = json.dumps(user, ensure_ascii=False)
    if qp:
        st.switch_page(page, query_params=qp, **kwargs)
    else:
        st.switch_page(page, **kwargs)



def _me_response_valid(data) -> bool:
    """纯函数：判断 /api/auth/me 的 `data`（user 对象）是否构成已登录的有效证明。

    接受以下任一结构（且 data 必须是 dict）：
      - 含 truthy 的 'username'
      - 含 truthy 的 'uid'
      - 嵌套 user 字典含 truthy 的 'username'
    空字符串 / None / 非 dict 一律视为无效。
    """
    if not isinstance(data, dict):
        return False
    if data.get("username"):
        return True
    if data.get("uid"):
        return True
    nested = data.get("user")
    if isinstance(nested, dict) and nested.get("username"):
        return True
    return False



def _verify_token(token: str):
    """调 /api/auth/me 验证 token。

    返回：
      - user dict           ：有效
      - _TOKEN_INVALID 哨兵  ：后端明确返回 401/403 或 status!=ok，token 已失效/伪造，应清登录态
      - None                ：网络错误/超时/5xx 等瞬态异常，无法判定，调用方应保留现有登录态
    """
    try:
        resp = http_get(
            f"{API_BASE}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") == "ok":
                data = body.get("data") or {}
                # /api/auth/me 返回 data 即为 user 对象（扁平结构）
                # 兼容 username / uid / 嵌套 user.username 多种有效登录证明
                if _me_response_valid(data):
                    # 兼容：若 data 内仍嵌套 user 键，返回内层 user 对象
                    if isinstance(data.get("user"), dict):
                        return data["user"]
                    return data
            # 200 但 status!=ok（如 token 过期但非标准 401）→ 视为无效
            return _TOKEN_INVALID
        if resp.status_code in (401, 403):
            # T-158：区分「过期」与「无效」——过期可静默续期，伪造/无效不可
            try:
                code = (resp.json() or {}).get("code")
            except Exception as e:
                logger.warning(f"[session] 401 body 解析异常: {e}")
                code = None
            if code == "token_expired":
                return _TOKEN_EXPIRED
            return _TOKEN_INVALID
        # 5xx / 其他状态码：服务端瞬态，保留登录态
        return None
    except Exception as e:
        logger.warning(f"[session] 处理异常: {e}")
        # 网络错误/超时：无法判定，保留现有登录态，不踢出（修复刷新时后端抖动被误踢）
        return None



def _try_refresh():
    """静默续期（T-158）：用现有 token 换新 access token。

    返回：
      - True               ：续期成功，新 token/user 已通过 set_auth 写入三层存储
      - _REFRESH_REJECTED  ：后端明确拒绝（超窗/用户禁用/伪造）→ 调用方应清登录态
      - None               ：网络瞬态/5xx，无法判定 → 调用方应保留登录态
    """
    token = st.session_state.get(KEY_TOKEN)
    if not token:
        return _REFRESH_REJECTED
    try:
        resp = http_post(
            f"{API_BASE}/api/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") == "ok":
                data = body.get("data") or {}
                new_token = data.get("token")
                user = data.get("user")
                if new_token and isinstance(user, dict) and _me_response_valid(user):
                    set_auth(new_token, user)
                    logger.info("[session] token 已静默续期")
                    return True
            # 200 但 status!=ok / data 不完整：按明确拒绝处理（异常响应不值得重试）
            return _REFRESH_REJECTED
        if resp.status_code in (401, 403):
            return _REFRESH_REJECTED
        # 5xx / 其他：服务端瞬态
        return None
    except Exception as e:
        logger.warning(f"[session] refresh 网络异常: {e}")
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
        logger.warning(f"[session] set_auth query_params error: {e}")



def clear_auth() -> None:
    """退出登录时调用：清除 session_state + URL query_params。"""
    st.session_state[KEY_TOKEN] = None
    st.session_state[KEY_USER] = None
    _clear_query_params()



def _clear_query_params() -> None:
    try:
        qp = st.query_params
        for k in (QP_TOKEN, QP_USER):
            if k in qp:
                del qp[k]
    except Exception as e:
        logger.warning(f"[session] _clear_query_params error: {e}")



def nav_query_string() -> str:
    """T-201：构造顶栏/命令面板导航 href 的查询串（token + u + prefs）。

    背景：<a href> 整页跳转会新建 Streamlit 会话，登录态/偏好只能靠 URL 恢复；
    localStorage 兜底已废弃（T-206 删除：st.markdown 注入的 <script> 被 Streamlit
    剥离从未生效，组件 iframe 又无法导航父页），故 token 必须随每个导航 href 走，
    落页由 _restore_from_query_params 快速路径（带 u 免 /me 往返）原位恢复登录态与界面状态。

    未登录返回空串（调用方据此省略查询串）。
    """
    token = st.session_state.get(KEY_TOKEN)
    if not token:
        return ""
    try:
        user = st.session_state.get(KEY_USER) or {}
        u_safe = {k: v for k, v in user.items() if k != "avatar"}
        params = {
            QP_TOKEN: token,
            QP_USER: json.dumps(u_safe, ensure_ascii=False),
            QP_PREFS: json.dumps(_current_prefs(), ensure_ascii=False),
        }
        from urllib.parse import urlencode
        return urlencode(params)
    except Exception as e:
        logger.warning(f"[session] nav_query_string error: {e}")
        return ""



def _current_prefs() -> dict:
    """从 session_state 收集当前偏好。"""
    return {
        "theme_mode": st.session_state.get("theme_mode", "dark"),
        "font_size": st.session_state.get("font_size", FONT_DEFAULT),
        "ui_style": st.session_state.get("ui_style", "classic"),
    }



def _restore_prefs_from_query_params() -> dict:
    """从 URL query_params 读取 prefs JSON，返回 dict（无则空）。"""
    try:
        raw = st.query_params.get(QP_PREFS)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"[session] 解析 prefs query 失败: {e}")
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
        logger.warning(f"[session] _sync_prefs_query_params error: {e}")



def _apply_user_settings(user: dict | None) -> None:
    """把后端返回的用户偏好（theme_mode / font_size）应用到当前会话，覆盖默认值。"""
    settings = (user or {}).get("settings")
    if not isinstance(settings, dict):
        return
    if settings.get("theme_mode") in ("dark", "light"):
        st.session_state["theme_mode"] = settings["theme_mode"]
    if settings.get("font_size"):
        st.session_state["font_size"] = settings["font_size"]
    _us = settings.get("ui_style")
    if _us:
        try:
            from .ui_theme import STYLE_PRESETS
            if _us in STYLE_PRESETS:
                st.session_state["ui_style"] = _us
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[session] ui_style 应用失败: {e}")



def push_settings_to_backend() -> None:
    """把当前偏好（主题/字号）按账号推到后端。失败静默忽略（用裸 requests，不触发自动登出）。"""
    token = get_token()
    if not token:
        return
    try:
        prefs = _current_prefs()
        http_post(
            f"{API_BASE}/api/auth/settings",
            json={"settings": prefs},
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
    except Exception as e:
        logger.warning(f"[session] set_user_setting 同步后端失败: {e}")



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
        http_post(
            f"{API_BASE}/api/auth/settings",
            json={"settings": settings},
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
    except Exception as e:
        logger.warning(f"[session] push_settings_to_backend 失败: {e}")



def persist_prefs() -> None:
    """偏好变更后调用：写入浏览器 localStorage（关闭浏览器兜底）+ 回写 URL query_params + 同步后端。"""
    try:
        from .prefs_persist import save_prefs
        save_prefs(_current_prefs())
    except Exception as e:
        logger.warning(f"[session] persist_prefs localStorage error: {e}")
    _sync_prefs_query_params()
    # 按账号持久化到后端（换设备/清缓存也不丢）；失败静默忽略
    if is_authenticated():
        try:
            push_settings_to_backend()
        except Exception as e:
            logger.warning(f"[session] persist_prefs 同步后端失败: {e}")



def get_token() -> str | None:
    return st.session_state.get(KEY_TOKEN)



def mask_token(token, keep_head: int = 4, keep_tail: int = 4) -> str:
    """安全脱敏 token（新能力，供日志/调试展示）：仅保留首尾各 keep_head/keep_tail 位，中间以 * 代替。

    绝不输出完整凭证；空或极短 token 返回占位符，避免反向泄露长度之外的信息。
    这是「可观测性 + 安全」的一次性增强：原先 token 一旦进入日志即整段明文，存在泄露风险。
    """
    if not token:
        return ""
    t = str(token)
    if len(t) <= keep_head + keep_tail:
        return "****"
    return f"{t[:keep_head]}{'*' * (len(t) - keep_head - keep_tail)}{t[-keep_tail:]}"



def get_user() -> dict | None:
    return st.session_state.get(KEY_USER)



def is_authenticated() -> bool:
    """检查是否已登录，并在本地校验 JWT 是否过期。

    仅检查 token 存在会导致「token 已过期但前端仍显示登录」的不一致。
    这里用 PyJWT 无签名验证地解析 exp：
    - 未过期 → True；
    - 已过期（T-158）→ 先试静默续期（滑动窗口内无感换新），续期成功仍算已登录；
      后端明确拒绝才清登录态；网络瞬态保留登录态（后端不可达时踢人只会放大故障）。
    """
    token = st.session_state.get(KEY_TOKEN)
    if not token:
        return False
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        if exp and isinstance(exp, (int, float)) and int(exp) < int(time.time()):
            r = _try_refresh()
            if r is True:
                return True
            if r is _REFRESH_REJECTED:
                clear_auth()
                return False
            # None：网络瞬态，保留现有登录态，待后端恢复
            return True
        return True
    except Exception as e:
        logger.warning(f"[session] token 校验异常: {e}")
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
    except Exception as e:
        logger.warning(f"[session] 处理异常: {e}")
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
        background: linear-gradient(145deg, color-mix(in srgb, var(--acc1) 10%, var(--card)) 0%, var(--card) 100%);
        border: 1px solid color-mix(in srgb, var(--acc1) 35%, var(--border));
        border-radius: var(--ss-login-radius, 28px);
        padding: 2.5rem 2rem 2.25rem 2rem;
        text-align: center;
        box-shadow: 0 32px 80px rgba(0, 0, 0, 0.45),
                    0 0 0 1px rgba(255, 255, 255, 0.05),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(12px);
    }}
    .ss-login-hero {{text-align:center;margin:4px 0 26px}}
    .ss-login-hero h1 {{font-size:2.2rem;font-weight:900;color:var(--txt);margin:0 0 6px}}
    .ss-login-hero h1 .ss-grad {{background:linear-gradient(90deg,var(--acc1),var(--acc2));
      -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}}
    .ss-login-hero p {{font-size:1rem;color:var(--txt2);margin:0}}
    .ss-login-hero p b {{color:var(--acc1);font-weight:800}}
    .ss-login-card::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 4px;
        background: linear-gradient(90deg, var(--acc1) 0%, var(--acc2) 50%, var(--acc1) 100%);
    }}
    .ss-login-card::after {{
        content: "";
        position: absolute;
        top: -60px; right: -60px;
        width: 140px; height: 140px;
        background: radial-gradient(circle, color-mix(in srgb, var(--acc2) 20%, transparent) 0%, transparent 70%);
        pointer-events: none;
    }}
    .ss-login-logo {{
        width: 96px;
        height: 96px;
        border-radius: 22px;
        box-shadow: 0 10px 32px color-mix(in srgb, var(--acc2) 30%, transparent);
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .ss-login-title {{
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(90deg, var(--acc1) 0%, var(--acc2) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.35rem;
        letter-spacing: -0.5px;
    }}
    .ss-login-subtitle {{
        color: var(--txt);
        font-size: 1.05rem;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }}
    .ss-login-desc {{
        color: var(--txt2);
        font-size: 0.9rem;
        margin-bottom: 1.25rem;
        line-height: 1.5;
    }}
    .ss-login-badge {{
        display: inline-block;
        background: color-mix(in srgb, var(--acc1) 12%, transparent);
        color: var(--acc1);
        border: 1px solid color-mix(in srgb, var(--acc1) 35%, transparent);
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
        background: linear-gradient(90deg, var(--acc1), var(--acc2));
        color: var(--ss-login-btn-text, #fff) !important;
        font-size: 1rem;
        font-weight: 700;
        text-align: center;
        text-decoration: none;
        border-radius: 12px;
        border: none;
        box-shadow: 0 8px 24px color-mix(in srgb, var(--acc1) 35%, transparent);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        cursor: pointer;
    }}
    .ss-login-btn:hover {{
        transform: translateY(-2px);
        box-shadow: 0 12px 32px color-mix(in srgb, var(--acc1) 45%, transparent);
    }}
    .ss-login-footer {{
        text-align: center;
        color: var(--txt2);
        font-size: 0.75rem;
        margin-top: 2rem;
    }}
    </style>
    <div class="ss-login-hero"><h1><span class="ss-grad">📊 决策</span> 放心交给 StockSignal</h1><p>超过 <b>3,300+</b> 条自动化测试护航 · <b>4,091</b> 日真实回测实证</p></div>
    <div class="ss-login-card">
        {logo_html}
        <div class="ss-login-title">StockSignal</div>
        <div class="ss-login-subtitle">A股事件驱动投资分析平台</div>
        <div class="ss-login-desc">登录后解锁行情看板、个股分析、形态选股等全部功能</div>
        <div class="ss-login-badge">🔑 默认演示账号：demo / Demo@123</div>
        <a class="ss-login-btn" href="/登录">🔑 去登录</a>
    </div>
    <div class="ss-login-footer">StockSignal · 仅供学习与研究所用，不构成投资建议</div>
    """, unsafe_allow_html=True)  # ui_audit_exempt: unsafe-allow_html 内部组件渲染层
    # T-197：未登录 gate 页也注入回顶悬浮（无命令面板索引）
    try:
        from modules.scroll_nav import inject_scroll_nav
        inject_scroll_nav()
    except Exception as e:
        logger.warning(f'[session] gate scroll_nav 注入失败: {e}')



def require_auth() -> None:
    """
    业务页面门禁：未登录 → 显示品牌登录引导 + 跳转按钮 + st.stop()
    """
    init_session_state()

    # 记录真实页面访问（仅页面切换计数，session 内去重），驱动侧边栏『⭐ 常用』动态 Top5。
    # 放在门禁最前、不依赖认证分支，确保跳转即统计；任何异常在内部 fail-safe 吞掉。
    from modules.widgets import record_nav_visit, _current_page_basename
    try:
        record_nav_visit(_current_page_basename())
    except Exception:  # ui_audit_exempt: except-pass 页面访问计数为侧边栏『常用』埋点，fail-safe 吞掉不得阻断登录门禁
        pass

    if is_authenticated():
        # 注入所有页面通用组件：顶栏 Mega 导航 + 右下角回顶悬浮（T-195）。
        # T-195 侧栏退役：render_sidebar_nav 保留函数但不再调用（顶栏为唯一主导航，
        # 参考阿里云官网 mega 面板交互）；函数与 _NAV_GROUPS 数据保留供回滚。
        from modules.widgets import inject_global_widgets
        inject_global_widgets()
        return

    _render_login_gate()
    st.stop()



def is_admin() -> bool:
    user = get_user() or {}
    return user.get("role") == "admin"



def require_admin() -> None:
    require_auth()
    if not is_admin():
        st.error("⛔ 该页面仅管理员可访问")
        st.caption("请联系管理员提升权限")
        st.stop()


__all__ = [
    "logger",
    "KEY_TOKEN",
    "KEY_USER",
    "QP_TOKEN",
    "QP_USER",
    "QP_PREFS",
    "_TOKEN_INVALID",
    "_TOKEN_EXPIRED",
    "_REFRESH_REJECTED",
    "trading_autorefresh",
    "init_session_state",
    "_restore_from_query_params",
    "_sync_query_params",
    "safe_switch_page",
    "_me_response_valid",
    "_verify_token",
    "_try_refresh",
    "set_auth",
    "clear_auth",
    "_clear_query_params",
    "nav_query_string",
    "_current_prefs",
    "_restore_prefs_from_query_params",
    "_sync_prefs_query_params",
    "_apply_user_settings",
    "push_settings_to_backend",
    "get_user_setting",
    "save_user_setting",
    "persist_prefs",
    "get_token",
    "mask_token",
    "get_user",
    "is_authenticated",
    "auth_headers",
    "_logo_base64",
    "_render_login_gate",
    "require_auth",
    "is_admin",
    "require_admin",
    "_safe_json",
    "_api_request",
    "api_get",
    "api_post",
    "api_put",
    "api_delete",
    "api_market_alerts",
    "api_mark_alert_read",
    "api_mark_all_alerts_read",
    "api_quote",
    "api_kline",
    "api_intraday",
    "api_junk_stocks",
    "api_add_junk_stock",
    "api_remove_junk_stock",
    "api_user_score",
    "get_watchlist",
    "api_save_user_score",
    "save_avatar_to_backend",
    "_avatar_dir",
    "get_avatar_path",
    "save_avatar",
    "render_avatar",
    "get_avatar_data_url",
    "set_avatar_data_url",
    "_refresh_user_from_backend",
    "_parse_iso",
    "_rel_time",
    "_parse_ts",
    "render_user_badge",
    "_confirm_logout_dialog",
    "_parse_alert_summary",
    "_cached_alert_summary",
    "render_market_alert_bell",
    "_cached_alerts_panel",
    "fragment_market_alerts_panel",
    "API_BASE",
    "FONT_DEFAULT",
]
