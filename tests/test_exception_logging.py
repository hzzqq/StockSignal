"""P0-1 回归测试：验证 fetcher/session/market_drivers 的裸吞 except Exception 已接 logger.warning。

注意：modules/_feed_io.py 中的 logger 设置 propagate=False 并自带 StreamHandler，
因此 pytest 的 caplog 无法捕获；改用 monkeypatch 拦截 logger.warning 方法本身。
"""
import pytest


def test_fetcher_data_source_health_logs_importlib_failure(monkeypatch):
    """data_source_health() 中 _spec() 捕获 importlib 异常时应打 warning。"""
    from modules.fetcher import StockFetcher
    import importlib.util

    warnings = []
    monkeypatch.setattr(
        "modules.fetcher.logger.warning", lambda msg, *a, **k: warnings.append(msg)
    )

    def _boom(*args, **kwargs):
        raise ValueError("spec boom")

    monkeypatch.setattr(importlib.util, "find_spec", _boom)

    result = StockFetcher().data_source_health()
    assert isinstance(result, dict)
    assert "sources" in result
    assert any("spec boom" in w for w in warnings)


def test_session_api_request_logs_network_error(monkeypatch):
    """_api_request 在 requests 网络错误兜底时应打 logger.warning。"""
    import requests
    from modules.session import _api_request

    class _DummyExc(requests.exceptions.RequestException):
        pass

    warnings = []
    monkeypatch.setattr(
        "modules.session.logger.warning", lambda msg, *a, **k: warnings.append(msg)
    )
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: (_ for _ in ()).throw(_DummyExc("network down"))
    )
    monkeypatch.setattr("time.sleep", lambda x: None)

    status, body = _api_request("GET", "/test")
    assert status == -1
    assert "network down" in body["message"]
    assert any("network down" in w for w in warnings)


def test_market_drivers_read_last_cached_logs_db_error(monkeypatch):
    """_read_last_cached_value 在 SQLite 读取异常时应打 warning 并返回 None。"""
    import sqlite3
    from modules.market_drivers import _read_last_cached_value

    warnings = []
    monkeypatch.setattr(
        "modules.market_drivers.logger.warning", lambda msg, *a, **k: warnings.append(msg)
    )
    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db locked"))
    )

    assert _read_last_cached_value("test_key") is None
    assert any("db locked" in w for w in warnings)


# ─────────────────────────────────────────────────────────────
#  全仓守卫：用 logger 之前必须先定义它
#  历史教训（2026-09-10 踩到）：往 pages/50_市场情绪.py 里插 logger.debug 做留痕，
#  但该页面根本没定义 logger —— 于是「为了不静默」写下的那行，会在异常分支真正
#  走到时抛 NameError，把容错变成新的崩溃点。修容错前必须先确认日志器存在。
# ─────────────────────────────────────────────────────────────
def test_no_page_or_module_uses_undefined_logger():
    """AST 静态扫描（作用域感知）：凡出现 ``logger.x()`` / ``_logger.x()`` / ``log.x()``
    的文件，该名字必须在**其所属作用域内真实可见**。认三种合法来源：

      ① 模块级 ``logger = logging.getLogger(__name__)``；
      ② 模块级 re-export ``from modules._feed_io import logger``（本项目标准做法）；
      ③ 局部绑定 —— ``for log in items`` / ``with open() as log`` / 函数内赋值，
         此时 ``log`` 只是个 DataFrame 或文件句柄，压根不是日志器，不该误报。

    并且**刻意不认**类体里的同名属性：类作用域不参与闭包查找，
    ``class A: logger = ...`` 之后在方法里裸写 ``logger`` 依旧是 NameError。

    历史教训（2026-09-10 踩到）：往 pages/50_市场情绪.py 里插 logger.debug 做留痕，
    但该页面根本没定义 logger —— 于是「为了不静默」写下的那行，会在异常分支真正
    走到时抛 NameError，把容错变成新的崩溃点。
    """
    import ast
    import pathlib

    ROOT = pathlib.Path(__file__).resolve().parent.parent
    TARGETS = ("logger", "_logger", "log")

    def _bind_targets(node):
        """提取赋值/绑定目标里的裸名字（支持元组解包）。"""
        out = set()
        stack = [node]
        while stack:
            t = stack.pop()
            if isinstance(t, ast.Name):
                out.add(t.id)
            elif isinstance(t, ast.Starred):
                stack.append(t.value)
            elif isinstance(t, (ast.Tuple, ast.List)):
                stack.extend(t.elts)
        return out

    def _own_bindings(scope):
        """收集 scope *自身* 作用域内的绑定名。

        遇到嵌套的 func/class 只取其名字（名字绑在外层），不下钻其函数体 ——
        它们各自是独立作用域，在里层赋值不会让外层同名变量变成已定义。
        """
        names = set()
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = scope.args
            for arg in (
                list(getattr(a, "posonlyargs", [])) + list(a.args) + list(a.kwonlyargs)
            ):
                names.add(arg.arg)
            for extra in (a.vararg, a.kwarg):
                if extra is not None:
                    names.add(extra.arg)

        def _scan(node):
            if node is not scope and isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                if not isinstance(node, ast.Lambda):
                    names.add(node.name)
                return
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    names.update(_bind_targets(t))
            elif isinstance(node, ast.AnnAssign):
                names.update(_bind_targets(node.target))
            elif isinstance(node, ast.AugAssign):
                names.update(_bind_targets(node.target))
            elif isinstance(node, ast.NamedExpr):
                names.update(_bind_targets(node.target))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                names.update(_bind_targets(node.target))
            elif isinstance(node, ast.comprehension):
                names.update(_bind_targets(node.target))
            elif isinstance(node, ast.withitem):
                if node.optional_vars is not None:
                    names.update(_bind_targets(node.optional_vars))
            elif isinstance(node, ast.ExceptHandler):
                if node.name:
                    names.add(node.name)
            elif isinstance(node, ast.Import):
                for al in node.names:
                    names.add((al.asname or al.name).split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for al in node.names:
                    names.add(al.asname or al.name)
            for child in ast.iter_child_nodes(node):
                _scan(child)

        _scan(scope)
        return names

    problems = []
    scanned = 0
    for d in ("pages", "modules", "scripts", "backend"):
        for f in sorted((ROOT / d).rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            scanned += 1

            parents = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[child] = node

            # global 声明的名字落在模块作用域，静态上视为「已定义」（偏宽松，宁漏不误报）
            declared_global = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Global):
                    declared_global.update(node.names)
            module_names = _own_bindings(tree) | declared_global
            scope_cache = {}

            def _visible(name, usage):
                cur = usage
                while cur is not None:
                    if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        if id(cur) not in scope_cache:
                            scope_cache[id(cur)] = _own_bindings(cur)
                        if name in scope_cache[id(cur)]:
                            return True
                    cur = parents.get(cur)
                return name in module_names

            missing = set()
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in TARGETS
                    and not _visible(node.value.id, node)
                ):
                    missing.add(node.value.id)
            if missing:
                problems.append(f"{f.relative_to(ROOT)} 使用了未定义的 {sorted(missing)}")

    assert scanned > 0, "扫描集为空，守卫形同虚设"
    assert not problems, (
        "以下文件用了未定义的日志器（会在异常分支抛 NameError）：\n"
        + "\n".join(problems)
    )
