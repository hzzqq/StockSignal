# -*- coding: utf-8 -*-
"""缓存维护：按保留期清理 + VACUUM（T-248 单一真理源）。

把原本散落/缺失的缓存清理收口到一处，供：
- clean_cache.py --include-db / --include-v2（手动）
- scripts/daily_snapshot.py 每日落盘后 best-effort 自动调用

覆盖对象（实证，见缓存体检）：
- data/cache.db        : daily_cache / index_cache / macro_cache / commodity_cache
                         （updated_at 为 ISO naive 文本；占 100MB，此前无保留期，只增不减）
- data/market_cache.db : market_indicator_cache（date 列；复用既有 clear_stale_cache 的
                         DELETE WHERE date<cutoff + VACUUM，该函数此前仅被测试调用、生产从不触发）
- data/news.db         : news（date 列）
- data/shepherd_cache        / data/shepherd_cache_v2 : 按 mtime 清理 CSV（v2 此前漏在默认范围外）

诚实语义：返回真实删除行数 / 释放字节；失败 warning 留痕绝不谎报；best-effort 不阻塞主流程。
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent.parent  # StockSignal 仓库根
DATA = HERE / "data"
DEFAULT_PRUNE_DAYS = 90

# cache.db 内各表 schema 统一为 (cache_key, data_json, updated_at)
CACHE_DB_TABLES = ["daily_cache", "index_cache", "macro_cache", "commodity_cache"]
NEWS_DB_TABLES = ["news"]


def _cutoff_date(days: int) -> str:
    """保留期截止日（含）：早于该日的行/文件清理。返回 YYYY-MM-DD。"""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def prune_sqlite_cache(
    db_path,
    tables: List[str],
    days: int = DEFAULT_PRUNE_DAYS,
    date_col: str = "updated_at",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """对 SQLite 库指定表按日期列做保留期清理；删除行 > 0 时 VACUUM 回收空间。

    - date_col 为 TEXT（cache.db 用 updated_at ISO；news 用 date YYYY-MM-DD）
    - cutoff = now - days；删除 date_col < cutoff 的行（边界日保留）
    - dry_run=True 仅统计不删、不 VACUUM
    返回 {db, deleted, freed_bytes, error}（诚实：freed_bytes 实测前后体积差）。
    """
    db_path = Path(db_path)
    res: Dict[str, Any] = {
        "db": str(db_path), "deleted": 0, "freed_bytes": 0,
        "error": None, "tables": tables, "date_col": date_col,
    }
    if not db_path.exists():
        res["error"] = "missing"
        return res
    size_before = db_path.stat().st_size
    cutoff = _cutoff_date(days)
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        for t in tables:
            try:
                cur = conn.execute(
                    f"DELETE FROM {t} WHERE {date_col} < ?", (cutoff,)
                )
                res["deleted"] += max(cur.rowcount or 0, 0)
            except sqlite3.OperationalError as e:
                if "no such table" in str(e).lower():
                    continue  # 该表从未写入，属预期
                res["error"] = f"{t}: {e}"
        if not dry_run:
            # 先提交删除，再 VACUUM（VACUUM 不允许在活动事务内执行，否则报
            # "cannot VACUUM from within a transaction" 并导致 DELETE 回滚——旧写法踩过）
            conn.commit()
            if res["deleted"] > 0:
                # 仅在有删除时才 VACUUM（避免无谓的独占锁，保护并发读取的老板服务）
                conn.execute("VACUUM")
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    size_after = db_path.stat().st_size if db_path.exists() else 0
    res["freed_bytes"] = max(size_before - size_after, 0)
    return res


def prune_shepherd_dirs(
    days: int = DEFAULT_PRUNE_DAYS,
    include_v2: bool = False,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """按 mtime 清理 shepherd_cache（及可选 shepherd_cache_v2）下超龄 CSV。

    这些「按股票代码缓存的日线 CSV」缺失会自动重新拉取，删了安全。
    返回 [{dir, removed, freed_bytes}]（removed 在 dry_run 下为预估，不实际删除）。
    """
    dirs = [DATA / "shepherd_cache"]
    if include_v2:
        dirs.append(DATA / "shepherd_cache_v2")
    cutoff = time.time() - days * 86400
    out: List[Dict[str, Any]] = []
    for d in dirs:
        removed, freed = 0, 0
        if d.exists():
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                if st.st_mtime < cutoff:
                    if dry_run:
                        removed += 1
                        freed += st.st_size
                    else:
                        try:
                            f.unlink()
                            removed += 1
                            freed += st.st_size
                        except OSError as exc:
                            # 单文件失败不影响其余（控制流不变）；T-317：必须留痕，
                            # 否则「清理了多少」与失败原因都无从诊断（权限/占用/只读）。
                            logger.warning("[cache_maintenance] 删除失败 %s: %s", f, exc)
        out.append({"dir": str(d), "removed": removed, "freed_bytes": freed})
    return out


def run_cache_maintenance(
    days: int = DEFAULT_PRUNE_DAYS,
    include_v2: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """统一缓存维护入口（单一真理源）。

    - cache.db 四表按 updated_at 保留期清理 + VACUUM（仅删除时）
    - market_cache.db 复用既有 clear_stale_cache（date 列 + VACUUM）
    - news.db 按 date 保留期清理
    - shepherd_cache（+可选 v2）按 mtime 清理
    返回报告 dict，含每源真实删除数 / 释放字节 / 错误。best-effort：单源失败不影响其余。
    """
    report: Dict[str, Any] = {
        "days": days, "dry_run": dry_run,
        "sqlite": [], "shepherd": [], "errors": [],
    }

    # 1) cache.db
    report["sqlite"].append(
        prune_sqlite_cache(DATA / "cache.db", CACHE_DB_TABLES, days, "updated_at", dry_run)
    )

    # 2) market_cache.db（复用既有 clear_stale_cache；懒导入避免硬依赖）
    try:
        from modules.market_cache import clear_stale_cache as _mclear
        size_before = (DATA / "market_cache.db").stat().st_size if (DATA / "market_cache.db").exists() else 0
        n = 0 if dry_run else _mclear(days)
        size_after = (DATA / "market_cache.db").stat().st_size if (DATA / "market_cache.db").exists() else 0
        report["sqlite"].append({
            "db": str(DATA / "market_cache.db"), "deleted": n,
            "freed_bytes": max(size_before - size_after, 0),
            "error": None, "via": "market_cache.clear_stale_cache",
        })
    except Exception as e:  # noqa: BLE001
        report["errors"].append(f"market_cache: {e}")

    # 3) news.db
    report["sqlite"].append(
        prune_sqlite_cache(DATA / "news.db", NEWS_DB_TABLES, days, "date", dry_run)
    )

    # 4) shepherd 缓存目录（CSV，mtime）
    report["shepherd"] = prune_shepherd_dirs(days, include_v2, dry_run)

    return report
