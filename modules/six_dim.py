"""六维量化评分（G4）纯逻辑。

六维：技术 / 资金 / 价值 / 成长 / 基本面 / 周期。每维输出 0–100，缺失维返回 None，
``compose`` 对有效维**等权平均并重新归一**（缺维不参与，避免用 0 拉低）。

诚实性：各维均为**可解释的启发式映射**（阈值为经验区间，非拟合模型）；
数据缺失维度明示为 None，**绝不用默认值假装有分**。所有映射方向与阈值写死在常量里，
便于单测与审计。
"""
from __future__ import annotations

import pandas as pd

# 各维映射区间（lo→0分, hi→100分；hi<lo 表示越小越好）
BANDS = {
    "value_pe": (80.0, 8.0),      # PE 8 倍=100分，80 倍=0分
    "value_pb": (8.0, 0.8),       # PB 0.8=100分，8 倍=0分
    "growth_yoy": (-30.0, 60.0),  # 净利同比 -30%=0分，60%=100分
    "fund_roe": (0.0, 20.0),      # ROE 0%=0分，20%=100分
    "capital_turnover": (0.5, 10.0),   # 换手 0.5%~10%
    "capital_volratio": (0.5, 3.0),    # 量比 0.5~3.0
    "tech_ma_pos": (-15.0, 15.0),      # 距 MA20 偏离 -15%~+15%
    "tech_mom20": (-20.0, 20.0),       # 20 日动量
    "tech_mom60": (-40.0, 40.0),       # 60 日动量
    "cycle_pos60": (-30.0, 30.0),      # 60 日累计涨跌
}

# 状态机五档 → 周期基础分
STATE_BASE = {"冰点": 70.0, "修复": 65.0, "震荡": 50.0, "主升": 80.0,
              "退潮": 35.0, "高潮": 45.0, "暴跌": 20.0, "恐慌": 15.0}

DIM_LABELS = {
    "technical": "技术", "capital": "资金", "value": "价值",
    "growth": "成长", "fundamental": "基本面", "cycle": "周期",
}


def clamp_score(value, lo: float, hi: float):
    """线性映射到 0–100 并截断；value 缺失(None/NaN) 返回 None。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if hi == lo:
        return 50.0
    s = (v - lo) / (hi - lo) * 100.0
    return float(max(0.0, min(100.0, s)))


def _weighted(parts):
    """[(score, weight)] → 加权平均（自动按有效项重新归一）；全缺返回 None。"""
    valid = [(s, w) for s, w in parts if s is not None]
    if not valid:
        return None
    tw = sum(w for _, w in valid)
    if tw <= 0:
        return None
    return round(sum(s * w for s, w in valid) / tw, 1)


def score_technical(close: pd.Series):
    """技术面：MA20 位置(0.4) + 20 日动量(0.3) + 60 日动量(0.3)。close 升序。"""
    if close is None or len(close.dropna()) < 21:
        return None
    c = close.dropna()
    last = float(c.iloc[-1])
    ma20 = float(c.tail(20).mean())
    ma_pos = clamp_score((last / ma20 - 1.0) * 100, *BANDS["tech_ma_pos"]) if ma20 else None
    mom20 = clamp_score((last / float(c.iloc[-21]) - 1.0) * 100, *BANDS["tech_mom20"]) if len(c) > 21 else None
    mom60 = clamp_score((last / float(c.iloc[-61]) - 1.0) * 100, *BANDS["tech_mom60"]) if len(c) > 61 else None
    return _weighted([(ma_pos, 0.4), (mom20, 0.3), (mom60, 0.3)])


def score_capital(turnover, vol_ratio):
    """资金面：换手(0.5) + 量比(0.5)。"""
    t = clamp_score(turnover, *BANDS["capital_turnover"])
    v = clamp_score(vol_ratio, *BANDS["capital_volratio"])
    return _weighted([(t, 0.5), (v, 0.5)])


def score_value(pe, pb):
    """价值面：PE(0.6) + PB(0.4)；负 PE 视为缺失（亏损股价值映射失真）。"""
    p = clamp_score(pe, *BANDS["value_pe"]) if (pe is not None and _pos(pe)) else None
    b = clamp_score(pb, *BANDS["value_pb"]) if (pb is not None and _pos(pb)) else None
    return _weighted([(p, 0.6), (b, 0.4)])


def score_growth(profit_yoy):
    """成长面：归母净利润同比。"""
    return clamp_score(profit_yoy, *BANDS["growth_yoy"])


def score_fundamental(roe):
    """基本面：ROE。"""
    return clamp_score(roe, *BANDS["fund_roe"])


def score_cycle(state, pos60_pct):
    """周期面：状态机五档基础分(0.6) + 60 日位置(0.4)。"""
    base = STATE_BASE.get(state) if state else None
    pos = clamp_score(pos60_pct, *BANDS["cycle_pos60"])
    return _weighted([(base, 0.6), (pos, 0.4)])


def _pos(x) -> bool:
    try:
        return float(x) > 0
    except (TypeError, ValueError):
        return False


def compose(dims: dict) -> dict:
    """等权平均六个有效维；返回 {'overall': float|None, 'dims': {...}}。"""
    valid = {k: v for k, v in dims.items() if v is not None}
    overall = round(sum(valid.values()) / len(valid), 1) if valid else None
    return {"overall": overall, "dims": dims, "coverage": len(valid)}


def _num_from_row(row, cols):
    # 东财财务摘要的数据列按「最新期在前」排列 → 正向取第一个有效值 = 最新可得期
    for c in cols:
        v = row.get(c)
        try:
            f = float(str(v).replace("%", "").replace(",", ""))
            if f == f:
                return f
        except (TypeError, ValueError):
            continue
    return None


def parse_fin(fin):
    """从东财财务摘要解析 (ROE, 归母净利润同比)。解析失败返回 (None, None)。"""
    if fin is None or len(fin) == 0:
        return None, None
    cols = list(fin.columns)
    name_col = cols[1] if len(cols) > 1 else cols[0]
    val_cols = [c for c in cols if c not in ("选项", name_col)]
    roe = yoy = None
    for _, r in fin.iterrows():
        nm = str(r.get(name_col, ""))
        if roe is None and "净资产收益率" in nm and "摊薄" not in nm:
            roe = _num_from_row(r, val_cols)
        if yoy is None and "净利润" in nm and "同比" in nm:
            yoy = _num_from_row(r, val_cols)
    return roe, yoy


def compute_dims(code, fetch_hist, fetch_spot, fetch_fin, state_fn=None):
    """编排六维取数与评分。三个 fetcher 与 state_fn 均可注入（便于单测）。

    返回 ``(compose_result, raw)``；任一源失败只影响对应维（该维 None），不抛出。
    """
    close = None
    try:
        h = fetch_hist(code)
        if h is not None and "收盘" in h.columns:
            close = pd.to_numeric(h["收盘"], errors="coerce").dropna().reset_index(drop=True)
    except Exception:  # noqa: BLE001
        pass

    try:
        row = fetch_spot(code) or {}
    except Exception:  # noqa: BLE001
        row = {}

    roe = yoy = None
    try:
        roe, yoy = parse_fin(fetch_fin(code))
    except Exception:  # noqa: BLE001
        pass

    state = None
    try:
        if state_fn is not None:
            state = state_fn()
    except Exception:  # noqa: BLE001
        pass

    pos60 = None
    if close is not None and len(close) > 61:
        pos60 = (float(close.iloc[-1]) / float(close.iloc[-61]) - 1.0) * 100.0

    dims = {
        "technical": score_technical(close),
        "capital": score_capital(row.get("换手率"), row.get("量比")),
        "value": score_value(row.get("市盈率-动态"), row.get("市净率")),
        "growth": score_growth(yoy),
        "fundamental": score_fundamental(roe),
        "cycle": score_cycle(state, pos60),
    }
    raw = {
        "pe": row.get("市盈率-动态"), "pb": row.get("市净率"), "roe": roe,
        "profit_yoy": yoy, "state": state, "turnover": row.get("换手率"),
        "vol_ratio": row.get("量比"), "pos60": pos60,
    }
    return compose(dims), raw
