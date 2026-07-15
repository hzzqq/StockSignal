"""
backend/scripts/migrate_add_settings.py
---------------------------------------
一次性迁移：为 users 表新增 settings 列（若不存在）。

- 仅在 SQLite 后端执行。
- 用 PRAGMA table_info 探测列是否存在，缺失则 ALTER TABLE 加 TEXT 可空列。
- init_db.py 会在建表后自动调用本迁移；也可单独运行：
    python -m backend.scripts.migrate_add_settings
"""
from __future__ import annotations

import os
import sqlite3
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app import create_app  # noqa: E402


def migrate(app) -> bool:
    """执行迁移。返回是否发生了加列操作。"""
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite"):
        return False

    db_path = uri.replace("sqlite:///", "", 1)
    if not db_path:
        return False

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}
        if "settings" in cols:
            return False
        cur.execute("ALTER TABLE users ADD COLUMN settings TEXT")
        conn.commit()
        return True
    finally:
        conn.close()


def main() -> None:
    app = create_app()
    with app.app_context():
        changed = migrate(app)
    print("[+] settings 迁移：" + ("已加列" if changed else "列已存在，跳过"))


if __name__ == "__main__":
    main()
