"""modules/proxy_pool.py — 免费代理 IP 池（Best-effort 抗封禁轮换）。

目标
----
每天爬取（akshare / 东方财富 / 新浪 等 HTTP scraper）时，若当前出口 IP 被封，
自动切换到下一个可用代理 IP，提高「封了换一个还能爬成功」的概率。

覆盖范围（诚实口径，重要）
--------------------------
- ✅ **HTTP 层 scraper 有效**：
  - 本项目用 ``request_utils.http_get/http_post`` 直接抓的源（东财 push2 / 新浪等）。
  - akshare：本模块在启用时把进程级 ``HTTPS_PROXY``/``HTTP_PROXY`` 设成当前代理，
    akshare 内部 ``requests`` 默认 ``trust_env=True`` 会继承，**自动走轮换出口 IP**，
    无需改动 akshare 任何调用点。
- ❌ **baostock 无效**：baostock 是**账号级**限流/连接数限制，不是 IP 封禁，
  换 IP 毫无作用。它的续拉由 Plan B 自动化另走（baostock 重拉），与本模块正交。

免费代理的硬现实（务必知悉）
----------------------------
- 公开免费代理质量极低：慢、大量失效、且存在**蜜罐/投毒**风险。
- 因此本模块**不保证 100% 成功**，它是「尽力而为」的韧性层，不是银弹。
- 每个代理有超时上限与连续失败计数，连续失败即降级跳过，**永不因死代理无限阻塞**。
- 代理池空 / 全失效时，**回退直连（无代理）**，绝不伪造数据、绝不无限等待。
- 真正可靠的出路是付费代理 / Tushare（见 docs），本模块只是「免费兜底」。

启用方式
--------
默认 **关闭**。设环境变量 ``SS_PROXY_POOL=1`` 启用；可选：
- ``SS_PROXIES=http://1.2.3.4:8080,http://5.6.7.8:8888`` 手动指定代理（跳过自动采集，
  适合临时塞入自有/付费列表）。
- ``SS_PROXY_COLLECT_INTERVAL=3600`` 自动采集间隔（秒）。
- ``SS_PROXY_VALIDATE_TIMEOUT=8`` 单个代理校验超时（秒）。
- ``SS_PROXY_MAX_ATTEMPTS=3`` 单次请求最多尝试几个代理。
"""

import logging
import os
import re
import threading
import time

import requests

logger = logging.getLogger(__name__)

_PROXY_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}:\d+$")

# 免费代理采集源（best-effort，任一挂了不影响其它；全挂则池为空→直连）。
_COLLECT_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
]

# 校验出口 IP 用的轻量端点（返回自身 IP 的 JSON）。
_VALIDATE_URL = "https://api.ipify.org?format=json"


class ProxyPool:
    """进程内免费代理池：采集 → 校验 → 轮换 → 失败即跳过。"""

    def __init__(self, enabled: bool | None = None,
                 collect_interval: float | None = None,
                 validate_timeout: float | None = None,
                 fail_threshold: int = 3):
        self.enabled = (
            os.environ.get("SS_PROXY_POOL", "0") == "1"
        ) if enabled is None else enabled
        self.collect_interval = (
            float(os.environ.get("SS_PROXY_COLLECT_INTERVAL", "3600"))
        ) if collect_interval is None else collect_interval
        self.validate_timeout = (
            float(os.environ.get("SS_PROXY_VALIDATE_TIMEOUT", "8"))
        ) if validate_timeout is None else validate_timeout
        self.fail_threshold = fail_threshold

        self._candidates: list[str] = []
        self._validated_ok: set[str] = set()
        self._dead: set[str] = set()
        self._fail: dict[str, int] = {}
        self._current: str | None = None
        self._cursor = -1  # 首次 next_candidate 返回下标 0
        self._last_collect = 0.0
        self._static_provided = False
        self._lock = threading.Lock()

        static = os.environ.get("SS_PROXIES", "")
        if static:
            norm = []
            for p in static.split(","):
                p = p.strip()
                if not p:
                    continue
                if "://" not in p:  # 补全 scheme，避免 http:// 漏写
                    p = "http://" + p
                norm.append(p)
            self._candidates = norm
            self._static_provided = bool(norm)
            self._last_collect = time.time()

    # ───────── 采集 ─────────
    def _collect(self) -> list[str]:
        """从公开源采集候选代理（best-effort，去重）。"""
        found: list[str] = []
        for url in _COLLECT_SOURCES:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                for line in r.text.splitlines():
                    line = line.strip()
                    if _PROXY_RE.match(line):
                        found.append("http://" + line)
            except Exception as e:  # noqa: BLE001
                logger.debug("代理采集源失败 %s: %s", url, e)
                continue
        seen: set[str] = set()
        out: list[str] = []
        for p in found:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def ensure_fresh(self) -> None:
        """若池空或已过期，重新采集（I/O 在锁外执行，避免阻塞其它请求）。"""
        if not self.enabled or self._static_provided:
            return
        with self._lock:
            stale = (time.time() - self._last_collect) > self.collect_interval
            empty = len(self._candidates) == 0
        if not (stale or empty):
            return
        cands = self._collect()
        with self._lock:
            if cands:
                self._candidates = cands
            self._last_collect = time.time()

    # ───────── 选取 ─────────
    def next_candidate(self, exclude=()) -> str | None:
        """按游标返回下一个未死亡 / 未排除的候选（无 I/O，线程安全）。"""
        with self._lock:
            n = len(self._candidates)
            if n == 0:
                return None
            for _ in range(n):
                self._cursor = (self._cursor + 1) % n
                p = self._candidates[self._cursor]
                if p in self._dead or p in exclude:
                    continue
                return p
            return None

    def as_requests_proxies(self, proxy: str) -> dict:
        return {"http": proxy, "https": proxy}

    # ───────── 校验（I/O，锁外调用） ─────────
    def validate(self, proxy: str) -> bool:
        """实测该代理能否出网（默认 trust_env=False 防止递归套代理）。"""
        try:
            s = requests.Session()
            s.trust_env = False
            r = s.get(_VALIDATE_URL,
                      proxies=self.as_requests_proxies(proxy),
                      timeout=self.validate_timeout)
            if r.status_code == 200:
                try:
                    r.json()
                    return True
                except Exception:  # noqa: BLE001
                    return False
            return False
        except Exception:  # noqa: BLE001
            return False

    # ───────── 健康记账 ─────────
    def report_success(self, proxy: str | None) -> None:
        if not proxy:
            return
        with self._lock:
            self._fail.pop(proxy, None)
            self._validated_ok.add(proxy)
            self._dead.discard(proxy)

    def report_failure(self, proxy: str | None) -> None:
        if not proxy:
            return
        with self._lock:
            n = self._fail.get(proxy, 0) + 1
            self._fail[proxy] = n
            if n >= self.fail_threshold:
                self._dead.add(proxy)

    # ───────── 进程级 env 桥（让 akshare / requests 继承） ─────────
    def _set_env(self, proxy: str) -> None:
        p = self.as_requests_proxies(proxy)
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[k] = p["https"]

    def _clear_env(self) -> None:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)

    def _bootstrap_next(self, max_try: int = 10) -> str | None:
        """从候选里挑一个可用的（校验通过）并设为当前 ; 全失败则清空 env。"""
        tried: set[str] = set()
        count = 0
        while count < max_try:
            cand = self.next_candidate(exclude=tried)
            if cand is None:
                break
            tried.add(cand)
            count += 1
            if cand in self._validated_ok and cand not in self._dead:
                self._current = cand
                self._set_env(cand)
                return cand
            if self.validate(cand):
                self.report_success(cand)
                self._current = cand
                self._set_env(cand)
                return cand
            self.report_failure(cand)
        self._current = None
        self._clear_env()
        return None

    def apply_to_env(self) -> str | None:
        """启用时调用一次：采集（如需）+ 选一个可用代理写入进程 env。"""
        if not self.enabled:
            return None
        self.ensure_fresh()
        if self._current and self._current in self._validated_ok \
                and self._current not in self._dead:
            self._set_env(self._current)
            return self._current
        return self._bootstrap_next()

    def acquire_for_request(self) -> dict | None:
        """请求前取当前代理（proxies dict）；无可用代理返回 None（交由直连）。"""
        if not self.enabled:
            return None
        self.ensure_fresh()
        if self._current and self._current in self._validated_ok \
                and self._current not in self._dead:
            return self.as_requests_proxies(self._current)
        self._bootstrap_next()
        if self._current:
            return self.as_requests_proxies(self._current)
        return None

    def rotate_on_failure(self) -> None:
        """当前代理疑似被封：标记失败并切换到下一个可用代理（同时更新 env）。"""
        if not self.enabled:
            return
        self.report_failure(self._current)
        self._bootstrap_next()

    # ───────── 观测 ─────────
    def stats(self) -> dict:
        with self._lock:
            return {
                "enabled": self.enabled,
                "static_provided": self._static_provided,
                "candidates": len(self._candidates),
                "validated_ok": len(self._validated_ok),
                "dead": len(self._dead),
                "current": self._current,
            }


_POOL: "ProxyPool | None" = None
_POOL_LOCK = threading.Lock()


def get_proxy_pool() -> "ProxyPool":
    """进程级单例。"""
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = ProxyPool()
    return _POOL


def proxy_pool_stats() -> dict:
    return get_proxy_pool().stats()


if __name__ == "__main__":
    # 手动调试：SS_PROXY_POOL=1 python -m modules.proxy_pool
    logging.basicConfig(level=logging.INFO)
    pool = ProxyPool(enabled=True)
    print("采集 + 校验中 …")
    cur = pool.apply_to_env()
    print("当前出口代理:", cur)
    print("池状态:", pool.stats())
