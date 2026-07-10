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


class Config:
    # 基础
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # 安全
    # 生产环境必须用环境变量注入；这里给一个开发态默认值方便本地启动
    SECRET_KEY = os.environ.get("STOCKSIGNAL_SECRET", "dev-only-change-me-in-production")

    # JWT
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES_SECONDS = int(os.environ.get("JWT_EXPIRES_SECONDS", "3600"))  # 1 小时
    JWT_HEADER = "Authorization"
    JWT_PREFIX = "Bearer "

    # 数据库
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CORS（开发态默认放行所有，方便 Streamlit 联调；生产请收紧）
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    # 错误响应开关：生产绝不暴露内部
    EXPOSE_INTERNAL_ERROR = os.environ.get("EXPOSE_INTERNAL_ERROR", "0") == "1"

    # 认证限流（进程内内存滑动窗口）：防 login/register 爆破
    # 测试可通过 STOCKSIGNAL_RATE_LIMIT_ENABLED=0 关闭，或用 reset_rate_limit()
    RATE_LIMIT_ENABLED = os.environ.get("STOCKSIGNAL_RATE_LIMIT_ENABLED", "1") != "0"
    RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", "5"))      # 单 key 窗口内最大次数
    RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))  # 滑动窗口秒数
