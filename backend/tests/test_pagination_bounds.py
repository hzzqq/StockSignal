"""
backend/tests/test_pagination_bounds.py
---------------------------------------
分页条数下界回归测试（c43 修复的真实缺陷）。

【缺陷本体】
  分页参数原先只钳上界不钳下界：

      limit = min(int(request.args.get("limit", 50)), 200)     # forum / market-alerts
      per_page = parse_int_param("per_page", default=50, hi=200)  # admin（无 lo）

  SQLite（本项目 DB）对 `LIMIT` 取负值的语义是「**不限制行数**」：

      sqlite> select * from t limit -1;   -- 返回全表

  因此 `?limit=-1` / `?per_page=-1` 会让 SQLAlchemy 生成 `LIMIT -1`，
  **200 条上限被完全绕过**：
    - /api/admin/users?per_page=-1   → 整张用户表一次性返回
    - /api/forum/posts?limit=-1      → 整个帖子表返回
    - /api/market-alerts?limit=-1    → 整个告警表返回
  既是数据过度暴露，也是「单请求打满内存/带宽」的 DoS 面。

【修复】
  新增 utils/params.parse_limit_param（lo 恒为 1）与 parse_page_param（lo=1），
  所有分页条数解析统一走它。

本文件三层护栏：
  1. 纯函数层：parse_limit_param 对负数 / 0 / 超上限 / 非数字的钳制。
  2. 行为层  ：种 260 条数据后用 ?limit=-1 打真实接口，断言 ≤ 200（旧实现必失败）。
  3. 源码层  ：防回退——路由里不得再出现「只钳上界」的裸写法。
"""
from __future__ import annotations

import os
import re
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest                                          # noqa: E402

from backend.app import create_app                     # noqa: E402
from backend.config import Config                      # noqa: E402
from backend.extensions import db                      # noqa: E402
from backend.models import User, ForumPost, MarketAlert  # noqa: E402
from backend.utils.params import (                     # noqa: E402
    parse_int_param,
    parse_limit_param,
    parse_page_param,
)

API_DIR = os.path.join(BACKEND_DIR, "api")
SEED_N = 260          # > 200，才能验证上限是否真的生效
HARD_CAP = 200


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'p.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        for uname, role in (("admin", "admin"), ("demo", "user")):
            if User.query.filter_by(username=uname).first() is None:
                u = User(username=uname, role=role)
                u.set_password("Pass@123")
                db.session.add(u)
        db.session.commit()

        uid = User.query.filter_by(username="demo").first().id
        db.session.add_all([
            ForumPost(user_id=uid, username="demo", title=f"帖子{i}",
                      content="x", stock_code="600519")
            for i in range(SEED_N)
        ])
        db.session.add_all([
            MarketAlert(metric_key="adl", metric_name="腾落线",
                        severity="info", message=f"告警{i}")
            for i in range(SEED_N)
        ])
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _token(client, username="demo"):
    r = client.post("/api/auth/login",
                    json={"username": username, "password": "Pass@123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.get_json()["data"]["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _items(resp):
    """统一取列表体：data 可能是 list，也可能是 {'items': [...]}。"""
    obj = resp.get_json(force=True)
    data = obj.get("data")
    if isinstance(data, dict):
        for key in ("items", "list", "alerts", "posts"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    return data if isinstance(data, list) else []


# ============================================================ 1. 纯函数层
class TestParseLimitParam:

    @pytest.mark.parametrize("raw", ["-1", "-999", "0", -1, 0])
    def test_non_positive_clamped_to_one(self, raw):
        """负数 / 0 一律钳到 1，绝不能透传出 <=0 的值（否则 SQL LIMIT 失效）。"""
        got = parse_limit_param("limit", default=50, hi=200, source={"limit": raw})
        assert got == 1, f"limit={raw!r} 未被钳制，得到 {got}"

    def test_above_hi_clamped(self):
        assert parse_limit_param("limit", default=50, hi=200,
                                 source={"limit": "10000"}) == 200

    def test_normal_value_kept(self):
        assert parse_limit_param("limit", default=50, hi=200,
                                 source={"limit": "77"}) == 77

    @pytest.mark.parametrize("raw", ["abc", "", None, "1;drop"])
    def test_garbage_falls_back_to_default(self, raw):
        assert parse_limit_param("limit", default=50, hi=200,
                                 source={"limit": raw}) == 50

    def test_missing_key_uses_default(self):
        assert parse_limit_param("limit", default=15, hi=50, source={}) == 15

    @pytest.mark.parametrize("raw,expect", [("-3", 1), ("0", 1), ("2", 2), ("abc", 1)])
    def test_page_param_lower_bound(self, raw, expect):
        """页码同样恒 >=1，避免 offset 变负。"""
        assert parse_page_param("page", default=1, source={"page": raw}) == expect

    def test_offset_still_clamped_at_zero(self):
        assert parse_int_param("offset", default=0, lo=0,
                               source={"offset": "-50"}) == 0


# ============================================================ 2. 行为层
class TestPaginationCapEnforced:
    """旧实现下这些用例会返回 260 条（全表），修复后恒 <= 200。"""

    def test_forum_negative_limit_cannot_bypass_cap(self, client):
        t = _token(client)
        r = client.get("/api/forum/posts?limit=-1", headers=_hdr(t))
        assert r.status_code == 200, r.text[:200]
        n = len(_items(r))
        assert n <= HARD_CAP, f"limit=-1 绕过上限，返回 {n} 条（种子 {SEED_N} 条）"

    def test_forum_zero_limit_returns_bounded(self, client):
        t = _token(client)
        r = client.get("/api/forum/posts?limit=0", headers=_hdr(t))
        assert r.status_code == 200
        n = len(_items(r))
        assert 0 < n <= HARD_CAP, f"limit=0 返回 {n} 条，应被钳为 1"

    def test_forum_huge_limit_capped(self, client):
        t = _token(client)
        r = client.get("/api/forum/posts?limit=99999", headers=_hdr(t))
        assert len(_items(r)) <= HARD_CAP

    def test_forum_normal_limit_still_works(self, client):
        t = _token(client)
        r = client.get("/api/forum/posts?limit=10", headers=_hdr(t))
        assert len(_items(r)) == 10, "正常分页不得被改坏"

    def test_forum_garbage_limit_does_not_500(self, client):
        t = _token(client)
        r = client.get("/api/forum/posts?limit=abc&offset=xyz", headers=_hdr(t))
        assert r.status_code == 200, f"非数字参数应兜底而非 500：{r.status_code}"
        assert len(_items(r)) <= HARD_CAP

    def test_market_alerts_negative_limit_capped(self, client):
        t = _token(client)
        r = client.get("/api/market-alerts?limit=-1", headers=_hdr(t))
        assert r.status_code == 200, r.text[:200]
        n = len(_items(r))
        assert n <= HARD_CAP, f"market-alerts limit=-1 返回 {n} 条"

    def test_market_alerts_normal_limit(self, client):
        t = _token(client)
        r = client.get("/api/market-alerts?limit=5", headers=_hdr(t))
        assert len(_items(r)) == 5

    def test_admin_users_negative_per_page_capped(self, client):
        t = _token(client, "admin")
        r = client.get("/api/admin/users?per_page=-1", headers=_hdr(t))
        assert r.status_code == 200, r.text[:200]
        assert len(_items(r)) <= HARD_CAP

    def test_admin_logs_negative_per_page_capped(self, client):
        t = _token(client, "admin")
        r = client.get("/api/admin/logs?per_page=-1", headers=_hdr(t))
        assert r.status_code == 200, r.text[:200]
        assert len(_items(r)) <= HARD_CAP

    def test_admin_users_negative_page_no_crash(self, client):
        """page=-5 旧实现 offset=(-5-1)*50=-300，语义无意义；现钳为第 1 页。"""
        t = _token(client, "admin")
        r = client.get("/api/admin/users?page=-5&per_page=1", headers=_hdr(t))
        assert r.status_code == 200, r.text[:200]
        assert len(_items(r)) == 1


# ============================================================ 3. 源码层防回退
class TestNoRegressionInSource:

    BAD_PATTERNS = [
        # 只钳上界的裸写法（正是本轮修掉的 bug 形态）
        re.compile(r"min\(\s*int\(\s*request\.args\.get\(\s*[\"'](?:limit|per_page)"),
    ]

    def _py_files(self):
        for fn in sorted(os.listdir(API_DIR)):
            if fn.endswith(".py"):
                yield os.path.join(API_DIR, fn)

    def test_no_unbounded_limit_parsing(self):
        offenders = []
        for path in self._py_files():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for pat in self.BAD_PATTERNS:
                if pat.search(src):
                    offenders.append(os.path.basename(path))
        assert not offenders, f"以下路由回退到「只钳上界」的分页写法: {offenders}"

    def test_limit_parsing_uses_safe_helper(self):
        """凡是解析 limit/per_page 的路由文件，必须引用 parse_limit_param。"""
        missing = []
        for path in self._py_files():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            declares = re.search(r"^\s*(?:limit|per_page)\s*=", src, re.M)
            if declares and "parse_limit_param" not in src:
                missing.append(os.path.basename(path))
        assert not missing, f"以下路由解析分页条数但未用 parse_limit_param: {missing}"

    def test_helper_hardcodes_lower_bound(self):
        """parse_limit_param 自身必须固定 lo=1，不允许调用方传低于 1 的下界。"""
        path = os.path.join(BACKEND_DIR, "utils", "params.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert "def parse_limit_param" in src
        body = src.split("def parse_limit_param", 1)[1].split("def parse_page_param", 1)[0]
        assert "lo=1" in body, "parse_limit_param 必须写死 lo=1"
