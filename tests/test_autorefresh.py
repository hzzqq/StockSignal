"""autorefresh 弹性导入回归测试（cycle 28）。

历史 bug：modules/autorefresh.py 在 try 里写成
    from modules.autorefresh import st_autorefresh   # 误写成「自我导入」
而非
    from streamlit_autorefresh import st_autorefresh
由于模块在自身定义 st_autorefresh 之前就「从自身导入」该名，
ImportError 必然触发 → 永远走 except 分支的 no-op，即使
streamlit_autorefresh 已安装，自动刷新也静默失效（设计文档承诺的
「包存在 → 透传真实 st_autorefresh」永远不生效）。

本测试通过注入/移除伪造的 streamlit_autorefresh 包并重载模块来验证：
- 包存在时，st_autorefresh 必须是「真实」实现（非 no-op）；
- 包缺失时，st_autorefresh 必须是可调用的 no-op（接受任意参数、返回 None）。
"""
import importlib
import sys
import types

import modules.autorefresh as ar


def _reload_with(pkg_present: bool):
    """在 sys.modules 注入/移除伪造的 streamlit_autorefresh 后重载模块，
    返回重载后的 st_autorefresh；finally 中还原环境，避免污染其它测试。"""
    pkg = "streamlit_autorefresh"
    saved = sys.modules.pop(pkg, None)
    if pkg_present:
        fake = types.ModuleType(pkg)

        def _real(*_a, **_k):
            return "REAL_AUTOREFRESH"

        fake.st_autorefresh = _real
        sys.modules[pkg] = fake
    try:
        importlib.reload(ar)
        return ar.st_autorefresh
    finally:
        if pkg in sys.modules:
            del sys.modules[pkg]
        if saved is not None:
            sys.modules[pkg] = saved
        # 还原到真实环境状态（本机未安装该包时为 no-op）
        importlib.reload(ar)


def test_uses_real_implementation_when_installed():
    fn = _reload_with(True)
    assert callable(fn)
    # 真实实现应被透传（返回我们注入的哨兵标记）
    assert fn(limit=5, key="x") == "REAL_AUTOREFRESH"


def test_degrades_to_noop_when_missing():
    fn = _reload_with(False)
    assert callable(fn)
    # no-op：接受任意参数、返回 None，绝不抛异常
    assert fn(limit=5, key="x") is None
    assert fn() is None
