"""P1 信号单向同步（StockSignal 侧自托管副本维护）。

背景：P1-QuantFactor 导出 ``signal_*.json`` 到其 processed 目录，StockSignal 侧
自托管一份副本（``data/p1_signals``），使平台可脱离 P1 路径依赖独立运行。
本模块只做「读 P1 侧 → 写 StockSignal 侧」的**单向 ingestion**，绝不回写 P1 仓。

口径（对齐项目约定，见本文件 docstring 上游约定）：
  · **单一真理源**：源目录发现一律走 ``modules.p1_signal.discover_source_dirs()``；
    本模块不抄任何机器绝对路径（AST 守卫 test_event_pool_bridge 强制）。
  · **候选选择**：按**数据日 ``latest_date`` 降序**，``mtime`` 仅作并列时的次键；
    禁止用文件 mtime 当数据新旧（会把更旧的数据当最新）。
  · **无效候选跳过不阻断**，但**全部无效时必须拒绝写入**（不覆盖既有副本）。
  · **结构校验复用** ``modules.p1_signal_quality.check_file``，不重写校验逻辑；
    新鲜度 SLA 不作为同步闸（fusion 存在设计性滞后），只作提示。
  · **绝不降级**：目标副本已是更新数据日时跳过写入（不回退到更旧的信号）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from modules.p1_signal import discover_source_dirs
from modules.p1_signal_quality import check_file, extract_model_key

logger = logging.getLogger(__name__)

__all__ = [
    "default_target_dir",
    "structural_ok",
    "collect_candidates",
    "pick_latest",
    "plan_sync",
    "apply_plan",
    "sync_once",
]

# 新鲜度类错误由 check_file 产生，属提示而非同步闸（fusion 设计性滞后）
_FRESHNESS_MARK = "数据滞后"


def default_target_dir() -> Path:
    """默认目标目录 = 仓库内 ``data/p1_signals``（相对仓库根计算，无机器绝对路径）。"""
    root = Path(__file__).resolve().parent.parent
    return root / "data" / "p1_signals"


def structural_ok(rec: dict) -> tuple[bool, list[str]]:
    """结构有效性判定（**不含新鲜度**）。

    :param rec: ``modules.p1_signal_quality.check_file`` 的返回体
    :return: (是否有效, 结构性错误列表)
    """
    errs = [e for e in (rec.get("errors") or []) if _FRESHNESS_MARK not in str(e)]
    if not rec.get("parseable"):
        return False, errs or ["不可解析"]
    if rec.get("missing_keys"):
        return False, errs or ["缺字段"]
    if not rec.get("latest_date"):
        return False, errs or ["latest_date 缺失或非法"]
    if not rec.get("symbol_ok", True):
        return False, errs or ["symbol 格式非法"]
    if not rec.get("rank_ok", True):
        return False, errs or ["rank 排序异常"]
    return (not errs), errs


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _mtime(path: Path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def collect_candidates(source_dirs: list[str] | None = None,
                       target_dir: Path | None = None,
                       today: date | None = None) -> list[dict]:
    """扫描候选源目录里的 ``signal_*.json``，做结构校验后返回候选列表。

    每个候选：{path, name, model_key, latest_date, mtime, ok, errors, rec}
    """
    dirs = list(source_dirs) if source_dirs is not None else list(discover_source_dirs())
    tgt = Path(target_dir) if target_dir is not None else default_target_dir()
    try:
        tgt_resolved = tgt.resolve()
    except OSError:
        tgt_resolved = tgt
    out: list[dict] = []
    for d in dirs:
        if not d:
            continue
        p = Path(d)
        try:
            if p.resolve() == tgt_resolved:
                continue  # 目标目录自身不是源
        except OSError:
            pass
        if not p.is_dir():
            continue
        for f in sorted(p.glob("signal_*.json")):
            model_key = extract_model_key(f.name)
            rec = check_file(str(f), model_key=model_key, today=today)
            ok, errs = structural_ok(rec)
            out.append({
                "path": str(f),
                "name": f.name,
                "model_key": model_key,
                "latest_date": rec.get("latest_date"),
                "mtime": _mtime(f),
                "ok": ok,
                "errors": errs,
                "rec": rec,
            })
    return out


def pick_latest(candidates: list[dict]) -> dict | None:
    """按 latest_date 降序、mtime 次键选出最优候选；全部无效返回 None。

    「无效」= 结构不合法（``ok`` 为 False）。损坏候选跳过不阻断；
    全无效时返回 None，调用方**必须**据此拒绝写入。
    """
    valid = [c for c in candidates if c.get("ok") and c.get("latest_date")]
    if not valid:
        return None
    return sorted(valid, key=lambda c: (str(c["latest_date"]), c.get("mtime", 0.0)),
                  reverse=True)[0]


def _target_state(target_dir: Path) -> dict[str, dict]:
    """扫描目标目录现有副本：{model_key: {"path","latest_date","md5"}}。"""
    state: dict[str, dict] = {}
    if not target_dir.is_dir():
        return state
    for f in sorted(target_dir.glob("signal_*.json")):
        mk = extract_model_key(f.name)
        latest = None
        try:
            with open(f, encoding="utf-8") as fh:
                latest = json.load(fh).get("latest_date")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            latest = None
        state[mk] = {"path": str(f), "latest_date": latest, "md5": _md5(f)}
    return state


def plan_sync(source_dirs: list[str] | None = None,
              target_dir: Path | None = None,
              today: date | None = None) -> dict:
    """生成同步计划（不写盘）。

    返回：{"items": [...], "all_invalid": bool, "target_dir": str, "n_candidates": int}
    item：{model_key, source, latest_date, target, action, reason}
      action ∈ copy / unchanged / target_newer
    """
    tgt = Path(target_dir) if target_dir is not None else default_target_dir()
    cands = collect_candidates(source_dirs, tgt, today=today)
    tstate = _target_state(tgt)

    by_model: dict[str, list[dict]] = {}
    for c in cands:
        by_model.setdefault(c.get("model_key") or c["name"], []).append(c)

    items: list[dict] = []
    for mk, group in sorted(by_model.items()):
        best = pick_latest(group)
        if best is None:
            # 全部候选结构无效：如实带出结构错误（不笼统说「无效」），并拒绝写入
            detail = "；".join(str(e) for e in (group[0].get("errors") or [])) or "未知结构问题"
            items.append({
                "model_key": mk, "source": None, "latest_date": None,
                "target": str(tgt / (group[0]["name"] if group else "")),
                "action": "skip",
                "reason": f"全部候选结构无效（拒绝写入）：{detail}",
            })
            continue
        tinfo = tstate.get(mk)
        tgt_path = Path(tinfo["path"]) if tinfo else tgt / best["name"]
        if tinfo and tinfo.get("latest_date"):
            # 绝不降级：目标已是更新数据日 → 跳过
            if str(tinfo["latest_date"]) > str(best["latest_date"]):
                items.append({
                    "model_key": mk, "source": best["path"],
                    "latest_date": best["latest_date"], "target": str(tgt_path),
                    "action": "target_newer",
                    "reason": f"目标副本 latest_date={tinfo['latest_date']} 更新于源 {best['latest_date']}，不回退",
                })
                continue
            if str(tinfo["latest_date"]) == str(best["latest_date"]) and tinfo.get("md5") == _md5(Path(best["path"])):
                items.append({
                    "model_key": mk, "source": best["path"],
                    "latest_date": best["latest_date"], "target": str(tgt_path),
                    "action": "unchanged", "reason": "内容一致（md5 相同），跳过",
                })
                continue
        items.append({
            "model_key": mk, "source": best["path"],
            "latest_date": best["latest_date"], "target": str(tgt_path),
            "action": "copy", "reason": "写入自托管副本",
        })

    all_invalid = bool(items) and all(i["action"] == "skip" for i in items)
    return {"items": items, "all_invalid": all_invalid,
            "target_dir": str(tgt), "n_candidates": len(cands)}


def apply_plan(plan: dict, dry_run: bool = False) -> dict:
    """按计划执行复制（幂等）。全部无效时拒绝写入并返回 ``written=False``。"""
    written: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    if plan.get("all_invalid"):
        return {"written": [], "skipped": [], "errors": ["全部候选无效，拒绝写入（保留既有副本）"],
                "written_any": False}
    for it in plan.get("items", []):
        act = it.get("action")
        if act == "copy":
            src = Path(it["source"])
            dst = Path(it["target"])
            if dry_run:
                skipped.append(f"{it.get('model_key')}: dry-run 未写入")
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                written.append(str(dst))
            except OSError as e:
                errors.append(f"{it.get('model_key')}: 写入失败 {type(e).__name__}: {e}")
                logger.warning("[p1_sync] 写入失败 %s: %s", it.get("model_key"), e)
        else:
            skipped.append(f"{it.get('model_key')}: {it.get('reason')}")
    return {"written": written, "skipped": skipped, "errors": errors,
            "written_any": bool(written)}


def sync_once(source_dirs: list[str] | None = None,
              target_dir: Path | None = None,
              today: date | None = None,
              dry_run: bool = False) -> dict:
    """一站式同步：计划 + 执行，返回合并结果。"""
    plan = plan_sync(source_dirs, target_dir, today=today)
    res = apply_plan(plan, dry_run=dry_run)
    out: dict[str, Any] = dict(res)
    out["plan"] = plan
    return out
