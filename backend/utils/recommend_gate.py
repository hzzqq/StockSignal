# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/utils/recommend_gate.py — 每日荐股「输出边界二道闸」纯函数层（T-245 收尾）。

上游 generate_daily_recommendation 已在 apply_risk_gate 踢出 overall_level==high，
本闸在输出边界（HTTP 服务层）再闸一次：防御陈旧/截断 JSON 或旁路写入把高危
标的重新带入推荐。被剔除项不静默——调用方须在信封 message 注明剔除数。

unknown≠guilty：仅剔除已确认 high（risk_scan.overall_level == RISK_HIGH），
low / medium / not_scanned / unknown 一律保留；data 非 dict 或 picks 非 list
时原样返回（不做任何改动）。

消费方：
  - backend/api/read_routes.py::_serve_recommendation_gated（/api/v2/read/daily-recommendation）
  - backend/api/recommend_routes.py（/api/recommendations/today、/api/recommendations/<date>）
"""
from __future__ import annotations

from typing import Any, Tuple

# T-245：六维排雷「高危」等级字面量（与 modules.stock_risk.RISK_HIGH 对齐）——单一真理源
RISK_HIGH = "high"


def gate_recommendation(data: Any) -> Tuple[Any, int]:
    """过滤推荐 data["picks"] 中 overall_level == "high" 的标的。

    返回 ``(data', dropped)``：
      - dropped > 0：data' = {**data, "picks": kept, "risk_gate_boundary_dropped": dropped}
        （不改动入参，浅拷贝展开）；
      - dropped == 0：原样返回 (data, 0)；
      - data 非 dict 或 picks 非 list：(data, 0)。

    判定红线（unknown≠guilty）：逐条 pick 仅当其为 dict 且 p["risk_scan"] 为 dict
    且 overall_level == "high" 才剔除；扫描失败 / 未扫 / low / medium 一律保留。
    """
    if not isinstance(data, dict):
        return data, 0
    picks = data.get("picks")
    if not isinstance(picks, list):
        return data, 0
    kept: list = []
    dropped = 0
    for p in picks:
        rs = p.get("risk_scan") if isinstance(p, dict) else None
        if isinstance(rs, dict) and rs.get("overall_level") == RISK_HIGH:
            dropped += 1
            continue
        kept.append(p)
    if dropped:
        return {**data, "picks": kept, "risk_gate_boundary_dropped": dropped}, dropped
    return data, 0
