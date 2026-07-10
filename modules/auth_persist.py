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

import streamlit.components.v1 as components

_LS_TOKEN = "ss_token"
_LS_USER = "ss_user"


def save_to_local_storage(token: str, user: dict) -> None:
    """把 token 与 user 写入浏览器 localStorage（token 单独存，user 以 JSON 字符串存）。"""
    try:
        # 双重 json.dumps：先序列化 user dict，再把它变成 JS 字符串字面量，避免引号/中文破坏脚本
        token_js = json.dumps(token, ensure_ascii=False)
        user_js = json.dumps(json.dumps(user, ensure_ascii=False), ensure_ascii=False)
        js = f"""
        <script>
        (function() {{
          try {{
            localStorage.setItem({json.dumps(_LS_TOKEN)}, {token_js});
            localStorage.setItem({json.dumps(_LS_USER)}, {user_js});
          }} catch (e) {{ /* 隐私模式/配额满 可能抛错，忽略 */ }}
        }})();
        </script>
        """
        components.html(js, height=0)
    except Exception:
        pass


def restore_from_local_storage() -> None:
    """
    若 localStorage 有 token 但当前 URL 没有，则把 token 补回 URL 并让父页面跳转。
    由 Streamlit 重新加载后，session.py 的 query_params 恢复逻辑会接管。
    仅当 URL 缺 token 时触发，避免死循环。
    """
    try:
        js = f"""
        <script>
        (function() {{
          try {{
            var token = localStorage.getItem({json.dumps(_LS_TOKEN)});
            if (!token) return;
            var params = new URLSearchParams(window.parent.location.search);
            if (params.get('token')) return;  /* 已有则不打扰 */
            params.set('token', token);
            window.parent.location.href = window.parent.location.pathname + '?' + params.toString();
          }} catch (e) {{}}
        }})();
        </script>
        """
        components.html(js, height=0)
    except Exception:
        pass


def clear_local_storage() -> None:
    """退出登录时清除浏览器 localStorage 中的凭证。"""
    try:
        js = f"""
        <script>
        (function() {{
          try {{
            localStorage.removeItem({json.dumps(_LS_TOKEN)});
            localStorage.removeItem({json.dumps(_LS_USER)});
          }} catch (e) {{}}
        }})();
        </script>
        """
        components.html(js, height=0)
    except Exception:
        pass
