"""形态扫描后端纯函数（v1 pages/31_形态选股.py 高级形态算法的服务端移植）。

设计约束：
  * 无 Streamlit / 无网络 / 无 Flask 依赖，可被后端端点与离线单测直接调用；
  * ``detect_advanced_patterns`` / ``merge_patterns`` 与 v1 同构同语义（含诚实降级）；
  * ``scan_patterns`` 接受 API 层传入的 K 线 dict 列表，构造 DataFrame 后返回结构化结果，
    数据不足 / 异常一律 available=false + reason，绝不伪造形态。
"""
from __future__ import annotations

import pandas as pd


def detect_advanced_patterns(df: pd.DataFrame) -> list[dict]:
    """最近窗口内识别趋势类形态：MACD金叉/死叉、均线金叉/死叉、KDJ金叉/死叉、底/顶背离。

    与 v1 ``pages/31_形态选股.py::_detect_advanced_patterns`` 原样语义移植：
      * 不足 35 行返回空；
      * 扫描全部交叉点，仅上报最近 6 日内的「最后一次」交叉方向，避免金叉死叉同时出现；
      * 检测异常时保住已命中的结果（best-effort），不向外抛异常、不伪造形态。
    """
    pats: list = []
    if df is None or df.empty or len(df) < 35:
        return pats
    try:
        df = df.reset_index(drop=True)  # 确保 idxmin 标签 == iloc 位置，避免错位
        close = df["close"]

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()

        def _latest_cross(a, b, up_name, up_bias, down_name, down_bias, win=6):
            """扫描全部交叉点，仅上报最近 win 日内的最后一次交叉方向。"""
            last = None
            for i in range(1, len(df)):
                if a.iloc[i - 1] <= b.iloc[i - 1] and a.iloc[i] > b.iloc[i]:
                    last = (i, up_name, up_bias)
                elif a.iloc[i - 1] >= b.iloc[i - 1] and a.iloc[i] < b.iloc[i]:
                    last = (i, down_name, down_bias)
            if last and last[0] >= len(df) - win:
                i, name, bias = last
                pats.append({"date": df["date"].iloc[i], "name": name, "bias": bias,
                             "desc": f"{name}：最近一次交叉信号"})
                return True
            return False

        # MACD 金叉/死叉
        _latest_cross(dif, dea, "MACD金叉", "看涨", "MACD死叉", "看跌")

        # 均线金叉 MA5 上穿 MA20
        if "ma5" in df.columns and "ma20" in df.columns:
            _latest_cross(df["ma5"], df["ma20"], "均线金叉", "看涨", "均线死叉", "看跌")

        # KDJ 金叉 / 死叉（9,3,3）
        low9 = df["low"].rolling(9).min()
        high9 = df["high"].rolling(9).max()
        rsv = (close - low9) / (high9 - low9).replace(0, pd.NA) * 100
        rsv = rsv.fillna(50)
        K = rsv.rolling(3).mean()
        D = K.rolling(3).mean()
        _latest_cross(K, D, "KDJ金叉", "看涨", "KDJ死叉", "看跌")

        # 底背离 / 顶背离（价格 vs DIF，近 60 日）
        if len(df) >= 60:
            recent = df.tail(30)
            pl = float(recent["close"].min())
            idx_low = int(recent["close"].idxmin())
            prev = df.iloc[:idx_low]
            if len(prev) >= 20:
                prev_low = float(prev["close"].tail(20).min())
                if pl < prev_low and dif.iloc[-1] > dif.iloc[idx_low]:
                    pats.append({"date": df["date"].iloc[-1], "name": "底背离", "bias": "看涨",
                                 "desc": "价格新低而 MACD 未新低，下跌动能衰竭"})
            ph = float(recent["close"].max())
            idx_high = int(recent["close"].idxmax())
            prev2 = df.iloc[:idx_high]
            if len(prev2) >= 20:
                prev_high = float(prev2["close"].tail(20).max())
                if ph > prev_high and dif.iloc[-1] < dif.iloc[idx_high]:
                    pats.append({"date": df["date"].iloc[-1], "name": "顶背离", "bias": "看跌",
                                 "desc": "价格新高而 MACD 未新高，上涨动能衰竭"})
    except Exception:
        # ui_audit_exempt: 顶底背离等高级形态为 best-effort 增补检测，
        # 异常时返回已命中的基础形态（不伪造、不外抛）。
        pass
    return pats


def merge_patterns(df: pd.DataFrame) -> list[dict]:
    """合并 K 线基础形态（modules.technical）与趋势类高级形态（本模块）。

    与 v1 ``_merge_patterns`` 语义一致：按 date 倒序、(name, bias) 去重、截断前 8。
    额外保证：advanced 检测抛异常时也只保基础形态，不中断、不伪造。
    """
    from modules import technical as _technical

    base = _technical.full_analysis(df).get("patterns", []) or []
    if isinstance(base, str):
        base = [base]
    try:
        adv = detect_advanced_patterns(df)
    except Exception:
        # ui_audit_exempt: 高级形态为 best-effort，异常时仅保留基础形态。
        adv = []
    merged = list(base) + list(adv)

    # 按日期倒序去重（同名同偏向只保留一个）；非 dict 元素（technical 偶发返回
    # {"error": ...} 的键名等）跳过，避免 .get 崩溃中断整个扫描结果。
    seen = set()
    out: list[dict] = []
    ordered = sorted(
        merged,
        key=lambda x: str(x.get("date", "")) if isinstance(x, dict) else "",
        reverse=True,
    )
    for p in ordered:
        if not isinstance(p, dict):
            continue
        key = (p.get("name"), p.get("bias"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out[:8]


# scan_patterns 诚实降级时给出的固定原因（供上层/测试断言，避免散落魔法字符串）
_REASON_EMPTY = "K线数据为空"
_REASON_SHORT = "K线不足35根，跳过形态识别"
_REASON_MISSING = "K线缺少必需字段: {cols}"
_REASON_EXC = "形态扫描异常: {exc}"


def scan_patterns(klines: list[dict]) -> dict:
    """接受 API 层传入的 K 线 dict 列表，构造 DataFrame 后返回结构化扫描结果。

    klines 每项需含 date/open/high/low/close，ma5/ma20 可选（缺省时按 close 滚动均值补齐，
    对齐 v1 经 DataCleaner.full_pipeline 后必带 ma5/ma20 的事实）。

    返回 ``{"available": bool, "patterns": [...], "reason": str|None, "n_bars": int}``。
    任何数据不足 / 缺字段 / 异常都返回 available=false + reason + patterns 为空，绝不伪造形态。
    """
    n_bars = len(klines) if isinstance(klines, list) else 0
    result: dict = {"available": False, "patterns": [], "reason": None, "n_bars": n_bars}

    if not isinstance(klines, list) or n_bars == 0:
        result["reason"] = _REASON_EMPTY
        return result
    if n_bars < 35:
        result["reason"] = _REASON_SHORT
        return result

    try:
        df = pd.DataFrame(klines)
        required = ("date", "open", "high", "low", "close")
        missing = [c for c in required if c not in df.columns]
        if missing:
            result["reason"] = _REASON_MISSING.format(cols=",".join(missing))
            return result

        for c in ("open", "high", "low", "close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        if "ma5" not in df.columns:
            df["ma5"] = df["close"].rolling(5).mean()
        if "ma20" not in df.columns:
            df["ma20"] = df["close"].rolling(20).mean()
        df = df.reset_index(drop=True)

        result["patterns"] = merge_patterns(df)
        result["available"] = True
        return result
    except Exception as e:  # noqa: BLE001 - 顶层诚实降级，绝不向外抛
        result["reason"] = _REASON_EXC.format(exc=type(e).__name__)
        result["patterns"] = []
        result["available"] = False
        return result
