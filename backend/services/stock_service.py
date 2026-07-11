"""
backend/services/stock_service.py
---------------------------------
股票搜索服务：支持代码 / 名称 / 拼音首字母 / 全拼 / 首字模糊匹配。

匹配优先级（score 越高排越前）：
  1000  代码精确匹配
   900  名称精确匹配
   800  代码前缀匹配
   700  名称前缀匹配
   600  拼音首字母精确匹配
   550  拼音首字母前缀匹配
   500  拼音全拼前缀匹配
   400  名称包含匹配
   300  拼音首字母包含匹配
   200  拼音全拼包含匹配
   100  首字模糊匹配
"""
from __future__ import annotations
from typing import List, Dict
from sqlalchemy import or_, select
from ..extensions import db
from ..models import Stock


def search_stocks(query: str, limit: int = 15) -> List[Dict]:
    """
    搜索股票，返回 [{code, name, market, score}] 按相关度排序。
    """
    q = query.strip().lower()
    if not q:
        return []

    results: List[Dict] = []

    # --- 纯数字 -> 代码匹配 ---
    if q.isdigit():
        exact = db.session.execute(
            select(Stock).where(Stock.code == q, Stock.is_active.is_(True))
        ).scalar_one_or_none()
        if exact:
            results.append({**exact.to_dict(), "score": 1000})

        prefix_rows = db.session.execute(
            select(Stock).where(
                Stock.code.startswith(q),
                Stock.code != q,
                Stock.is_active.is_(True),
            ).limit(limit * 2)
        ).scalars()
        for r in prefix_rows:
            results.append({**r.to_dict(), "score": 800})
    else:
        # --- 名称 / 拼音匹配 ---
        # 一次性查出候选集：名称 LIKE 或 拼音 LIKE
        candidates = db.session.execute(
            select(Stock).where(
                Stock.is_active.is_(True),
                or_(
                    Stock.name.startswith(q),
                    Stock.name.contains(q),
                    Stock.pinyin_initials.startswith(q),
                    Stock.pinyin_initials.contains(q),
                    Stock.pinyin_full.startswith(q),
                    Stock.pinyin_full.contains(q),
                ),
            ).limit(limit * 4)
        ).scalars()

        for r in candidates:
            name_l = r.name.lower()
            pi = (r.pinyin_initials or "").lower()
            pf = (r.pinyin_full or "").lower()
            score = 0

            if name_l == q:
                score = 900
            elif name_l.startswith(q):
                score = 700
            elif pi == q:
                score = 600
            elif pi.startswith(q):
                score = 550
            elif pf.startswith(q):
                score = 500
            elif q in name_l:
                score = 400
            elif q in pi:
                score = 300
            elif q in pf:
                score = 200
            elif len(q) == 1 and name_l.startswith(q):
                score = 100

            if score > 0:
                results.append({**r.to_dict(), "score": score})

    # 去重（同 code 取最高 score）
    seen: Dict[str, Dict] = {}
    for item in results:
        code = item["code"]
        if code not in seen or item["score"] > seen[code]["score"]:
            seen[code] = item

    # 排序 + 截断
    sorted_list = sorted(seen.values(), key=lambda x: (-x["score"], x["code"]))
    return sorted_list[:limit]


def get_stock_list(page: int = 1, per_page: int = 50, keyword: str = "") -> dict:
    """分页获取股票列表（管理后台用）。"""
    stmt = select(Stock).where(Stock.is_active.is_(True))
    if keyword:
        stmt = stmt.where(
            or_(
                Stock.code.contains(keyword),
                Stock.name.contains(keyword),
                Stock.pinyin_initials.contains(keyword),
            )
        )
    stmt = stmt.order_by(Stock.code.asc())

    total = db.session.execute(
        select(db.func.count()).select_from(stmt.subquery())
    ).scalar() or 0

    rows = db.session.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).scalars()

    return {
        "items": [r.to_dict() for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }
