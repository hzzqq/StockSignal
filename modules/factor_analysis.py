"""因子分析纯逻辑（G3）：IC/IR、分层收益、多空组合。

全部为**纯函数**（输入 panel，输出 panel/Series），便于单测与复用，页面只做编排。

约定：
- ``factor_panel`` / ``ret_panel``：index=日期（**升序**），columns=标的，values=数值。
- ``forward=h`` 表示用 t 日因子预测 t+h 日收益。``ret_panel`` 存 **t 日收益**，
  计算时用 ``iloc[i+h]`` 取未来收益，**严格后移**避免前视泄漏。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rank_ic(factor: pd.Series, fwd_ret: pd.Series) -> float:
    """单期截面 Spearman 秩相关 IC（抗极值）。有效样本 < 3 返回 NaN。"""
    df = pd.concat([pd.Series(factor), pd.Series(fwd_ret)], axis=1).dropna()
    if len(df) < 3:
        return float("nan")
    a, b = df.iloc[:, 0], df.iloc[:, 1]
    if a.nunique() < 2 or b.nunique() < 2:
        return float("nan")
    return float(a.corr(b, method="spearman"))


def ic_series(factor_panel: pd.DataFrame, ret_panel: pd.DataFrame, forward: int = 1) -> pd.Series:
    """逐期截面 IC 序列（index=因子可用日）。"""
    dates = list(factor_panel.index)
    out: dict = {}
    for i, d in enumerate(dates):
        j = i + forward
        if j >= len(dates):
            break
        out[d] = rank_ic(factor_panel.loc[d], ret_panel.iloc[j])
    return pd.Series(out, dtype="float64").dropna()


def ic_summary(ic: pd.Series) -> dict:
    """IC 汇总：均值/标准差/IR(=均值/标准差)/胜率/t 值/样本数。"""
    ic = pd.Series(ic, dtype="float64").dropna()
    n = int(len(ic))
    if n == 0:
        return {"n": 0, "ic_mean": float("nan"), "ic_std": float("nan"),
                "ir": float("nan"), "positive_ratio": float("nan"), "t_stat": float("nan")}
    mean = float(ic.mean())
    std = float(ic.std(ddof=1)) if n > 1 else float("nan")
    ir = mean / std if std and std > 0 else float("nan")
    t = mean / (std / np.sqrt(n)) if std and std > 0 else float("nan")
    return {"n": n, "ic_mean": mean, "ic_std": std, "ir": ir,
            "positive_ratio": float((ic > 0).mean()), "t_stat": t}


def layered_returns(factor_panel: pd.DataFrame, ret_panel: pd.DataFrame,
                    n_layers: int = 5, forward: int = 1) -> pd.DataFrame:
    """因子分层收益：每期按因子值分 n 层，取各层未来收益均值。

    返回 index=日期，columns=层号(0=因子最小层 … n-1=因子最大层)。
    """
    dates = list(factor_panel.index)
    rows: dict = {}
    for i, d in enumerate(dates):
        j = i + forward
        if j >= len(dates):
            break
        f = pd.Series(factor_panel.loc[d])
        r = pd.Series(ret_panel.iloc[j])
        df = pd.concat([f, r], axis=1).dropna()
        if len(df) < n_layers:
            continue
        try:
            q = pd.qcut(df.iloc[:, 0], n_layers, labels=False, duplicates="drop")
        except Exception:  # noqa: BLE001
            continue
        if q.nunique() < 2:
            continue
        rows[d] = df.iloc[:, 1].groupby(q).mean()
    return pd.DataFrame(rows).T.sort_index()


def cumulative(layer_rets: pd.DataFrame) -> pd.DataFrame:
    """把逐期分层收益（简单收益）累积成净值曲线（起点 0 = 累计收益）。"""
    if layer_rets is None or layer_rets.empty:
        return pd.DataFrame()
    return (1.0 + layer_rets.fillna(0.0)).cumprod() - 1.0


def long_short(layer_rets: pd.DataFrame) -> pd.Series:
    """多空组合逐期收益 = 最高层 − 最低层（因子越大越看好）。"""
    if layer_rets is None or layer_rets.empty or layer_rets.shape[1] < 2:
        return pd.Series(dtype="float64")
    cols = sorted(layer_rets.columns, key=lambda c: int(c))
    return (layer_rets[cols[-1]] - layer_rets[cols[0]]).dropna()


FACTORS = {
    "momentum": "20 日动量",
    "reversal": "5 日反转",
    "volatility": "20 日波动率",
    "turnover": "20 日平均换手",
}


def build_panels(codes, days, factor: str, fetch_hist):
    """由逐股历史构建「因子面板 / 收益面板」。

    ``fetch_hist(code) -> DataFrame``，须含列 ``['日期','收盘']``，可选 ``['换手率']``。
    返回 ``(factor_panel, ret_panel, errs)``：标的不足 3 只时面板为 None（诚实不出结论）。
    ``ret_panel[t]`` = t 日收益（close[t]/close[t-1]-1），配合 ``forward=1`` 取 t+1 为未来。
    """
    closes: dict = {}
    turns: dict = {}
    errs: list = []
    for c in codes:
        try:
            h = fetch_hist(c)
            if h is None or len(h) == 0:
                errs.append((c, "空数据"))
                continue
            if "日期" not in h.columns or "收盘" not in h.columns:
                errs.append((c, "缺列"))
                continue
            h = h.tail(int(days) + 1)
            idx = pd.to_datetime(h["日期"], errors="coerce")
            closes[c] = pd.Series(pd.to_numeric(h["收盘"], errors="coerce").values, index=idx)
            if "换手率" in h.columns:
                turns[c] = pd.Series(pd.to_numeric(h["换手率"], errors="coerce").values, index=idx)
        except Exception as e:  # noqa: BLE001
            errs.append((c, str(e)[:60]))

    if len(closes) < 3:
        return None, None, errs

    close = pd.DataFrame(closes).sort_index()
    ret = close.pct_change()
    if factor == "momentum":
        fp = close.pct_change(20)
    elif factor == "reversal":
        fp = -close.pct_change(5)
    elif factor == "volatility":
        fp = close.pct_change().rolling(20).std()
    elif factor == "turnover":
        if len(turns) < 3:
            return None, None, errs + [("-", "该数据源无换手率字段")]
        fp = pd.DataFrame(turns).sort_index().rolling(20).mean()
    else:
        fp = close.pct_change(20)

    common = fp.index.intersection(ret.index)
    return fp.loc[common], ret.loc[common], errs
