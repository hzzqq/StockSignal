"""backend/tests/test_webapps_static_route.py
--------------------------------------------
网页作品集静态路由（/webapps/<path:filename>）回归测试。

目标：
  1. 正常作品文件可访问（200，Content-Type=text/html）。
  2. 目录穿越必须被拒（../app.py、..%2fapp.py、..%5c、%2e%2e 编码变体
     一律 403/404，绝不 200）——send_from_directory 的 safe_join 是最后防线，
     本测试把它锁死，防未来换实现时静默回退。
  3. 不存在的文件 404（JSON 信封，不漏 Flask 默认 HTML 错误页）。

运行（独立库，勿占生产库锁）：
    DATABASE_URL="sqlite:///E:/tmp/ss_probe/webapp_dev.db" \
        python -m pytest backend/tests/test_webapps_static_route.py -q
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.app import create_app          # noqa: E402
from backend.config import Config           # noqa: E402

import pytest                               # noqa: E402


class _TestConfig(Config):
    TESTING = True


@pytest.fixture(scope="module")
def client():
    app = create_app(_TestConfig)
    # webapps/emotion-cycle-clock/index.html 随仓库入库，正常路径用例依赖它存在
    sample = os.path.join(PROJECT_ROOT, "webapps", "emotion-cycle-clock", "index.html")
    if not os.path.exists(sample):
        pytest.skip("示例作品尚未收录（webapps/emotion-cycle-clock/index.html 缺失）")
    return app.test_client()


# ---------------- 正常路径 ----------------

def test_normal_index_html_served(client):
    resp = client.get("/webapps/emotion-cycle-clock/index.html")
    assert resp.status_code == 200, f"status={resp.status_code}"
    assert "text/html" in (resp.headers.get("Content-Type") or "")
    body = resp.get_data(as_text=True)
    assert "<canvas" in body or "<!DOCTYPE html>" in body or "<html" in body.lower()


def test_meta_json_served(client):
    resp = client.get("/webapps/emotion-cycle-clock/meta.json")
    assert resp.status_code == 200
    assert "json" in (resp.headers.get("Content-Type") or "")


def test_missing_file_is_404_json(client):
    resp = client.get("/webapps/emotion-cycle-clock/不存在.html")
    assert resp.status_code == 404
    # 错误出口统一 JSON 信封（沿用全局 errorhandler 红线）
    obj = resp.get_json()
    assert obj is not None and obj.get("status") == "error"


# ---------------- 目录穿越（必须 403/404，绝不 200） ----------------

@pytest.mark.parametrize(
    "payload",
    [
        "../app.py",                    # 明文穿越（浏览器/客户端可能预先归一化）
        "..%2fapp.py",                  # URL 编码斜杠
        "%2e%2e/app.py",                # 编码点号
        "%2e%2e%2fapp.py",              # 全编码
        "..%5capp.py",                  # 反斜杠变体（Windows 语义）
        "../backend/config.py",
        "..%2f..%2fbackend%2fconfig.py",
        "emotion-cycle-clock/../../backend/app.py",
    ],
)
def test_traversal_attempts_rejected(client, payload):
    resp = client.get(f"/webapps/{payload}")
    assert resp.status_code in (403, 404), (
        f"目录穿越未被拦截：GET /webapps/{payload!r} -> {resp.status_code}，"
        f"body 前 200 字：{resp.get_data(as_text=True)[:200]!r}"
    )
    # 关键红线：绝不能把 backend 源码吐出去
    assert b"def create_app" not in resp.get_data()
