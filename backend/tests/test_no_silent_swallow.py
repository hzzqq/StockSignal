"""backend/tests/test_no_silent_swallow.py

**禁止「宽泛静默吞异常」** —— 源码级防回退。

问题：``except Exception: pass`` 会把任何错误（含 Bug、依赖故障、数据损坏）
无声吞掉，线上表现为「功能莫名不生效」且**日志里什么都没有**，
排查成本极高。项目此前已在前端 modules 层做过同类治理（Cycle 18-20），
本次补齐后端。

约定：
- **宽泛捕获**（``except:`` / ``except Exception:`` / ``except BaseException:``）
  的函数体不得只有 ``pass``——至少要 ``logger.*`` 留痕，或显式处理；
- 具体异常类型的窄捕获（如 ``except ValueError: pass``）通常是刻意的
  （例如「非数字字符串保留原值」），不在本测试约束范围内，避免过度严格。

Cycle 70 已将后端全部 6 处宽泛静默吞异常改为日志留痕：
- app.py ×3（Content-Type 兜底 / token 解析 / 监控指标采集）
- broker/__init__.py ×1（服务端取最新价）
- conditional_engine.py ×1（条件单取最新价）
- market_alert_config.py ×1（阈值 JSON 解析）

2026-08-28 新增（Cycle 70）。
"""
from __future__ import annotations

import ast
import glob
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND_DIR)
for p in (ROOT, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

BROAD = {"Exception", "BaseException"}


def _is_broad(node) -> bool:
    t = node.type
    if t is None:
        return True  # 裸 except:
    if isinstance(t, ast.Name):
        return t.id in BROAD
    if isinstance(t, ast.Attribute):
        return t.attr in BROAD
    return False


def _silently_passes(node) -> bool:
    body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def test_no_broad_silent_swallow():
    bad = []
    for path in sorted(glob.glob(os.path.join(BACKEND_DIR, "**", "*.py"), recursive=True)):
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        if "/tests/" in rel or rel.endswith("/conftest.py"):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _is_broad(node) and _silently_passes(node):
                bad.append((rel, node.lineno))

    assert not bad, (
        "发现宽泛静默吞异常（except Exception: pass）——错误会被无声吞掉、日志无痕。\n"
        "请至少改为 logger.debug/warning 留痕，或改用具体异常类型窄捕获:\n"
        + "\n".join(f"  {r}:{ln}" for r, ln in bad)
    )
