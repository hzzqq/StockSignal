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
from typing import List, Dict, Optional
from sqlalchemy import or_, select
from ..extensions import db
from ..models import Stock


# ---------------------------------------------------------------------------
# 纯逻辑辅助函数（无 DB / 网络依赖，便于离线单测，并对 None/空输入做防御）
# ---------------------------------------------------------------------------

def normalize_symbol(code: Optional[str]) -> str:
    """
    将股票代码规范化为带市场前缀的完整符号。

    约定（A 股）：
      6xxxxx / 688xxx -> sh（上交所 / 科创板）
      0xxxxx / 3xxxxx -> sz（深交所 / 创业板）
      8xxxxx / 4xxxxx -> bj（北交所）
      若已带 sh/sz/bj 前缀则原样返回（小写）。
    空 / None 输入返回空字符串，绝不抛异常。
    """
    if not code:
        return ""
    code = str(code).strip()
    if not code:
        return ""
    lowered = code.lower()
    if lowered.startswith(("sh", "sz", "bj")):
        return lowered
    if code[0] == "6":
        return "sh" + code
    if code[0] in ("0", "3"):
        return "sz" + code
    if code[0] in ("8", "4"):
        return "bj" + code
    return code


def filter_by_market(items: Optional[List[Dict]], market: Optional[str]) -> List[Dict]:
    """
    按市场过滤股票列表。对 None / 空输入安全：
      - items 为空 -> 返回 []
      - market 为空 -> 原样返回（副本）
      - 单条记录缺 'market' 键不会抛 KeyError
    """
    if not items:
        return []
    if not market:
        return list(items)
    return [it for it in items if isinstance(it, dict) and it.get("market") == market]


def compute_match_score(name: Optional[str],
                        pinyin_initials: Optional[str],
                        pinyin_full: Optional[str],
                        query: Optional[str]) -> int:
    """
    纯函数：根据名称 / 拼音与查询词计算匹配分（见模块顶部优先级表）。
    所有入参均为 None 安全；查询为空时返回 0（视为无匹配）。
    """
    q = (query or "").strip().lower()
    if not q:
        return 0

    name_l = (name or "").lower()
    pi = (pinyin_initials or "").lower()
    pf = (pinyin_full or "").lower()

    if name_l == q:
        return 900
    if name_l.startswith(q):
        return 700
    if pi == q:
        return 600
    if pi.startswith(q):
        return 550
    if pf.startswith(q):
        return 500
    if q in name_l:
        return 400
    if q in pi:
        return 300
    if q in pf:
        return 200
    if len(q) == 1 and name_l.startswith(q):
        return 100
    return 0


def rank_and_dedup(results: Optional[List[Dict]], limit: int = 15) -> List[Dict]:
    """
    纯函数：对候选结果去重（同 code 取最高 score）、按相关度排序并截断。
    对 None / 空 / 缺键记录全部防御：
      - results 为空 -> []
      - 单条非 dict、缺 'code'、缺 'score' 均跳过或安全取默认
    """
    if not results:
        return []
    seen: Dict[str, Dict] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if code is None:
            continue
        score = item.get("score", 0)
        if code not in seen or score > seen[code].get("score", 0):
            seen[code] = item

    sorted_list = sorted(
        seen.values(),
        key=lambda x: (-x.get("score", 0), x.get("code", "")),
    )
    if limit and limit > 0:
        return sorted_list[:limit]
    return sorted_list


def search_stocks(query: str, limit: int = 15) -> List[Dict]:
    """
    搜索股票，返回 [{code, name, market, score}] 按相关度排序。
    """
    q = (query or "").strip().lower()
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
            score = compute_match_score(r.name, r.pinyin_initials, r.pinyin_full, q)
            if score > 0:
                results.append({**r.to_dict(), "score": score})

    # 去重（同 code 取最高 score）+ 排序 + 截断
    return rank_and_dedup(results, limit)


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
