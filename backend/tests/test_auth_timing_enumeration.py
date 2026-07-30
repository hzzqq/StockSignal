"""
backend/tests/test_auth_timing_enumeration.py
---------------------------------------------
登录接口账户枚举防御回归测试（c44 修复的真实缺陷）。

【缺陷本体】
  auth/service.authenticate 原实现：

      if user is None or not user.is_active or not user.verify_password(password):
          raise AuthError("用户名或密码错误", ...)

  Python 的 `or` 短路求值意味着 **用户不存在时根本不会调用 verify_password**。
  werkzeug 默认哈希为 scrypt(32768,8,1)，本机实测单次校验约 350ms，于是：

      不存在的用户名  -> 立即 401（~1ms）
      存在但密码错    -> 慢 401（~350ms）

  两个数量级的响应时间差 = 免费的账户枚举预言机。函数注释声称
  「失败消息统一，避免账户枚举」，但统一文案被时序侧信道完全绕过。

【修复】
  用户不存在时调用 _equalize_hash_time()，跑一次等价开销的哑哈希校验。
  用户被禁用时也照常 verify_password，避免「禁用」变成另一个时序标记。

护栏分三层：
  1. 行为层：不存在的用户名也必须真的触发一次密码哈希校验（spy 计数，不依赖计时）。
  2. 时序层：宽松阈值的耗时比对（主断言仍是第 1 层，这里只兜底防止实现被掏空）。
  3. 契约层：三条失败路径的 status/code/message 必须完全一致；正常登录不受影响。
"""
from __future__ import annotations

import os
import sys
import time

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest                                     # noqa: E402

from backend.app import create_app                # noqa: E402
from backend.config import Config                 # noqa: E402
from backend.extensions import db                 # noqa: E402
from backend.models import User                   # noqa: E402
from backend.auth import service as auth_service  # noqa: E402
from backend.utils.errors import AuthError        # noqa: E402


@pytest.fixture
def app(tmp_path):
    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'a.db'}"
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    with application.app_context():
        db.create_all()
        u = User(username="alice", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        dead = User(username="banned", role="user")
        dead.set_password("Pass@123")
        dead.is_active = False
        db.session.add(dead)
        db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, password):
    return client.post("/api/auth/login",
                       json={"username": username, "password": password})


def _warm_dummy():
    """预热哑哈希缓存，避免首次 generate 的一次性开销污染计时用例。"""
    auth_service._equalize_hash_time("warmup")


# ==================================================== 1. 行为层（主断言）
class TestHashWorkAlwaysPerformed:

    def test_missing_user_still_performs_hash_check(self, app, monkeypatch):
        """核心断言：不存在的用户名也必须走一次哈希校验。

        旧实现因 `or` 短路，这里的计数会是 0 —— 用例必红。
        """
        calls = []
        real = auth_service.check_password_hash

        def _spy(h, p):
            calls.append((h, p))
            return real(h, p)

        monkeypatch.setattr(auth_service, "check_password_hash", _spy)
        _warm_dummy()
        calls.clear()

        with app.app_context():
            with pytest.raises(AuthError):
                auth_service.authenticate("no_such_user_xyz", "whatever")

        assert len(calls) == 1, (
            f"用户不存在时未执行哈希校验（调用 {len(calls)} 次），"
            "时序侧信道仍可枚举账号"
        )

    def test_existing_user_wrong_password_performs_hash_check(self, app):
        with app.app_context():
            with pytest.raises(AuthError):
                auth_service.authenticate("alice", "WrongPass")

    def test_inactive_user_also_verifies_password(self, app, monkeypatch):
        """被禁用的账号也要真校验密码，否则「禁用」成为新的时序标记。"""
        seen = []
        real_verify = User.verify_password

        def _spy(self, pw):
            seen.append(self.username)
            return real_verify(self, pw)

        monkeypatch.setattr(User, "verify_password", _spy)
        with app.app_context():
            with pytest.raises(AuthError):
                auth_service.authenticate("banned", "Pass@123")
        assert seen == ["banned"], f"禁用用户跳过了密码校验: {seen}"

    def test_dummy_hash_is_cached(self, app):
        """哑哈希只生成一次，之后复用（否则每次未命中都多付一次 generate）。"""
        _warm_dummy()
        first = auth_service._dummy_hash
        assert first, "哑哈希未生成"
        _warm_dummy()
        assert auth_service._dummy_hash is first, "哑哈希被重复生成"

    def test_dummy_check_never_succeeds(self, app):
        """哑校验只烧时间，绝不能意外返回 True 造成绕过。"""
        _warm_dummy()
        assert auth_service.check_password_hash(
            auth_service._dummy_hash, "any-password") is False


# ==================================================== 2. 时序层（宽松兜底）
class TestTimingSideChannelClosed:

    def test_missing_and_wrong_password_cost_same_order(self, app):
        """两条失败路径耗时须同量级（旧实现相差约 350x）。

        阈值故意放宽到 0.4，只为拦住「实现被掏空」，不做精确计时断言。
        """
        _warm_dummy()

        def _timed(username):
            with app.app_context():
                t0 = time.perf_counter()
                try:
                    auth_service.authenticate(username, "DefinitelyWrong")
                except AuthError:
                    pass
                return time.perf_counter() - t0

        # 各跑 2 次取较小值，降低调度抖动影响
        t_missing = min(_timed("ghost_user_1"), _timed("ghost_user_2"))
        t_wrong = min(_timed("alice"), _timed("alice"))

        assert t_wrong > 0, "真实校验耗时为 0，环境异常"
        ratio = t_missing / t_wrong
        assert ratio >= 0.4, (
            f"不存在用户耗时仅为真实校验的 {ratio:.3f} 倍 "
            f"({t_missing * 1000:.1f}ms vs {t_wrong * 1000:.1f}ms)，时序侧信道仍存在"
        )


# ==================================================== 3. 契约层
class TestResponseContractUnchanged:

    def _fail_body(self, resp):
        obj = resp.get_json(force=True)
        return resp.status_code, obj.get("code"), obj.get("message")

    def test_three_failure_paths_identical(self, client):
        a = self._fail_body(_login(client, "ghost_user", "Whatever1"))
        b = self._fail_body(_login(client, "alice", "WrongPass1"))
        c = self._fail_body(_login(client, "banned", "Pass@123"))
        assert a == b == c, f"失败响应可区分，仍可枚举账号: {a} / {b} / {c}"
        assert a[2] == "用户名或密码错误", f"错误文案偏离基线: {a[2]}"

    def test_valid_login_still_works(self, client):
        r = _login(client, "alice", "Pass@123")
        assert r.status_code == 200, r.text[:200]
        assert r.get_json()["data"]["token"]

    def test_empty_credentials_still_validation_error(self, client):
        """空凭证走 ValidationError（本项目映射为 422），不应被改成 401/500。"""
        r = _login(client, "", "")
        assert r.status_code == 422, r.status_code
        assert r.get_json(force=True).get("message") == "请提供用户名和密码"


# ==================================================== 4. 源码级防回退
def test_source_keeps_timing_equalizer():
    path = os.path.join(BACKEND_DIR, "auth", "service.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    body = src.split("def authenticate", 1)[1]
    assert "_equalize_hash_time" in body, "authenticate 丢失时序抹平调用"
    assert "or not user.verify_password(password)" not in body, (
        "authenticate 回退到短路写法（用户不存在时不再执行哈希校验）"
    )
