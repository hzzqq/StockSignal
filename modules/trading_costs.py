# -*- coding: utf-8 -*-
"""
modules/trading_costs.py — A 股交易成本模型单源（T-274 R10）。

背景（docs/alignment-matrix.md #7）：回测端此前未计入交易成本/滑点的统一口径，
任何「含成本」收益表述都不成立。本模块把成本参数与计算**单源化**，供各回测面
统一接入。

诚实红线（写死，守卫钉住）：
- **49.1% 方向命中锚（1722/3507，4092 交易日）不受成本影响**——方向命中率度量
  「次日涨跌方向判断」，与交易成本（收益层扣减）分属不同口径；本模块绝不回写/
  调整任何方向命中数字，双口径分列（见矩阵 #5）。
- 成本参数为 2024-2026 A 股零售**业界典型值**，非本项目实测账单——用户实际费率
  以券商合同为准，参数全部可配置；
- 印花税按 2023-08-28 减半后的 0.05%（仅卖出）；
- 数据不足/非法输入（金额 ≤0 / 非 数值）诚实返回 None 或抛 ValueError，不编造。
"""
from __future__ import annotations

# ── 成本参数（单源常量；业界典型值，非实测——以券商合同为准）─────────────
COMMISSION_RATE = 2.5e-4    # 佣金万 2.5（双边收取）
COMMISSION_MIN = 5.0        # 单笔最低佣金 5 元
STAMP_TAX_RATE = 5e-4       # 印花税 0.05%（2023-08-28 减半，仅卖出）
SLIPPAGE_RATE = 1e-3        # 滑点 0.1%（双边，市价单冲击保守估计）
TRANSFER_FEE_RATE = 1e-5    # 过户费 0.001%（双边，沪市；深市 2022 后同费率，统一计入）


def _validate_amount(amount) -> float:
    """金额校验：>0 数值；非法抛 ValueError（不编造、不静默归零）。"""
    try:
        amt = float(amount)
    except (TypeError, ValueError) as e:
        raise ValueError(f"金额非法: {amount!r}") from e
    if amt <= 0:
        raise ValueError(f"金额必须 > 0，得到 {amt}")
    return amt


def _commission(amount: float) -> float:
    """佣金 = max(金额 × 费率, 最低佣金)。"""
    return max(amount * COMMISSION_RATE, COMMISSION_MIN)


def buy_cost(amount) -> dict:
    """买入成本：佣金（含最低）+ 滑点 + 过户费。

    :param amount: 买入金额（元）
    :returns: {commission, slippage, transfer_fee, total, total_rate}
    """
    amt = _validate_amount(amount)
    commission = _commission(amt)
    slippage = amt * SLIPPAGE_RATE
    transfer = amt * TRANSFER_FEE_RATE
    total = commission + slippage + transfer
    return {"commission": round(commission, 2), "slippage": round(slippage, 2),
            "transfer_fee": round(transfer, 2), "total": round(total, 2),
            "total_rate": round(total / amt, 6)}


def sell_cost(amount) -> dict:
    """卖出成本：佣金（含最低）+ 印花税（仅卖出）+ 滑点 + 过户费。"""
    amt = _validate_amount(amount)
    commission = _commission(amt)
    stamp = amt * STAMP_TAX_RATE
    slippage = amt * SLIPPAGE_RATE
    transfer = amt * TRANSFER_FEE_RATE
    total = commission + stamp + slippage + transfer
    return {"commission": round(commission, 2), "stamp_tax": round(stamp, 2),
            "slippage": round(slippage, 2), "transfer_fee": round(transfer, 2),
            "total": round(total, 2), "total_rate": round(total / amt, 6)}


def round_trip_cost(amount) -> dict:
    """一买一卖全成本（同金额近似；返回合计与占本金比例）。

    :returns: {buy, sell, total, total_rate}——total_rate 为全成本占本金比例。
    """
    b = buy_cost(amount)
    s = sell_cost(amount)
    total = round(b["total"] + s["total"], 2)
    amt = _validate_amount(amount)
    return {"buy": b, "sell": s, "total": total,
            "total_rate": round(total / amt, 6)}


def round_trip_rate(amount: float = 100_000.0) -> float:
    """快速估算：一买一卖全成本率（默认按 10 万元本金，覆盖最低佣金影响）。

    供回测面对收益率序列做统一扣减的近似常数（收益 ≥ 该值才有正期望空间）。
    """
    return round_trip_cost(amount)["total_rate"]
