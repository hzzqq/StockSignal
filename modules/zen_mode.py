"""Zen 专注模式（G11）——一键隐藏侧栏与装饰元素，进入低干扰专注态。

对标 ghostfolio 的 Zen Mode：持续做「减法」，专注阅读/研究时屏蔽导航噪声。

设计原则（对齐项目纪律）：
- **纯 UI 增强，零业务副作用**；状态存 ``st.session_state['zen_mode']``。
- **单点注入**：由 ``modules/page_utils.render_standard_page()`` 每页调用
  ``render_zen_toggle()``，全站 41 页自动生效，**零逐页改动**。
- **不困住用户**：侧栏被隐藏后，主区顶部保留「✕ 退出专注」按钮。
- **失败静默**：任何注入异常都吞掉（记 warning），绝不影响页面主流程——
  与项目「诚实语义/不崩溃」红线一致。
"""
from __future__ import annotations

import logging

import streamlit as st

logger = logging.getLogger(__name__)

ZEN_KEY = "zen_mode"

# 隐藏侧栏 + 页头装饰 + 收敛主区留白（低干扰阅读态）
_ZEN_CSS = """
<style>
section[data-testid="stSidebar"]{display:none !important;}
[data-testid="stHeader"]{display:none !important;}
[data-testid="stToolbar"]{display:none !important;}
#MainMenu{visibility:hidden;}
footer{visibility:hidden;}
[data-testid="stAppViewContainer"] .block-container{
  max-width:1180px;padding-top:1.1rem;padding-bottom:3rem;
}
</style>
"""


def zen_enabled() -> bool:
    """当前是否处于 Zen 专注态（读 session_state，异常安全）。"""
    try:
        return bool(st.session_state.get(ZEN_KEY, False))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[zen_mode] 读取状态失败: {e}")
        return False


def _render_exit() -> None:
    """悬浮式退出入口：侧栏隐藏后用户仍能一键退出，避免被困。"""
    _, right = st.columns([6, 1])
    with right:
        try:
            if st.button("✕ 退出专注", key="_zen_exit", help="退出 Zen 专注模式，恢复侧栏导航"):
                st.session_state[ZEN_KEY] = False
                st.rerun()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[zen_mode] 退出按钮渲染失败: {e}")


def render_zen_toggle() -> None:
    """渲染 Zen 开关并（开启时）注入隐藏 CSS。每个页面渲染一次，幂等。

    - 嵌入态（``_embed_active``）跳过：子视图内不应再叠加全站级控件。
    - 开关固定 key ``zen_mode``；异常（含重复 key）一律吞掉，不阻断页面。
    """
    try:
        if st.session_state.get("_embed_active"):
            return
        try:
            import streamlit as _st_check  # noqa: F401
            with st.sidebar:
                st.toggle(
                    "🧘 Zen 专注模式",
                    key=ZEN_KEY,
                    help="隐藏侧栏与装饰，进入低干扰专注态（⌘K 跳转在专注态下暂不可用）",
                )
        except AttributeError:
            # 老版本 Streamlit 无 st.toggle → 退化为 checkbox（同 key）
            with st.sidebar:
                st.checkbox("🧘 Zen 专注模式", key=ZEN_KEY, help="隐藏侧栏与装饰，进入低干扰专注态")
        if st.session_state.get(ZEN_KEY):
            st.markdown(_ZEN_CSS, unsafe_allow_html=True)
            _render_exit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[zen_mode] 注入失败: {e}")
