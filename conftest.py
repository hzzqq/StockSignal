"""pytest 全局前置（根目录 conftest）。

确保在收集任何测试之前，streamlit 就以**真实**（venv 已装 1.59.2，API 完整）形式
常驻 sys.modules。这样各测试文件即使写了 `sys.modules["streamlit"] = 残缺桩`
（历史遗留），也会被真实 streamlit 占位、无法覆盖，从而避免 import 真实模块
（如 modules.session 的 @st.cache_data / @st.dialog / `from streamlit import v1`）
时因拿到残缺桩而抛 AttributeError。

若 venv 未安装 streamlit，则提供一份完整兜底桩（装饰器返回 identity，其余 noop），
行为等价。
"""
import sys


def _install_streamlit():
    # 优先使用真实 streamlit
    try:
        import streamlit  # noqa: F401  (真实，API 完整)
        return
    except Exception:
        pass

    # 兜底：venv 无 streamlit 时提供完整桩
    import types

    class _CtxMgr:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __getattr__(self, name):
            def _noop(*a, **k):
                return False

            return _noop

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.query_params = {}
    st.cache_data = lambda *a, **k: (lambda f: f)
    st.cache_resource = lambda *a, **k: (lambda f: f)
    st.fragment = lambda *a, **k: (lambda f: f)
    st.dialog = lambda *a, **k: (lambda f: f)
    st.singleton = lambda *a, **k: (lambda f: f)
    st.container = lambda *a, **k: _CtxMgr()
    st.columns = lambda sizes, *a, **k: [_CtxMgr() for _ in sizes]
    st.spinner = lambda *a, **k: _CtxMgr()
    for fn in (
        "markdown", "title", "caption", "metric", "success", "info", "warning",
        "error", "button", "checkbox", "radio", "text_input", "text_area",
        "selectbox", "slider", "set_page_config", "rerun", "write", "header",
        "subheader", "json", "dataframe", "table", "image", "plotly_chart",
        "pyplot", "line_chart", "bar_chart", "sidebar", "expander", "tabs",
        "balloons", "snow", "toast", "exception", "code", "divider", "stop",
    ):
        setattr(st, fn, lambda *a, **k: None)

    def _getattr(name):
        if name.startswith("cache") or name.startswith("experimental_") or name in (
            "fragment", "dialog", "singleton",
        ):
            return lambda *a, **k: (lambda f: f)
        return lambda *a, **k: None

    st.__getattr__ = _getattr
    sys.modules["streamlit"] = st


_install_streamlit()


def _install_offline_guard():
    """session 级永久网络屏蔽（R95 加固回归稳定性）。

    替代 test_pages_smoke 内 autouse fixture 的「fixture 级 monkeypatch 复原」——
    旧方案在 fixture yield 后复原网络桩，AppTest 子线程若延后触网会真连网被沙箱屏蔽→挂死，
    整批 pytest 被单页卡死拖垮（此前只能靠 SMOKE_BATCH 手动分批绕过）。

    这里在 session 启动时**永久**替换 socket.create_connection / urllib.urlopen /
    requests.Session.request 为即时失败，scope=session，不随用例复原，
    彻底杜绝「复原后延后触网」的卡死窗口。可用环境变量 OFFLINE_TEST=0 关闭（调试用）。
    """
    import os
    if os.environ.get("OFFLINE_TEST", "1") == "0":
        return
    import urllib.request as _urllib_req
    import socket as _sock

    try:
        import requests
    except Exception:  # pragma: no cover
        requests = None

    def _fail(*args, **kwargs):
        # 模拟「后端/网络不可达」——抛 ConnectionError（requests.exceptions.RequestException
        # 子类），与真实「Flask 没起 / 断网」时 requests 抛出的异常一致，从而让页面内
        # 既有的 _api_request 降级路径（返回 -1, {message}）正常生效，而非裸 OSError
        # 穿透未被捕获的 RequestException 分支。这是验证真实降级能力，而非创造新异常。
        raise requests.exceptions.ConnectionError("smoke: offline guard (session-level)")

    def _fail_urlopen(*a, **k):
        raise OSError("smoke: offline guard (urllib)")

    def _fail_conn(*a, **k):
        raise OSError("smoke: offline guard (socket)")

    _sock.create_connection = _fail_conn
    _urllib_req.urlopen = _fail_urlopen
    if requests is not None:
        requests.Session.request = _fail
        # 持久信号：netguard/fundflow 的 timeout 补丁会再包一层 Session.request
        # （函数名不再是 _fail），但不会动这个属性——测试用它判断守卫是否生效。
        requests.Session._ss_offline_guard = True


_install_offline_guard()


def _install_data_isolation():
    """测试期数据落盘隔离（收尾硬伤修复）。

    把 SS_DATA_DIR 指向一个 session 级临时目录。所有依赖 data/ 的模块
    （shepherd_ladder.LADDER_FILE / decision.DATA_DIR 等）在测试中写到 tmp，
    而非污染真实 data/shepherd_ladder_history.json —— 后者是 15:30 自动化读取、
    晋级率/回测依赖的真实数据源，绝不能被测试 stub 假数据覆盖。

    仅当环境变量未显式设置时启用（本地调试可 SS_DATA_DIR=真实路径 覆盖回真实目录）。
    """
    import os
    import tempfile

    if os.environ.get("SS_DATA_DIR"):
        return
    os.environ["SS_DATA_DIR"] = tempfile.mkdtemp(prefix="ss_test_data_")


_install_data_isolation()


def pytest_sessionfinish(session, exitstatus):
    """session 收尾：打印 skip 率与覆盖率红线提示。

    暴露「黑盒测试大量 pytest.skip 致覆盖率虚高」问题（评测集诊断项 #3）。
    仅观测、不强制 fail——CI 可据 .coverage.json 自行设门槛。
    """
    try:
        stats = session.testscollected
        skipped = session.skipped
        if stats:
            rate = skipped / stats * 100
            msg = (
                f"\n[评测集体检] 收集 {stats} 用例 | 跳过 {skipped} "
                f"({rate:.1f}%) | 通过 {session.testspassed} "
                f"| 失败 {session.testsfailed}"
            )
            if rate > 30:
                msg += "\n  ⚠️ skip 率 >30%：黑盒/集成用例大量跳过，覆盖率存在虚高风险，"
                msg += "建议补真网集成测试或区分『真 skip』与『应跑未跑』。"
            print(msg, flush=True)
    except Exception:
        pass
