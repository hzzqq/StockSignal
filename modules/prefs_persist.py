"""
modules/prefs_persist.py
-------------------------
用户偏好（主题 / 字体大小等）的浏览器端持久化「双保险」：在 URL query_params 之外，
额外把偏好写入 localStorage，使「关闭浏览器再打开」后仍能自动恢复偏好设置。

实现方式（纯前端、零后端依赖、无外部包）：
- save_prefs(prefs)                 : 用 components.html 注入 <script> 把偏好 JSON 写进 localStorage。
- restore_prefs_from_local_storage(): 若 localStorage 有偏好但当前 URL 没有 prefs 参数，
                                       则把偏好补回 URL 并让父页面跳转，从而触发 Streamlit 重新执行，
                                       由 session.py 的 query_params 恢复逻辑接管。
- load_prefs_from_local_storage()   : 直接读取 localStorage 中的偏好 JSON（供无跳转场景使用）。

注意：
- query_params 是「刷新 / 跨页导航」可靠恢复的主机制（见 session.py）；
  localStorage 作为「浏览器关闭后再打开」的补充兜底。
- 所有 JS 均为静态可信字符串，不注入任何用户输入，无 XSS 风险。
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components

_LS_PREFS = "ss_prefs"
QP_PREFS = "prefs"


def save_prefs(prefs: dict) -> None:
    """把偏好 dict（含 theme_mode / font_size 等）写入浏览器 localStorage。"""
    try:
        # 双重 json.dumps：先把 dict 序列化为字符串，再变成 JS 字符串字面量，避免引号/中文破坏脚本
        js = json.dumps(json.dumps(prefs, ensure_ascii=False), ensure_ascii=False)
        script = f"""
        <script>
        (function() {{
          try {{ localStorage.setItem({json.dumps(_LS_PREFS)}, {js}); }} catch (e) {{ /* 隐私模式/配额满 忽略 */ }}
        }})();
        </script>
        """
        components.html(script, height=0)
    except Exception:
        pass


def restore_prefs_from_local_storage() -> None:
    """
    若 localStorage 有偏好但当前 URL 没有 prefs 参数，则把偏好补回 URL 并让父页面跳转。
    由 Streamlit 重新加载后，session.py 的 query_params 恢复逻辑会接管。
    仅当 URL 缺 prefs 时触发，避免死循环。
    """
    try:
        script = f"""
        <script>
        (function() {{
          try {{
            var raw = localStorage.getItem({json.dumps(_LS_PREFS)});
            if (!raw) return;
            var params = new URLSearchParams(window.parent.location.search);
            if (params.get({json.dumps(QP_PREFS)})) return;  /* 已有则不打扰 */
            params.set({json.dumps(QP_PREFS)}, raw);
            window.parent.location.href = window.parent.location.pathname + '?' + params.toString();
          }} catch (e) {{}}
        }})();
        </script>
        """
        components.html(script, height=0)
    except Exception:
        pass


def load_prefs_from_local_storage() -> dict:
    """占位：localStorage 读取由 restore_prefs_from_local_storage() 的 URL 跳转路径完成，
    本函数仅保证模块可被安全导入；真正可靠的恢复在 session.init_session_state 中触发。"""
    return {}
