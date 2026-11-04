"""P1 信号自托管副本的日检闭环（同步 → 体检 → 状态快照 → 可选告警）。

背景：``modules.p1_sync`` 提供了**一次性**单向同步能力，``scripts/refresh_p1_signals.py``
是它的 CLI；但「谁在天天跑、跑完副本新不新、结构有没有破」此前没有任何落地判定
（``modules/data_health.py`` 的 p1_event 刷新指引还写着「本仓无刷新入口」）。

本模块把三步合成一个可复用环（调度器与 CLI 共用，避免两套口径）：
  1. **同步**：``p1_sync.sync_once`` —— 单向、幂等、绝不降级覆盖更新副本；
  2. **体检**：``p1_signal_quality.summarize`` —— 结构与新鲜度 SLA 直接复用，不重写；
  3. **落档**：结论原子写进 ``data/p1_sync_status.json``（``data/`` 已 gitignore）。

纪律：
  · **结构 / 新鲜度分开判**：``check_file`` 的 ``ok`` 把新鲜度也算红，本模块用
    ``p1_sync.structural_ok`` 剥掉「数据滞后」再判结构，滞后单列 ``stale``，否则
    一个设计性滞后的 fusion 会被误报成「副本损坏」。
  · **失败绝不写 ok**：同步异常、全部候选无效、结构红逐项进 ``errors`` / ``health``。
  · **不抄机器绝对路径**：目标目录一律走 ``p1_sync.default_target_dir()``。

口径分工：``backend/data_refresh_engine.alert_p1_stale`` 盯的是**跨仓事件因子停更**
（P1-QuantFactor 导出链断没断）；本模块盯的是**本仓自托管副本**（同步跑没跑、
副本新不新、结构破没破）。两者互补，不重复告警。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules import p1_sync
from modules.atomic_io import atomic_json_dump
from modules.p1_signal_quality import summarize

logger = logging.getLogger(__name__)

STATUS_FILENAME = "p1_sync_status.json"
DEFAULT_INTERVAL_MINUTES = 60
# 上次运行距今超过 N 个调度间隔 → 疑似停摆（调度线程静默死掉是最常见的假绿）
_LIVENESS_FACTOR = 3

__all__ = [
    "STATUS_FILENAME",
    "DEFAULT_INTERVAL_MINUTES",
    "status_path",
    "assess_p1_sync_health",
    "run_sync_cycle",
]


def status_path(target_dir: Path | str | None = None) -> Path:
    """状态快照路径 = 目标目录同级的 ``p1_sync_status.json``（随 data/ 一起 gitignore）。"""
    tgt = Path(target_dir) if target_dir is not None else p1_sync.default_target_dir()
    return tgt.parent / STATUS_FILENAME


def _read_status(path: Path) -> dict:
    """读既有快照；损坏或不存在都按空档继续（但留痕，不静默吞掉解析错误）。"""
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("[p1_sync_health] 状态快照读取失败（按空档继续）: %s", e)
        return {}
    return raw if isinstance(raw, dict) else {}


def _liveness_note(prev: dict, now: datetime) -> str | None:
    """调度活跃度：只有 ``mode=scheduler`` 的快照才判停摆（CLI 手跑不算停摆）。"""
    if prev.get("mode") != "scheduler" or not prev.get("run_at"):
        return None
    try:
        last = datetime.fromisoformat(str(prev["run_at"]))
        idle_min = (now - last).total_seconds() / 60.0
    except (ValueError, TypeError):  # ui_audit_exempt: 时间戳格式异常 → 视为无活跃度证据，不据此报停摆（不编造）
        return None
    interval = int(prev.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES)
    limit = _LIVENESS_FACTOR * max(5, interval)
    if idle_min > limit:
        return f"调度器疑似停摆：上次运行 {int(idle_min)} 分钟前（阈值 {limit} 分钟）"
    return None


def assess_p1_sync_health(now: datetime | None = None,
                          target_dir: Path | str | None = None,
                          status_file: Path | str | None = None) -> dict:
    """副本健康（纯读，不写盘）：ok / warn / dead + 逐项证据。

    - ``dead``：目录不存在 / 无副本 / 全部副本结构不合格（同步没跑成，或写入被拒）
    - ``warn``：部分副本结构异常、或超出新鲜度 SLA、或调度器疑似停摆
    - ``ok``：全部副本结构合格且新鲜度达标
    """
    now = now or datetime.now()
    today = now.date()
    tgt = Path(target_dir) if target_dir is not None else p1_sync.default_target_dir()
    spath = Path(status_file) if status_file is not None else status_path(tgt)

    rows: list[dict] = []
    models: list[str] = []
    summarize_error = None
    if tgt.is_dir():
        try:
            rep = summarize(str(tgt), today=today)
            rows = rep.get("rows") or []
            models = rep.get("models_found") or []
        except Exception as e:  # noqa: BLE001 — 体检自身失败必须如实上报，不伪装成健康
            summarize_error = f"{type(e).__name__}: {e}"
            logger.warning("[p1_sync_health] 副本体检失败: %s", e)
    else:
        summarize_error = f"副本目录不存在：{tgt}"

    rows_out: list[dict] = []
    structural_bad: list[str] = []
    stale: list[str] = []
    for r in rows:
        sok, _serrs = p1_sync.structural_ok(r)
        row = {
            "file": r.get("file"),
            "model_key": r.get("model_key"),
            "latest_date": r.get("latest_date"),
            "age_days": r.get("age_days"),
            "structural_ok": sok,
            "freshness_ok": bool(r.get("freshness_ok")),
            "errors": list(r.get("errors") or []),
        }
        rows_out.append(row)
        if not sok:
            structural_bad.append(str(r.get("file")))
        elif r.get("latest_date") and not r.get("freshness_ok"):
            stale.append(str(r.get("file")))

    latest = max((str(r["latest_date"]) for r in rows_out if r.get("latest_date")), default=None)
    age = None
    if latest:
        try:
            age = (today - date.fromisoformat(latest)).days
        except ValueError:
            age = None

    if not rows_out:
        status = "dead"
        message = summarize_error or "自托管副本为空：从未同步过 signal_*.json"
    elif not any(r["structural_ok"] for r in rows_out):
        status = "dead"
        message = f"全部副本结构不合格（{len(rows_out)} 个文件），最近一次同步疑似被拒"
    elif structural_bad or stale:
        status = "warn"
        bits = []
        if structural_bad:
            bits.append(f"{len(structural_bad)} 个副本结构异常")
        if stale:
            bits.append(f"{len(stale)} 个副本超出新鲜度 SLA")
        message = "；".join(bits)
    else:
        status = "ok"
        message = f"{len(rows_out)} 个副本结构与新鲜度均达标（最新 {latest}）"

    prev = _read_status(spath)
    liveness = _liveness_note(prev, now)
    if liveness:
        message = f"{message}；{liveness}" if message else liveness
        if status == "ok":
            status = "warn"

    return {
        "status": status,
        "message": message,
        "latest": latest,
        "age_days": age,
        "models": models,
        "rows": rows_out,
        "structural_bad": structural_bad,
        "stale": stale,
        "liveness": liveness,
        "last_run_at": prev.get("run_at"),
        "last_run_ok": prev.get("ok"),
        "signal_dir": str(tgt),
        "status_file": str(spath),
        "today": today.isoformat(),
    }


def _maybe_alert(snap: dict, prev: dict, now: datetime) -> None:
    """失败才推送（默认关；按自然日去重；绝不谎报已推送）。"""
    if os.environ.get("STOCKSIGNAL_P1_SYNC_PUSH") != "1":
        return
    if snap.get("ok"):
        return
    today = now.date().isoformat()
    if prev.get("alert_date") == today:
        return
    try:
        from modules.push_channel import push_text

        h = snap.get("health") or {}
        lines = [f"⚠️ P1 信号同步异常（{today}）",
                 f"状态 {h.get('status')}：{h.get('message')}"]
        errs = snap.get("errors") or []
        if errs:
            lines.append("错误：" + "；".join(str(e) for e in errs[:3]))
        lines.append("详见 data/p1_sync_status.json；非投资建议。")
        res = push_text("\n".join(lines))
        ok = bool(res.get("ok")) if isinstance(res, dict) else False
        snap["alert_date"] = today
        snap["alert_ok"] = ok
        if ok:
            logger.info("[p1_sync_health] 异常推送成功: %s", res)
        else:
            logger.warning("[p1_sync_health] 异常推送未成功: %s", res)
    except Exception as e:  # noqa: BLE001 — 推送失败不得掩盖同步结论，但必须留痕
        logger.warning("[p1_sync_health] 异常推送失败: %s", e)


def run_sync_cycle(source_dirs: list[str] | None = None,
                   target_dir: Path | str | None = None,
                   today: date | None = None,
                   dry_run: bool = False,
                   status_file: Path | str | None = None,
                   mode: str = "once",
                   interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
                   now: datetime | None = None) -> dict[str, Any]:
    """跑一轮：同步 → 体检 → 落档。返回本轮快照（与写盘内容一致，dry_run 不写盘）。"""
    now = now or datetime.now()
    tgt = Path(target_dir) if target_dir is not None else p1_sync.default_target_dir()
    spath = Path(status_file) if status_file is not None else status_path(tgt)
    prev = _read_status(spath)

    try:
        res = p1_sync.sync_once(source_dirs=source_dirs, target_dir=tgt,
                                today=today, dry_run=dry_run)
    except Exception as e:  # noqa: BLE001 — 同步异常保留既有副本，但必须进快照
        logger.warning("[p1_sync_health] 同步异常（保留既有副本）: %s", e)
        res = {"written": [], "skipped": [],
               "errors": [f"同步异常 {type(e).__name__}: {e}"], "plan": {}}

    plan = res.get("plan") or {}
    counts: dict[str, int] = {"copy": 0, "unchanged": 0, "target_newer": 0, "skip": 0}
    for it in plan.get("items") or []:
        act = str(it.get("action") or "unknown")
        counts[act] = counts.get(act, 0) + 1
    errors = [str(x) for x in (res.get("errors") or [])]
    health = assess_p1_sync_health(now=now, target_dir=tgt, status_file=spath)

    snap: dict[str, Any] = {
        "run_at": now.isoformat(timespec="seconds"),
        "mode": mode,
        "interval_minutes": int(interval_minutes),
        "dry_run": bool(dry_run),
        "ok": (not errors) and health.get("status") != "dead",
        "target_dir": str(tgt),
        "written": [str(x) for x in (res.get("written") or [])],
        "skipped": [str(x) for x in (res.get("skipped") or [])],
        "errors": errors,
        "all_invalid": bool(plan.get("all_invalid")),
        "counts": counts,
        "health": health,
        "prev_run_at": prev.get("run_at"),
    }

    if not dry_run:
        _maybe_alert(snap, prev, now)
        try:
            atomic_json_dump(snap, str(spath))
        except OSError as e:
            logger.warning("[p1_sync_health] 状态快照落盘失败: %s", e)
            snap["status_write_error"] = f"{type(e).__name__}: {e}"
    return snap
