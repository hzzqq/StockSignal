# -*- coding: utf-8 -*-  # noqa: UP009
"""
backend/tests/test_read_routes_review_images.py — 复盘笔记图片上传/读取端点守卫。

覆盖：
  1. 正常上传（真实 PNG 头）：200 + ok 信封结构 + 文件真实落盘（临时 data/review_images/）；
  2. magic bytes 双重校验：伪装 .png（实为文本）→ 422；JPEG/GIF/WEBP 真头 → 200；
  3. 超 5MB / 非白名单扩展 / 缺 file 字段 / 非法 date → 422；
  4. _require_json 豁免不泄漏：multipart 发到其他端点仍 422；
  5. GET：回显相同字节 + 正确 Content-Type；穿越/不存在/非白名单扩展 → 404；无 jwt → 401。

目录常量 monkeypatch：模块级 fixture 直接改 rr._DATA_DIR（_review_img_dir 请求时求值），
fixture 结束时还原。
"""
from __future__ import annotations

import io
import os
import re
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as rr  # noqa: E402

UPLOAD_URL = "/api/v2/read/review-images"

# ── 真实 magic bytes（手写 header + 随机体即可，后端只校验头）──
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF"
GIF_MAGIC = b"GIF89a\x01\x00\x01\x00"
WEBP_MAGIC = b"RIFF\x24\x00\x00\x00WEBPVP8 "


def _png_bytes(size: int = 256) -> bytes:
    return PNG_MAGIC + bytes(range(256))[:size]


def _upload(client, headers, png_body=_png_bytes(), filename="shot.png",
            date="2026-11-20"):
    return client.post(
        UPLOAD_URL,
        data={"date": date, "file": (io.BytesIO(png_body), filename)},
        headers=headers,
    )


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{tmp_path_factory.mktemp('db') / 'img.db'}"
        )

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="imguser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def client(app, tmp_path_factory, request):
    # 隔离的临时 data 树，把 rr._DATA_DIR 指过去（_review_img_dir 请求时求值）
    root = tmp_path_factory.mktemp("imgroot")
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    original = rr._DATA_DIR
    rr._DATA_DIR = data

    def _restore():
        rr._DATA_DIR = original

    request.addfinalizer(_restore)
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="imguser").first()
        return issue_token(u)


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ─────────────────────────── 上传 ───────────────────────────

def test_upload_png_ok(client, token):
    """正常 PNG 上传：200 + ok 信封结构 + 文件真实落在临时 data/review_images/。"""
    body = _png_bytes()
    resp = _upload(client, _auth(token), png_body=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    obj = resp.get_json()
    assert obj["status"] == "ok" and obj["code"] == "ok", obj
    d = obj["data"]
    assert d["date"] == "2026-11-20"
    # 文件名服务端生成：review_<date>_<12位随机hex>.png
    assert re.fullmatch(r"review_2026-11-20_[0-9a-f]{12}\.png", d["filename"]), d
    # 文件名服务端生成：不含原始文件名 shot.png
    assert "shot" not in d["filename"]
    assert d["url"] == f"{UPLOAD_URL}/2026-11-20/{d['filename']}"
    # 文件真实落盘且字节一致
    stored = rr._DATA_DIR / "review_images" / d["filename"]
    assert stored.is_file()
    assert stored.read_bytes() == body


@pytest.mark.parametrize("magic,ext", [
    (JPEG_MAGIC, "jpg"),
    (JPEG_MAGIC, "jpeg"),
    (GIF_MAGIC, "gif"),
    (WEBP_MAGIC, "webp"),
])
def test_upload_real_magics_ok(client, token, magic, ext):
    resp = _upload(client, _auth(token), png_body=magic + b"\x00" * 64,
                   filename=f"img.{ext}", date="2026-11-19")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    d = resp.get_json()["data"]
    assert d["date"] == "2026-11-19"
    assert d["filename"].endswith(f".{ext}")
    assert d["url"].startswith(f"{UPLOAD_URL}/2026-11-19/")


def test_upload_disguised_png_rejected(client, token):
    """扩展 .png 实为文本 → magic bytes 校验 422。"""
    resp = _upload(client, _auth(token), png_body=b"hello world not an image" * 4,
                   filename="fake.png")
    assert resp.status_code == 422
    obj = resp.get_json()
    assert obj["status"] == "error" and "扩展名不符" in obj["message"], obj


def test_upload_too_large_rejected(client, token):
    """超 5MB → 422。"""
    big = PNG_MAGIC + b"\x00" * (5 * 1024 * 1024)  # 略超 5MB
    resp = _upload(client, _auth(token), png_body=big, filename="big.png")
    assert resp.status_code == 422
    assert "5MB" in resp.get_json()["message"]


def test_upload_bad_extension_rejected(client, token):
    for name in ("evil.txt", "evil.exe"):
        resp = _upload(client, _auth(token), png_body=PNG_MAGIC + b"x" * 32,
                       filename=name)
        assert resp.status_code == 422, name
        assert "png/jpg/jpeg/gif/webp" in resp.get_json()["message"]


def test_upload_missing_file_field(client, token):
    resp = client.post(
        UPLOAD_URL,
        data={"date": "2026-11-20"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert "file" in resp.get_json()["message"]


def test_upload_invalid_date(client, token):
    resp = _upload(client, _auth(token), date="2026-13-01")
    assert resp.status_code == 422
    assert "date" in resp.get_json()["message"]


def test_upload_no_jwt_401(client):
    resp = client.post(
        UPLOAD_URL,
        data={"date": "2026-11-20", "file": (io.BytesIO(_png_bytes()), "a.png")},
    )
    assert resp.status_code == 401


# ─────────────────── 豁免不泄漏（_require_json）───────────────────

def test_json_enforcement_still_applies_elsewhere(client, token):
    """multipart 发到其他需 JSON 的端点仍被 422 拦截（豁免范围未泄漏）。"""
    resp = client.put(
        "/api/v2/read/review-notes",
        data={"date": "2026-11-20", "content": "x"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert "请求体必须为 JSON" in resp.get_json()["message"]


# ─────────────────────────── GET ───────────────────────────

def test_get_image_roundtrip(client, token):
    body = _png_bytes(512)
    fn = _upload(client, _auth(token), png_body=body, filename="rt.png").get_json()["data"]["filename"]
    resp = client.get(f"{UPLOAD_URL}/2026-11-20/{fn}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.content_type == "image/png"
    assert resp.get_data() == body


@pytest.mark.parametrize("fn", [
    "..%2Freview_notes_2026-11-20.md",
    "sub%2F..%2F..%2Fsecret.png",
    "..\\..\\app.py",
    "review.png%00.png",
])
def test_get_traversal_404(client, token, fn):
    resp = client.get(f"{UPLOAD_URL}/2026-11-20/{fn}", headers=_auth(token))
    assert resp.status_code == 404, fn


def test_get_nonexistent_404(client, token):
    resp = client.get(f"{UPLOAD_URL}/2026-11-20/review_2026-11-20_ffffffffffff.png",
                      headers=_auth(token))
    assert resp.status_code == 404


def test_get_bad_extension_404_no_leak(client, token):
    """扩展不在白名单 → 404（不泄露文件存在性）。"""
    resp = client.get(f"{UPLOAD_URL}/2026-11-20/notes.html", headers=_auth(token))
    assert resp.status_code == 404


def test_get_no_jwt_401(client):
    resp = client.get(f"{UPLOAD_URL}/2026-11-20/review_2026-11-20_000000000000.png")
    assert resp.status_code == 401


# ───────── 全局 MAX_CONTENT_LENGTH 加固（2026-11-20 修复死代码 setdefault）─────────
def test_max_content_length_configured_above_image_limit(app):
    """全局请求体上限必须真实生效且 > 5MB 图片限制（旧 setdefault 在 Flask 预置
    None 上永远空转，从未生效——探针实测复现过 3MB 穿透到端点层）。"""
    mcl = app.config.get("MAX_CONTENT_LENGTH")
    assert isinstance(mcl, int) and mcl > 0, f"MAX_CONTENT_LENGTH 未配置: {mcl!r}"
    # 下限：不低于 review-images 5MB 限制的钳制值（6MB），否则图片上传会被 413 误杀
    assert mcl >= 6 * 1024 * 1024, f"上限 {mcl} 低于图片上传 6MB 下限"


def test_request_over_global_cap_rejected_413_json(client, token):
    """超过全局上限（默认 10MB）的请求体 → 413，且为 JSON 信封而非 Flask 默认 HTML 错误页。"""
    huge = PNG_MAGIC + b"\x00" * (11 * 1024 * 1024)  # 11MB > 默认 10MB 上限
    resp = _upload(client, _auth(token), png_body=huge, filename="huge.png")
    assert resp.status_code == 413, resp.status_code
    assert resp.content_type.startswith("application/json")
    obj = resp.get_json()
    assert obj is not None and obj.get("status") == "error"
