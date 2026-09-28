"""实时强势榜数据与评分（G8 纯逻辑层）。

抽取到模块层的目的：① 评分是纯函数，可单测；② 取数入口可被测试 monkeypatch，
页面只做编排（与 ``modules/shepherd`` 的测试模式一致）。

数据源三层（T-177/T-178）：
  1. 东财直连薄层 ``em_snapshot.fetch_a_spot_em``（主域，防 clist 频率风控）；
  2. akshare ``stock_zh_a_spot_em`` 兜底（82 子域在本机恒断，仅应急）；
  3. 腾讯 qt 批量应急层（东财 clist 全封期间撑榜，覆盖与字段较少，如实标注）。
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

# 东财快照列名候选（字段偶有增删，按候选表匹配而非硬编码）
COL = {
    "code": ["代码"],
    "name": ["名称"],
    "price": ["最新价"],
    "chg": ["涨跌幅"],
    "amount": ["成交额"],
    "turnover": ["换手率"],
    "vol_ratio": ["量比"],
}

# 评分权重（合计 1.0）：涨幅 0.40 / 量比 0.30 / 换手 0.20 / 成交额 0.10
WEIGHTS = {"chg": 0.40, "vol_ratio": 0.30, "turnover": 0.20, "amount": 0.10}


def _col(df: pd.DataFrame, key: str):
    for c in COL.get(key, []):
        if c in df.columns:
            return c
    return None


def _num(df: pd.DataFrame, key: str, default: float = 0.0) -> pd.Series:
    c = _col(df, key)
    if not c:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[c], errors="coerce").fillna(default)


def _ordinal_pct(series: pd.Series) -> pd.Series:
    """百分位排名(0-100)，抗极值（单只巨量不会把其余压成一条线）。"""
    n = len(series)
    if n <= 1:
        return pd.Series([100.0] * n, index=series.index)
    return series.rank(pct=True, method="average") * 100.0


def strong_score(df: pd.DataFrame) -> pd.DataFrame:
    """多因子强势评分（启发式加权，非预测模型）。"""
    out = df.copy()
    out["_s_chg"] = _ordinal_pct(_num(df, "chg")).round(1)
    out["_s_vr"] = _ordinal_pct(_num(df, "vol_ratio")).round(1)
    out["_s_to"] = _ordinal_pct(_num(df, "turnover")).round(1)
    out["_s_amt"] = _ordinal_pct(_num(df, "amount")).round(1)
    out["_score"] = (
        WEIGHTS["chg"] * out["_s_chg"]
        + WEIGHTS["vol_ratio"] * out["_s_vr"]
        + WEIGHTS["turnover"] * out["_s_to"]
        + WEIGHTS["amount"] * out["_s_amt"]
    ).round(1)
    return out


def _spot_cached_akshare() -> pd.DataFrame:
    """akshare 兜底源（82.push2 子域在本机恒断连，仅当直连层 None 时才走）。"""
    import akshare as ak
    return ak.stock_zh_a_spot_em()


# ───────────────── 腾讯应急层（T-178）：东财 clist 全封期间撑榜 ─────────────────
QQ_URL = "https://qt.gtimg.cn/q="
_QQ_BATCH = 400            # 每批代码数（实测 500 只 HTTP 200）
_QQ_MIN_ROWS = 1000        # 覆盖阈值：低于此数视为「装不成全市场」，诚实返 None
_QQ_TTL = 60.0             # 成功共享缓存
_QQ_COOLDOWN = 300.0       # 失败冷却（与 em_snapshot 同防风控语义）
_qq_state = {"df": None, "ts": 0.0, "cool_until": 0.0}


def _reset_qq_state_for_test() -> None:
    _qq_state.update({"df": None, "ts": 0.0, "cool_until": 0.0})


def _qq_get_raw(url: str, **kwargs):
    """requests 抽象层（测试 monkeypatch 点）。"""
    import requests
    return requests.get(url, **kwargs)


def _qq_headers() -> dict:
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}


def _qq_prefix(code: str) -> str:
    """6/5 开头沪、0/3 开头深、4/8/9 开头北交所（920 等，实测 sh 前缀无效）。"""
    c = str(code).strip()
    if c.startswith(("4", "8", "9")):
        return f"bj{c}"
    if c.startswith(("6", "5")):
        return f"sh{c}"
    return f"sz{c}"


def _qq_codes() -> list[str]:
    """本地股票库全市场代码（零网络；库为空则应急层不可用，诚实返空）。"""
    try:
        from modules.fetcher import StockFetcher
        return [str(c) for c in StockFetcher().get_all_codes() if str(c).strip()]
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("[spot_rank] 本地代码库不可用: %s", e)
        return []


def _parse_qq_batch(text: str) -> pd.DataFrame:
    """腾讯批量响应 → 中文列 DataFrame。坏行跳过；成交额万→元（与东财列对齐）。"""
    rows = []

    def _tof(v: str) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    for seg in text.split(";"):
        if '="' not in seg:
            continue
        body = seg.split('="', 1)[1].rstrip('"')
        f = body.split("~")
        if len(f) < 50 or not f[2] or not f[1]:
            continue
        rows.append({
            "代码": str(f[2]).zfill(6),
            "名称": f[1],
            "最新价": _tof(f[3]),
            "涨跌幅": _tof(f[32]),
            "成交额": _tof(f[37]) * 1e4,   # 腾讯单位=万，东财列单位=元
            "换手率": _tof(f[38]),
            "量比": _tof(f[49]),
        })
    return pd.DataFrame(rows)


def _spot_from_qq() -> pd.DataFrame | None:
    """腾讯应急快照：本地代码库分批拉取合并。覆盖不足/失败/冷却中 → None。"""
    now = time.time()
    if now - _qq_state["ts"] < _QQ_TTL and _qq_state["df"] is not None:
        return _qq_state["df"].copy()
    if now < _qq_state["cool_until"]:
        return None
    codes = _qq_codes()
    if not codes:
        return None
    import logging
    logger = logging.getLogger(__name__)
    rows: list[pd.DataFrame] = []
    for i in range(0, len(codes), _QQ_BATCH):
        batch = codes[i:i + _QQ_BATCH]
        url = QQ_URL + ",".join(_qq_prefix(c) for c in batch)
        try:
            resp = _qq_get_raw(url, headers=_qq_headers(), timeout=10)
            resp.raise_for_status()
            text = resp.content.decode("gbk", errors="replace")
            df_b = _parse_qq_batch(text)
            if not df_b.empty:
                rows.append(df_b)
        except Exception as e:  # noqa: BLE001 - 单批失败不拖垮整层
            logger.debug("[spot_rank] 腾讯批 %d 失败: %s", i // _QQ_BATCH + 1, e)
    if not rows:
        _qq_state["cool_until"] = now + _QQ_COOLDOWN
        logger.warning("[spot_rank] 腾讯应急层全部批次失败，冷却 %.0fs", _QQ_COOLDOWN)
        return None
    df = pd.concat(rows, ignore_index=True).drop_duplicates(subset="代码")
    if len(df) < _QQ_MIN_ROWS:
        logger.warning("[spot_rank] 腾讯应急层仅覆盖 %d 只（<%d），不装全市场，诚实返 None",
                       len(df), _QQ_MIN_ROWS)
        return None
    _qq_state.update({"df": df, "ts": now})
    logger.info("[spot_rank] 腾讯应急快照 %d 只（%d 批）", len(df),
                (len(codes) + _QQ_BATCH - 1) // _QQ_BATCH)
    return df.copy()


def _spot_impl():
    """东财直连薄层优先（T-177）→ akshare 兜底 → 腾讯应急（T-178）。
    返回 (快照, 数据源标注)；三源全失败异常上抛，由页面诚实降级。"""
    from modules import em_snapshot as ems
    df = ems.fetch_a_spot_em()
    if df is not None and not df.empty:
        return df, "东财实时快照（直连）"
    try:
        d = _spot_cached_akshare()
        if d is not None and not d.empty:
            return d, "东财实时快照（akshare）"
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("[spot_rank] akshare 兜底失败: %s", e)
    d = _spot_from_qq()
    if d is not None and not d.empty:
        return d, "腾讯应急快照（东财接口风控期间，覆盖略小）"
    raise ConnectionError("东财直连/akshare/腾讯应急三源均不可用")


@st.cache_data(ttl=60, show_spinner=False)
def _spot_cached_with_source():
    """全市场实时快照（缓存 60s，含数据源标注）。失败抛出，由调用方诚实降级。"""
    return _spot_impl()


def load_spot_with_source():
    """返回 (快照|None, 数据源标注)。页面据此如实标注本次数据来源。

    三源全失败时返回 (None, "不可用")——不抛异常，由页面按未就绪降级。
    """
    try:
        return _spot_cached_with_source()
    except Exception:  # noqa: BLE001 - 三源全失败：诚实返回 None 交页面降级
        return None, "不可用"


def load_spot():
    """取快照并剔除非正常交易标的（ST/退市/新股）。取不到返回 None。"""
    df = load_spot_with_source()[0]
    if df is None or df.empty:
        return None
    d = df.copy()
    name_c = _col(d, "name")
    if name_c:
        mask = ~d[name_c].astype(str).str.contains("ST|退|^N|^U", case=False, regex=True, na=False)
        d = d[mask]
    return d
