"""
backend/scripts/migrate_add_trading.py
--------------------------------------
实盘交易 & 智能条件单 4 张表建表迁移（幂等）：
  real_accounts / real_positions / real_orders / conditional_orders

- 仅在 SQLite 后端执行（后端使用 sqlite:///...）。
- 依赖 db.create_all() 幂等建表（已存在的表不会重建）。
- init_db.py 会在建表后自动调用本迁移；也可单独运行：
    python -m backend.scripts.migrate_add_trading
"""
from __future__ import annotations

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import inspect  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
# 导入即确保 4 个模型注册到 db.Model.metadata，create_all 才能识别
from backend.models import (  # noqa: E402
    RealAccount, RealOrder, RealPosition, ConditionalOrder,
)


def migrate(app) -> bool:
    """执行建表迁移。返回是否新增了表（幂等，已存在的表不会重建）。"""
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite"):
        return False
    tables = [
        RealAccount.__table__,
        RealPosition.__table__,
        RealOrder.__table__,
        ConditionalOrder.__table__,
    ]
    target_names = {t.name for t in tables}
    with app.app_context():
        inspector = inspect(db.engine)
        existing_before = set(inspector.get_table_names())
        if target_names.issubset(existing_before):
            return False  # 4 张表已存在，跳过
        db.metadata.create_all(db.engine, tables=tables)
        existing_after = set(inspector.get_table_names())
        created = existing_after - existing_before
        if created:
            app.logger.info("已创建交易表: %s", sorted(created))
        return bool(created)


def main() -> None:
    app = create_app()
    with app.app_context():
        changed = migrate(app)
    print("[+] 交易表迁移：" + ("已完成建表" if changed else "表已存在，跳过"))


if __name__ == "__main__":
    main()
