"""
modules/auth_persist.py
-----------------------
浏览器端登录态「双保险」：在 URL query_params 之外，额外把 token 写入
localStorage，使整页刷新(F5) 或跨页面跳转丢失 query_params 时仍能自动恢复登录态。

实现方式（纯前端、零后端依赖、无外部包）：
- save_to_local_storage()   : 用 components.html 注入一段 <script> 把 token/user 写进 localStorage（fire-and-forget，不需回传）。
- restore_from_local_storage(): 注入一段 <script>，若 localStorage 有 token 但当前 URL 没有，则把 token 补回 URL 并让父页面跳转，
                                从而触发 Streamlit 重新执行、由 session.py 的 query_params 恢复逻辑接管。
- clear_local_storage()     : 退出登录时清掉 localStorage 中的凭证。

为什么不用 cookie：Streamlit 1.58 下 streamlit-cookies-manager 不稳定；localStorage 同源可靠且不受 session GC 影响。

注意：
- 仅当 URL 缺 token 时才触发跳转，避免死循环。
- 所有 JS 均为静态可信字符串，不注入任何用户输入，无 XSS 风险。
"""
from __future__ import annotations
import json
import logging
import streamlit.components.v1 as components
import streamlit as st
logger = logging.getLogger(__name__)
_LS_TOKEN = 'ss_token'
_LS_USER = 'ss_user'

def save_to_local_storage(token: str, user: dict) -> None:
    """把 token 与 user 写入浏览器 localStorage（token 单独存，user 以 JSON 字符串存）。"""
    try:
        token_js = json.dumps(token, ensure_ascii=False)
        user_js = json.dumps(json.dumps(user, ensure_ascii=False), ensure_ascii=False)
        js = f'\n        <script>\n        (function() {{\n          try {{\n            localStorage.setItem({json.dumps(_LS_TOKEN)}, {token_js});\n            localStorage.setItem({json.dumps(_LS_USER)}, {user_js});\n          }} catch (e) {{ /* 隐私模式/配额满 可能抛错，忽略 */ }}\n        }})();\n        </script>\n        '
        st.markdown(js, unsafe_allow_html=True)
    except Exception as e:
        logger.warning('[auth_persist] save_to_local_storage 失败: %s', e)

def restore_from_local_storage() -> None:
    """
    若 localStorage 有 token 但当前 URL 没有，则把 token 补回 URL 并让父页面跳转。
    由 Streamlit 重新加载后，session.py 的 query_params 恢复逻辑会接管。
    仅当 URL 缺 token 时触发，避免死循环。
    """
    try:
        js = f"\n        <script>\n        (function() {{\n          try {{\n            var token = localStorage.getItem({json.dumps(_LS_TOKEN)});\n            if (!token) return;\n            var params = new URLSearchParams(window.parent.location.search);\n            if (params.get('token')) return;  /* 已有则不打扰 */\n            params.set('token', token);\n            window.parent.location.href = window.parent.location.pathname + '?' + params.toString();\n          }} catch (e) {{}}\n        }})();\n        </script>\n        "
        st.markdown(js, unsafe_allow_html=True)
    except Exception as e:
        logger.warning('[auth_persist] restore_from_local_storage 失败: %s', e)

def clear_local_storage() -> None:
    """退出登录时清除浏览器 localStorage 中的凭证。"""
    try:
        js = f'\n        <script>\n        (function() {{\n          try {{\n            localStorage.removeItem({json.dumps(_LS_TOKEN)});\n            localStorage.removeItem({json.dumps(_LS_USER)});\n          }} catch (e) {{}}\n        }})();\n        </script>\n        '
        st.markdown(js, unsafe_allow_html=True)
    except Exception as e:
        logger.warning('[auth_persist] clear_local_storage 失败: %s', e)