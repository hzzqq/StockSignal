"""AppTest 桩页面：仅调用 init_session_state，用于验证刷新保持登录的 URL 回写。

不参与业务，仅作为回归测试的最小可运行页面。
"""
import streamlit as st

from modules.session import init_session_state

init_session_state()
st.write("init-done")
