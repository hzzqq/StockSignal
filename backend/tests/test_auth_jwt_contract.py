"""auth/service.py — issue_token / decode_token JWT 安全契约（SDD+TDD, Cycle 76）。

真零覆盖盲区：仓库内此前无任何测试触达这两个 JWT 签发/验签入口
（test_auth_decorators.py 用 monkeypatch 把 decode_token 换成 lambda 跳过）。

本测试基于 *安全需求* 冻结契约，并用 mutation 门（见 run_mutation_check）证明非假绿：
若 decode_token 把 ExpiredSignatureError 的 raise 吞掉，AC2 必须变红。
"""
from __future__ import annotations

import os
import sys
import time

import jwt
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.app import create_app          # noqa: E402
from backend.config import Config          # noqa: E402
from backend.auth import service as auth_service  # noqa: E402
from backend.utils.errors import AuthError  # noqa: E402


class _StubUser:
    def __init__(self, username, uid, role):
        self.username = username
        self.id = uid
        self.role = role


@pytest.fixture
def app_ctx(tmp_path):
    class _C(Config):
        TESTING = True
        SECRET_KEY = "unit-test-secret-do-not-use"
        JWT_ALGORITHM = "HS256"
        JWT_EXPIRES_SECONDS = 3600
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'a.db'}"
        RATE_LIMIT_ENABLED = False

    application = create_app(_C)
    with application.app_context():
        yield application


def test_ac1_roundtrip_claims(app_ctx):
    """签发→验签往返，claims 完整正确，exp-iat == JWT_EXPIRES_SECONDS。"""
    u = _StubUser("alice", 7, "admin")
    tok = auth_service.issue_token(u)
    claims = auth_service.decode_token(tok)
    assert claims["sub"] == "alice"
    assert claims["uid"] == 7
    assert claims["role"] == "admin"
    assert claims["exp"] - claims["iat"] == 3600


def test_ac2_expired_token_rejected(tmp_path):
    """过期令牌必须被拒，且 code==token_expired（不得静默接受过期会话）。"""
    class _ExpiredCfg(Config):
        TESTING = True
        SECRET_KEY = "unit-test-secret-do-not-use"
        JWT_ALGORITHM = "HS256"
        JWT_EXPIRES_SECONDS = -10  # 签发即过期
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'a.db'}"
        RATE_LIMIT_ENABLED = False

    with create_app(_ExpiredCfg).app_context():
        u = _StubUser("bob", 9, "user")
        tok = auth_service.issue_token(u)
        with pytest.raises(AuthError) as exc:
            auth_service.decode_token(tok)
    assert exc.value.code == "token_expired"


def test_ac3_tampered_signature_rejected(app_ctx):
    """篡改签名字节必须被拒，code==invalid_token。"""
    u = _StubUser("carol", 11, "user")
    tok = auth_service.issue_token(u)
    # 篡改签名：整段替换为等长占位（T-158 修复时间性 flaky——base64url 末字符
    # 只有 4 个有效位，逐字符翻转有 ~1/16 概率解码等价而逃过验签）。
    head, _, sig = tok.rpartition(".")
    tampered = f"{head}.{'A' * len(sig)}"
    with pytest.raises(AuthError) as exc:
        auth_service.decode_token(tampered)
    assert exc.value.code == "invalid_token"


def test_ac4_malformed_token_rejected(app_ctx):
    """非 JWT 字符串/空串必须被拒，code==invalid_token。"""
    for bad in ("not-a-jwt", "", "abc.def"):
        with pytest.raises(AuthError) as exc:
            auth_service.decode_token(bad)
        assert exc.value.code == "invalid_token"


def test_ac5_alg_none_rejected(app_ctx):
    """算法混淆攻击：用 alg='none' 伪造的令牌必须被拒。"""
    forged = jwt.encode({"sub": "root", "exp": int(time.time()) + 9999},
                        key="", algorithm="none")
    with pytest.raises(AuthError) as exc:
        auth_service.decode_token(forged)
    assert exc.value.code == "invalid_token"


def test_ac6_wrong_secret_rejected(app_ctx):
    """用与 SECRET_KEY 不同的密钥签发的令牌必须被拒。"""
    other = jwt.encode({"sub": "mallory", "exp": int(time.time()) + 9999},
                       key="a-totally-different-key", algorithm="HS256")
    with pytest.raises(AuthError) as exc:
        auth_service.decode_token(other)
    assert exc.value.code == "invalid_token"
