"""tests/test_no_conn_leak.py

SQLite 连接泄漏回归（2026-09-09 锐评 R6）。

背景（真实缺陷）：
``modules/_market_data_io.py`` 的 ``fetch_concept_list`` 两处
``conn = fetcher._get_conn()`` 都**没有关闭**：
  - 命中缓存时 ``return cached`` 提前返回 → 连接泄漏；
  - 未命中缓存时继续走网络 → 连接同样泄漏；
  - 写缓存那处也没有 close。

而 ``fetch_concept_list`` 被概念/板块页面调用，Streamlit 每次交互都会整页重跑，
因此泄漏是**高频累积**的：最终耗尽文件句柄，并让 SQLite 文件长期被占用
（连带触发其它模块 ``database is locked`` —— 与 R5 的缓存清除失败同源）。

本测试锁定两条：
  1. 行为：``fetch_concept_list`` 无论命中缓存还是走网络写缓存，连接都必须关闭；
  2. 源码守卫：modules/ 与 pages/ 下，任何"赋值得到的连接"在同一函数内
     必须有 ``.close()``（或经 ``contextlib.closing`` 托管），防止将来新增泄漏。

2026-09-09 新增（锐评 R6）。
"""
import ast
import os
import sys
import types

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules import _market_data_io as mdio  # noqa: E402


class _FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeFetcher:
    """记录所有下发的连接，便于断言它们最终都被关闭。"""

    def __init__(self, cached=None):
        self.conns = []
        self._cached = cached
        self.written = []

    def _get_conn(self):
        c = _FakeConn()
        self.conns.append(c)
        return c

    def _read_cache(self, conn, table, key, max_age_hours=0):
        return self._cached

    def _write_cache(self, conn, table, key, df):
        self.written.append((table, key, len(df)))


def test_cache_hit_closes_connection():
    """命中缓存提前 return 时，连接也必须已关闭（原实现泄漏在此路径）。"""
    cached = pd.DataFrame([{"sector": "半导体", "change_pct": 1.5}])
    f = _FakeFetcher(cached=cached)

    out = mdio.fetch_concept_list(f, force_refresh=False)

    assert out is cached  # 确走缓存命中分支
    assert f.conns, "应至少取过一次连接"
    assert all(c.closed for c in f.conns), "命中缓存提前 return 时连接未关闭 = 泄漏"


def test_network_path_closes_connection(monkeypatch):
    """未命中缓存 → 拉取 → 写缓存：读连接与写连接都必须关闭。"""
    df = pd.DataFrame({"板块名称": ["光伏", "储能"], "涨跌幅": [2.0, -1.0]})
    monkeypatch.setattr(mdio, "_retry_request", lambda fn, **kw: df)
    fake_ak = types.ModuleType("akshare")
    fake_ak.stock_board_concept_name_em = lambda: df
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    f = _FakeFetcher(cached=None)
    out = mdio.fetch_concept_list(f, force_refresh=False)

    assert list(out.columns) == ["sector", "change_pct"]
    assert f.written, "应写入缓存"
    assert all(c.closed for c in f.conns), "读/写路径的连接存在未关闭 = 泄漏"


# ─────────────────────────── 源码守卫 ───────────────────────────

SCAN_DIRS = ["modules", "pages", "backend", "scripts"]
FACTORY_FUNCS = {"_get_conn", "get_conn"}  # 工厂函数本身「返回」连接，由调用方关闭


def _is_conn_call(node):
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
    if name in ("_get_conn", "get_conn"):
        return True
    if name == "connect":
        base = f.value
        bname = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
        return bname == "sqlite3"
    return False


def _iter_py():
    for sub in SCAN_DIRS:
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".py"):
                yield os.path.join(d, fn)
    # 仓库根目录下的入口脚本
    for fn in sorted(os.listdir(ROOT)):
        if fn.endswith(".py"):
            yield os.path.join(ROOT, fn)


def test_no_unclosed_sqlite_connection_in_source():
    leaks = []
    scanned = 0
    for path in _iter_py():
        scanned += 1
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:  # 语法错误交给别的测试报，这里不阻塞
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name in FACTORY_FUNCS:
                continue  # 工厂自身把连接 return 出去
            assigned = {}
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign) and _is_conn_call(node.value):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            assigned[t.id] = node.lineno
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                        and _is_conn_call(node.value):
                    assigned[node.target.id] = node.lineno
            if not assigned:
                continue
            closed = set()
            managed = set()  # 交给 contextlib.closing / with 托管
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == "close" and isinstance(node.func.value, ast.Name):
                    closed.add(node.func.value.id)
                if isinstance(node, (ast.With, ast.AsyncWith)):
                    for item in node.items:
                        cx = item.context_expr
                        if isinstance(cx, ast.Call) and _is_conn_call(cx.args[0] if cx.args else None):
                            managed.add(getattr(cx, "lineno", -1))
                        if _is_conn_call(cx):
                            managed.add(getattr(cx, "lineno", -1))
            for var, line in assigned.items():
                if var in closed or line in managed:
                    continue
                leaks.append(f"{os.path.relpath(path, ROOT)}:{line} (fn={fn.name})")

    assert scanned > 50, f"扫描文件数异常（{scanned}），疑似路径错误"
    assert not leaks, "存在未关闭的 SQLite 连接（会累积泄漏并锁住 DB 文件）：" + "; ".join(leaks)
