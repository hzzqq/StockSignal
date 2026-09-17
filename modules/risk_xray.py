"""modules/risk_xray.py — 组合风险透视（H4）。

持仓只做「盈亏归因」是不够的：同样的收益，集中度、行业暴露、相关性、抗情景
能力完全不同。本模块补上这些风险维度（对标米筐 RQBeta / 雪球组合 / 组合 X-ray）：

- ``concentration``     权重集中度（HHI / 最大权重 / 有效持仓数 / 集中档位）
- ``sector_exposure``   行业暴露（按行业聚合权重，未知行业如实单列）
- ``correlation_matrix``两两收益相关性矩阵
- ``scenario_pnl``      历史/自定义情景下的组合损益（含覆盖率与缺失清单）
- ``brinson``           简化 Brinson 归因（配置效应 / 选择效应 / 交互效应）

红线（诚实口径）：
- 纯计算、不触网，数据由调用方注入；
- 数据不足（无权重 / 有效序列 <2 / 行业缺失率过高）一律返回带 ``status`` 的
  **显式不可用**语义，**绝不默认成 0**、绝不编造结论；
- 任何异常兜底为安全默认值，不向上抛。
"""

from __future__ import annotations

import math
from typing import Any

__all__ = [
    "concentration",
    "sector_exposure",
    "correlation_matrix",
    "scenario_pnl",
    "brinson",
]

_UNKNOWN = "未知"


def _clean_weights(weights: dict | None) -> dict:
    """清洗权重：保留有限正数，其余（None/NaN/<=0/非数值）丢弃。"""
    out: dict = {}
    for k, v in (weights or {}).items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(fv) and fv > 0:
            out[k] = fv
    return out


def _pearson(a: list, b: list) -> float | None:
    """皮尔逊相关系数；任一方差为 0 或样本 <2 时返回 None（而不是 0）。"""
    n = min(len(a), len(b))
    if n < 2:
        return None
    xs, ys = [float(x) for x in a[:n]], [float(y) for y in b[:n]]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def concentration(weights: dict | None) -> dict:
    """集中度：HHI、最大权重、有效持仓数（1/HHI）、集中档位。"""
    w = _clean_weights(weights)
    if not w:
        return {"status": "unavailable", "reason": "无有效持仓权重"}
    total = sum(w.values())
    p = {k: v / total for k, v in w.items()}
    hhi = sum(x * x for x in p.values())
    mx = max(p.values())
    eff_n = (1.0 / hhi) if hhi > 0 else 0.0
    if hhi < 0.15:
        level = "分散"
    elif hhi < 0.25:
        level = "适中"
    else:
        level = "集中"
    top = sorted(p.items(), key=lambda kv: -kv[1])[:5]
    return {
        "status": "ok", "n": len(p), "hhi": round(hhi, 4),
        "max_weight_pct": round(mx * 100, 1), "effective_n": round(eff_n, 2),
        "level": level, "top": [(k, round(v * 100, 1)) for k, v in top],
    }


def sector_exposure(weights: dict | None, sector_of: dict | None) -> dict:
    """行业暴露：按行业聚合权重占比；未知行业单列并给出缺失率。"""
    w = _clean_weights(weights)
    if not w:
        return {"status": "unavailable", "reason": "无有效持仓权重"}
    total = sum(w.values())
    agg: dict = {}
    unknown = 0.0
    for code, v in w.items():
        sec = (sector_of or {}).get(code) or _UNKNOWN
        agg[sec] = agg.get(sec, 0.0) + v
        if sec == _UNKNOWN:
            unknown += v
    exposure = {s: round(v / total * 100, 1)
                for s, v in sorted(agg.items(), key=lambda kv: -kv[1])}
    unknown_pct = round(unknown / total * 100, 1)
    return {
        "status": "ok", "exposure": exposure, "n_sectors": len(exposure),
        "unknown_pct": unknown_pct,
        "warning": ("行业映射缺失较多，暴露结论仅供参考" if unknown_pct > 30 else None),
    }


def correlation_matrix(returns: dict | None) -> dict:
    """两两收益相关性矩阵。

    ``returns`` = ``{code: [逐日收益...]}``。有效序列 <2 条 → unavailable。
    """
    data = {}
    for k, v in (returns or {}).items():
        try:
            series = [float(x) for x in (v or []) if x is not None and math.isfinite(float(x))]
        except (TypeError, ValueError):
            continue
        if len(series) >= 2:
            data[k] = series
    codes = sorted(data)
    if len(codes) < 2:
        return {"status": "unavailable", "codes": [], "matrix": [],
                "reason": "有效收益序列不足 2 条，无法计算相关性"}
    m = min(len(data[c]) for c in codes)
    matrix = [[(_pearson(data[a][-m:], data[b][-m:]) or 0.0) if a != b else 1.0
               for b in codes] for a in codes]
    avg = None
    pairs = [matrix[i][j] for i in range(len(codes)) for j in range(i + 1, len(codes))]
    if pairs:
        avg = round(sum(pairs) / len(pairs), 3)
    return {"status": "ok", "codes": codes, "matrix": matrix, "n_obs": m,
            "avg_corr": avg}


def scenario_pnl(weights: dict | None, scenario_returns: dict | None) -> dict:
    """情景压力测试：组合在给定情景下的损益（收益用小数，如 -0.3 表示 -30%）。

    返回损益 + **覆盖率**（有多少权重参与了情景）+ 缺失标的清单，绝不假装全覆盖。
    """
    w = _clean_weights(weights)
    if not w:
        return {"status": "unavailable", "reason": "无有效持仓权重"}
    if not scenario_returns:
        return {"status": "unavailable", "reason": "无情景收益数据"}
    total = sum(w.values())
    covered = 0.0
    pnl = 0.0
    missing: list = []
    for code, v in w.items():
        r = scenario_returns.get(code)
        if r is None:
            missing.append(code)
            continue
        try:
            pnl += (v / total) * float(r)
        except (TypeError, ValueError):
            missing.append(code)
            continue
        covered += v
    return {
        "status": "ok", "pnl_pct": round(pnl * 100, 2),
        "coverage_pct": round(covered / total * 100, 1),
        "n_missing": len(missing), "missing": sorted(missing)[:20],
    }


def _group_by_sector(weights: dict, returns: dict, sectors: dict | None) -> dict:
    """按行业聚合 → ``{sector: {"w": 权重和, "r": 权重加权收益}}``。"""
    agg: dict = {}
    for code, w in weights.items():
        sec = (sectors or {}).get(code) or _UNKNOWN
        d = agg.setdefault(sec, {"w": 0.0, "wr": 0.0})
        d["w"] += w
        r = (returns or {}).get(code)
        if r is not None:
            try:
                d["wr"] += w * float(r)
            except (TypeError, ValueError):
                pass
    for d in agg.values():
        d["r"] = (d["wr"] / d["w"]) if d["w"] else None
    return agg


def brinson(port_weights: dict | None, bench_weights: dict | None,
            port_returns: dict | None, bench_returns: dict | None,
            sectors: dict | None) -> dict:
    """简化 Brinson 归因：逐行业的配置效应 / 选择效应 / 交互效应 + 合计。

    收益用小数。缺基准权重或组合权重 → unavailable。某行业缺基准收益时按 0 处理
    并在 ``note`` 中如实标注，不臆造。
    """
    pw = _clean_weights(port_weights)
    bw = _clean_weights(bench_weights)
    if not pw or not bw:
        return {"status": "unavailable", "reason": "缺组合或基准权重"}
    tw, tbw = sum(pw.values()), sum(bw.values())
    if tw <= 0 or tbw <= 0:
        return {"status": "unavailable", "reason": "权重合计非正"}
    pwn = {k: v / tw for k, v in pw.items()}
    bwn = {k: v / tbw for k, v in bw.items()}
    pg = _group_by_sector(pwn, port_returns or {}, sectors)
    bg = _group_by_sector(bwn, bench_returns or {}, sectors)

    rb_total = 0.0
    for k, w in bwn.items():
        r = (bench_returns or {}).get(k)
        if r is not None:
            try:
                rb_total += w * float(r)
            except (TypeError, ValueError):
                pass

    rows: list = []
    tot_alloc = tot_sel = tot_inter = 0.0
    missing_bench: list = []
    for sec in sorted(set(pg) | set(bg)):
        wp = pg.get(sec, {}).get("w", 0.0)
        rp = pg.get(sec, {}).get("r")
        wb = bg.get(sec, {}).get("w", 0.0)
        rb = bg.get(sec, {}).get("r")
        if rb is None:
            if wb > 0:
                missing_bench.append(sec)
            rb = 0.0
        rp_eff = rb if rp is None else rp
        alloc = (wp - wb) * (rb - rb_total)
        sel = wb * (rp_eff - rb)
        inter = (wp - wb) * (rp_eff - rb)
        tot_alloc += alloc
        tot_sel += sel
        tot_inter += inter
        rows.append({
            "sector": sec,
            "alloc_pct": round(alloc * 100, 3),
            "select_pct": round(sel * 100, 3),
            "inter_pct": round(inter * 100, 3),
            "port_w_pct": round(wp * 100, 1),
            "bench_w_pct": round(wb * 100, 1),
        })
    rows.sort(key=lambda r: -(abs(r["alloc_pct"]) + abs(r["select_pct"])))
    return {
        "status": "ok", "rows": rows,
        "total_alloc_pct": round(tot_alloc * 100, 3),
        "total_select_pct": round(tot_sel * 100, 3),
        "total_inter_pct": round(tot_inter * 100, 3),
        "total_pct": round((tot_alloc + tot_sel + tot_inter) * 100, 3),
        "n_missing_bench": len(missing_bench),
        "note": ("部分行业缺基准收益，已按 0 处理" if missing_bench else None),
    }
