"""用户区渲染（session 拆分·用户域）。

职责：头像存取 / 用户徽章与退出确认 / 市场异动提醒铃与面板 / 时间与摘要工具。
循环导入说明：get_user / get_token / is_authenticated / clear_auth / safe_switch_page /
_sync_query_params / _verify_token 属主入口认证链，在各函数内**函数级延迟导入**
（模块级导入会形成 session ↔ session_user 循环）。
零业务逻辑改动：源码自 ``modules/session.py`` 原样搬运。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import streamlit as st

from modules.page_guard import safe_fragment
from modules.time_utils import now_cst_naive
from modules.ui_kit import info_banner, xc_warn_box
from modules.session_api import (
    api_get,
    api_mark_alert_read,
    api_mark_all_alerts_read,
    api_market_alerts,
    api_post,
)

# 与主入口共用同名 logger（getLogger 单例），既有按名打补丁/过滤继续生效
logger = logging.getLogger("modules.session")

def _avatar_dir() -> str:
    """头像本地存储目录：<项目根>/data/avatars（测试期跟随 SS_DATA_DIR 隔离）。"""
    d = os.path.join(os.environ.get("SS_DATA_DIR") or os.path.dirname(os.path.dirname(__file__)), "data", "avatars")
    os.makedirs(d, exist_ok=True)
    return d



def get_avatar_path(username: str | None = None) -> str | None:
    """返回当前用户的头像文件路径（存在则返回，否则 None）。"""
    from modules.session import get_user  # 延迟导入：避 session ↔ 本模块循环
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
        except Exception as e:
            logger.warning(f"[session] 删除旧头像失败: {e}")
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
    except Exception as e:
        logger.warning(f"[session] 渲染头像失败: {e}")



def get_avatar_data_url() -> str | None:
    """返回当前用户头像的 base64 data URL（来自后端，按账号持久化）。

    会话内若暂无头像（如刷新后 URL 未带 avatar 字段），则向后端 /api/auth/me
    补拉一次并缓存，保证「刷新 / 跨页」后头像不丢失。无头像返回 None。
    """
    from modules.session import get_user, is_authenticated  # 延迟导入：避 session ↔ 本模块循环
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
    from modules.session import KEY_USER, _sync_query_params  # 延迟导入：避 session ↔ 本模块循环
    user = st.session_state.get(KEY_USER)
    if isinstance(user, dict):
        user["avatar"] = data_url
    st.session_state["_avatar_checked"] = True
    _sync_query_params()



def _refresh_user_from_backend() -> dict | None:
    """调 /api/auth/me 重新拉取最新 user（含 avatar）。"""
    from modules.session import _verify_token, get_token  # 延迟导入：避 session ↔ 本模块循环
    res = _verify_token(get_token())
    # 只返回有效 user dict；无效哨兵/网络异常统一转 None，避免调用方 .get 崩
    return res if isinstance(res, dict) else None



def _parse_iso(ts):
    """把 ISO 时间戳解析为 datetime（统一来源；丢弃时区信息以与 datetime.now() 一致比较）。

    隐式修复（R2）：原先 _rel_time / _parse_ts 各自内联同一段 `replace("Z","").replace("+08:00","")`
    解析逻辑；且未丢弃 tzinfo，若时间戳带时区会与朴素 datetime.now() 混合比较抛 TypeError。
    这里归一为朴素 datetime，作为全模块唯一的 ISO 解析入口。
    """
    if not ts:
        return None
    s = str(ts).replace("Z", "").replace("+08:00", "").replace("+00:00", "")
    try:
        dt = datetime.fromisoformat(s)
    except Exception as e:
        logger.warning(f"[session] parse_ts 失败: {e}")
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", ""))
        except Exception as e:
            logger.warning(f"[session] 处理异常: {e}")
            return None
    # 丢弃时区，统一按朴素时间比较
    return dt.replace(tzinfo=None)



def _rel_time(ts) -> str:
    """把 ISO 时间戳转成友好相对时间（UI-only）：刚刚 / N分钟前 / N小时前 / 昨天 / N天前 / MM-DD。"""
    if not ts:
        return ""
    dt = _parse_iso(ts)
    if dt is None:
        return str(ts)[:16].replace("T", " ")
    diff = (now_cst_naive() - dt).total_seconds()
    if diff < 0:
        return "刚刚"
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    if diff < 86400 * 2:
        return "昨天"
    if diff < 86400 * 7:
        return f"{int(diff // 86400)}天前"
    return dt.strftime("%m-%d")



def _parse_ts(ts):
    """把 ISO 时间戳解析为 datetime（失败返回 None），供「仅看未读」客户端过滤。"""
    return _parse_iso(ts)



def render_user_badge(sidebar: bool = True) -> None:
    """在侧边栏/顶栏渲染当前用户头像 + 用户名 + 退出登录按钮 + 市场异动铃铛。"""
    from modules.session import get_user  # 延迟导入：避 session ↔ 本模块循环
    user = get_user() or {}
    username = user.get("username", "?")
    role_cn = "管理员" if user.get("role") == "admin" else "普通用户"
    target = st.sidebar if sidebar else st
    _avatar = get_avatar_data_url() or get_avatar_path(username)
    if _avatar:
        render_avatar(target, _avatar, width=64)
    target.markdown(f"**👤 {username} · {role_cn}**")

    # 退出登录：先弹确认对话框，避免误触（对话框内 st.rerun 为页面级，安全）
    if st.session_state.get("_show_logout_dialog"):
        _confirm_logout_dialog()
    if target.button("🚪 退出登录", key="logout_btn", width="stretch"):
        st.session_state["_show_logout_dialog"] = True
        st.rerun()  # ui_audit_exempt: bare-rerun 置位退出确认对话框标记后必须重跑，@st.dialog 才能弹出

    # 市场异动铃铛（全局，挂用户区下方）
    try:
        render_market_alert_bell(target)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[session] 处理异常: {e}")
        target.caption(f"提醒加载失败：{str(e)[:40]}")



@st.dialog("确认退出登录？")
def _confirm_logout_dialog() -> None:
    """退出登录确认对话框：防误触。确认 → 清登录态并跳登录页；取消 → 关闭。"""
    from modules.session import clear_auth, safe_switch_page  # 延迟导入：避 session ↔ 本模块循环
    xc_warn_box("退出后需要重新登录才能继续使用全部功能。")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("确认退出", key="dlg_logout_yes", width="stretch", type="primary"):
            clear_auth()
            safe_switch_page("pages/90_登录.py")
    with c2:
        if st.button("取消", key="dlg_logout_no", width="stretch"):
            st.session_state["_show_logout_dialog"] = False
            st.rerun()  # ui_audit_exempt: bare-rerun 关闭退出确认对话框，重跑以收尾 dialog 交互



def _parse_alert_summary(code: int, body) -> dict:
    """纯函数：把 /api/market-alerts 的 (code, body) 解析为摘要 dict。

    仅当 HTTP 200 + 响应信封 status=="ok" + data 为 dict 时返回 data；
    其余情况（非 200 / 信封非 ok / data 非 dict / body 非 dict）一律返回 {}。

    抽离动机（隐式修复）：原 `_cached_alert_summary` 在 `if code==200…` 块内才赋值
    `data`，但随后「无条件」`if isinstance(data, dict)` 引用它——一旦 API 返回非 200，
    `data` 根本未绑定，会抛 NameError。该异常被外层 broad except 静默吞掉、恰好返回 {}，
    行为「看似正确」实则极脆弱（一旦收窄 except 立即崩）。此处归一为纯函数，彻底消除
    悬空引用，并便于单测覆盖各分支。
    """
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return {}



@st.cache_data(ttl=30, show_spinner=False)
def _cached_alert_summary(token: str, nonce: int) -> dict:
    """缓存市场异动摘要（未读数 + 最近 5 条），nonce 变化即击穿重取。"""
    try:
        code, body = api_get("/api/market-alerts?limit=5", timeout=8)
        return _parse_alert_summary(code, body)
    except Exception as e:
        logger.warning(f"[session] 获取异动摘要失败: {e}")
    return {}



def render_market_alert_bell(target=st.sidebar) -> None:
    """侧边栏市场异动铃铛：常驻侧边栏，点击展开 popover 显示未读摘要 + 最近异动 + 全部已读。"""
    from modules.session import get_token  # 延迟导入：避 session ↔ 本模块循环
    nonce = int(st.session_state.get("_alert_nonce", 0))
    data = _cached_alert_summary(get_token() or "", nonce)
    unread = int(data.get("unread_count", 0) or 0)
    items = data.get("items", []) or []

    badge = f" 🔴{unread}" if unread else ""
    with target.popover(f"🔔 市场异动{badge}", width="stretch"):
        _sev_icon = {"danger": "⛔", "warning": "⚠️", "info": "ℹ️"}
        if items:
            for it in items[:5]:
                sev = it.get("severity", "info")
                icon = _sev_icon.get(sev, "ℹ️")
                ts = _rel_time(it.get("created_at"))
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
    """共享市场异动面板：可在任意页面末尾挂载；T-224 起整体可折叠（默认收起，未读数进标签）。"""
    from modules.session import get_token  # 延迟导入：避 session ↔ 本模块循环
    nonce = int(st.session_state.get("_alert_panel_nonce", 0))
    data = _cached_alerts_panel(get_token() or "", nonce)
    items = data.get("items", []) or []
    unread = int(data.get("unread_count", 0) or 0)

    label = "🔔 近期异动提醒（自动扫描 · 后台调度）"
    if unread:
        label += f" · 未读 {unread} 条"
    with st.expander(label, expanded=False):
        # 「仅看未读」客户端过滤（依据后端 last_seen，无需改后端 / 重启服务）
        last_seen = _parse_ts(data.get("last_seen")) if data.get("last_seen") else None
        if st.checkbox("仅看未读", key="panel_unread_only", value=False):
            if last_seen is not None:
                items = [it for it in items if (_parse_ts(it.get("created_at")) or datetime.min) > last_seen]
            else:
                items = []  # 从未查看过 → 全部视为已读
        if st.button("✅ 全部标为已读", key="panel_mark_all"):
            code, _ = api_mark_all_alerts_read()
            if code == 200:
                st.session_state["_alert_panel_nonce"] = nonce + 1

        if not items:
            info_banner("暂无异动提醒。后台调度器会在交易时段扫描广度/情绪/估值指标越界并推送。")
            return

        _sev_icon = {"danger": "⛔", "warning": "⚠️", "info": "ℹ️"}
        for it in items:
            sev = it.get("severity", "info")
            icon = _sev_icon.get(sev, "ℹ️")
            ts = _rel_time(it.get("created_at"))
            c1, c2 = st.columns([0.88, 0.12])
            with c1:
                st.markdown(f"{icon} **{it.get('metric_name')}**：{it.get('message')}")
                st.caption(f"　└ {ts}　值 {it.get('value')}　阈值 {it.get('threshold')}")
            with c2:
                if st.button("✓", key=f"panel_read_{it.get('id')}", help="标为已读"):
                    code, _ = api_mark_alert_read(it.get("id"))
                    if code == 200:
                        st.session_state["_alert_panel_nonce"] = nonce + 1
