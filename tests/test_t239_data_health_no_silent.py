"""T-239 round2 定点守卫：data_health.py 的「内容日期读取失败 → 静默回退 mtime」

不得再静默吞（T-235 时效护栏诚信漏洞）：
- _json_max_date / _sqlite_col_max_date 解析失败时回退 mtime 会「假新鲜」，
  必须以 logger.warning 留痕，禁止 `except: pass`。
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "modules" / "data_health.py"


def _silent_pass_handlers(tree):
    """返回体为纯 `pass` 的 except handler 行号。"""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                out.append(node.lineno)
    return out


def _handlers_with_logger(tree):
    src = TARGET.read_text(encoding="utf-8")
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            seg = ast.get_source_segment(src, node) or ""
            if "logger." in seg:
                out.append(node.lineno)
    return out


def test_data_health_no_silent_except_pass():
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    silent = _silent_pass_handlers(tree)
    assert silent == [], f"data_health.py 仍存在静默 except:pass @ {silent}"


def test_data_health_fallback_handlers_logged():
    tree = ast.parse(TARGET.read_text(encoding="utf-8"))
    logged = _handlers_with_logger(tree)
    # 至少 _json_max_date(97) 与 _sqlite_col_max_date(121) 两处回退处理器须留痕
    assert len(logged) >= 2, f"data_health.py 回退处理器未留痕: {logged}"
