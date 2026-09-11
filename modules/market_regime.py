"""市场状态机 + 历史情境类比引擎（Market Regime State Machine + Historical Analog）。

设计原则（与 P3 一致的诚实口径）：

* 只吃**全历史可比、且真实存在**的广度字段，绝不用缺失特征建模。
  JSON 历史（data/shepherd_history.json，4771 天，2007-2026）里
  ``zt_fail_ratio`` / ``zt_prev_ret`` 有 4756 天是 NaN → 直接弃用；
  只用 ``red_ratio`` / ``limit_up`` / ``limit_down``（全样本非空）。
* 状态机是**规则可解释**的 5 档分类，阈值由全样本分位定（见 classify_state），
  不做黑箱聚类、不声称预测能力。
* 历史类比（analog）是**相似日回看统计**，不是预测：对「今天」的广度向量，
  在全历史里找欧氏距离最近的 k 个交易日，统计那些日之后 5/10/20 日的
  市场表现（红盘率均值、上涨日占比、红盘率中位变化）。明确标注「历史相似，
  不代表未来」，杜绝过度拟合表述。
* 全程离线、零网络；纯函数 + 薄 IO，可单测。
"""

from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np
import pandas as pd

# ── 路径 ────────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "data"))
_HISTORY_JSON = os.path.join(_DATA_DIR, "shepherd_history.json")
_REPORT_OUT = os.path.join(_DATA_DIR, "..", "reports", "market_regime.json")

# 状态顺序（从最弱到最强），用于转移矩阵行列对齐
STATE_ORDER = ["暴跌", "恐慌", "震荡", "结构牛", "普涨"]

# 类比使用的特征（全样本非空，已校验）
_FEATURES = ["red_ratio", "limit_up", "limit_down"]

# 类比前瞻窗口（交易日）
_HORIZONS = (5, 10, 20)


def load_breadth_history(path: Optional[str] = None) -> pd.DataFrame:
    """加载牧羊人广度长历史（健康镜像 JSON，4771 天真值）。

    :returns: DataFrame[date, up_count, down_count, flat_count, limit_up,
              limit_down, red_ratio, connect_hl, zt_fail_ratio, zt_prev_ret]
              按 date 升序；数值列已 to_numeric。
    """
    p = path or _HISTORY_JSON
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    for c in ["up_count", "down_count", "flat_count", "limit_up", "limit_down",
              "red_ratio", "connect_hl", "zt_fail_ratio", "zt_prev_ret"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # 防御：缺失特征填 0，避免类比距离被 NaN 污染
    for c in _FEATURES:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)
    return df


def classify_state(row) -> str:
    """规则可解释的五档状态分类（阈值由全样本分位定）。

    优先级：暴跌 > 恐慌 > 普涨 > 结构牛 > 震荡，互斥。
    """
    rr = float(row.get("red_ratio", np.nan))
    ld = float(row.get("limit_down", np.nan))
    lu = float(row.get("limit_up", np.nan))
    if np.isnan(rr):
        rr = 50.0
    if np.isnan(ld):
        ld = 0.0
    if np.isnan(lu):
        lu = 0.0

    # 暴跌：跌停家数爆量（全样本前 ~2.7%，>=100 共 130 天）
    if ld >= 100:
        return "暴跌"
    # 恐慌：跌停显著放大，或红盘率极低（前 ~10%，<=15）
    if ld >= 50 or rr <= 15:
        return "恐慌"
    # 普涨：压倒性红盘且几乎无跌停（红盘率前 ~13% 且跌停<=10）
    if rr >= 70 and ld <= 10:
        return "普涨"
    # 结构牛：偏强红盘 + 涨停活跃 + 跌停可控
    if rr >= 55 and lu >= 40 and ld <= 20:
        return "结构牛"
    # 震荡：其余
    return "震荡"


def build_state_series(df: pd.DataFrame) -> pd.Series:
    """对全历史逐日分类，返回与 df 对齐的状态序列。"""
    return df.apply(classify_state, axis=1)


def state_distribution(df: pd.DataFrame) -> dict:
    """各状态出现天数（全样本）。"""
    s = build_state_series(df)
    counts = s.value_counts().to_dict()
    return {st: int(counts.get(st, 0)) for st in STATE_ORDER}


def build_transition_matrix(df: pd.DataFrame) -> dict:
    """状态转移矩阵（行随机：从状态 i 出发，次日落在各状态的概率）。

    :returns: {state_i: {state_j: prob}}，概率按行归一；无后继的状态行全 0。
    """
    s = build_state_series(df).tolist()
    matrix = {a: {b: 0 for b in STATE_ORDER} for a in STATE_ORDER}
    for a, b in zip(s[:-1], s[1:]):
        if a in matrix and b in matrix[a]:
            matrix[a][b] += 1
    out = {}
    for a in STATE_ORDER:
        tot = sum(matrix[a].values())
        out[a] = {b: (matrix[a][b] / tot if tot else 0.0) for b in STATE_ORDER}
    return out


def _features_matrix(df: pd.DataFrame) -> np.ndarray:
    """构造 z-score 标准化特征矩阵 (n, 3)，避免单特征量纲主导距离。"""
    raw = df[_FEATURES].to_numpy(dtype=float)
    mu = np.nanmean(raw, axis=0)
    sd = np.nanstd(raw, axis=0)
    sd[sd == 0] = 1.0
    return (raw - mu) / sd


def _state_confidence(row, state: str) -> float:
    """状态置信度（0~1，轻量、可解释），仅作展示辅助，不参与任何决策。"""
    rr = float(row.get("red_ratio", 50.0))
    ld = float(row.get("limit_down", 0.0))
    lu = float(row.get("limit_up", 0.0))
    if state == "普涨":
        return float(np.clip((rr - 60) / 40, 0, 1))
    if state == "结构牛":
        return float(np.clip((rr - 50) / 30, 0, 1))
    if state == "震荡":
        return float(np.clip(1 - abs(rr - 50) / 25, 0, 1) * 0.6)
    if state == "恐慌":
        return float(np.clip(ld / 80 + (15 - rr) / 15, 0, 1))
    if state == "暴跌":
        return float(np.clip(ld / 150, 0, 1))
    return 0.0


def find_analogs(df: pd.DataFrame, target_idx: int, k: int = 8,
                 exclude_window: int = 5) -> list:
    """对目标日找全历史中广度向量最近的 k 个相似交易日，并统计其后市表现。

    :param target_idx: 目标日在 df 中的行号（通常为最新日）。
    :param exclude_window: 排除目标日 ±N 邻居，避免「自己配自己/相邻日」的平凡匹配。
    :returns: 列表，每项为 {date, distance, metrics, forward}；forward 含 d5/d10/d20 的
              avg_red（红盘率均值）、up_frac（上涨日占比）、median_delta（红盘率中位变化）。
    """
    feats = _features_matrix(df)
    n = len(df)
    tgt = feats[target_idx]
    dist = np.linalg.norm(feats - tgt, axis=1)

    # 无前视泄漏：只检索**严格早于**目标日的过去样本（类比不能「看见未来」）。
    # 另排除目标日紧邻的 ±window 邻居，避免「相邻日」平凡匹配。
    mask = np.ones(n, dtype=bool)
    mask[target_idx:] = False
    lo = max(0, target_idx - exclude_window)
    mask[lo:target_idx] = False
    dist[~mask] = np.inf

    order = np.argsort(dist)[:k]
    out = []
    for i in order:
        d_i = dist[i]
        if not np.isfinite(d_i):
            continue
        rec = {
            "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
            "distance": round(float(d_i), 4),
            "metrics": {
                "red_ratio": round(float(df["red_ratio"].iloc[i]), 2),
                "limit_up": int(df["limit_up"].iloc[i]),
                "limit_down": int(df["limit_down"].iloc[i]),
            },
            "state": classify_state(df.iloc[i]),
        }
        fwd = {}
        for h in _HORIZONS:
            endi = min(n, i + 1 + h)
            if endi <= i + 1:
                continue
            window = df.iloc[i + 1:endi]
            avg_red = float(window["red_ratio"].mean())
            up_frac = float((window["red_ratio"] > 50).mean())
            med_delta = float((window["red_ratio"] - df["red_ratio"].iloc[i]).median())
            fwd[f"d{h}"] = {
                "avg_red": round(avg_red, 2),
                "up_frac": round(up_frac, 3),
                "median_delta": round(med_delta, 2),
            }
        rec["forward"] = fwd
        out.append(rec)
    # 按距离升序
    out.sort(key=lambda x: x["distance"])
    return out


def regime_report(target_date: Optional[str] = None, k: int = 8,
                  path: Optional[str] = None) -> dict:
    """生成完整报告字典（供页面/JSON 消费）。

    :param target_date: 指定目标日（YYYY-MM-DD）；None 取历史最新日。
    :param k: 类比返回的最相似日数量。
    """
    df = load_breadth_history(path)
    if df.empty:
        return {"available": False, "reason": "广度历史为空（数据缺失）"}

    if target_date is not None:
        td = pd.to_datetime(target_date)
        matches = df.index[df["date"] == td]
        if len(matches) == 0:
            return {"available": False, "reason": f"目标日 {target_date} 不在历史中"}
        target_idx = int(matches[0])
    else:
        target_idx = len(df) - 1

    row = df.iloc[target_idx]
    state = classify_state(row)
    report = {
        "available": True,
        "data": {
            "rows": int(len(df)),
            "start": df["date"].iloc[0].strftime("%Y-%m-%d"),
            "end": df["date"].iloc[-1].strftime("%Y-%m-%d"),
        },
        "latest": {
            "date": row["date"].strftime("%Y-%m-%d"),
            "state": state,
            "confidence": round(_state_confidence(row, state), 3),
            "metrics": {
                "red_ratio": round(float(row["red_ratio"]), 2),
                "limit_up": int(row["limit_up"]),
                "limit_down": int(row["limit_down"]),
            },
        },
        "state_distribution": state_distribution(df),
        "transition_matrix": build_transition_matrix(df),
        "analogs": find_analogs(df, target_idx, k=k),
    }
    return report


def write_regime_report(out_path: Optional[str] = None,
                        target_date: Optional[str] = None,
                        k: int = 8) -> dict:
    """计算报告并落盘 reports/market_regime.json（页面可直接读，免去每次重算）。"""
    rep = regime_report(target_date=target_date, k=k)
    p = out_path or _REPORT_OUT
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    return rep


if __name__ == "__main__":
    r = write_regime_report(k=8)
    if r.get("available"):
        print(f"状态机报告已生成：{r['data']['rows']} 天 {r['data']['start']}~{r['data']['end']}")
        print(f"最新日 {r['latest']['date']} → 状态【{r['latest']['state']}】"
              f" 置信度 {r['latest']['confidence']}")
        print(f"状态分布：{r['state_distribution']}")
        print(f"Top-3 相似日：")
        for a in r["analogs"][:3]:
            print(f"  {a['date']} 距离{a['distance']} 状态{a['state']} "
                  f"→ 后5日红盘率均值{a['forward'].get('d5',{}).get('avg_red')}"
                  f" 上涨日占比{a['forward'].get('d5',{}).get('up_frac')}")
    else:
        print("报告生成失败：", r.get("reason"))
