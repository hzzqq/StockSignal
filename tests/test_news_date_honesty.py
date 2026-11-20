# -*- coding: utf-8 -*-
"""tests/test_news_date_honesty.py

新闻数据日期诚实性 + 重大预警有效性守卫（2026-11-20）。

锁定三缺陷不回退：
1. 取数源日期禁止用 now_cst_str/today 兜底——源无日期必须留空；
2. save_news 必须把 sentiment 产出的 is_major 落库，且 NaT/"NaT" 日期统一转空串；
3. alert_check 必须按 inserted_at（真实入库时刻）过滤，能查到当天重大新闻。
"""
import ast
from pathlib import Path

import pandas as pd
import pytest

from modules.news import NewsDatabase, EventMiner

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def db(tmp_path, monkeypatch):
    """每例独立隔离库，绝不触碰生产 data/news.db。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    return NewsDatabase()


# ---------- 缺陷1：取数源日期 today 兜底 ----------

def test_no_today_fallback_for_news_date_source():
    """AST 守卫：_news_io.py 中不得出现把 now_cst_str 结果赋给日期字段的写法。"""
    src = (ROOT / "modules" / "_news_io.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        val = node.value
        if val is None:
            continue
        # 精确检测：把 now_cst_str("%Y-%m-%d") 当发布日期赋给 date 字段。
        # 排除 now_cst_str("%Y%m%d") —— 那是传给 ak.news_cctv 的查询入参（请求当天联播），
        # 不是新闻数据日期；两者靠格式串是否带连字符区分。
        fmt_with_dash = False
        for sub in ast.walk(val):
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", "") == "now_cst_str":
                for arg in sub.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "-" in arg.value:
                        fmt_with_dash = True
        if not fmt_with_dash:
            continue
        for t in targets:
            t_src = ast.dump(t)
            if "date_str" in t_src or ("'date'" in t_src) or ('"date"' in t_src):
                offenders.append(getattr(node, "lineno", "?"))
    assert not offenders, (
        "取数源存在用 today 兜底新闻日期（诚实红线）：行 " + ", ".join(map(str, offenders))
    )


def test_caixin_source_has_no_fabricated_date():
    """财新接口无日期字段，_fetch_caixin 必须把 date 置空而非编造今日。"""
    src = (ROOT / "modules" / "_news_io.py").read_text(encoding="utf-8")
    fn_src = src.split("def _fetch_caixin(")[1].split("def _fetch_cctv(")[0]
    assert 'df["date"] = ""' in fn_src, "财新源 date 未留空"
    assert 'now_cst_str' not in fn_src, "财新源仍用 today 编造日期"


# ---------- 缺陷2：is_major 落库 + 日期诚实 ----------

def test_save_news_persists_is_major(db):
    df = pd.DataFrame([
        {"title": "重大利好A", "content": "", "url": "u1", "source": "s",
         "date": "2026-11-20 00:00:00", "is_major": True, "type": "正面", "sentiment_score": 0.8},
        {"title": "普通B", "content": "", "url": "u2", "source": "s",
         "date": "2026-11-20 00:00:00", "is_major": False, "type": "中性", "sentiment_score": 0.1},
    ])
    db.save_news(df)
    import sqlite3
    conn = sqlite3.connect(str(Path(db.db_path)))
    rows = conn.execute("SELECT title, is_major FROM news ORDER BY id").fetchall()
    conn.close()
    assert rows == [("重大利好A", 1), ("普通B", 0)]


def test_save_news_nat_date_becomes_empty(db):
    df = pd.DataFrame([
        {"title": "NaT日期", "content": "", "url": "u1", "source": "s",
         "date": pd.NaT, "is_major": False, "type": "中性", "sentiment_score": 0.0},
        {"title": "字符串NaT日期", "content": "", "url": "u2", "source": "s",
         "date": "NaT", "is_major": False, "type": "中性", "sentiment_score": 0.0},
    ])
    db.save_news(df)
    import sqlite3
    conn = sqlite3.connect(str(Path(db.db_path)))
    dates = [r[0] for r in conn.execute("SELECT date FROM news ORDER BY id").fetchall()]
    conn.close()
    assert dates == ["", ""], f"NaT 日期必须转空串，实际 {dates}"


# ---------- 缺陷3：alert_check 时间窗 ----------

def test_alert_check_uses_inserted_at_and_finds_same_day(db):
    """当天 00:00:00 发布的重大新闻，按最近6小时预警必须能命中。"""
    df = pd.DataFrame([
        {"title": "当天重大利空", "content": "", "url": "u1", "source": "s",
         "date": "2026-11-20 00:00:00", "is_major": True, "type": "负面", "sentiment_score": -0.9},
        {"title": "当天普通", "content": "", "url": "u2", "source": "s",
         "date": "2026-11-20 00:00:00", "is_major": False, "type": "中性", "sentiment_score": 0.1},
    ])
    db.save_news(df)
    miner = EventMiner.__new__(EventMiner)
    miner.db = db
    alerts = miner.alert_check(hours=6)
    assert len(alerts) == 1, f"应命中1条当天重大新闻，实际 {alerts}"
    assert alerts[0]["title"] == "当天重大利空"


def test_query_supports_inserted_from(db):
    df = pd.DataFrame([
        {"title": "A", "content": "", "url": "u1", "source": "s",
         "date": "", "is_major": True, "type": "正面", "sentiment_score": 0.8},
    ])
    db.save_news(df)
    # 极早的 inserted_from 应过滤掉全部
    assert db.query(inserted_from="2099-01-01 00:00")["title"].tolist() == []
    # 极早之前界应命中
    assert "A" in db.query(inserted_from="2000-01-01 00:00")["title"].tolist()
