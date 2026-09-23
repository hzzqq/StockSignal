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

import json
import logging
import os
import threading
import time
from urllib.parse import urlparse

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


# ─────────── 请求治理层（R91，对标 quantdash 代理层 / 治愈上游限流） ───────────
# 背景：本项目被上游限流拖死过多次（腾讯行情卡在 2026-08-28；baostock 全量刷新 11h
# 只跑完约 1/3）。requests 自带 Retry 只在**单次请求**维度退避，缺三条更关键的治理：
#   ① per-host 最小请求间隔（节流）——防止密集请求把上游打爆
#   ② 连续失败熔断（circuit breaker）——上游已挂时快速失败，别硬等超时
#   ③ 快照回退 + source 标注——失败时回退**上次真实快照**，并如实标注来源
# 红线（诚实口径）：③ 回退的是"上次真实抓到的快照"，**绝不回退到演示/合成数据**；
#   回退结果必须带 source="snapshot" 与快照时间，让调用方和 UI 能如实披露。

HOST_MIN_INTERVAL = float(os.environ.get("SS_HOST_MIN_INTERVAL", "0.2"))
FAIL_THRESHOLD = int(os.environ.get("SS_FAIL_THRESHOLD", "5"))
COOLDOWN_SECONDS = float(os.environ.get("SS_COOLDOWN_SECONDS", "60"))

_last_call_at: dict = {}
_consec_fail: dict = {}
_cooldown_until: dict = {}
_gov_lock = threading.Lock()


class CircuitOpenError(requests.RequestException):
    """上游处于熔断冷却中，快速失败。

    故意继承 ``requests.RequestException``：调用方已有的
    ``except requests.RequestException`` 无需改动即可兜住，不引入新的崩溃路径。
    """


def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        return url


_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "0.0.0.0")


def _throttle(host: str) -> None:
    """同一 host 两次请求之间至少间隔 HOST_MIN_INTERVAL 秒。

    本机后端（127.0.0.1/localhost）**不节流**——节流是为了防上游限流，
    给自家 Flask 后端加上限只会拖慢页面渲染，属于自我伤害。
    """
    if HOST_MIN_INTERVAL <= 0:
        return
    if host.split(":")[0] in _LOCAL_HOSTS:
        return
    with _gov_lock:
        wait = HOST_MIN_INTERVAL - (time.monotonic() - _last_call_at.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    with _gov_lock:
        _last_call_at[host] = time.monotonic()


def _in_cooldown(host: str) -> bool:
    with _gov_lock:
        until = _cooldown_until.get(host, 0.0)
    return time.monotonic() < until


def record_success(host: str) -> None:
    with _gov_lock:
        _consec_fail[host] = 0
        _cooldown_until.pop(host, None)


def record_failure(host: str) -> None:
    with _gov_lock:
        n = _consec_fail.get(host, 0) + 1
        _consec_fail[host] = n
        if n >= FAIL_THRESHOLD:
            _cooldown_until[host] = time.monotonic() + COOLDOWN_SECONDS


def breaker_stats() -> dict:
    """各 host 的熔断观测（供 SLA 看板 / 排障）。"""
    now = time.monotonic()
    with _gov_lock:
        hosts = set(_consec_fail) | set(_cooldown_until) | set(_last_call_at)
        return {
            h: {
                "consec_fail": _consec_fail.get(h, 0),
                "cooling": now < _cooldown_until.get(h, 0.0),
                "cooldown_remain": round(max(0.0, _cooldown_until.get(h, 0.0) - now), 1),
            }
            for h in sorted(hosts)
        }


def reset_governance() -> None:
    """清空治理状态（测试用）。"""
    with _gov_lock:
        _last_call_at.clear()
        _consec_fail.clear()
        _cooldown_until.clear()


def _snapshot_dir() -> str:
    base = os.environ.get("SS_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    return os.path.join(base, "http_snapshots")


# ─────────── 代理 IP 池接入（免费 best-effort 抗封禁轮换） ───────────
# 启用条件：环境变量 SS_PROXY_POOL=1。仅对**非本机**目标生效；本机 Flask 后端不走代理。
# 代理池空/全失效时回退直连，绝不伪造数据、绝不无限阻塞。
# 红线：本模块只改请求出口，不改动既有熔断/节流/快照回退逻辑；失败时仍如实走快照回退。
_PROXY_MAX_ATTEMPTS = int(os.environ.get("SS_PROXY_MAX_ATTEMPTS", "3"))


def _should_use_proxy(host: str) -> bool:
    try:
        from modules.proxy_pool import get_proxy_pool
    except Exception:  # noqa: BLE001
        return False
    pool = get_proxy_pool()
    if not pool.enabled:
        return False
    if host.split(":")[0] in _LOCAL_HOSTS:
        return False
    return True


def _call(method: str, url: str, kwargs: dict):
    """执行单次请求（不记账）。"""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    sess = get_session()
    if method == "POST":
        return sess.post(url, **kwargs)
    return sess.get(url, **kwargs)


def _account(resp, host: str) -> None:
    if getattr(resp, "status_code", 200) >= 500:
        record_failure(host)
    else:
        record_success(host)


def _request(method: str, url: str, **kwargs):
    """带治理 + 代理轮换的请求入口（http_get / http_post 共用）。"""
    host = _host_of(url)
    if _in_cooldown(host):
        raise CircuitOpenError(f"上游熔断冷却中，已跳过请求: {host}")
    _throttle(host)

    # 未启用代理 或 目标为本机后端 → 直连（沿用既有熔断/节流/记账）
    if not _should_use_proxy(host):
        try:
            resp = _call(method, url, kwargs)
        except Exception:
            record_failure(host)
            raise
        _account(resp, host)
        return resp

    # 代理轮换模式：封了换一个 IP 再试
    max_attempts = 1 if method == "POST" else _PROXY_MAX_ATTEMPTS
    for _ in range(max_attempts):
        try:
            from modules.proxy_pool import get_proxy_pool
            pool = get_proxy_pool()
            proxies = pool.acquire_for_request()
        except Exception:  # noqa: BLE001
            proxies = None
        if proxies is None:
            break  # 无可用代理 → 走直连兜底
        kwargs["proxies"] = proxies
        try:
            resp = _call(method, url, kwargs)
        except (requests.RequestException, OSError) as e:
            logger.debug("代理出口失败，准备轮换: %s", e)
            try:
                pool.rotate_on_failure()
            except Exception:  # noqa: BLE001
                pass
            continue
        code = getattr(resp, "status_code", 200)
        # 这些状态码通常意味着当前出口 IP 被限/被封 → 换 IP 重试
        if code in (407, 429, 403) or code >= 500:
            logger.debug("代理出口返回 %s，准备轮换", code)
            try:
                pool.rotate_on_failure()
            except Exception:  # noqa: BLE001
                pass
            continue
        _account(resp, host)
        return resp

    # 兜底：直连（无代理）
    kwargs.pop("proxies", None)
    logger.warning("代理池不可用/耗尽，回退直连: %s", host)
    try:
        resp = _call(method, url, kwargs)
    except Exception:
        record_failure(host)
        raise
    _account(resp, host)
    return resp


def http_get(url: str, **kwargs):
    """共享会话 GET（per-host 节流 + 熔断 + 可选代理轮换）。

    - 未显式传 timeout 时回落到 site_config.REQUEST_TIMEOUT；
    - 上游熔断冷却中抛 ``CircuitOpenError``（RequestException 子类，现有 except 不受影响）；
    - 成功/失败均记账，供 ``breaker_stats()`` 观测；
    - 启用 ``SS_PROXY_POOL=1`` 时，对非本机目标自动轮换免费代理 IP，封了换一个再试，
      池空/全失效则回退直连（绝不伪造数据）。
    """
    return _request("GET", url, **kwargs)


def http_post(url: str, **kwargs):
    """共享会话 POST（不自动重试，见模块红线；可选代理出口）。未显式传 timeout 时回落到默认。"""
    return _request("POST", url, **kwargs)


def fetch_with_snapshot(key: str, fetcher, ttl: float = 600.0,
                        snapshot_dir: str | None = None) -> dict:
    """带快照回退的取数：成功缓存真实结果，失败回退上次真实快照并**如实标注**。

    返回 ``{data, source, as_of, error}``，``source`` 三态：
      - ``"live"``        本次真实抓取成功
      - ``"snapshot"``    本次失败，回退上次真实快照（``as_of`` = 快照时间）
      - ``"unavailable"`` 既没抓到、也无任何历史快照 —— **绝不合成数据填充**

    ``ttl`` 秒内快照视为新鲜直接复用（不重复打上游）；``fetcher`` 抛异常不向上抛，
    而是转成 snapshot/unavailable 结果，由调用方决定如何披露（这是诚实口径的关键）。
    """
    import datetime as _dt

    d = snapshot_dir or _snapshot_dir()
    path = os.path.join(d, f"{key}.json")

    def _read() -> dict | None:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return None

    snap = _read()
    now = time.time()
    if snap is not None and (now - float(snap.get("_ts", 0))) < ttl:
        return {"data": snap.get("data"), "source": "snapshot",
                "as_of": snap.get("_iso"), "error": None}
    try:
        data = fetcher()
    except Exception as e:  # noqa: BLE001
        if snap is None:
            return {"data": None, "source": "unavailable", "as_of": None,
                    "error": f"{type(e).__name__}: {e}"}
        return {"data": snap.get("data"), "source": "snapshot",
                "as_of": snap.get("_iso"), "error": f"{type(e).__name__}: {e}"}
    iso = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_ts": now, "_iso": iso, "data": data}, f, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001  # 缓存写失败不影响本次真实结果（T-160 留痕）
        logger.debug("[request_utils] 缓存写盘失败(%s): %s", path, e)
    return {"data": data, "source": "live", "as_of": iso, "error": None}
