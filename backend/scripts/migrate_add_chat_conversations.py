"""
backend/scripts/migrate_add_chat_conversations.py
-------------------------------------------------
T-311 星辰 AI 多会话建表迁移（幂等）：``chat_conversations``

- 仅在 SQLite 后端执行（后端使用 sqlite:///...）。
- 依赖 db.create_all() 幂等建表（已存在的表不会重建）。
- init_db.py 会在建表后自动调用本迁移；也可单独运行：
    python -m backend.scripts.migrate_add_chat_conversations

背景：ChatConversation 模型于 T-311（星辰 AI 多会话）引入，历史库不会自动获得
新表 → /api/chat/conversations* 报 `no such table: chat_conversations`。
一次性数据导入：仅当本次迁移**新建了表**时，把旧单记录表 chat_history 中
非空历史导入为各用户的「历史对话」会话；旧记录此后保留不动（只读兼容）。
即使本迁移未运行，前端首次访问也会自愈式导入（见 53 页 restore 逻辑），双保险。
"""
from __future__ import annotations

import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import inspect  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
# 导入即确保模型注册到 db.Model.metadata，create_all 才能识别
from backend.models import ChatConversation, ChatHistory  # noqa: E402


def _parse_messages(raw) -> list:
    """旧单记录 JSON 文本 → 消息列表（损坏/非列表诚实降级为空，不抛）。"""
    if not raw:
        return []
    try:
        msgs = json.loads(raw)
    except Exception:
        return []
    return msgs if isinstance(msgs, list) else []


def migrate(app) -> bool:
    """执行建表迁移；返回是否新增了表（幂等，已存在的表不会重建、不重复导入）。

    注意：历史导入与建表绑定（仅「本次新建了表」时执行一次），因此用户后来
    删除全部会话后重跑本脚本，不会把已删除的历史再导回来（防僵尸复活）。
    """
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite"):
        return False
    tables = [ChatConversation.__table__]
    target_names = {t.name for t in tables}
    with app.app_context():
        inspector = inspect(db.engine)
        existing_before = set(inspector.get_table_names())
        if target_names.issubset(existing_before):
            return False  # 表已存在，跳过
        db.metadata.create_all(db.engine, tables=tables)
        # 重新 inspect：Inspector 会缓存表名，复用同一实例会读到建表前的旧快照，
        # 导致明明建了表却返回 changed=False（诚实性）。
        existing_after = set(inspect(db.engine).get_table_names())
        created = existing_after - existing_before
        imported = 0
        if created:
            # 一次性导入：旧单记录非空 → 各建一个「历史对话」会话
            for rec in ChatHistory.query.all():
                msgs = _parse_messages(rec.messages)
                if not msgs:
                    continue
                db.session.add(ChatConversation(
                    user_id=rec.user_id,
                    title="历史对话",
                    messages=json.dumps(msgs, ensure_ascii=False),
                ))
                imported += 1
            if imported:
                db.session.commit()
                app.logger.info("已从旧单记录导入 %s 个「历史对话」会话", imported)
        return bool(created)


def main() -> None:
    app = create_app()
    with app.app_context():
        changed = migrate(app)
    print("[+] 星辰 AI 多会话表迁移：" + ("已完成建表（含历史导入）" if changed else "表已存在，跳过"))


if __name__ == "__main__":
    main()
