"""
backend/scripts/import_stocks.py
--------------------------------
从 data/cache.db 的 all_stocks 缓存中导入全部 A 股基础信息到后端 app.db。
同时预计算每只股票的拼音首字母和全拼，用于搜索。

运行：python -m backend.scripts.import_stocks
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

# 支持 python -m backend.scripts.import_stocks 和 python import_stocks.py 两种运行方式
if __package__ is None or __package__ == "":
    _backend_dir = str(Path(__file__).resolve().parent.parent)
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)

from backend.extensions import db
from backend.models import Stock
from backend.services.pinyin_util import to_initials, to_full_pinyin


# A 股代码段过滤规则
def _classify_market(code: str) -> str:
    """根据代码判断市场：SH / SZ / A。"""
    if code.startswith("6"):
        return "SH"
    elif code.startswith("0") or code.startswith("3"):
        return "SZ"
    elif code.startswith("8") or code.startswith("4"):
        return "BJ"
    return "A"


def main():
    from backend.app import create_app
    app = create_app()

    # 找到前端 cache.db
    project_root = Path(__file__).resolve().parent.parent.parent
    cache_db = project_root / "data" / "cache.db"

    if not cache_db.exists():
        print(f"[!] cache.db not found at {cache_db}")
        print("    Please run the Streamlit app once first to generate stock cache.")
        return

    # 读取 all_stocks 缓存
    conn = sqlite3.connect(str(cache_db))
    cursor = conn.execute(
        "SELECT data_json FROM all_stocks WHERE cache_key = 'all' LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        print("[!] No stock data found in cache.db (all_stocks table)")
        return

    stocks_data = json.loads(row[0])
    print(f"[+] Loaded {len(stocks_data)} stocks from cache.db")

    with app.app_context():
        db.create_all()

        # 清空旧数据
        db.session.query(Stock).delete()
        db.session.commit()

        batch = []
        for item in stocks_data:
            code = item.get("code", "").strip()
            name = item.get("name", "").strip()
            if not code or not name:
                continue

            # 跳过非 6 位数字代码（排除指数/基金等）
            if not code.isdigit() or len(code) != 6:
                continue

            market = _classify_market(code)
            pi = to_initials(name)
            pf = to_full_pinyin(name)

            batch.append(Stock(
                code=code,
                name=name,
                market=market,
                pinyin_initials=pi,
                pinyin_full=pf,
                is_active=True,
            ))

        # 去重（同 code 保留第一条）
        seen_codes = set()
        deduped = []
        for s in batch:
            if s.code not in seen_codes:
                seen_codes.add(s.code)
                deduped.append(s)

        # 批量插入
        db.session.bulk_save_objects(deduped)
        db.session.commit()

        count = db.session.query(Stock).count()
        print(f"[+] Imported {count} stocks into app.db")
        print(f"    Sample: {batch[0].code} {batch[0].name} ({batch[0].pinyin_initials})")


if __name__ == "__main__":
    main()
