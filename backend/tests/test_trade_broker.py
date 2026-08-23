"""
backend/tests/test_trade_broker.py
----------------------------------
实盘交易闭环测试（P1 补测试覆盖，之前为零测试）：

  1) SimulatedBroker 模拟撮合：买入建仓/卖出平仓/资金不足拒绝/数量非100倍数拒绝
  2) risk_check 风控：交易时段（盘内/盘外）、单笔金额上限、当日亏损停手线
  3) get_broker 工厂：sim 分支默认返回 SimulatedBroker；live 分支依赖缺失抛 BrokerUnavailable
  4) execute_order 统一入口：sim 模式落 RealOrder 流水 + 风控拦截落 rejected
  5) conditional_engine.evaluate_order：ma5_break_up / ma5_break_down / margin_stock 触发判定
  6) scan_and_execute：条件单触发后经 broker 落单（sim）

隔离：每个用例独立临时 SQLite；行情源用 monkeypatch 替换，绝不触网。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from flask import Flask

from backend.app import create_app
from backend.extensions import db
from backend.config import Config
from backend.models import User, RealAccount, RealOrder, RealPosition, ConditionalOrder
from backend.broker import (
    SimulatedBroker, get_broker, risk_check, execute_order,
    BrokerUnavailable, in_trading_window,
)
from backend.broker.base import OrderResult
from backend.conditional_engine import evaluate_order, scan_and_execute


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'trade.db'}"
        TESTING = True
        SECRET_KEY = "test"
        JWT_SECRET_KEY = "test"
    app = create_app(_TestConfig)
    with app.app_context():
        db.create_all()
        u = User(username="trader", role="user")
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        uid = u.id
    app.config["_uid"] = uid
    yield app
    with app.app_context():
        db.drop_all()


def _quote(px):
    return lambda code: px


# ================================================================== 1) 模拟撮合
def test_sim_buy_and_sell(app):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], cash=100000.0)
        db.session.add(acc)
        db.session.commit()
        br = SimulatedBroker(acc, db.session, quote_fn=_quote(10.0))
        r = br.place_order("600900", "buy", 100)
        assert r.ok and r.status == "filled"
        assert acc.cash == 100000.0 - 100 * 10.0
        pos = RealPosition.query.filter_by(user_id=acc.user_id, stock_code="600900").first()
        assert pos and pos.quantity == 100 and pos.avg_cost == 10.0
        # 卖出
        r2 = br.place_order("600900", "sell", 100)
        assert r2.ok and r2.status == "filled"
        assert acc.cash == 100000.0


def test_sim_insufficient_cash(app):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], cash=500.0)
        db.session.add(acc)
        db.session.commit()
        br = SimulatedBroker(acc, db.session, quote_fn=_quote(10.0))
        r = br.place_order("600900", "buy", 100)  # 需 1000 元
        assert not r.ok and r.status == "rejected"
        assert "资金不足" in r.message


def test_sim_qty_must_be_100(app):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], cash=100000.0)
        db.session.add(acc)
        db.session.commit()
        br = SimulatedBroker(acc, db.session, quote_fn=_quote(10.0))
        r = br.place_order("600900", "buy", 150)  # 非 100 倍数
        assert not r.ok and r.status == "rejected"


def test_sim_no_quote_fails(app):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], cash=100000.0)
        db.session.add(acc)
        db.session.commit()
        br = SimulatedBroker(acc, db.session, quote_fn=lambda code: None)
        r = br.place_order("600900", "buy", 100)
        assert not r.ok and r.status == "failed"


# ================================================================== 2) 风控
def test_risk_check_outside_trading_window(app, monkeypatch):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"])
        db.session.add(acc)
        db.session.commit()
        # 周日 00:00 盘外
        now = datetime(2026, 8, 23, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("backend.broker._now_bj", lambda: now)
        assert not in_trading_window(now)
        reason = risk_check(acc, db.session, "600900", "buy", 100, 10.0)
        assert reason and "交易时段" in reason


def test_risk_check_inside_window_passes(app, monkeypatch):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"])
        db.session.add(acc)
        db.session.commit()
        # 周三 10:00 盘内
        now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("backend.broker._now_bj", lambda: now)
        assert in_trading_window(now)
        reason = risk_check(acc, db.session, "600900", "buy", 100, 10.0)
        assert reason is None


def test_risk_check_amount_limit(app, monkeypatch):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], max_order_amount=1000.0)
        db.session.add(acc)
        db.session.commit()
        now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("backend.broker._now_bj", lambda: now)
        # 100 股 * 50 元 = 5000 > 1000 上限
        reason = risk_check(acc, db.session, "600900", "buy", 100, 50.0)
        assert reason and "上限" in reason


def test_risk_check_daily_loss_pause(app, monkeypatch):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], risk_paused_date="2026-08-26")
        db.session.add(acc)
        db.session.commit()
        now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("backend.broker._now_bj", lambda: now)
        reason = risk_check(acc, db.session, "600900", "buy", 100, 10.0)
        assert reason and "停手" in reason


# ================================================================== 3) 工厂
def test_get_broker_sim_default(app):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"])  # live_mode=False
        db.session.add(acc)
        db.session.commit()
        br = get_broker(acc, db.session)
        assert isinstance(br, SimulatedBroker)
        assert not br.is_live


def test_get_broker_live_unavailable(app, monkeypatch):
    with app.app_context():
        acc = RealAccount(user_id=app.config["_uid"], broker_type="qmt", live_mode=True,
                          broker_config='{"qmt_path":"/x","account_id":"123"}')
        db.session.add(acc)
        db.session.commit()
        # xtquant 在测试环境不存在 → 应抛 BrokerUnavailable
        with pytest.raises(BrokerUnavailable):
            get_broker(acc, db.session)


# ================================================================== 4) execute_order 统一入口
def test_execute_order_sim_filled_and_audit(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr("backend.broker._server_quote", _quote(10.0))
        monkeypatch.setattr("backend.broker._now_bj",
                            lambda: datetime(2026, 8, 26, 10, 0, tzinfo=timezone(timedelta(hours=8))))
        acc = RealAccount(user_id=app.config["_uid"], cash=100000.0)
        db.session.add(acc)
        db.session.commit()
        order, result = execute_order(acc, db.session, code="600900", name="长电科技",
                                      side="buy", quantity=100, price=10.0, source="manual")
        db.session.commit()
        assert result.ok and order.status == "filled"
        assert order.amount == 1000.0
        assert RealOrder.query.filter_by(user_id=acc.user_id).count() == 1


def test_execute_order_risk_rejected_audited(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr("backend.broker._server_quote", _quote(10.0))
        monkeypatch.setattr("backend.broker._now_bj",
                            lambda: datetime(2026, 8, 26, 10, 0, tzinfo=timezone(timedelta(hours=8))))
        acc = RealAccount(user_id=app.config["_uid"], cash=100000.0,
                          max_order_amount=500.0)  # 100*10=1000 > 500
        db.session.add(acc)
        db.session.commit()
        order, result = execute_order(acc, db.session, code="600900", name="",
                                      side="buy", quantity=100, price=10.0)
        db.session.commit()
        assert not result.ok and order.status == "rejected"
        # 风控拒绝也落流水（可审计）
        assert RealOrder.query.filter_by(user_id=acc.user_id).count() == 1


# ================================================================== 5) 条件单评估
def test_cond_ma5_break_up_triggers(app, monkeypatch):
    co = ConditionalOrder(user_id=app.config["_uid"], stock_code="600900",
                          trigger_type="ma5_break_up", action="buy", quantity=100)
    # 构造：昨收<=昨MA5，现价>今MA5
    closes = [9.0, 9.1, 9.0, 9.2, 8.9]  # 末值8.9<MA5(9.04)，满足昨收<=昨MA5
    monkeypatch.setattr("backend.conditional_engine._recent_closes", lambda code, n=10: closes)
    monkeypatch.setattr("backend.conditional_engine._latest_price", lambda code: 9.5)  # 现价突破
    hit, info = evaluate_order(co)
    assert hit, info


def test_cond_ma5_break_down_triggers(app, monkeypatch):
    co = ConditionalOrder(user_id=app.config["_uid"], stock_code="600900",
                          trigger_type="ma5_break_down", action="sell", quantity=100)
    closes = [10.0, 10.1, 10.0, 10.2, 10.1]  # MA5≈10.08
    monkeypatch.setattr("backend.conditional_engine._recent_closes", lambda code, n=10: closes)
    monkeypatch.setattr("backend.conditional_engine._latest_price", lambda code: 9.5)  # 跌破
    hit, info = evaluate_order(co)
    assert hit, info


def test_cond_margin_stock(app, monkeypatch):
    co = ConditionalOrder(user_id=app.config["_uid"], stock_code="600900",
                          trigger_type="margin_stock", action="buy", quantity=100,
                          trigger_params='{"threshold": 1000}')
    monkeypatch.setattr("modules.margin_trading.get_stock_margin_buy",
                        lambda code: {"date": "2026-08-25", "rzmr": 2_000_000})  # 200万元 < 1000万
    hit, info = evaluate_order(co)
    assert not hit  # 200万 < 1000万阈值
    monkeypatch.setattr("modules.margin_trading.get_stock_margin_buy",
                        lambda code: {"date": "2026-08-25", "rzmr": 20_000_000})  # 2000万 >= 1000万
    hit2, _ = evaluate_order(co)
    assert hit2


# ================================================================== 6) 扫描执行落单
def test_scan_and_execute_fills_conditional(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr("backend.conditional_engine._recent_closes",
                            lambda code, n=10: [9.0, 9.1, 9.0, 9.2, 8.9])
        monkeypatch.setattr("backend.conditional_engine._latest_price", lambda code: 9.5)
        monkeypatch.setattr("backend.broker._server_quote", _quote(9.5))
        monkeypatch.setattr("backend.broker._now_bj",
                            lambda: datetime(2026, 8, 26, 10, 0, tzinfo=timezone(timedelta(hours=8))))
        co = ConditionalOrder(user_id=app.config["_uid"], stock_code="600900",
                              stock_name="长电科技", trigger_type="ma5_break_up",
                              action="buy", quantity=100, status="pending", active=True)
        db.session.add(co)
        acc = RealAccount(user_id=app.config["_uid"], cash=100000.0)
        db.session.add(acc)
        db.session.commit()

        stats = scan_and_execute(app)
        assert stats["checked"] >= 1
        assert stats["triggered"] >= 1
        assert stats["filled"] >= 1
        # 模拟账本应已建仓
        pos = RealPosition.query.filter_by(user_id=acc.user_id, stock_code="600900").first()
        assert pos and pos.quantity == 100
