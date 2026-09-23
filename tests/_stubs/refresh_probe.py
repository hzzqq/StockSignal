"""AppTest 桩页面：is_authenticated + 过期续期行为探针。

不参与业务。运行时假定 session_state 里可能已注入 auth_token；
页面输出 RESULT:<is_authenticated 结果> 供测试断言。
"""
import streamlit as st

from modules import session

session.init_session_state()
st.write(f"RESULT:{session.is_authenticated()}")
