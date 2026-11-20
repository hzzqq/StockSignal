"""
backend/scripts/migrate_add_asset_type.py
-----------------------------------------
一次性迁移：为 stocks 表新增 asset_type 列（若不存在）。

- 仅在 SQLite 后端执行（后端使用 sqlite:///...）。
- 用 PRAGMA table_info 探测列是否存在，缺失则 ALTER TABLE 加列，
  带默认值 'stock'，向后兼容（历史记录默认 stock）。
- init_db.py 会在建表后自动调用本迁移；也可单独运行：
    python -m backend.scripts.migrate_add_asset_type
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
    from backend.db_dialect import Dialect, column_exists_sql, dialect_from_url

    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    dialect = dialect_from_url(uri)

    if dialect is Dialect.POSTGRESQL:
        # PostgreSQL 分支：列存在性探测经方言层生成 information_schema SQL
        from sqlalchemy import text

        from backend.extensions import db

        with db.engine.begin() as conn:
            probe_sql, probe_params = column_exists_sql(Dialect.POSTGRESQL, "stocks", "asset_type")
            if conn.execute(text(probe_sql), probe_params).fetchone() is not None:
                return False
            conn.execute(text(
                "ALTER TABLE stocks ADD COLUMN asset_type VARCHAR(16) NOT NULL DEFAULT 'stock'"
            ))
        return True

    if not uri.startswith("sqlite"):
        # 非 SQLite 且非 PG 的 URL（无法识别）原样跳过
        return False

    db_path = uri.replace("sqlite:///", "", 1)
    if not db_path:
        return False

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(stocks)")
        cols = {row[1] for row in cur.fetchall()}
        if "asset_type" in cols:
            return False
        # SQLite 支持带默认值加列（NOT NULL + DEFAULT 仅对新增行生效，
        # 已有行自动填充默认值 'stock'）
        cur.execute(
            "ALTER TABLE stocks ADD COLUMN asset_type VARCHAR(16) NOT NULL DEFAULT 'stock'"
        )
        conn.commit()
        return True
    finally:
        conn.close()


def main() -> None:
    app = create_app()
    with app.app_context():
        changed = migrate(app)
    print("[+] asset_type 迁移：" + ("已加列" if changed else "列已存在，跳过"))


if __name__ == "__main__":
    main()
