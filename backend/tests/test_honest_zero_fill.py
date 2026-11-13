"""backend/tests/test_honest_zero_fill.py — 诚实红线回归：缺失/无报价不得伪装成 0。

1) RealPosition.to_dict：从未刷到报价（last_price 默认 0.0 / None）→ 输出 null，
   绝不序列化出 ¥0.000 / 市值 0 / 盈亏 0；有报价时正常计算。
2) modules.macro_data._parse_usdcny：数据日期必须用源自带日期，禁止用机器当前
   日期冒充；无日期列时返回 None（前端 MacroData.tsx 显示「—」）。
"""
from __future__ import annotations

import os
import sys

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
from backend.models import User, RealPosition


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'honest.db'}"
        TESTING = True
        SECRET_KEY = "test"
        JWT_SECRET_KEY = "test"

    app = create_app(_TestConfig)
    with app.app_context():
        db.create_all()
        u = User(username="honest", role="user")
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        uid = u.id
    app.config["_uid"] = uid
    yield app
    with app.app_context():
        db.drop_all()


def test_realposition_unpriced_emits_null(app):
    """从未刷到报价：last_price 默认 0.0 → 绝不伪装成 ¥0.000。"""
    with app.app_context():
        pos = RealPosition(
            user_id=app.config["_uid"], stock_code="600519", stock_name="贵州茅台",
            quantity=100, available=100, avg_cost=10.0, last_price=0.0,
        )
        db.session.add(pos)
        db.session.commit()
        d = pos.to_dict()
    assert d["last_price"] is None
    assert d["market_value"] is None
    assert d["pnl"] is None
    assert d["pnl_pct"] is None
    assert d["quantity"] == 100      # 持仓数量仍如实返回
    assert d["avg_cost"] == 10.0     # 成本仍如实返回


def test_realposition_unpriced_explicit_none_emits_null(app):
    """last_price 显式 None → 同样视为无报价，输出 null。"""
    with app.app_context():
        pos = RealPosition(
            user_id=app.config["_uid"], stock_code="000001", quantity=0,
            avg_cost=0.0, last_price=None,
        )
        db.session.add(pos)
        db.session.commit()
        d = pos.to_dict()
    assert d["last_price"] is None
    assert d["market_value"] is None


def test_realposition_priced_computes_normally(app):
    """有报价时正常计算市值/盈亏，不被 null 逻辑误伤。"""
    with app.app_context():
        pos = RealPosition(
            user_id=app.config["_uid"], stock_code="600900", quantity=100,
            available=100, avg_cost=1000.0, last_price=1500.0,
        )
        db.session.add(pos)
        db.session.commit()
        d = pos.to_dict()
    assert d["last_price"] == 1500.0
    assert d["market_value"] == 150000.0
    assert d["pnl"] == 50000.0
    assert d["pnl_pct"] == 50.0


def test_macro_usdcny_no_date_col_returns_none():
    """fx_pair_quote 宽表无日期列 → date 为 None，绝不返回机器今天。"""
    import pandas as pd
    from modules.macro_data import _parse_usdcny

    df = pd.DataFrame([{"货币对": "USDCNY", "买报价": "7.1234"}])
    out = _parse_usdcny(df)
    assert out is not None
    assert out["value"] == 7.1234
    assert out["date"] is None


def test_macro_usdcny_uses_source_date():
    """源宽表自带日期列 → 用源日期，而非机器当前日期。"""
    import pandas as pd
    from modules.macro_data import _parse_usdcny

    df = pd.DataFrame([{"货币对": "USDCNY", "买报价": "7.1234", "日期": "2026-09-21"}])
    out = _parse_usdcny(df)
    assert out is not None
    assert out["date"] == "2026-09-21"
