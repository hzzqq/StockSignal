"""
scripts/init_db.py
------------------
建表 + 写入一个 admin 和一个演示用户。

启动方式（任选其一）：
    cd backend
    python -m scripts.init_db

    # 或
    python scripts/init_db.py   （脚本会自行把 backend/ 加进 sys.path）

默认账号：
    admin  / Admin@123   （角色：admin）
    demo   / Demo@123    （角色：user，对应截图中"演示用户"）
"""
from __future__ import annotations
import os
import sys

# 允许 `python scripts/init_db.py` 直接跑
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app import create_app       # noqa: E402
from backend.extensions import db        # noqa: E402
from backend.models import User, SystemConfig  # noqa: E402
from backend.scripts.migrate_add_asset_type import migrate as migrate_asset_type  # noqa: E402
from backend.scripts.migrate_add_avatar import migrate as migrate_avatar  # noqa: E402
from backend.scripts.migrate_add_settings import migrate as migrate_settings  # noqa: E402
from backend.scripts.migrate_add_alert_type import migrate as migrate_alert_type  # noqa: E402


_DEFAULT_CONFIGS = [
    {"key": "cache_days", "value": "7", "description": "行情缓存天数"},
    {"key": "cache_hours_today", "value": "6", "description": "当日数据缓存小时数"},
    {"key": "jwt_expires_seconds", "value": "604800", "description": "JWT 过期时间（秒）"},
    {"key": "default_page_size", "value": "50", "description": "默认分页大小"},
    {"key": "search_limit", "value": "15", "description": "股票搜索最大返回数"},
]


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        # 历史库无 asset_type 列时自动补列（向后兼容）
        migrate_asset_type(app)
        # 历史库无 avatar 列时自动补列（向后兼容）
        migrate_avatar(app)
        # 历史库无 settings 列时自动补列（向后兼容）
        migrate_settings(app)
        # 历史库无 alert_type/params 列时自动补列（多维预警向后兼容）
        migrate_alert_type(app)

        seeds = [
            {"username": "admin", "password": "Admin@123", "role": "admin"},
            {"username": "demo",  "password": "Demo@123",  "role": "user"},
        ]
        for s in seeds:
            u = User.query.filter_by(username=s["username"]).first()
            if u is None:
                u = User(username=s["username"], role=s["role"])
                u.set_password(s["password"])
                db.session.add(u)
                print(f"[+] created user: {s['username']} ({s['role']})")
            else:
                print(f"[=] exists: {s['username']}")
        db.session.commit()

        # 系统配置种子
        for cfg in _DEFAULT_CONFIGS:
            existing = SystemConfig.query.filter_by(key=cfg["key"]).first()
            if existing is None:
                db.session.add(SystemConfig(**cfg))
                print(f"[+] created config: {cfg['key']}")
        db.session.commit()

        print("done.")


if __name__ == "__main__":
    main()
