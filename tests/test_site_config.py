"""site_config 离线测试：环境变量覆盖 + 关键不变量（网络超时 < 调用硬边界）。"""
import importlib

import modules.site_config as sc


def test_defaults_sane():
    """默认：REQUEST_TIMEOUT=10，CALL_TIMEOUT_CAP > REQUEST_TIMEOUT（防丢线程的关键）。"""
    assert sc.REQUEST_TIMEOUT == 10.0
    assert sc.CALL_TIMEOUT_CAP > sc.REQUEST_TIMEOUT
    assert sc.PROXY_DEFAULT.startswith("http")


def test_env_override(monkeypatch):
    # 重新导入，避免被其它测试（如 test_netguard 的 _drop_modules）卸载 modules.* 影响
    import modules.site_config as sc_local
    monkeypatch.setenv("STOCKSIGNAL_REQ_TIMEOUT", "7")
    monkeypatch.setenv("STOCKSIGNAL_PROXY", "http://proxy.example:9999")
    monkeypatch.setenv("STOCKSIGNAL_CALL_TIMEOUT", "20")
    importlib.reload(sc_local)
    try:
        assert sc_local.REQUEST_TIMEOUT == 7.0
        assert sc_local.PROXY_DEFAULT == "http://proxy.example:9999"
        assert sc_local.CALL_TIMEOUT_CAP == 20.0
        # 不变量仍成立：CALL_TIMEOUT_CAP > REQUEST_TIMEOUT
        assert sc_local.CALL_TIMEOUT_CAP > sc_local.REQUEST_TIMEOUT
    finally:
        importlib.reload(sc_local)  # 还原为默认，避免影响同会话其它测试


def test_no_leak_invariant_comment_holds():
    """强约束：取数硬边界必须严格大于底层网络默认超时，否则仍会丢线程。"""
    assert sc.CALL_TIMEOUT_CAP > sc.REQUEST_TIMEOUT
