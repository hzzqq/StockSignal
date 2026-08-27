"""并发取数助手：把页面里串行发起的多个独立网络调用并行化，显著缩短首屏等待。

与 timeout_exec 共用共享线程池，每个任务都有硬边界（不会无限阻塞），且底层
网络超时 < 任务边界，不泄漏线程。

典型用法（页面首屏一次性并发预取多路数据）：::

    @st.cache_data(show_spinner=False, ttl=300)
    def _prefetch_all():
        tasks = [
            ("northbound", get_northbound_fund_flow),
            ("industry", get_industry_fund_flow),
            ("market", lambda: get_market_fund_flow(days=30)),
            ...
        ]
        return fetch_many(tasks, max_workers=6, timeout=14)

    data = _prefetch_all()          # 并发跑完，最坏 ~14s（而非各路串行之和）
    nb = data.get("northbound")
"""
import concurrent.futures as cf
import logging
import threading

from modules.timeout_exec import _pool
from modules.site_config import FETCH_MAX_WORKERS, CALL_TIMEOUT_CAP
from modules.errors import report_error

logger = logging.getLogger(__name__)


def _safe(fn):
    """包装：任务内任何异常都转成 None，绝不让单个取数拖垮整批。"""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        report_error("fetch_parallel", e, context="single task")
        return None


def _gated(fn, sem):
    """信号量限流包装：真正约束单批并发度，避免一批任务吃满共享池饿死其他页面。"""
    def _run():
        with sem:
            return _safe(fn)
    return _run


def fetch_many(tasks, max_workers=None, timeout=None):
    """并发执行多个取数任务。

    :param tasks: 可迭代的 ``(key, callable)`` 二元组。
    :param max_workers: 本批并发度上限（默认 site_config.FETCH_MAX_WORKERS）。
        共享池总容量固定，这里用信号量真实限流；否则单页一次提交 30 个任务
        会吃满全部共享线程，其他页面的取数被饿死。
    :param timeout: 整批硬边界（秒，默认 site_config.CALL_TIMEOUT_CAP）。
        并发下整批耗时 ≈ 最慢单任务，因此以整批为边界即可，且**必须**传给
        ``as_completed``：否则某个任务永久阻塞时 as_completed 会无限等待，
        后面的 ``fut.result(timeout=...)`` 根本执行不到，超时保护形同虚设。
    :returns: ``dict{key: result}``，任务超时 / 异常对应值为 None。
        返回的 key 集合与入参 tasks 完全一致（超时项预填 None，不会缺键）。
    """
    if max_workers is None:
        max_workers = FETCH_MAX_WORKERS
    if timeout is None:
        timeout = CALL_TIMEOUT_CAP

    task_list = list(tasks)
    if not task_list:
        return {}

    sem = threading.Semaphore(max(1, int(max_workers)))
    futs = {_pool().submit(_gated(fn, sem)): key for key, fn in task_list}
    # 预填 None：整批超时后未完成的 key 仍然存在，调用方可以安全 .get()/索引。
    out = {key: None for _, key in futs.items()}

    try:
        for fut in cf.as_completed(list(futs), timeout=timeout):
            key = futs[fut]
            try:
                out[key] = fut.result()      # 已完成，立即返回，不再二次计时
            except Exception as e:  # noqa: BLE001
                report_error("fetch_parallel", e, context=f"task:{key}")
                out[key] = None
    except Exception:  # noqa: BLE001  整批超时：未完成项保持预填的 None
        pending = [k for f, k in futs.items() if not f.done()]
        if pending:
            logger.warning(
                "[fetch_parallel] 整批超时 %.1fs，%d/%d 个任务未完成: %s",
                timeout, len(pending), len(task_list), pending[:5],
            )
    return out
