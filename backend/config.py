"""
backend/config.py
-----------------
集中管理配置。生产环境请通过环境变量覆盖 SECRET_KEY。
"""
from __future__ import annotations
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _env_int(name: str, default: int) -> int:
    """安全读取整型环境变量：缺失/空/非法（非数字）一律回退默认，
    避免误配导致整个后端在 import 时 int() 抛 ValueError 崩溃。"""
    try:
        v = os.environ.get(name)
        return int(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


# 密钥持久化文件（模块级：测试可注入重定向；gitignore 覆盖 backend/data/）
SECRET_KEY_FILE = DATA_DIR / "secret_key"


def _resolve_secret() -> str:
    """SECRET_KEY 解析（T-144 缺陷③修复）：env 优先；未设置时首启生成随机密钥并
    持久化到 backend/data/secret_key（每机唯一、重启稳定），消除公开弱默认的
    「JWT 可被任何知道该默认值的人伪造」风险。极端只读环境兜底为进程内随机。"""
    env = os.environ.get("STOCKSIGNAL_SECRET")
    if env:
        return env
    key_file = SECRET_KEY_FILE
    try:
        if key_file.exists():
            cached = key_file.read_text(encoding="utf-8").strip()
            if len(cached) >= 32:
                return cached
        import secrets as _secrets
        generated = _secrets.token_urlsafe(48)
        key_file.write_text(generated, encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return generated
    except Exception:  # noqa: BLE001
        import secrets as _secrets
        return _secrets.token_urlsafe(48)


class Config:
    # 基础
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # 安全（T-144 缺陷③：不再使用公开弱默认）
    SECRET_KEY = _resolve_secret()

    # JWT
    JWT_ALGORITHM = "HS256"
    # 默认 7 天：本地演示环境浏览器常驻，避免长时间停留后被迫重新登录。
    # 可通过环境变量 JWT_EXPIRES_SECONDS 覆盖（生产建议缩短）。
    JWT_EXPIRES_SECONDS = _env_int("JWT_EXPIRES_SECONDS", 604800)  # 7 天
    JWT_HEADER = "Authorization"
    JWT_PREFIX = "Bearer "

    # 数据库
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 数据库引擎选项（多用户并发关键配置）
    # - check_same_thread=False：允许连接池跨线程复用（Flask 多线程处理并发请求必须）
    # - timeout=30：SQLite 锁等待 30s，配合下方 WAL 的 busy_timeout 彻底避免
    #   "database is locked" 导致接口报错/堵塞
    # - pool_pre_ping / pool_recycle：自动剔除失效连接，避免隔夜连接僵死占用池
    # - pool_size / max_overflow：并发连接上限（局域网/实训多账号场景足够）
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {"check_same_thread": False, "timeout": 30},
    }

    # CORS（T-144 缺陷②收紧）：默认收敛到本机前后端来源；局域网/生产用 env 覆盖
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:8899,http://127.0.0.1:8899,"
        "http://localhost:8501,http://127.0.0.1:8501,"
        "http://localhost:5050,http://127.0.0.1:5050",
    )

    # 错误响应开关：生产绝不暴露内部
    EXPOSE_INTERNAL_ERROR = os.environ.get("EXPOSE_INTERNAL_ERROR", "0") == "1"

    # 认证限流（进程内内存滑动窗口）：防 login/register 爆破
    # 测试可通过 STOCKSIGNAL_RATE_LIMIT_ENABLED=0 关闭，或用 reset_rate_limit()
    RATE_LIMIT_ENABLED = os.environ.get("STOCKSIGNAL_RATE_LIMIT_ENABLED", "1") != "0"
    RATE_LIMIT_MAX = _env_int("RATE_LIMIT_MAX", 5)        # 单 key 窗口内最大次数
    RATE_LIMIT_WINDOW = _env_int("RATE_LIMIT_WINDOW", 60)  # 滑动窗口秒数
