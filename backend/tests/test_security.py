"""
backend/tests/test_security.py
-------------------------------
针对"登录后 HTML 泄露"漏洞的回归测试。

测试目标（每一条都对应一种漏洞形态）：
    1. 登录成功 -> 纯 JSON
    2. 密码错  -> 纯 JSON，且 message 不暴露用户是否存在
    3. 用户不存在 -> 消息与密码错时一致（防账户枚举）
    4. token 缺失/无效/过期 -> 纯 JSON
    5. 角色不足 -> 纯 JSON
    6. 错误路由 404 -> 纯 JSON（不允许 Flask 默认 HTML 错误页）
    7. 错误方法 405 -> 纯 JSON
    8. Content-Type 必须是 application/json
    9. 响应体里不能包含 <html>、<body>、Traceback、File "<stdin>" 这类痕迹
   10. 强制 trigger 内部异常 -> 响应是 JSON，不会泄漏 stacktrace

启动方式：
    cd backend
    python -m tests.test_security
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import threading
from typing import Tuple

import requests

# 启动 Flask 测试客户端不需要 requests + 真实端口；这里两种都覆盖

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app import create_app           # noqa: E402
from backend.extensions import db            # noqa: E402
from backend.models import User              # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


FORBIDDEN_PATTERNS = [
    re.compile(r"<\s*html", re.IGNORECASE),
    re.compile(r"<\s*body", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"<\s*style", re.IGNORECASE),
    re.compile(r"Traceback\s*\(most recent call last\)"),
    re.compile(r'File\s+["<][^"]*["<]'),  # File "xxx" / File <xxx>
    re.compile(r"\bat\s+0x[0-9a-fA-F]+"),   # 内存地址
]


def _assert_clean_json(resp: requests.Response, label: str) -> dict:
    """断言响应是合法 JSON 且不含 HTML/调试痕迹。"""
    ctype = resp.headers.get("Content-Type", "")
    assert "application/json" in ctype, (
        f"[{label}] Content-Type 不是 JSON: {ctype!r} body={resp.text[:200]!r}"
    )
    body = resp.text
    for pat in FORBIDDEN_PATTERNS:
        assert not pat.search(body), (
            f"[{label}] 响应体里出现被禁模式 {pat.pattern!r}，body 前 400 字：\n{body[:400]}"
        )
    try:
        return resp.get_json()
    except Exception as e:
        raise AssertionError(f"[{label}] 响应不是合法 JSON: {e}; body={body[:200]!r}")


def _assert_envelope(obj: dict, label: str, expect_status: str) -> None:
    for k in ("status", "code", "message", "data"):
        assert k in obj, f"[{label}] 缺字段 {k!r}: {obj}"
    assert obj["status"] == expect_status, f"[{label}] status 应为 {expect_status!r} 实际 {obj['status']!r}"
    # message 必须是字符串
    assert isinstance(obj["message"], str) and obj["message"], f"[{label}] message 非法: {obj}"


def _make_user(app, username: str, password: str, role: str = "user") -> None:
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if u is None:
            u = User(username=username, role=role)
            u.set_password(password)
            db.session.add(u)
        else:
            u.password_hash = generate_password_hash(password)
            u.role = role
            u.is_active = True
        db.session.commit()


def run_all() -> int:
    print("=" * 72)
    print("StockSignal 后端 - 安全回归测试")
    print("=" * 72)

    # ---- 启动 Flask 测试客户端（避免真实端口依赖） ----
    app = create_app()
    with app.app_context():
        db.create_all()
        _make_user(app, "admin", "Admin@123", role="admin")
        _make_user(app, "demo",  "Demo@123",  role="user")

    # 注册一个会抛 500 的路由（必须在第一次请求前完成）
    @app.route("/api/_test_boom")
    def _boom_route():
        raise RuntimeError("secret-internal-thing-should-never-leak")

    client = app.test_client()

    def post(path, json=None, headers=None):
        return client.post(path, json=json, headers=headers or {})

    def get(path, headers=None):
        return client.get(path, headers=headers or {})

    fail_count = 0
    passed = 0

    def case(name: str, fn):
        nonlocal fail_count, passed
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}\n         -> {e}")
            fail_count += 1
        except Exception as e:
            import traceback
            print(f"  [ERR ] {name}\n         -> {type(e).__name__}: {e}")
            traceback.print_exc()
            fail_count += 1

    # ---- 2. 登录成功 ----
    def t_login_ok():
        resp = post("/api/auth/login", json={"username": "demo", "password": "Demo@123"})
        assert resp.status_code == 200, f"status={resp.status_code} body={resp.data!r}"
        obj = _assert_clean_json(resp, "login_ok")
        _assert_envelope(obj, "login_ok", expect_status="ok")
        assert isinstance(obj["data"], dict)
        assert "token" in obj["data"] and isinstance(obj["data"]["token"], str)
        assert obj["data"]["user"]["username"] == "demo"
    case("登录成功返回纯 JSON + token", t_login_ok)

    # ---- 3. 密码错 ----
    def t_login_wrong_pwd():
        resp = post("/api/auth/login", json={"username": "demo", "password": "WRONG"})
        assert resp.status_code == 401, "status=" + repr(resp.status_code)
        obj = _assert_clean_json(resp, "login_wrong_pwd")
        _assert_envelope(obj, "login_wrong_pwd", expect_status="error")
        msg = obj.get("message", "")
        # 统一提示必须是这条（不能区分用户存在与否）
        assert msg == "用户名或密码错误", "msg=" + repr(msg)
        # 不应出现区分性文案
        for leak in ("用户不存在", "账号不存在", "密码不正确", "password", "user not found"):
            assert leak not in msg, "leak=" + repr(leak)
    case("密码错误：纯 JSON + 不暴露内部细节", t_login_wrong_pwd)

    # ---- 4. 用户不存在 vs 密码错：消息一致（防枚举） ----
    def t_login_no_user():
        resp = post("/api/auth/login", json={"username": "ghost", "password": "x"})
        assert resp.status_code == 401
        obj = _assert_clean_json(resp, "login_no_user")
        # 消息和密码错场景必须完全相同
        assert obj["message"] == "用户名或密码错误", f"message 暴露用户存在与否: {obj['message']!r}"
    case("不存在的用户：与密码错返回同样的消息", t_login_no_user)

    # ---- 5. token 缺失 ----
    def t_no_token():
        resp = get("/api/auth/me")
        assert resp.status_code == 401
        obj = _assert_clean_json(resp, "no_token")
        _assert_envelope(obj, "no_token", expect_status="error")
    case("缺 token 访问受保护接口：纯 JSON", t_no_token)

    # ---- 6. token 无效 ----
    def t_bad_token():
        resp = get("/api/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
        assert resp.status_code == 401
        obj = _assert_clean_json(resp, "bad_token")
    case("非法 token：纯 JSON", t_bad_token)

    # ---- 7. role 不足 ----
    def t_role_denied():
        # demo 是 user
        login = post("/api/auth/login", json={"username": "demo", "password": "Demo@123"})
        token = login.get_json()["data"]["token"]
        resp = get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        obj = _assert_clean_json(resp, "role_denied")
        assert obj["code"] == "forbidden"
        assert obj["message"] == "无权限访问"
    case("普通用户访问 admin 接口：纯 JSON + 403", t_role_denied)

    # ---- 8. admin 可以列用户 ----
    def t_admin_ok():
        login = post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = login.get_json()["data"]["token"]
        resp = get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        obj = _assert_clean_json(resp, "admin_ok")
        _assert_envelope(obj, "admin_ok", expect_status="ok")
        # 兼容分页格式 {items: [...]} 和直接数组格式
        data = obj["data"]
        users_list = data["items"] if isinstance(data, dict) and "items" in data else data
        usernames = {u["username"] for u in users_list}
        assert {"admin", "demo"}.issubset(usernames)
        # 关键：不能包含 password_hash
        for u in users_list:
            assert "password_hash" not in u, "泄漏了 password_hash!"
    case("admin 列表：不暴露 password_hash", t_admin_ok)

    # ---- 9. 404：路由不存在 → JSON ----
    def t_404():
        resp = get("/api/this/does/not/exist")
        assert resp.status_code == 404
        obj = _assert_clean_json(resp, "404")
        _assert_envelope(obj, "404", expect_status="error")
    case("未知路由 404：纯 JSON（不允许默认 HTML 错误页）", t_404)

    # ---- 10. 405：方法不允许 → JSON ----
    def t_405():
        # /api/auth/login 是 POST，GET 应得 405
        resp = get("/api/auth/login")
        assert resp.status_code == 405
        obj = _assert_clean_json(resp, "405")
    case("方法不允许 405：纯 JSON", t_405)

    # ---- 11. 非 JSON 提交 → 422 ----
    def t_not_json():
        resp = client.post("/api/auth/login", data="username=demo&password=Demo@123")
        assert resp.status_code == 422
        obj = _assert_clean_json(resp, "not_json")
    case("非 application/json 提交：纯 JSON", t_not_json)

    # ---- 12. 触发内部异常 → 纯 JSON，不泄漏 stack ----
    def t_internal_error():
        resp = get("/api/_test_boom")
        assert resp.status_code == 500
        obj = _assert_clean_json(resp, "internal_error")
        assert obj["code"] == "internal_error"
        assert obj["message"] == "服务内部错误"
        assert "secret-internal" not in resp.text
        assert "Traceback" not in resp.text
    case("内部异常：纯 JSON + 不暴露 stacktrace", t_internal_error)

    # ---- 13. Content-Type 与 nosniff ----
    def t_security_headers():
        resp = get("/api/health")
        assert resp.headers.get("Content-Type", "").startswith("application/json")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    case("安全响应头：Content-Type=JSON + nosniff", t_security_headers)

    # ---- 总结 ----
    print("=" * 72)
    print(f"通过 {passed} / 失败 {fail_count}")
    print("=" * 72)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
