"""
模块 event_compare：事件信号 × 市场广度 对照分析（方案②）

数据边界（诚实声明）：
  · 本地事件因子池 data/event_pool_brief.json 是 P1-QuantFactor EV 模型的
    「个股级信号快照」（含 symbol / signal 看多·看空 / score），**没有历史事件日期**，
    也**没有逐股后续涨跌**。
  · 因此本模块只做「信号极性 × 当日市场广度」的截面对照（congruence），
    不做「事件→股价因果回测」——后者需要逐股历史价格，离线基座无此数据。
  · 个股信号强弱（score）与市场广度（红盘率/涨跌家数/涨跌停）并置，
    用于直观判断「信号与广度是否同向 / 是否逆向抄底」。

所有取数失败均优雅降级（available=False），绝不编造。
"""
import logging

from modules import shepherd_ladder
from modules import shepherd

logger = logging.getLogger(__name__)


def load_event_pool(path: str | None = None) -> dict:
    """读本地事件因子池（P1 EV 信号离线快照）。

    直接复用 shepherd_ladder.load_event_pool，保证与 F4 同源、同降级语义。
    返回：{available, date, pool(list), stale, live, note, source}
    """
    return shepherd_ladder.load_event_pool(path)


def current_breadth(days: int = 250) -> dict:
    """取最新牧羊人广度快照（默认近 250 日窗口末行）。

    返回：{available, date, red_ratio, up_count, down_count, limit_up, limit_down, note}
    取数失败 / 无数据 → available=False，各字段为 None。
    """
    try:
        df, meta = shepherd.get_shepherd_indicators(days=days)
    except Exception as exc:  # pragma: no cover - 防御性
        logger.warning("breadth load failed: %s", exc)
        return dict(available=False, date=None, red_ratio=None, up_count=None,
                    down_count=None, limit_up=None, limit_down=None, note=str(exc))
    if df is None or len(df) == 0:
        return dict(available=False, date=None, red_ratio=None, up_count=None,
                    down_count=None, limit_up=None, limit_down=None,
                    note="无广度历史数据")
    row = df.iloc[-1]
    return dict(
        available=True,
        date=str(row.get("date")),
        red_ratio=_num(row.get("red_ratio")),
        up_count=_num(row.get("up_count")),
        down_count=_num(row.get("down_count")),
        limit_up=_num(row.get("limit_up")),
        limit_down=_num(row.get("limit_down")),
        note="",
    )


def _num(v):
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f  # NaN → None
    except (TypeError, ValueError):
        return None


def _avg_score(items):
    vals = [float(s["score"]) for s in items if s.get("score") is not None]
    return (sum(vals) / len(vals)) if vals else None


def signal_breadth_compare(pool_result: dict | None = None,
                           breadth: dict | None = None) -> dict:
    """核心对照：信号极性 vs 当日市场广度。

    输出结构化结论，供页面直接渲染。所有字段在计算失败时为 None，页面负责兜底。
    """
    pool_result = pool_result if pool_result is not None else load_event_pool()
    breadth = breadth if breadth is not None else current_breadth()

    pool = pool_result.get("pool") or []
    bull = [s for s in pool if str(s.get("signal", "")).strip() == "看多"]
    bear = [s for s in pool if str(s.get("signal", "")).strip() == "看空"]
    n, nb, nbe = len(pool), len(bull), len(bear)
    bull_pct = (nb / n * 100.0) if n else None
    rr = breadth.get("red_ratio")

    # 同向 / 逆向判定（诚实、可解释）
    if rr is None or bull_pct is None:
        alignment = "未知（数据不足）"
        alignment_kind = "unknown"
    elif rr >= 50 and (bull_pct or 0) >= 50:
        alignment = "同向·动量共振（广度扩张 + 看多信号占优）"
        alignment_kind = "momentum"
    elif rr < 40 and (bull_pct or 0) >= 50:
        alignment = "逆向·信号抄底（广度偏冷但看多信号占优）"
        alignment_kind = "contrarian"
    elif rr >= 50 and (bull_pct or 0) < 50:
        alignment = "背离·广度偏热但看空信号占优"
        alignment_kind = "diverge_hot"
    else:
        alignment = "同向·谨慎（广度偏冷 + 看空信号占优）"
        alignment_kind = "cautious"

    return dict(
        n=n, bull=nb, bear=nbe, bull_pct=bull_pct,
        bull_score_avg=_avg_score(bull), bear_score_avg=_avg_score(bear),
        red_ratio=rr,
        alignment=alignment, alignment_kind=alignment_kind,
        pool_date=pool_result.get("date"),
        breadth_date=breadth.get("date"),
        pool_available=bool(pool_result.get("available", False)),
        breadth_available=bool(breadth.get("available", False)),
        pool_note=pool_result.get("note", ""),
        breadth_note=breadth.get("note", ""),
        pool_stale=bool(pool_result.get("stale", False)),
        pool_live=bool(pool_result.get("live", False)),
    )


def build_compare_rows(pool_result: dict | None = None,
                       breadth: dict | None = None) -> list:
    """生成信号-广度对照表行（按 score 降序）。

    每行：rank / symbol / signal / score / 当日红盘率(市场上下文)。
    信号本身无逐股历史价格，故「市场上下文」统一取当日全市场红盘率作为参照。
    """
    pool_result = pool_result if pool_result is not None else load_event_pool()
    breadth = breadth if breadth is not None else current_breadth()
    rr = breadth.get("red_ratio")
    pool = pool_result.get("pool") or []
    rows = []
    for s in sorted(pool, key=lambda x: float(x.get("score") or 0), reverse=True):
        rows.append(dict(
            rank=s.get("rank"),
            symbol=s.get("symbol"),
            signal=s.get("signal"),
            score=s.get("score"),
            source=s.get("source"),
            market_red_ratio=rr,
        ))
    return rows
