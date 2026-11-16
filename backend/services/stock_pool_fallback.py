"""
股票池兜底：`stocks` 表未灌入时，用 v1 自建的真实股票池支撑搜索。

背景（2026-11-16 实证）：`backend/data/app.db` 的 `stocks` 表为 0 行，
`GET /api/stocks/search?q=600519|贵州茅台|gzmt` 一律返回 `[]`，
v1 的 `_search_via_backend` 因此永远回落本地 `lookup_code`；
v2 若直接接这个端点，会表现为「股票搜索永远无结果」。

本模块不改表、不做数据迁移、不写 gitignored 数据：只读 v1 的股票池
（`data/cache.db::all_stocks`，5191 条真实 A 股 code/name），预计算拼音后复用
`stock_service.compute_match_score` / `rank_and_dedup`，与库内搜索保持同一套评分口径。

诚实红线：
 - 池文件缺失 / 损坏 / 无有效行 -> 返回空，绝不编造股票、绝不补零、不 fallback 到假样例；
 - 返回结构与 `Stock.to_dict()` + `score` 一致，前端契约不变；
 - 仅在 `stocks` 表为空时启用；表一旦灌入真实数据即自动让位。
"""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from .pinyin_util import to_initials, to_full_pinyin
from .stock_service import compute_match_score, rank_and_dedup

# backend/services/ -> backend/ -> 仓库根
_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DB = _ROOT / "data" / "cache.db"


def _market_of(code: str) -> str:
    """与 v1 market_utils.guess_exchange 同口径（6->SH / 0,3->SZ / 4,8,9->BJ）。"""
    if not code:
        return "A"
    head = code[0]
    if head == "6":
        return "SH"
    if head in ("0", "3"):
        return "SZ"
    if head in ("4", "8", "9"):
        return "BJ"
    return "A"


@lru_cache(maxsize=1)
def load_stock_pool() -> tuple[dict, ...]:
    """只读加载股票池并预计算拼音；任何异常都诚实返回空 tuple。

    返回 tuple 而非 list：作为 lru_cache 结果不可被调用方意外修改。
    """
    if not _CACHE_DB.exists():
        return ()
    try:
        uri = f"file:{_CACHE_DB.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            row = con.execute(
                "SELECT data_json FROM all_stocks WHERE cache_key='all' LIMIT 1"
            ).fetchone()
        finally:
            con.close()
        if not row or not row[0]:
            return ()
        raw = json.loads(row[0])
        if not isinstance(raw, list):
            return ()
        out: list[dict] = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            code = str(it.get("code") or "").strip()
            name = str(it.get("name") or "").strip()
            if len(code) != 6 or not code.isdigit() or not name:
                continue
            out.append({
                "code": code,
                "name": name,
                "market": _market_of(code),
                "asset_type": "stock",
                "pinyin_initials": to_initials(name),
                "pinyin_full": to_full_pinyin(name),
            })
        return tuple(out)
    except (sqlite3.Error, ValueError, TypeError, OSError):
        return ()


def pool_size() -> int:
    """股票池条目数（0 表示不可用，供上层如实提示）。"""
    return len(load_stock_pool())


def search_stock_pool(query: str, limit: int = 15) -> list[dict]:
    """与 `stock_service.search_stocks` 同口径：代码 1000/800，名称与拼音 900..100。"""
    q = (query or "").strip().lower()
    if not q:
        return []
    pool = load_stock_pool()
    if not pool:
        return []

    results: list[dict] = []
    if q.isdigit():
        # 数字只按代码匹配，不拿代码去撞名称，避免「600」命中一堆无关票
        for it in pool:
            if it["code"] == q:
                score = 1000
            elif it["code"].startswith(q):
                score = 800
            else:
                continue
            results.append({**it, "score": score})
    else:
        for it in pool:
            score = compute_match_score(
                it["name"], it["pinyin_initials"], it["pinyin_full"], q
            )
            if score > 0:
                results.append({**it, "score": score})

    return rank_and_dedup(results, limit)
