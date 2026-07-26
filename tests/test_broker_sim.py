"""
tests/test_broker_sim.py
=========================
模拟账本券商（backend.broker.sim.SimulatedBroker）纯逻辑测试。

为避免引入 SQLAlchemy / 调度器等重依赖，用轻量替身替换 RealPosition，
并通过 monkeypatch backend.models.RealPosition 让 sim.py 内部的局部 import 取到替身。
"""
import sys
import types

import pytest


# ── 轻量替身 ──────────────────────────────────────────────
class FakeRealPosition:
    def __init__(self, user_id, stock_code, quantity=0, available=0, avg_cost=0.0):
        self.user_id = user_id
        self.stock_code = stock_code
        self.quantity = quantity
        self.available = available
        self.avg_cost = avg_cost
        self.last_price = None
        self.updated_at = None


class FakeAccount:
    def __init__(self, user_id, cash=0.0):
        self.user_id = user_id
        self.cash = cash


class FakeQuery:
    def __init__(self, store):
        self._store = store
        self._kw = {}

    def filter_by(self, **kw):
        self._kw = kw
        return self

    def first(self):
        code = self._kw.get("stock_code")
        return self._store.get(code)


class FakeSession:
    def __init__(self):
        self._positions = {}
        self.added = []
        self.deleted = []

    def query(self, cls):
        return FakeQuery(self._positions)

    def add(self, obj):
        self.added.append(obj)
        self._positions[obj.stock_code] = obj

    def delete(self, obj):
        self.deleted.append(obj)
        self._positions.pop(obj.stock_code, None)


@pytest.fixture
def patched(monkeypatch):
    """把 sim.py 内部的 RealPosition 局部 import 指向替身。"""
    import backend.broker.sim as sim_mod
    import backend.models as models_mod
    monkeypatch.setattr(models_mod, "RealPosition", FakeRealPosition)
    return sim_mod


def _broker(cash=0.0, quote=None):
    import backend.broker.sim as sim_mod
    acct = FakeAccount(user_id="u1", cash=cash)
    sess = FakeSession()
    return sim_mod.SimulatedBroker(acct, sess, quote_fn=quote), acct, sess


def test_buy_success_reduces_cash():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 10.0)
    res = broker.place_order("600519", "buy", 100)  # 100 股 * 10 = 1000
    assert res.ok is True
    assert res.status == "filled"
    assert acct.cash == pytest.approx(99000.0)
    assert len(sess.added) == 1
    assert sess.added[0].quantity == 100
    assert sess.added[0].avg_cost == pytest.approx(10.0)


def test_buy_with_explicit_price_uses_price():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 99.0)
    res = broker.place_order("600519", "buy", 100, price=12.5)
    assert res.ok is True
    assert res.price == pytest.approx(12.5)
    assert acct.cash == pytest.approx(100000.0 - 1250.0)


def test_buy_insufficient_funds_with_none_cash_does_not_crash():
    """回归：cash 为 None（全新/迁移账户未初始化余额）时，拒绝分支不应
    因 f-string 格式化 None 触发 TypeError。"""
    broker, acct, sess = _broker(cash=None, quote=lambda c: 10.0)
    res = broker.place_order("600519", "buy", 100)
    assert res.ok is False
    assert res.status == "rejected"
    assert "可用资金不足" in res.message
    assert acct.cash is None  # 不应被错误改写


def test_buy_insufficient_funds_message():
    broker, acct, sess = _broker(cash=500.0, quote=lambda c: 10.0)
    res = broker.place_order("600519", "buy", 100)  # 需 1000
    assert res.ok is False
    assert "可用资金不足" in res.message
    assert acct.cash == pytest.approx(500.0)  # 未扣款


def test_invalid_quantity_rejected():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 10.0)
    res = broker.place_order("600519", "buy", 150)  # 非 100 整数倍
    assert res.ok is False
    assert res.status == "rejected"
    assert "100" in res.message


def test_sell_without_position_rejected():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 10.0)
    res = broker.place_order("600519", "sell", 100)
    assert res.ok is False
    assert "可卖数量不足" in res.message


def test_sell_success_updates_cash_and_removes_position_when_empty():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 10.0)
    broker.place_order("600519", "buy", 200)
    res = broker.place_order("600519", "sell", 200)
    assert res.ok is True
    assert acct.cash == pytest.approx(100000.0)  # 买 2000 + 卖回 2000
    assert "600519" not in sess._positions  # 清仓后删除持仓记录


def test_unknown_side_rejected():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 10.0)
    res = broker.place_order("600519", "hold", 100)
    assert res.ok is False
    assert "未知方向" in res.message


def test_no_price_and_no_quote_fails_cleanly():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: None)
    res = broker.place_order("600519", "buy", 100)
    assert res.ok is False
    assert res.status == "failed"
    assert "最新价" in res.message


def test_avg_cost_after_two_buys():
    broker, acct, sess = _broker(cash=100000.0, quote=lambda c: 10.0)
    broker.place_order("600519", "buy", 100)  # 成本 10
    broker.place_order("600519", "buy", 100)  # 再买 100 @10
    pos = sess._positions["600519"]
    assert pos.quantity == 200
    assert pos.avg_cost == pytest.approx(10.0)
