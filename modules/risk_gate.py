"""T-245 荐股排雷二道闸（统一落点）。

把 recommend_engine 内的六维排雷二道闸上提为跨页通用模块，供所有「荐股 / 榜单 /
选股」出口在渲染前统一调用，高危标的被拦截并带明确中文原因，绝不静默放行。

诚实红线（与 recommend_engine 既有契约一致）：
- unknown ≠ guilty：扫描不可得（网络/接口失败）按 not_scanned 如实降级，不阻塞主流程、不误判安全；
- overall_level == high 才硬踢出；medium/low 一律保留并携带 risk_scan 元数据。
"""
from __future__ import annotations

import logging

from modules.stock_risk import DIMENSIONS, RISK_HIGH, scan_many as _scan_many

logger = logging.getLogger(__name__)

__all__ = ["apply_risk_gate", "scan_and_gate", "to_6digit"]


def to_6digit(code: str) -> str:
    """把任意 A股代码形态规整为 6 位数字字符串（供 stock_risk 扫描 key 对齐）。

    ``"sh600869"`` / ``"600869.SH"`` / ``"600869"`` -> ``"600869"``；
    不足 6 位或无数字则原样返回（不臆造）。
    """
    if code is None:
        return ""
    s = str(code).strip().upper()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 6:
        return digits[-6:]
    return s


def apply_risk_gate(rows: list, scan_map: dict, top_k: int, gate_n: int) -> tuple:
    """六维排雷二道闸（纯逻辑，可单测）。

    与 recommend_engine.apply_risk_gate 行为一致：``rows`` 已按 composite 降序，
    ``scan_map`` 键为 6 位代码。``overall_level == high`` 硬踢出；unknown/medium/low
    保留并携带 ``risk_scan`` 元数据；被踢不足 ``top_k`` 从闸门段外补入并标
    ``not_scanned``；``scan_map`` 空 -> 全部 ``not_scanned``，主流程不阻塞。

    返回 ``(gated_rows, gate_summary)``；gated_rows 元素新增 ``risk_scan`` 字段。
    """
    gate_n = max(int(gate_n), int(top_k))
    head, tail = rows[:gate_n], rows[gate_n:]
    if not scan_map:
        for r in rows:
            r["risk_scan"] = {"status": "not_scanned"}
        summary = {"status": "unavailable", "gate_size": len(head), "scanned": 0,
                   "kicked": [],
                   "reason": "六维排雷扫描不可用（网络或接口失败），如实降级不阻塞"}
        return list(rows), summary

    kept: list = []
    kicked: list = []
    for r in head:
        scan = scan_map.get(to_6digit(r.get("code", "")))
        report = (scan or {}).get("report") or {}
        if report.get("overall_level") == RISK_HIGH:
            reasons = []
            for key, cn, _unit in DIMENSIONS:
                comp = (scan.get("components") or {}).get(key) or {}
                if comp.get("level") == RISK_HIGH:
                    note = str(comp.get("note") or "").strip()
                    reasons.append(f"{cn}·{note}"[:60] if note else cn)
            kicked.append({"code": r.get("code"), "name": r.get("name"),
                           "overall_level": RISK_HIGH,
                           "n_high": report.get("n_high"), "reasons": reasons})
            continue
        r["risk_scan"] = {"status": "scanned",
                          "overall_level": report.get("overall_level"),
                          "risk_score": report.get("risk_score"),
                          "reliable": report.get("reliable"),
                          "n_high": report.get("n_high", 0)}
        kept.append(r)
    for r in tail:
        r["risk_scan"] = {"status": "not_scanned"}
    summary = {"status": "ok", "gate_size": len(head), "scanned": len(scan_map),
               "kicked": kicked, "reason": ""}
    return kept + tail, summary


def scan_and_gate(candidates: list, top_k: int, gate_n: int | None = None,
                  code_key: str = "code", name_key: str = "name") -> tuple:
    """页面便捷封装：对候选列表做一次六维排雷，返回 ``(gated, summary)``。

    - ``candidates``: ``[{code, name, ...score...}, ...]``；code 可为
      ``sh600869`` / ``600869.SH`` / ``600869``
    - 内部规整为 6 位代码后调用 ``stock_risk.scan_many``（仅扫闸门段，控成本）
    - 还原原始 code 到返回结果（keep/tail 行 + kicked 项），页面无感
    - 扫描异常 -> ``scan_map`` 空 -> 全部 ``not_scanned`` 如实降级（不阻塞）

    返回结构与 ``apply_risk_gate`` 一致；gated 元素 code 还原为原始形态。
    """
    gate_n = max(int(gate_n or top_k), int(top_k))
    rows = []
    norm_to_orig: dict = {}
    for c in candidates:
        norm = to_6digit(c.get(code_key))
        rc = dict(c)
        norm_to_orig[norm] = c.get(code_key)
        rc[code_key] = norm
        rows.append(rc)

    head_items = [(r[code_key], r.get(name_key) or r[code_key]) for r in rows[:gate_n]]
    try:
        results = _scan_many(head_items)
    except Exception as e:  # noqa: BLE001
        logger.warning("[risk_gate] 六维排雷扫描失败，如实降级: %s", e)
        results = []
    scan_map = {to_6digit(r.get("code")): r for r in results}

    gated, summary = apply_risk_gate(rows, scan_map, top_k, gate_n)

    # 还原原始 code（keep/tail 行 + kicked 项），页面无感
    for r in gated:
        n = to_6digit(r.get(code_key))
        if n in norm_to_orig:
            r[code_key] = norm_to_orig[n]
    for k in summary.get("kicked", []):
        n = to_6digit(k.get("code"))
        if n in norm_to_orig:
            k["code"] = norm_to_orig[n]
    return gated, summary
