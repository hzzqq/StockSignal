"""tests/test_clear_cache_truthful.py

缓存清除「如实反馈」回归（2026-09-09 锐评 R5）。

背景（真实缺陷，非演练）：
``StockFetcher.clear_cache`` 内层是 ``except sqlite3.OperationalError: pass``，
而调用方 ``pages/11_股票选取.py`` 的「🔄 强制刷新数据」按钮：
  1) 调 ``clear_cache``（失败被静默吞掉）；
  2) 自己再跑一次 ``DELETE ... LIKE``，用 ``except Exception: pass`` 又吞一次；
  3) **无条件**弹 ``xc_success_box("缓存已清除，正在刷新...")``。

后果：当库被锁 / 磁盘 I/O 错误 / 无写权限时，两次删除都没生效，用户却看到
"缓存已清除"，随后拿到旧缓存数据当成最新行情 —— 典型的「静默错结果」，
与牧羊人二元组 footgun 同源（错误不崩溃但语义错）。

本测试锁定四条不变量：
  1. ``clear_cache`` 返回**实际删除行数**（不再是无返回值）；
  2. 表不存在（首次运行没写过该表）属预期，**不得**打 WARNING 噪音；
  3. 其余 OperationalError（如 database is locked）**必须** warning 留痕、
     且仍不向上抛（保持容错），但不能装没发生；
  4. 页面刷新缓存所在文件**不得**再出现 ``except: pass`` 式静默兜底（AST 源码守卫）。

2026-09-09 新增（锐评 R5）。
"""
import ast
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.fetcher import StockFetcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE11 = os.path.join(ROOT, "pages", "11_股票选取.py")


def _make_db(tmp_path, rows=3):
    """建一个落盘的 SQLite（不是 :memory:）——因为 clear_cache 会 close 连接，
    落盘库才能跨连接观察表内容，贴近生产中 db_path 的真实语义。"""
    db = os.path.join(str(tmp_path), "cache.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE daily_cache (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)"
    )
    for i in range(rows):
        conn.execute(
            "INSERT INTO daily_cache VALUES (?,?,?)", (f"k{i}", "{}", "2026-01-01")
        )
    conn.commit()
    conn.close()
    return db


def _instance_for(db_path):
    """绕过 __init__（避免网络/DB 预热），_get_conn 每次返回新连接（同生产实现）。"""
    f = StockFetcher.__new__(StockFetcher)
    f._get_conn = lambda: sqlite3.connect(db_path)  # type: ignore[method-assign]
    return f


def _count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM daily_cache").fetchone()[0]
    finally:
        conn.close()


def test_clear_cache_returns_real_deleted_count(tmp_path):
    """返回值必须是真实删除行数（0 也要如实返回，不能 None）。"""
    db = _make_db(tmp_path, rows=3)
    f = _instance_for(db)

    assert f.clear_cache(table_name="daily_cache") == 3
    assert _count(db) == 0
    # 再清一次已经没有数据了 —— 必须返回 0 而非 None/异常
    assert f.clear_cache(table_name="daily_cache") == 0


def test_clear_cache_exact_key_returns_one(tmp_path):
    db = _make_db(tmp_path, rows=3)
    f = _instance_for(db)

    assert f.clear_cache(table_name="daily_cache", cache_key="k1") == 1
    assert _count(db) == 2


def test_missing_table_is_benign_and_silent(tmp_path, monkeypatch):
    """表尚未创建属预期，不该产生 WARNING 噪音（否则日志被刷爆）。

    注：本项目的 logger 设了 ``propagate=False`` 且自带 handler，pytest 的 caplog
    抓不到，故沿用 tests/test_exception_logging.py 的既定做法 —— 直接拦截方法本身。
    """
    db = _make_db(tmp_path, rows=1)
    f = _instance_for(db)

    warns = []
    monkeypatch.setattr(
        "modules.fetcher.logger.warning", lambda msg, *a, **k: warns.append(msg)
    )
    deleted = f.clear_cache(table_name="commodity_cache")

    assert deleted == 0
    assert not warns, f"表不存在属预期，不该打 WARNING：{warns}"


class _LockedConn:
    """模拟 database is locked：任何执行都抛 OperationalError。"""

    def execute(self, sql, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    def commit(self):
        pass

    def close(self):
        pass


def test_locked_db_logs_warning_instead_of_silent_pass(monkeypatch):
    """核心回归：非「表不存在」的 OperationalError 必须留痕，且不静默假装成功。"""
    f = StockFetcher.__new__(StockFetcher)
    f._get_conn = lambda: _LockedConn()  # type: ignore[method-assign]

    warns = []
    monkeypatch.setattr(
        "modules.fetcher.logger.warning", lambda msg, *a, **k: warns.append(msg)
    )
    deleted = f.clear_cache(table_name="daily_cache")

    assert deleted == 0, "删除失败时不得虚报删除条数"
    assert warns, "删除失败必须留下 WARNING（旧实现是静默 pass）"
    assert any("缓存未清空" in str(w) for w in warns)


def test_page_refresh_path_has_no_silent_except_pass():
    """AST 源码守卫：该页不得再有 ``except: pass`` 静默兜底。"""
    tree = ast.parse(open(PAGE11, encoding="utf-8").read())
    silent = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        # 处理器体里除 Pass 外没有任何「实质语句」→ 属静默吞异常
        if not [n for n in node.body if not isinstance(n, ast.Pass)]:
            silent.append(node.lineno)
    assert not silent, f"pages/11 存在静默 except: pass（行 {silent}），会掩盖失败原因"


def test_page_reports_failure_to_user():
    """页面必须把缓存清除失败告知用户，而不是无条件报成功。"""
    src = open(PAGE11, encoding="utf-8").read()
    assert "xc_warn_box" in src, "清除失败必须用警告卡告知用户"
    assert "batch_failed" in src, "页面需记录批量删除是否失败并据此反馈"
