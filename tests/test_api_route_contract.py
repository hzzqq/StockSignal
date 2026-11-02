"""API 路由契约守卫（后端 API 补漏专项 · 防漂移）

问题背景
--------
StockSignal 前端（Streamlit pages/modules）通过 ``requests`` 调用 Flask 后端
``/api/...`` 端点。此前项目**没有任何机制**保证「前端调用的路径后端已实现」——
一旦某次 PR 改了前端调用路径却忘了加后端路由，会在运行时静默 404，且无测试拦截。

本守卫以**运行时内省 Flask url_map** 为权威路由源（静态文本扫描会漏掉动态注册，
已实测：本项目 89 个路由里静态扫描只能命中 5 个），逐一校验 modules/ 与 pages/
里所有字面量 ``/api/...`` 调用都能匹配到后端已注册路由（含 ``<code>`` / ``<int:id>``
等动态段）。

设计要点
--------
- 不修改任何功能代码，纯新增测试。
- 关闭全部后台调度器（STOCKSIGNAL_ENABLE_*_SCHEDULER=0 / DATA_REFRESH=0），
  避免测试导入 app 时拉起守护线程。
- 分段匹配：前端路径与后端规则按 ``/`` 切段，后端 ``<var>`` / 前端 ``{p}`` 视为动态段，
  任意非空前端段均可匹配动态段；段数相同且逐段匹配即视为「路由存在」。
- ALLOWLIST：若确有前端调用指向外部服务或经其它机制解析、不应由本仓库后端承接，
  在此显式登记并注释原因（当前为空——全量比对后确认 0 真实缺口）。
"""
from __future__ import annotations

import os
import sys

# ── 关闭后台调度器，避免导入 app 时拉起守护线程 ──
for _flag in (
    "STOCKSIGNAL_ENABLE_ALERT_SCHEDULER",
    "STOCKSIGNAL_ENABLE_COND_SCHEDULER",
    "STOCKSIGNAL_ENABLE_DATA_REFRESH",
    "STOCKSIGNAL_ENABLE_RESEARCH_WATCH",
    "STOCKSIGNAL_ENABLE_RECOMMEND_SCHEDULER",
):
    os.environ.setdefault(_flag, "0")

# 独立测试库，避免占用老板正在运行的后端 SQLite
os.environ.setdefault(
    "DATABASE_URL", "sqlite:///E:/tmp/ss_contract/app.db"
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

# 前端调用中、经 f-string 归一后的动态段标记（如 /api/stocks/{code} -> /api/stocks/{p}）
_FRONTEND_DYN = "{p}"


def _segs(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _is_dynamic(seg: str) -> bool:
    return seg.startswith("<") or seg == _FRONTEND_DYN or seg.startswith("{")


def _route_matches(frontend: str, backend: str) -> bool:
    fs, bs = _segs(frontend), _segs(backend)
    if len(fs) != len(bs):
        return False
    return all(
        _is_dynamic(b) or _is_dynamic(f) or f == b for f, b in zip(fs, bs)
    )


def _collect_backend_routes() -> set[str]:
    from backend.app import create_app

    app = create_app()
    rules = set()
    for r in app.url_map.iter_rules():
        rule = r.rule.rstrip("/") or r.rule
        if rule.startswith("/api"):
            rules.add(rule)
    return rules


def _collect_frontend_calls() -> set[str]:
    import re

    out = set()
    pat = re.compile(r'["\'](/api/[A-Za-z0-9_/{}.\-]*)["\']')
    for d in (os.path.join(ROOT, "modules"), os.path.join(ROOT, "pages")):
        for dp, _, fns in os.walk(d):
            for fn in fns:
                if not fn.endswith(".py") or fn.startswith("__"):
                    continue
                try:
                    src = open(os.path.join(dp, fn), encoding="utf-8").read()
                except Exception:
                    continue
                for mm in pat.finditer(src):
                    p = mm.group(1)
                    if "{" in p and "}" in p and "{p}" not in p:
                        p = re.sub(r"\{[^}]+\}", _FRONTEND_DYN, p)
                    out.add(p.rstrip("/") or p)
    return out


# 经全量比对后确认：前端所有 /api 字面量调用均有后端实现，无需豁免。
ALLOWLIST: set[str] = set()


def test_api_route_contract_no_drift():
    """前端调用的每个 /api 路径都必须匹配到后端已注册路由（含动态段）。"""
    backend = _collect_backend_routes()
    frontend = _collect_frontend_calls()

    assert backend, "后端未解析到任何 /api 路由——introspect 失败或 app 导入异常"

    gaps = []
    for fcall in sorted(frontend):
        if fcall in ALLOWLIST:
            continue
        if not any(_route_matches(fcall, b) for b in backend):
            gaps.append(fcall)

    assert not gaps, (
        f"前端调用了 {len(gaps)} 个后端未实现的 /api 路径（前后端漂移）：\n"
        + "\n".join(f"  - {g}" for g in gaps)
        + "\n若确属外部服务/其它解析机制，请显式登记进 ALLOWLIST 并注释原因。"
    )


def test_api_route_contract_backend_count_sane():
    """护栏：后端 /api 路由数应在合理区间（防 introspect 静默退化为 0）。"""
    backend = _collect_backend_routes()
    # 历史基线：运行时实测 89。留 30% 余量防误判，下限卡死防 introspect 静默失效。
    assert 60 <= len(backend), f"后端 /api 路由数异常偏低：{len(backend)}"
