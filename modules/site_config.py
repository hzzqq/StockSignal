"""集中管理前端 / 中间件散落的魔法值与默认配置，统一从环境变量读取（带兜底常量）。

把此前散落在 fundflow / netguard / market_drivers 等处的硬编码（本机代理地址
``127.0.0.1:26561``、网络超时 ``15s``、弱测试密钥 ``stocksignal-smoke``）集中到一处，
换机器 / 换端口 / 生产部署时只需改环境变量，不必改业务代码。

关键约束：``REQUEST_TIMEOUT``（底层网络默认超时）**必须 <** ``CALL_TIMEOUT_CAP``
（单调用硬边界）。这样阻塞的网络调用会先被传输层超时唤醒、被包装函数正常返回，
``future`` 在硬边界内完成，线程回到池中复用——避免 ``_run_with_timeout`` 丢弃线程造成泄漏。
"""
import os

# 本机代理（akshare 经此访问东方财富 / 同花顺）。可用 STOCKSIGNAL_PROXY 覆盖。
PROXY_DEFAULT = os.environ.get("STOCKSIGNAL_PROXY", "http://127.0.0.1:26561")

# 网络请求 / 连接默认超时（秒）。requests 与 socket 双层均使用此值。
# 必须 < CALL_TIMEOUT_CAP，否则仍会被硬边界丢弃线程（泄漏）。
REQUEST_TIMEOUT = float(os.environ.get("STOCKSIGNAL_REQ_TIMEOUT", "10"))

# 单只取数调用的硬边界（秒）。需 > REQUEST_TIMEOUT。
CALL_TIMEOUT_CAP = float(os.environ.get("STOCKSIGNAL_CALL_TIMEOUT", str(REQUEST_TIMEOUT + 2)))

# 并发取数助手默认并发度
FETCH_MAX_WORKERS = int(os.environ.get("STOCKSIGNAL_FETCH_WORKERS", "6"))

# 冒烟测试用的弱密钥（仅测试桩，非生产）。生产由 STOCKSIGNAL_SECRET 控制。
TEST_SMOKE_SECRET = os.environ.get("STOCKSIGNAL_TEST_SECRET", "stocksignal-smoke")


# ── 不变量校验（防线程泄漏的关键闸门）──────────────────────────────────
# CALL_TIMEOUT_CAP 必须大于 REQUEST_TIMEOUT，否则底层网络不会先被传输层超时唤醒、
# 共享线程池会被硬边界丢弃线程 → 泄漏。错误配置（如运维误设 CALL_TIMEOUT_CAP 过小）
# 时自动纠正为 REQUEST_TIMEOUT + 2 并打告警，而不是静默留下泄漏隐患。
if CALL_TIMEOUT_CAP <= REQUEST_TIMEOUT:
    import logging

    logging.getLogger(__name__).warning(
        "[site_config] CALL_TIMEOUT_CAP(%.1f) <= REQUEST_TIMEOUT(%.1f)，"
        "底层网络不会先超时→共享线程池会丢弃线程造成泄漏！已自动纠正为 REQUEST_TIMEOUT+2。",
        CALL_TIMEOUT_CAP,
        REQUEST_TIMEOUT,
    )
    CALL_TIMEOUT_CAP = REQUEST_TIMEOUT + 2

