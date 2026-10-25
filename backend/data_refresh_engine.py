"""backend/data_refresh_engine.py — T-324 方向A②：数据源每日自动刷新调度器。

背景：牧羊人广度真值（data/shepherd_history.csv）在 2026-09-04 缓存事故后停更近 40 天
才被发现（T-323 人工激活修复）。根因是「刷新只靠人跑脚本」——本模块把
``scripts/refresh_shepherd_history_recent.py`` 纳入每日调度，让停更在 24h 内自愈。

设计要点（契约）：
- **触发窗口**：工作日（周一~五）≥17:35 且当日未成功刷过；守护线程 tick 30 分钟。
  节假日不特判——无新数据由 ``no_new_data`` 诚实收口（当日不再重试）。
- **产出校验以 CSV 末行推进为准**：退出码仅参考（脚本失败路径不写盘，末行推进即产出；
  超时强杀后末行已推进也接受）。失败/超时 ``logger.error`` 留痕，绝不粉饰。
- **超时防线**：子进程 20 分钟硬超时 → ``taskkill /T /F`` 杀进程树（挂起不累积僵尸）。
- **P1 停更告警**：刷新后复验 ``modules.data_health.health_rows()``，P1 事件因子
  lag ≥ ``modules.decision.FRESH_STALE_DAYS``（单一真理源，勿在本模块重定义阈值）→
  落库 ``MarketAlert``（24h 去重），消息诚实标注「需 sj 空间（P1-QuantFactor）重训导出」。
- **状态文件**：``data/data_refresh_state.json``（原子写，防重启后当日重复刷）；
  失败允许当日重试，上限 ``MAX_ATTEMPTS_PER_DAY`` 次（防反复撞网）。
- **测试隔离**：PYTEST / TESTING / ``STOCKSIGNAL_ENABLE_DATA_REFRESH=0`` 三闸门不启动。
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_CSV = os.path.join(_ROOT, "data", "shepherd_history.csv")
STATE_PATH = os.path.join(_ROOT, "data", "data_refresh_state.json")
CHILD_LOG = os.path.join(_ROOT, "logs", "data_refresh_child.log")
REFRESH_MODULE = "scripts.refresh_shepherd_history_recent"

TICK_SECONDS = 30 * 60            # 每 tick 半小时
TRIGGER_TIME = dtime(17, 35)      # 工作日 17:35 后触发（收盘数据已出）
SUBPROCESS_TIMEOUT_S = 1200       # 20 分钟硬超时（实测正常路径 <300s）
WORKERS = 8                       # 增量刷新并发（脚本默认 12，调度场景收敛到 8）
SINCE_BACKWARD_DAYS = 14          # since = CSV 末行 -14 天（覆盖周末+预热冗余）
MAX_ATTEMPTS_PER_DAY = 3          # 当日失败重试上限
P1_ALERT_COOLDOWN_HOURS = 24      # P1 停更告警冷却

RESULT_OK = "ok"
RESULT_NO_NEW = "no_new_data"
RESULT_FAILED = "failed"

_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

_SCHEDULER_STARTED = False


# ───────────────────────── 纯函数（离线可测） ─────────────────────────
def past_refresh_time(now: datetime) -> bool:
    """工作日（周一~五）且 ≥17:35。节假日不特判（无新数据 → no_new_data 收口）。"""
    return now.weekday() < 5 and now.time() >= TRIGGER_TIME


def build_since_arg(last_date) -> str:
    """刷新窗口起点：CSV 末行 -14 天（merge_recent 按日期合并、新值优先，重叠幂等）。"""
    return (last_date - timedelta(days=SINCE_BACKWARD_DAYS)).strftime("%Y-%m-%d")


def classify_result(exit_code, advanced: bool, killed: bool) -> str:
    """产出校验唯一口径：**CSV 末行推进为准，退出码仅参考**（纯函数）。

    - ``ok``：末行推进（哪怕被超时强杀 / 退出码非 0——脚本失败路径不写盘，推进即产出）；
    - ``no_new_data``：正常退出且无推进（节假日 / 数据源未发布）→ 当日完成，不再重试；
    - ``failed``：其余（超时无推进 / 非零退出无推进）→ 当日有限重试。
    """
    if advanced:
        return RESULT_OK
    if killed:
        return RESULT_FAILED
    if exit_code == 0:
        return RESULT_NO_NEW
    return RESULT_FAILED


def should_trigger(state: dict, now: datetime) -> tuple[bool, str]:
    """触发判定（纯函数）：工作日过点 + 当日未成功 + 尝试未超限。"""
    if not past_refresh_time(now):
        return False, "未到触发时段（工作日 ≥17:35）"
    run_date = now.strftime("%Y-%m-%d")
    if state.get("last_run_date") == run_date:
        if state.get("last_result") in (RESULT_OK, RESULT_NO_NEW):
            return False, "当日已完成"
        if int(state.get("attempts_today") or 0) >= MAX_ATTEMPTS_PER_DAY:
            return False, f"当日尝试已达上限 {MAX_ATTEMPTS_PER_DAY}"
    return True, "ok"


def p1_message(as_of, lag_days: int, stale_days: int) -> str:
    """P1 停更告警文案（纯函数）：诚实标注跨仓依赖，绝不把旧口径当当日结论。"""
    return (f"P1 事件因子数据停更：真实截止日 {as_of or '未知'}，已滞后 {lag_days} 天"
            f"（阈值 {stale_days} 天）。该源由独立仓库 P1-QuantFactor（sj 空间）产出，"
            f"本仓只读、不擅改——需 sj 空间重训并导出 signal_*.json 后才会恢复；"
            f"在此之前事件看多/看空榜为旧口径，请勿当当日结论使用。")


# ───────────────────────── 状态文件（原子写，防重启后重复刷） ─────────────────────────
def load_state(path: str | None = None) -> dict:
    p = path or STATE_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        logger.warning("[data_refresh] 状态文件不可读，按空状态处理（%s）：%s", p, e)
        return {}


def save_state(state: dict, path: str | None = None) -> None:
    from modules.atomic_io import atomic_json_dump
    atomic_json_dump(state, path or STATE_PATH, ensure_ascii=False, indent=2)


# ───────────────────────── CSV 末行（产出校验唯一权威） ─────────────────────────
def csv_last_date(path: str | None = None):
    """CSV 末行真实数据日（date）；取不到 → None（诚实，不猜）。"""
    p = path or HISTORY_CSV
    try:
        import pandas as pd
        df = pd.read_csv(p, usecols=[0], encoding="utf-8-sig")
        s = pd.to_datetime(df.iloc[:, 0], errors="coerce").dropna()
        return None if s.empty else s.iloc[-1].date()
    except Exception as e:  # noqa: BLE001
        logger.error("[data_refresh] 读取牧羊人历史 CSV 末行失败（%s）：%s", p, e)
        return None


# ───────────────────────── 子进程执行（超时杀进程树） ─────────────────────────
def _kill_tree(pid: int) -> None:
    """Windows 进程树强杀（taskkill /T /F）；失败留痕不静默。"""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=30)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:  # noqa: BLE001
        logger.error("[data_refresh] 杀进程树失败（PID=%s）：%s", pid, e)


def _default_popen(cmd: list[str], logf):
    """子进程输出直写日志文件（避免管道缓冲填满导致子进程阻塞死锁）。"""
    return subprocess.Popen(cmd, cwd=_ROOT, stdout=logf, stderr=subprocess.STDOUT,
                            creationflags=_CREATION_FLAGS)


def _spawn_and_wait(cmd: list[str], *, popen_fn=None, kill_fn=None,
                    timeout: int = SUBPROCESS_TIMEOUT_S) -> tuple:
    """拉起刷新子进程并限时等待。返回 ``(exit_code, killed)``。"""
    os.makedirs(os.path.dirname(CHILD_LOG), exist_ok=True)
    with open(CHILD_LOG, "a", encoding="utf-8") as logf:
        popen = (popen_fn or _default_popen)(cmd, logf)
        killed = False
        try:
            rc = popen.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            killed = True
            logger.error("[data_refresh] 刷新子进程超时（>%ds），强杀进程树 PID=%s",
                         timeout, popen.pid)
            (kill_fn or _kill_tree)(popen.pid)
            try:
                rc = popen.wait(timeout=60)
            except Exception:  # noqa: BLE001
                rc = None
        return rc, killed


# ───────────────────────── P1 停更告警（复验 data_health） ─────────────────────────
def alert_p1_stale(app, *, exists_fn=None, add_fn=None) -> bool:
    """P1 事件因子 lag ≥ FRESH_STALE_DAYS → MarketAlert 落库（24h 去重）。

    - 阈值引用 ``modules.decision.FRESH_STALE_DAYS`` 单一真理源（勿重定义）；
    - ``exists_fn`` 注入点：默认查 24h 内同 metric_key 告警（DB 权威去重）；
    - ``add_fn`` 注入点：默认 ``db.session.add(MarketAlert(...))``（消息中心可见）。
    """
    from modules.data_health import health_rows
    from modules.decision import FRESH_STALE_DAYS
    row = next((r for r in health_rows() if r.get("key") == "p1_event"), None)
    lag = (row or {}).get("lag_days")
    as_of = (row or {}).get("as_of")
    if not isinstance(lag, int) or lag < FRESH_STALE_DAYS:
        return False
    if exists_fn is None:
        def exists_fn() -> bool:
            from .models import MarketAlert
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC（与列口径一致）
            cutoff = now_utc - timedelta(hours=P1_ALERT_COOLDOWN_HOURS)
            hit = MarketAlert.query.filter(MarketAlert.metric_key == "p1_event",
                                           MarketAlert.created_at >= cutoff).first()
            return hit is not None
    if exists_fn():
        return False
    msg = p1_message(as_of, lag, FRESH_STALE_DAYS)
    if add_fn is not None:
        add_fn(msg, lag)
    else:
        from .extensions import db
        from .models import MarketAlert
        db.session.add(MarketAlert(
            metric_key="p1_event", metric_name="P1 事件因子", severity="warning",
            message=msg, value=float(lag), threshold=float(FRESH_STALE_DAYS)))
        db.session.commit()
    logger.warning("[data_refresh] P1 事件因子停更告警：as_of=%s lag=%d 天", as_of, lag)
    return True


# ───────────────────────── 单次刷新（阻塞，含状态落盘） ─────────────────────────
def run_refresh_once(app, *, csv_path: str | None = None,
                     state_path: str | None = None,
                     popen_fn=None, kill_fn=None) -> dict:
    """执行一次牧羊人增量刷新 + P1 复验（阻塞，最长约 SUBPROCESS_TIMEOUT_S+60s）。

    :return: 刷新记录 dict（result/detail/attempts_today/…），供调度日志与测试断言。
    """
    now = datetime.now()
    run_date = now.strftime("%Y-%m-%d")
    state = load_state(state_path)
    if state.get("last_run_date") != run_date:
        state["attempts_today"] = 0
    state["attempts_today"] = int(state.get("attempts_today") or 0) + 1

    last_before = csv_last_date(csv_path)
    if last_before is None:
        # 诚实语义：基线读不到 → 拒绝盲跑（不猜 since，不粉饰）
        result, detail = RESULT_FAILED, "CSV 末行不可读，拒绝盲跑"
    else:
        since_arg = build_since_arg(last_before)
        cmd = [sys.executable, "-m", REFRESH_MODULE,
               "--since", since_arg, "--workers", str(WORKERS)]
        rc, killed = _spawn_and_wait(cmd, popen_fn=popen_fn, kill_fn=kill_fn)
        last_after = csv_last_date(csv_path)
        advanced = bool(last_after and last_after > last_before)
        result = classify_result(rc, advanced, killed)
        detail = (f"exit={rc} killed={killed} since={since_arg} "
                  f"末行 {last_before} → {last_after}（{'推进' if advanced else '未推进'}）")

    state.update({
        "last_run_date": run_date,
        "last_result": result,
        "finished_at": now.isoformat(timespec="seconds"),
        "last_csv_date": str(last_before) if last_before else None,
        "detail": detail,
    })
    save_state(state, state_path)
    if result == RESULT_FAILED:
        logger.error("[data_refresh] 刷新失败：%s", detail)      # 留痕不粉饰
    else:
        logger.info("[data_refresh] 刷新完成（%s）：%s", result, detail)

    try:  # 刷新后复验 P1 新鲜度；复验失败仅留痕，不影响调度链路
        alert_p1_stale(app)
    except Exception as e:  # noqa: BLE001
        logger.warning("[data_refresh] P1 新鲜度复验失败：%s", e)

    return {"result": result, "detail": detail,
            "attempts_today": state["attempts_today"], "run_date": run_date}


# ───────────────────────── 调度器（守护线程） ─────────────────────────
def start_data_refresh_scheduler(app, *, tick_seconds: int = TICK_SECONDS,
                                 initial_delay: float = 60.0) -> None:
    """启动每日数据刷新守护线程（测试/禁用环境自动跳过）。"""
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    if os.environ.get("PYTEST_CURRENT_TEST") or app.config.get("TESTING"):
        logger.info("检测到测试环境，跳过数据刷新调度器")
        return
    if os.environ.get("STOCKSIGNAL_ENABLE_DATA_REFRESH", "1") == "0":
        logger.info("STOCKSIGNAL_ENABLE_DATA_REFRESH=0，跳过数据刷新调度器")
        return
    _SCHEDULER_STARTED = True

    def _loop() -> None:
        time.sleep(initial_delay)
        while True:
            try:
                ok, why = should_trigger(load_state(), datetime.now())
                if ok:
                    app.logger.info("[data_refresh] 触发每日数据刷新")
                    run_refresh_once(app)
                else:
                    app.logger.debug("[data_refresh] 跳过：%s", why)
            except Exception as e:  # noqa: BLE001
                app.logger.warning("[data_refresh] 调度异常：%s", e)
            time.sleep(tick_seconds)

    threading.Thread(target=_loop, daemon=True,
                     name="data-refresh-scheduler").start()
    app.logger.info("数据刷新调度器已启动（工作日 ≥17:35 触发，tick %d 分钟）",
                    tick_seconds // 60)
