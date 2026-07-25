"""
backend/conditional_engine.py
-----------------------------
智能条件单评估引擎 + 后台调度器（镜像 market_alert_engine 范式）。

触发类型：
- margin_stock   单只股票最近披露日融资买入额 ≥ 阈值（万元）
- margin_market  全市场（沪+深）融资买入额合计 ≥ 阈值（亿元）
- ma5_break_up   现价上穿 5 日均线（沿 MA5 上涨突破）
- ma5_break_down 现价跌破 5 日均线（沿 MA5 下跌破位）

安全：
- 触发后经 backend.broker.execute_order 统一下单（含风控 + live 护栏）；
- 调度器为守护线程，pytest / TESTING / STOCKSIGNAL_ENABLE_COND_SCHEDULER=0 时跳过；
- 仅在 A 股交易时段扫描。
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

# 确保项目根在 sys.path（复用 modules/*）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("stocksignal.conditional")

SCAN_INTERVAL_MINUTES = 3
_SCHEDULER_STARTED = False
_SCHEDULER_LOCK = threading.Lock()


# ================================================================== 评估函数
def _latest_price(code: str):
    try:
        from .api.market_routes import get_fetcher
        q = get_fetcher().get_realtime_quote(code)
        if q and q.get("current"):
            px = float(q["current"])
            return px if px > 0 else None
    except Exception:
        pass
    return None


def _recent_closes(code: str, n: int = 10):
    """取最近 n 个交易日收盘价列表（旧→新）。失败返回 None。"""
    try:
        from .api.market_routes import get_fetcher
        start = (datetime.now() - timedelta(days=n * 3 + 20)).strftime("%Y-%m-%d")
        df = get_fetcher().get_kline(code, start, None, "daily", "qfq")
        if df is None or len(df) == 0:
            return None
        close_col = next((c for c in df.columns if str(c).lower() in ("close", "收盘", "收盘价")), None)
        if close_col is None:
            return None
        closes = [float(x) for x in df[close_col].tolist() if x is not None]
        return closes[-n:] if len(closes) >= 5 else None
    except Exception:
        return None


def eval_margin_stock(order) -> tuple[bool, str]:
    """单只股票融资买入额 ≥ 阈值（万元）。"""
    from modules.margin_trading import get_stock_margin_buy
    params = order.params_dict()
    threshold_wan = float(params.get("threshold") or 0)
    if threshold_wan <= 0:
        return False, "阈值未配置"
    info = get_stock_margin_buy(order.stock_code)
    if not info:
        return False, "暂无该股融资明细数据（可能非两融标的或数据未披露）"
    rzmr_wan = info["rzmr"] / 1e4
    if rzmr_wan >= threshold_wan:
        return True, f"{info['date']} 融资买入额 {rzmr_wan:,.0f} 万元 ≥ 阈值 {threshold_wan:,.0f} 万元"
    return False, f"{info['date']} 融资买入额 {rzmr_wan:,.0f} 万元 < 阈值 {threshold_wan:,.0f} 万元"


def eval_margin_market(order) -> tuple[bool, str]:
    """全市场融资买入额合计 ≥ 阈值（亿元）。"""
    from modules.margin_trading import get_latest_margin_summary
    params = order.params_dict()
    threshold_yi = float(params.get("threshold") or 0)
    if threshold_yi <= 0:
        return False, "阈值未配置"
    summary = get_latest_margin_summary() or {}
    total_yi = summary.get("total_rzmr_yi")
    if total_yi is None:
        return False, "暂无全市场融资数据"
    if float(total_yi) >= threshold_yi:
        return True, f"{summary.get('date')} 全市场融资买入额 {float(total_yi):,.1f} 亿元 ≥ 阈值 {threshold_yi:,.1f} 亿元"
    return False, f"全市场融资买入额 {float(total_yi):,.1f} 亿元 < 阈值 {threshold_yi:,.1f} 亿元"


def eval_ma5_break(order, direction: str) -> tuple[bool, str]:
    """MA5 突破/破位。

    direction=up：昨收 ≤ 昨日MA5 且 现价 > 今日MA5*(1+confirm%)
    direction=down：昨收 ≥ 昨日MA5 且 现价 < 今日MA5*(1-confirm%)
    今日 MA5 用「最近 4 个收盘 + 现价」滚动估算。
    """
    params = order.params_dict()
    confirm_pct = float(params.get("confirm_pct") or 0) / 100.0
    closes = _recent_closes(order.stock_code, n=10)
    if not closes or len(closes) < 5:
        return False, "K 线数据不足（需至少 5 个交易日）"
    px = _latest_price(order.stock_code) or closes[-1]

    prev_close = closes[-1]                       # 昨收
    prev_ma5 = sum(closes[-5:]) / 5.0             # 昨日 MA5
    ma5_now = (sum(closes[-4:]) + px) / 5.0       # 今日滚动 MA5

    if direction == "up":
        was_below = prev_close <= prev_ma5 * 1.001
        is_above = px > ma5_now * (1 + confirm_pct)
        if was_below and is_above:
            return True, f"现价 {px:.2f} 上穿 MA5 {ma5_now:.2f}（昨收 {prev_close:.2f} ≤ 昨MA5 {prev_ma5:.2f}）"
        return False, f"未上穿：现价 {px:.2f} / MA5 {ma5_now:.2f}"
    else:
        was_above = prev_close >= prev_ma5 * 0.999
        is_below = px < ma5_now * (1 - confirm_pct)
        if was_above and is_below:
            return True, f"现价 {px:.2f} 跌破 MA5 {ma5_now:.2f}（昨收 {prev_close:.2f} ≥ 昨MA5 {prev_ma5:.2f}）"
        return False, f"未跌破：现价 {px:.2f} / MA5 {ma5_now:.2f}"


_EVALUATORS = {
    "margin_stock": eval_margin_stock,
    "margin_market": eval_margin_market,
    "ma5_break_up": lambda o: eval_ma5_break(o, "up"),
    "ma5_break_down": lambda o: eval_ma5_break(o, "down"),
}

TRIGGER_TYPES = tuple(_EVALUATORS.keys())


def evaluate_order(order) -> tuple[bool, str]:
    """评估单个条件单。返回 (是否触发, 说明)。异常不上抛。"""
    fn = _EVALUATORS.get(order.trigger_type)
    if fn is None:
        return False, f"未知触发类型 {order.trigger_type}"
    try:
        return fn(order)
    except Exception as e:
        logger.warning("条件单 #%s 评估异常: %s", order.id, e)
        return False, f"评估异常：{e}"


# ================================================================== 扫描 + 执行
def scan_and_execute(app) -> dict:
    """扫描全部待触发条件单；触发者经 broker 统一下单。返回统计 dict。"""
    from .extensions import db
    from .models import ConditionalOrder, RealAccount
    from .broker import execute_order

    stats = {"checked": 0, "triggered": 0, "filled": 0, "failed": 0, "expired": 0}
    today = datetime.now().strftime("%Y-%m-%d")

    with app.app_context():
        orders = (ConditionalOrder.query
                  .filter_by(status="pending", active=True)
                  .all())
        for co in orders:
            stats["checked"] += 1
            # 到期失效
            if co.expire_date and co.expire_date < today:
                co.status = "expired"
                co.active = False
                stats["expired"] += 1
                db.session.commit()
                continue

            hit, info = evaluate_order(co)
            co.last_checked_at = datetime.utcnow()
            if not hit:
                db.session.commit()
                continue

            # 触发 → 下单
            co.status = "triggered"
            co.triggered_at = datetime.utcnow()
            co.triggered_info = (info or "")[:250]
            stats["triggered"] += 1

            account = RealAccount.query.filter_by(user_id=co.user_id).first()
            if account is None:
                account = RealAccount(user_id=co.user_id)
                db.session.add(account)
                db.session.flush()

            try:
                _order, result = execute_order(
                    account, db.session,
                    code=co.stock_code, name=co.stock_name,
                    side=co.action, quantity=co.quantity, price=None,
                    source="conditional", cond_order_id=co.id)
                if result.ok:
                    co.status = "filled" if result.status == "filled" else "triggered"
                    stats["filled"] += 1
                else:
                    co.status = "failed"
                    co.triggered_info = f"{co.triggered_info}｜下单失败：{result.message}"[:250]
                    stats["failed"] += 1
                co.active = False
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.exception("条件单 #%s 执行异常", co.id)
                try:
                    co.status = "failed"
                    co.active = False
                    co.triggered_info = f"执行异常：{e}"[:250]
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                stats["failed"] += 1
    return stats


# ================================================================== 调度器
def start_conditional_scheduler(app, interval_minutes: int = SCAN_INTERVAL_MINUTES) -> None:
    """启动条件单守护线程调度器（幂等）。"""
    global _SCHEDULER_STARTED
    if os.environ.get("PYTEST_CURRENT_TEST") or app.config.get("TESTING"):
        return
    if os.environ.get("STOCKSIGNAL_ENABLE_COND_SCHEDULER", "1") == "0":
        logger.info("STOCKSIGNAL_ENABLE_COND_SCHEDULER=0，跳过条件单调度器")
        return
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        _SCHEDULER_STARTED = True

    def _loop():
        from .broker import in_trading_window
        logger.info("条件单调度器启动，间隔 %s 分钟", interval_minutes)
        while True:
            try:
                if in_trading_window():
                    stats = scan_and_execute(app)
                    if stats["checked"]:
                        logger.info("条件单扫描: %s", stats)
            except Exception:
                logger.exception("条件单调度循环异常")
            time.sleep(max(60, interval_minutes * 60))

    threading.Thread(target=_loop, name="conditional-scheduler", daemon=True).start()
