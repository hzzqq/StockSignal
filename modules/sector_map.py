# -*- coding: utf-8 -*-
"""全行业实体映射层（一期：90 个纯行业）的 SQLite 持久化。

诚实红线：
- 与 ``sectors`` 精编表同库（data/news.db），但**绝不修改 sectors 表任何一行**。
- keywords 分级：L0 = 板块名本身；L1 = 内置少量常见同义词词典；不做 LLM 精编
  （931 个板块无法逐一精编，诚实标注 rule_l0 / rule_l1）。
- 不编造成分股：member_count=0 且 stock_codes='' 的行必须 fetch_status='failed'。
"""
from __future__ import annotations

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

# 表结构与连接：与 modules/macro_store.py 的 _get_conn 模式对齐（守卫白名单）。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sector_entity_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_name TEXT NOT NULL,
    board_code TEXT,
    board_type TEXT NOT NULL,
    keywords TEXT DEFAULT '',
    stock_codes TEXT DEFAULT '',
    member_count INTEGER DEFAULT 0,
    source TEXT DEFAULT '',
    fetch_status TEXT DEFAULT 'ok',
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(board_name, board_type)
);
CREATE INDEX IF NOT EXISTS idx_sector_entity_map_name
    ON sector_entity_map(board_name);
CREATE INDEX IF NOT EXISTS idx_sector_entity_map_status
    ON sector_entity_map(fetch_status);
"""

# L1 同义词词典：只收少量常见行业，避免伪装成「全量精编」。
_SYNONYMS = {
    "半导体": "芯片,集成电路,晶圆",
    "光伏": "太阳能,硅料,组件",
    "白酒": "酿酒,酒类",
    "证券": "券商",
    "银行": "银保",
    "煤炭": "动力煤,焦煤",
    "医药": "生物医药,创新药",
}


def _db_path() -> str:
    """默认与 news.py 的 NewsDB 同库；测试可用 SECTOR_MAP_DB_PATH 隔离。"""
    override = os.environ.get("SECTOR_MAP_DB_PATH")
    if override:
        return override
    base = os.environ.get("SS_DATA_DIR") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "news.db")


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def init_table() -> None:
    """建表（幂等）。_get_conn 内已 executescript，这里仅显式提交并关闭。"""
    conn = _get_conn()
    try:
        conn.commit()
    finally:
        conn.close()


def build_keywords(name: str) -> tuple[str, str]:
    """返回 (keywords, source)：L0 板块名 / L1 同义词词典。"""
    key = (name or "").strip()
    syn = _SYNONYMS.get(key)
    if syn:
        return ((key + "," + syn) if key else syn), "rule_l1"
    return key, "rule_l0"


def upsert_sector(row: dict) -> bool:
    """幂等写入一个板块映射；keywords/source 缺省时按 L0/L1 自动生成。"""
    name = (row.get("board_name") or "").strip()
    if not name:
        logger.warning("[sector_map] upsert 缺少 board_name: %r", row)
        return False
    board_type = (row.get("board_type") or "industry").strip() or "industry"
    keywords = row.get("keywords") or ""
    source = (row.get("source") or "").strip()
    if not keywords:
        keywords, source = build_keywords(name)

    codes = row.get("stock_codes") or ""
    if not isinstance(codes, str):
        codes = ",".join(str(c) for c in codes)
    member_count = row.get("member_count")
    if member_count is not None:
        member_count = int(member_count)

    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO sector_entity_map
                (board_name, board_code, board_type, keywords, stock_codes,
                 member_count, source, fetch_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(board_name, board_type) DO UPDATE SET
                board_code=excluded.board_code,
                keywords=excluded.keywords,
                stock_codes=excluded.stock_codes,
                member_count=excluded.member_count,
                source=excluded.source,
                fetch_status=excluded.fetch_status,
                updated_at=datetime('now','localtime')
        """, (
            name,
            (row.get("board_code") or "").strip() or None,
            board_type,
            keywords,
            codes,
            member_count,
            source,
            (row.get("fetch_status") or "ok").strip(),
        ))
        conn.commit()
        return True
    finally:
        conn.close()


def resolve_sector(name: str) -> dict | None:
    """先查 sectors 精编表（manual），miss 再查 sector_entity_map。"""
    key = (name or "").strip()
    if not key:
        return None

    conn = _get_conn()
    try:
        try:
            manual = conn.execute(
                "SELECT name, keywords, stock_codes, description "
                "FROM sectors WHERE name=?",
                (key,),
            ).fetchone()
        except sqlite3.OperationalError:
            logger.debug("[sector_map] sectors 表不可用，跳过精编查询: %s", key)
            manual = None

        if manual is not None:
            return {
                "name": manual["name"],
                "board_code": None,
                "board_type": "industry",
                "keywords": manual["keywords"],
                "stock_codes": manual["stock_codes"],
                "member_count": None,
                "source": "manual",
                "fetch_status": "ok",
                "description": manual["description"],
                "updated_at": None,
            }

        row = conn.execute(
            "SELECT board_name, board_code, board_type, keywords, stock_codes, "
            "member_count, source, fetch_status, updated_at "
            "FROM sector_entity_map WHERE board_name=? "
            "ORDER BY board_type LIMIT 1",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "name": row["board_name"],
            "board_code": row["board_code"],
            "board_type": row["board_type"],
            "keywords": row["keywords"],
            "stock_codes": row["stock_codes"],
            "member_count": row["member_count"],
            "source": row["source"],
            "fetch_status": row["fetch_status"],
            "description": None,
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def list_sectors(status: str | None = None) -> list:
    """列出 sector_entity_map；status 可选（ok|failed|stale）。"""
    cols = ("board_name, board_code, board_type, keywords, stock_codes, "
            "member_count, source, fetch_status, updated_at")
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                f"SELECT {cols} FROM sector_entity_map "
                "WHERE fetch_status=? ORDER BY board_name", (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {cols} FROM sector_entity_map ORDER BY board_name"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_failed(name: str) -> None:
    """标记抓取失败；行不存在时建 failed 空行，供 resume 识别。不编造 codes。"""
    key = (name or "").strip()
    if not key:
        logger.warning("[sector_map] mark_failed 空名称")
        return
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE sector_entity_map SET fetch_status='failed' WHERE board_name=?",
            (key,),
        )
        if cur.rowcount == 0:
            keywords, source = build_keywords(key)
            conn.execute(
                "INSERT INTO sector_entity_map "
                "(board_name, board_type, keywords, stock_codes, member_count, "
                " source, fetch_status) VALUES (?, 'industry', ?, '', 0, ?, 'failed')",
                (key, keywords, source),
            )
        conn.commit()
    finally:
        conn.close()


def sector_map_stats() -> dict:
    """统计映射表状态分布 + sectors 精编行数（不修改任何数据）。"""
    conn = _get_conn()
    try:
        stats = {"total": 0, "ok": 0, "failed": 0, "stale": 0}
        for r in conn.execute(
            "SELECT fetch_status, COUNT(*) AS n "
            "FROM sector_entity_map GROUP BY fetch_status"
        ).fetchall():
            st = r["fetch_status"] or "unknown"
            stats[st] = r["n"]
            stats["total"] += r["n"]
        try:
            stats["manual_sectors"] = conn.execute(
                "SELECT COUNT(*) AS n FROM sectors"
            ).fetchone()["n"]
        except sqlite3.OperationalError:
            logger.debug("[sector_map] sectors 表不可用，manual_sectors 记为 0")
            stats["manual_sectors"] = 0
        return stats
    finally:
        conn.close()
