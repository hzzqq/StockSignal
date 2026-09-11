"""modules/request_utils.py — 项目级共享 HTTP 会话（R89）。

统一 Connection/Read 超时、重试退避，替代各模块零散 ``requests.get/post`` 直连，
复用 TCP/TLS 连接（连接池）降低后端 API 调用开销。

红线（沿用既有约定，不可破坏）：
- 超时兜底：``fundflow._patch_requests_timeout`` 在类层面给 ``requests.Session.request``
  注入默认 timeout，对所有 Session 实例（含本模块共享会话）生效；``http_get/http_post``
  也显式带默认 timeout，双重保险。
- SSL 校验：默认开启；仅 ``STOCKSIGNAL_SSL_BYPASS=1`` 时由 ssl_helper 在类层面临时关闭。
- 代理：``requests.Session`` 默认 ``trust_env=True``，继承 HTTP_PROXY/HTTPS_PROXY
  环境变量（与 ``fundflow._ensure_proxy_and_ssl`` 一致），按请求时读取，无需在此重复设置。
- 重试仅对幂等方法（GET/HEAD/OPTIONS）生效，POST 不重试（避免非幂等副作用，如重复登录/提交）。
"""

import logging
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.site_config import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_SESSION = None
_SESSION_LOCK = threading.Lock()


def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD", "OPTIONS"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.trust_env = True  # 继承代理环境变量
    return s


def get_session() -> requests.Session:
    """返回项目级共享 Session（懒初始化、线程安全、连接池复用）。"""
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                _SESSION = _build_session()
    return _SESSION


def http_get(url: str, **kwargs):
    """共享会话 GET；未显式传 timeout 时回落到 site_config.REQUEST_TIMEOUT。"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    return get_session().get(url, **kwargs)


def http_post(url: str, **kwargs):
    """共享会话 POST（不自动重试，见模块红线）。未显式传 timeout 时回落到默认。"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    return get_session().post(url, **kwargs)
