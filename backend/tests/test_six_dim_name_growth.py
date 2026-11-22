# -*- coding: utf-8 -*-
"""2026-11-22 六维补缺守卫（真机取证驱动，禁回退）。

守住另一账号 4 文件修复的四项契约：
  1. parse_fin 同时兼容新旧「净利润增长率」行名（旧只认「同比」导致 growth 恒缺）；
  2. _qq_spot_single 腾讯单票字段索引 f[1]/[38]/[46]/[49]/[52] 与换源降级语义；
  3. _six_dim_spot 腾讯主源失败时回退 spot_em，全失败返 {}（不补 0）；
  4. six_dim 端点 data.name 来自数据源（腾讯 f[1]/spot_em 名称），取不到为 None，
     绝不按 code 编造名称。
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
import pytest

import backend.api.read_routes as rr
from modules.six_dim import parse_fin


# ── 1. parse_fin 新旧行名 ──────────────────────────────────────────────
def _fin_frame(growth_label: str) -> pd.DataFrame:
    return pd.DataFrame({
        "选项": ["指标", "指标"],
        "指标": ["净资产收益率(ROE)", growth_label],
        "20260930": ["24.47", "-0.246524"],
        "20251231": ["32.53", "-4.532254"],
    })


@pytest.mark.parametrize("label", [
    "归母净利润同比增长率",       # 旧行名
    "归属母公司净利润增长率",     # 2026-11-22 真机 akshare 新行名（无「同比」二字）
    "归母净利润增长率",           # 其它常见变体
])
def test_parse_fin_accepts_both_growth_labels(label):
    roe, yoy = parse_fin(_fin_frame(label))
    assert roe == pytest.approx(24.47)
    assert yoy == pytest.approx(-0.246524)


def test_parse_fin_ignores_unrelated_net_profit_rows():
    """「经营活动净现金/归属母公司的净利润」等非增长率行不得被误当 yoy。"""
    fin = pd.DataFrame({
        "选项": ["指标", "指标", "指标"],
        "指标": ["净资产收益率", "经营活动净现金/归属母公司的净利润", "净利润"],
        "20260930": ["10", "88", "99"],
    })
    roe, yoy = parse_fin(fin)
    assert roe == 10.0
    assert yoy is None


def test_parse_fin_missing_is_none_not_zero():
    assert parse_fin(None) == (None, None)
    assert parse_fin(pd.DataFrame()) == (None, None)


# ── 2. 腾讯单票字段索引 ───────────────────────────────────────────────
class _FakeResp:
    status_code = 200

    def __init__(self, text: str):
        self.content = text.encode("gbk")

    def raise_for_status(self):
        return None


def _qq_text(name="贵州茅台", turnover="0.54", pb="6.85", volratio="1.77", pe="21.61"):
    """模拟 qt.gtimg.cn 响应；索引与真机 2026-11-22 取证一致。"""
    f = [""] * 88
    f[1], f[2] = name, "600519"
    f[38], f[46], f[49], f[52] = turnover, pb, volratio, pe
    return f'v_sh600519="{ "~".join(f) }";'


def test_qq_spot_single_field_mapping(monkeypatch):
    monkeypatch.setattr(rr.time, "time", lambda: 1000.0)
    rr._qq_spot_cache.update({"key": None, "data": None, "ts": 0.0})
    monkeypatch.setattr(
        "requests.get",
        lambda url, headers=None, timeout=None: _FakeResp(_qq_text()),
    )
    row = rr._qq_spot_single("600519")
    assert row == {
        "名称": "贵州茅台",
        "换手率": 0.54,
        "市净率": 6.85,
        "量比": 1.77,
        "市盈率-动态": 21.61,
    }


def test_qq_spot_single_cache_hit(monkeypatch):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _FakeResp(_qq_text())

    clock = {"t": 1000.0}
    monkeypatch.setattr(rr.time, "time", lambda: clock["t"])
    monkeypatch.setattr("requests.get", fake_get)
    rr._qq_spot_cache.update({"key": None, "data": None, "ts": 0.0})
    rr._qq_spot_single("600519")
    clock["t"] = 1059.0  # 59s < TTL 60
    rr._qq_spot_single("600519")
    assert calls["n"] == 1
    clock["t"] = 1061.0  # 过期重拉
    rr._qq_spot_single("600519")
    assert calls["n"] == 2


def test_qq_spot_single_failure_is_empty_not_zero(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("proxy blocked")

    monkeypatch.setattr("requests.get", boom)
    rr._qq_spot_cache.update({"key": None, "data": None, "ts": 0.0})
    assert rr._qq_spot_single("600519") == {}


def test_qq_spot_single_short_payload_is_empty(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _FakeResp('v_sh600519="1~茅台~600519";'))
    rr._qq_spot_cache.update({"key": None, "data": None, "ts": 0.0})
    assert rr._qq_spot_single("600519") == {}


# ── 3. 换源降级 ────────────────────────────────────────────────────────
def test_six_dim_spot_qq_primary(monkeypatch):
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {"名称": "贵州茅台", "换手率": 0.54})
    monkeypatch.setattr(rr, "_six_dim_num", lambda v: v)
    assert rr._six_dim_spot("600519")["名称"] == "贵州茅台"


def test_six_dim_spot_falls_back_to_em_when_qq_empty(monkeypatch):
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {})

    class FakeDF:
        def __getitem__(self, key):
            return self

        @property
        def astype(self):
            return lambda _t: self

        def __eq__(self, other):
            return self

        def iloc(self):
            return self

    # 用真实 DataFrame 走 panda 分支，避免手写链式的脆弱 mock
    import akshare as ak
    df = pd.DataFrame([{"代码": "600519", "名称": "贵州茅台", "换手率": 0.54}])
    monkeypatch.setattr(ak, "stock_zh_a_spot_em", lambda: df)
    row = rr._six_dim_spot("600519")
    assert row["名称"] == "贵州茅台"


def test_six_dim_spot_all_sources_fail_empty(monkeypatch):
    monkeypatch.setattr(rr, "_qq_spot_single", lambda code: {})
    import akshare as ak

    def boom():
        raise RuntimeError("em blocked")

    monkeypatch.setattr(ak, "stock_zh_a_spot_em", boom)
    assert rr._six_dim_spot("600519") == {}


# ── 4. 端点 name 字段 ─────────────────────────────────────────────────
def _client_and_token():
    from backend.app import create_app
    from backend.extensions import db
    from backend.models import User
    from backend.auth.service import issue_token

    app = create_app()
    with app.app_context():
        u = User.query.filter_by(username="tester_sixdim_name").first()
        if u is None:
            u = User(username="tester_sixdim_name")
            u.set_password("Test@123")
            db.session.add(u)
            db.session.commit()
        token = issue_token(u)
    return app, token


def _stub_sources(monkeypatch, spot):
    hist = pd.DataFrame({"收盘": [10.0 + i for i in range(80)]})
    fin = pd.DataFrame({
        "选项": ["指标", "指标"],
        "指标": ["净资产收益率(ROE)", "归属母公司净利润增长率"],
        "20260930": ["20", "5"],
    })
    monkeypatch.setattr(rr, "_six_dim_hist", lambda code: hist)
    monkeypatch.setattr(rr, "_six_dim_spot", lambda code: spot)
    monkeypatch.setattr(rr, "_six_dim_fin", lambda code: fin)


def test_six_dim_name_from_qq(monkeypatch):
    app, token = _client_and_token()
    _stub_sources(monkeypatch, {"名称": "贵州茅台", "换手率": 0.54, "量比": 1.77,
                                "市盈率-动态": 21.61, "市净率": 6.85})
    with app.test_client() as client:
        resp = client.get("/api/v2/read/six-dim?code=600519",
                          headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["name"] == "贵州茅台"
    assert data["coverage"] == 6
    assert data["dims"]["growth"] is not None


def test_six_dim_name_null_when_source_has_none(monkeypatch):
    app, token = _client_and_token()
    _stub_sources(monkeypatch, {"换手率": 0.54, "量比": 1.77})
    with app.test_client() as client:
        resp = client.get("/api/v2/read/six-dim?code=600519",
                          headers={"Authorization": f"Bearer {token}"})
    data = resp.get_json()["data"]
    assert data["name"] is None  # 不按 code 编造「600519」当名字
