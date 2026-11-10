# -*- coding: utf-8 -*-
"""前端 v2 视觉审计基础设施守卫：路由覆盖 + dev 代理 + 真后端探针不变量。

真缺陷背景（2026-11-09 批次 14）：scripts/shoot_frontend_v2.py 的 ROUTES 只覆盖 12/25 条
真实路由，视觉审计长期漏掉 /decision /replay /morning /p1 /recommend /paper /alerts /
webapps /diagnostics /settings /catalog /data /matrix /guide 共 14 页，且注释谎称「与 AppPath
对齐」。本守卫双向校验，杜绝「漏页」与「残留已删路由」两类静默漂移。

2026-11-09 补充：dev server 不得劫持 SPA 路由。vite.config.ts 的 webapps 代理必须是
收窄正则 '^/webapps/.+'；若退回前缀 '/webapps'，裸 /webapps 整页导航会被转发到 5050，
后端未启动时 502、React 根节点永远挂不上（全量真浏览器目检实测）。

2026-11-10 补充：真后端联调探针 scripts/probe_frontend_v2_realbackend.py 不得用假 token、
开着 MSW 或接管活端口来「冒充」联调通过，以下不变量逐条硬锁。

不依赖网络 / 数据库，只做源文件真扫。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAV_TS = ROOT / "frontend-v2" / "src" / "nav" / "nav.ts"
SHOOT_PY = ROOT / "scripts" / "shoot_frontend_v2.py"
VITE_CONFIG = ROOT / "frontend-v2" / "vite.config.ts"
PROBE_PY = ROOT / "scripts" / "probe_frontend_v2_realbackend.py"
READ_ROUTES_PY = ROOT / "backend" / "api" / "read_routes.py"
INDEX_WORKER_PY = ROOT / "backend" / "api" / "_index_daily_worker.py"

# AppPath 联合类型里的路由：`  | '/decision'`
_APP_PATH_RE = re.compile(r"^\s*\|\s*'(/[^']*)'\s*$")
# ROUTES 元组项：`    ("/route", "name"),`
_ROUTE_RE = re.compile(r'\(\s*"(/[^"]*)"\s*,\s*"([^"]*)"\s*\)')
# vite.config.ts proxy key 行：`  '^/webapps/.+': {`
_PROXY_KEY_RE = re.compile(r"""^\s*['"](\^?/webapps[^'"]*)['"]\s*:\s*\{""", re.M)

_SCHEDULER_FLAGS = (
    "STOCKSIGNAL_ENABLE_COND_SCHEDULER",
    "STOCKSIGNAL_ENABLE_DATA_REFRESH",
    "STOCKSIGNAL_ENABLE_ALERT_SCHEDULER",
    "STOCKSIGNAL_ENABLE_RECOMMEND_SCHEDULER",
    "STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER",
    "STOCKSIGNAL_ENABLE_RESEARCH_WATCH",
)


def _parse_app_paths() -> set[str]:
    text = NAV_TS.read_text(encoding="utf-8")
    found: set[str] = set()
    for line in text.splitlines():
        m = _APP_PATH_RE.match(line)
        if m:
            found.add(m.group(1))
    return found


def _parse_routes() -> list[tuple[str, str]]:
    text = SHOOT_PY.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    for m in _ROUTE_RE.finditer(text):
        route = m.group(1)
        name = m.group(2)
        out.append((route, name))
    return out


def _parse_webapps_proxy_keys() -> list[str]:
    text = VITE_CONFIG.read_text(encoding="utf-8")
    return [m.group(1) for m in _PROXY_KEY_RE.finditer(text)]


def test_visual_audit_infrastructure_sane():
    assert NAV_TS.is_file(), f"nav.ts 缺失：{NAV_TS}"
    assert SHOOT_PY.is_file(), f"shoot_frontend_v2.py 缺失：{SHOOT_PY}"
    assert VITE_CONFIG.is_file(), f"vite.config.ts 缺失：{VITE_CONFIG}"
    keys = _parse_webapps_proxy_keys()
    assert keys == ["^/webapps/.+"], (
        "vite.config.ts 的 webapps 代理 key 必须是 '^/webapps/.+'：裸 /webapps 是 SPA 路由"
        "（nav.ts AppPath），前缀 '/webapps' 会把整页导航转发到 5050，后端未启动时 502、"
        "React 根节点永远挂不上（2026-11-09 全量真浏览器目检实测）。当前：%r" % (keys,)
    )

    assert PROBE_PY.is_file(), f"真后端联调探针缺失：{PROBE_PY}"
    src = PROBE_PY.read_text(encoding="utf-8")
    invariants = {
        "关 MSW": '"VITE_ENABLE_MOCKS": "false"' in src,
        "代理指向隔离后端": '"VITE_PROXY_TARGET": base_backend' in src,
        "真实登录取 JWT": '"/api/auth/login"' in src,
        "不使用演示假 token": "visual-audit-local-token" not in src,
        "MockBanner 防伪断言": "演示数据（Mock）" in src,
        "独立 secret": '"STOCKSIGNAL_SECRET": secret' in src,
        "独立 SQLite 库": '"DATABASE_URL": db_uri' in src,
        "6 个调度器全关": all(k in src for k in _SCHEDULER_FLAGS),
        "指纹端点为本地只读": 'FINGERPRINT_ENDPOINT = "/api/v2/read/webapps"' in src,
        "V8 修复后实时端点已纳入联调": (
            "REALTIME_ENDPOINTS" in src
            and "probe_realtime_endpoints" in src
            and '("/", "dashboard")' in src
            and "/quote-board" in src
            and "EXCLUDED_ENDPOINTS" not in src
        ),
        "逐页复核后端存活": '"/api/health", timeout=3' in src,
        "默认端口避开活服务": bool(re.search(r"DEFAULT_BACKEND_PORT\s*=\s*5051", src))
                             and bool(re.search(r"DEFAULT_FRONTEND_PORT\s*=\s*5181", src)),
    }
    broken = [k for k, v in invariants.items() if not v]
    assert not broken, (
        f"真后端联调探针不变量被破坏：{broken}；禁止用假 token / 开着 MSW / 接管 5050 "
        "冒充真后端联调通过"
    )

    # V8 进程隔离防回潮：Flask 进程内绝不能重新出现「import akshare + 直调新浪日线」。
    # 2026-11-10 真后端联调实测该组合触发 py_mini_racer(V8) native FATAL，直接杀死后端。
    assert INDEX_WORKER_PY.is_file(), f"指数日线独立解释器 worker 缺失：{INDEX_WORKER_PY}"
    import ast as _ast
    rr = READ_ROUTES_PY.read_text(encoding="utf-8")
    bodies = {
        n.name: _ast.get_source_segment(rr, n)
        for n in _ast.parse(rr).body
        if isinstance(n, _ast.FunctionDef)
        and n.name in ("_w4x_index_daily", "_w4x_index_daily_batch")
    }
    assert set(bodies) == {"_w4x_index_daily", "_w4x_index_daily_batch"}, (
        "指数日线子进程隔离函数缺失，V8 修复疑似回潮")
    for _name, _body in bodies.items():
        assert "import akshare" not in _body and "stock_zh_index_daily(" not in _body, (
            f"{_name} 回潮到 Flask 进程内直调 akshare 新浪日线；V8 native 崩溃会打挂后端")


def test_app_paths_parsed_nonempty():
    app = _parse_app_paths()
    # 防伪阳性：源文件改格式也要 ≥ 现有路由数下限
    assert len(app) >= 20, f"AppPath 解析异常，仅 {len(app)} 条（疑似 nav.ts 改了格式）"
    assert "/" in app, "AppPath 必含首页 /"
    assert "/login" in app, "AppPath 必含 /login"


def test_routes_parsed_nonempty():
    routes = _parse_routes()
    assert len(routes) >= 20, f"ROUTES 解析异常，仅 {len(routes)} 条"
    # 每个元组项都应有非空路由与文件名
    for route, name in routes:
        assert route.startswith("/"), f"ROUTES 项路由非法：{route!r}"
        assert name, f"ROUTES 项缺少截图文件名：{route!r}"


def test_routes_cover_all_app_paths():
    app = _parse_app_paths()
    routes = _parse_routes()
    covered = {r.split("?")[0] for r, _ in routes}
    missing = sorted(p for p in app if p not in covered)
    assert not missing, (
        f"截图脚本 ROUTES 漏覆盖 {len(missing)} 条 AppPath 路由：{missing}；"
        "请在 scripts/shoot_frontend_v2.py 的 ROUTES 补上，与 nav.ts AppPath 对齐"
    )


def test_routes_have_no_stale_entries():
    app = _parse_app_paths()
    routes = _parse_routes()
    stale = sorted({r.split("?")[0] for r, _ in routes if r.split("?")[0] not in app})
    assert not stale, (
        f"ROUTES 含 {len(stale)} 条已不在 AppPath 的残留路由：{stale}；"
        "nav.ts 已删除这些路由，请同步清理脚本"
    )
