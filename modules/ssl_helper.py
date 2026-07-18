"""
公共 SSL 关闭工具（收敛 #404）。

本机系统代理会做 TLS 拦截，akshare 部分数据源（新浪财务报表、东方财富 push2 等）
在直连时会因证书链不可达而抛 SSLCertVerificationError。历史上项目里多处各自
patch `requests`，其中行情看板 `_load_lhb` 曾把模块级 `requests.get` 永久改成
`verify=False` 且从不还原，污染整个进程后续所有请求的 TLS 校验（安全隐患）。

此模块统一提供一个**局部生效、退出即恢复**的上下文管理器，patch
`requests.Session.request`（覆盖 requests.get / Session.get / akshare 内部所有走
Session 的请求），避免全局污染。所有需要临时关闭 SSL 校验的地方都应改用它。
"""
import contextlib


@contextlib.contextmanager
def ssl_bypass():
    """临时关闭 requests 的 SSL 校验，仅在 with 块内生效，退出后恢复。

    用法::

        from modules.ssl_helper import ssl_bypass
        with ssl_bypass():
            df = ak.stock_lhb_detail_em(...)

    patch 的是 `requests.Session.request`（而非 `requests.get`），因为 akshare
    内部大量调用走 Session.request；只 patch requests.get 覆盖不全。
    """
    import urllib3
    import requests

    urllib3.disable_warnings()
    _orig = requests.Session.request

    def _patched(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        return _orig(self, *args, **kwargs)

    requests.Session.request = _patched
    try:
        yield
    finally:
        requests.Session.request = _orig
