"""tests/test_no_credential_leak.py

锁死「凭据零泄露」基线：**序列化出口不得带凭证字段，日志不得插值凭证变量**。

三层防线：
  1. 运行时：``User.to_public()`` 即便对象上真的挂着 password_hash，
     输出也必须不含任何 password 相关字段（数据最小化）。
  2. 源码层：backend 下所有序列化方法（to_public / to_dict / as_dict / serialize）
     不得出现 password / secret / api_key / private_key 等敏感键名或属性引用。
  3. 源码层：backend + modules 的日志调用中，f-string 不得插值
     password / passwd / secret / api_key 等凭证变量（防凭据落盘到日志）。

与项目既有安全基线一致（后端约定：任何业务接口都不要新增 password_hash 字段到 to_public）。
审计时点为 0 违例；本测试用于防止后续改动悄悄把凭据带出去。

2026-08-28 新增（Cycle 65）。
"""
import ast
import glob
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 凭证类敏感词（序列化键名 / 属性名 / 日志插值变量）
SENSITIVE_SERIALIZE = ("password", "passwd", "pwd", "secret",
                       "api_key", "apikey", "private_key", "access_key")
SENSITIVE_LOG = ("password", "passwd", "secret", "api_key", "apikey")
SERIALIZERS = ("to_public", "to_dict", "as_dict", "serialize")
LOG_METHODS = ("debug", "info", "warning", "error", "exception", "critical")


def _iter_backend_py():
    for path in sorted(glob.glob(os.path.join(ROOT, "backend", "**", "*.py"), recursive=True)):
        if os.sep + "tests" + os.sep in path:
            continue
        yield path


def test_user_to_public_never_exposes_credentials():
    """运行时验证：即便实例上真的有 password_hash，to_public 也不得外泄。"""
    from backend.models import User

    # 用普通替身对象调用未绑定的 to_public：既真实执行方法体，
    # 又绕开 SQLAlchemy 描述符（无需 DB / app 上下文 / 网络）。
    class _StubUser:
        id = 1
        username = "alice"
        role = "user"
        created_at = datetime(2026, 1, 1)
        is_active = True
        avatar = ""
        settings = None
        password_hash = "pbkdf2:sha256:260000$S3CR3T$deadbeefcafe"  # 故意挂上真实哈希

    pub = User.to_public(_StubUser())

    leak_keys = [k for k in pub if any(s in str(k).lower() for s in SENSITIVE_SERIALIZE)]
    assert not leak_keys, f"to_public 泄露了凭证字段: {leak_keys}"

    # 序列化后的文本里也不得出现哈希片段
    text = json.dumps(pub, ensure_ascii=False, default=str).lower()
    assert "password" not in text
    assert "pbkdf2" not in text
    assert "s3cr3t" not in text

    # 正常字段仍在（防止为了「去敏」把功能删没了）
    assert pub["username"] == "alice"
    assert pub["role"] == "user"


def test_serializers_do_not_expose_credential_fields():
    bad = []
    for path in _iter_backend_py():
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name not in SERIALIZERS:
                continue
            # 字典字面量里的敏感键名
            for sub in ast.walk(node):
                if isinstance(sub, ast.Dict):
                    for k in sub.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            kv = k.value.lower()
                            if any(s in kv for s in SENSITIVE_SERIALIZE):
                                bad.append((rel, node.name, sub.lineno, f"dict key '{k.value}'"))
                # 敏感属性引用（如 self.password_hash）
                if isinstance(sub, ast.Attribute):
                    av = sub.attr.lower()
                    if any(s in av for s in SENSITIVE_SERIALIZE):
                        bad.append((rel, node.name, sub.lineno, f"attr 'self.{sub.attr}'"))
    assert not bad, (
        "序列化方法中出现凭证字段（应剔除后再输出）:\n"
        + "\n".join(f"  {p}:{ln} {fn}() -> {why}" for p, fn, ln, why in sorted(set(bad)))
    )


def test_logs_do_not_interpolate_credentials():
    bad = []
    for path in sorted(glob.glob(os.path.join(ROOT, "backend", "**", "*.py"), recursive=True)
                       + glob.glob(os.path.join(ROOT, "modules", "**", "*.py"), recursive=True)):
        if os.sep + "tests" + os.sep in path:
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            nm = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if nm not in LOG_METHODS:
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.JoinedStr):
                    continue
                for v in sub.values:
                    if not isinstance(v, ast.FormattedValue):
                        continue
                    e = v.value
                    tgt = e.attr if isinstance(e, ast.Attribute) else (e.id if isinstance(e, ast.Name) else None)
                    if tgt and any(s in tgt.lower() for s in SENSITIVE_LOG):
                        bad.append((rel, node.lineno, f"{nm}() -> {{{tgt}}}"))
    assert not bad, (
        "日志中插值了凭证变量（凭据会落盘到日志文件）:\n"
        + "\n".join(f"  {p}:{ln} {why}" for p, ln, why in sorted(set(bad)))
    )
