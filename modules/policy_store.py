# -*- coding: utf-8 -*-
"""政策原文持久化层（policy_documents 表，独占 data/policy.db）。

背景：政策原文抓取层需要独立落盘，避免与 news.db / macro_history.db 等
并行数据层抢写锁。本模块**只**读写 data/policy.db（可用 POLICY_DB_PATH 覆盖
供测试隔离，生产默认独占 policy.db）。

诚实红线：
- 取不到的字段一律存 None，绝不编造；
- publish_date 是**数据原文日期**，绝不拿 crawled_at / now() 兜底；
- crawled_at 单独记录抓取时间，与 publish_date 语义严格分离；
- is_fresh 解析失败一律判过期（宁可重取，不吃坏数据）。

表结构：
    policy_documents(
        policy_id TEXT PK,        -- md5(source_url)
        title TEXT NOT NULL,
        issuing_body TEXT,
        doc_number TEXT,
        publish_date TEXT,        -- 数据原文日期，可空
        source_url TEXT NOT NULL,
        source TEXT,              -- gov.cn | ndrc
        body_text TEXT,
        body_source TEXT,         -- html | attachment | none
        content_hash TEXT,
        crawled_at TEXT NOT NULL  -- 抓取时间（不是数据日期）
    )
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_documents (
    policy_id    TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    issuing_body TEXT,
    doc_number   TEXT,
    publish_date TEXT,
    source_url   TEXT NOT NULL,
    source       TEXT,
    body_text    TEXT,
    body_source  TEXT,
    content_hash TEXT,
    crawled_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_documents_publish_date
    ON policy_documents(publish_date);
"""

_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "policy.db",
)


def _db_path() -> str:
    """库路径：生产独占 data/policy.db；POLICY_DB_PATH 仅供测试隔离覆盖。"""
    return os.environ.get("POLICY_DB_PATH") or _DEFAULT_DB


def _get_conn() -> sqlite3.Connection:
    """连接工厂（守卫白名单函数，连接由调用方负责关闭）。"""
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


def _content_hash(doc: dict) -> str:
    """内容指纹：仅由业务内容字段构成（不含抓取时间），内容不变则 hash 不变。"""
    parts = [
        str(doc.get("title") or ""),
        str(doc.get("publish_date") or ""),
        str(doc.get("doc_number") or ""),
        str(doc.get("body_text") or ""),
        str(doc.get("issuing_body") or ""),
    ]
    return hashlib.md5("\u241f".join(parts).encode("utf-8")).hexdigest()


def upsert_policy(doc: dict) -> bool:
    """幂等写入一条政策。

    返回 True=新写入/内容有更新；False=内容指纹未变（skipped）或入参非法。
    publish_date 严格取 doc 原文，缺失存 None —— 绝不写 now()。
    """
    if not isinstance(doc, dict):
        return False
    source_url = doc.get("source_url")
    title = doc.get("title")
    if not source_url or not title:
        return False
    policy_id = hashlib.md5(str(source_url).encode("utf-8")).hexdigest()
    c_hash = _content_hash(doc)
    crawled_at = datetime.now().isoformat()
    conn = _get_conn()
    try:
        with conn:
            row = conn.execute(
                "SELECT content_hash FROM policy_documents WHERE policy_id = ?",
                (policy_id,),
            ).fetchone()
            if row is not None and row["content_hash"] == c_hash:
                return False  # 内容未变 → 跳过，不刷新 crawled_at
            conn.execute(
                "INSERT OR REPLACE INTO policy_documents"
                "(policy_id, title, issuing_body, doc_number, publish_date, "
                "source_url, source, body_text, body_source, content_hash, crawled_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    policy_id,
                    str(title),
                    doc.get("issuing_body") or None,
                    doc.get("doc_number") or None,
                    doc.get("publish_date") or None,  # 原文缺失 → None，绝不 now() 兜底
                    str(source_url),
                    doc.get("source") or None,
                    doc.get("body_text") or None,
                    doc.get("body_source") or None,
                    c_hash,
                    crawled_at,
                ),
            )
        return True
    except sqlite3.Error as e:  # noqa: BLE001 - 落盘失败不阻断抓取主流程
        logger.warning(f"[policy_store] upsert 失败 policy_id={policy_id}: {e}")
        return False
    finally:
        conn.close()


def read_recent(limit: int = 20) -> list[dict]:
    """按 publish_date 倒序读最近 N 条；空库返回 []。"""
    try:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT policy_id, title, issuing_body, doc_number, publish_date, "
                "source_url, source, body_text, body_source, content_hash, crawled_at "
                "FROM policy_documents "
                "ORDER BY COALESCE(publish_date, '') DESC, crawled_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:  # noqa: BLE001
        logger.warning(f"[policy_store] read_recent 失败: {e}")
        return []
    return [
        {
            "policy_id": r["policy_id"],
            "title": r["title"],
            "issuing_body": r["issuing_body"],
            "doc_number": r["doc_number"],
            "publish_date": r["publish_date"],
            "source_url": r["source_url"],
            "source": r["source"],
            "body_text": r["body_text"],
            "body_source": r["body_source"],
            "content_hash": r["content_hash"],
            "crawled_at": r["crawled_at"],
        }
        for r in rows
    ]


def policy_store_stats() -> dict:
    """库内统计（供运维/健康页展示）。"""
    try:
        conn = _get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM policy_documents").fetchone()[0]
            by_source = conn.execute(
                "SELECT source, COUNT(*) AS n FROM policy_documents GROUP BY source"
            ).fetchall()
            latest = conn.execute(
                "SELECT MAX(publish_date) FROM policy_documents"
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error as e:  # noqa: BLE001
        logger.warning(f"[policy_store] 统计失败: {e}")
        return {"total": 0, "by_source": {}, "latest_publish_date": None}
    return {
        "total": int(total),
        "by_source": {(r["source"] or "unknown"): int(r["n"]) for r in by_source},
        "latest_publish_date": latest,
    }


def is_fresh(date_str: str | None, ttl_days: int = 45) -> bool:
    """按数据原文日期判定是否仍在 TTL 内。解析失败 → False（判过期，宁可重取）。"""
    if not date_str:
        return False
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        # ui_audit_exempt: 日期解析失败判过期，宁可重取也不吃坏数据
        return False
    return (datetime.now() - d) <= timedelta(days=ttl_days)
