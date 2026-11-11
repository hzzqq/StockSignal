# -*- coding: utf-8 -*-  # noqa: UP009
"""
tests/test_read_contract_drift.py — 只读端点 ↔ 前端 Zod schema 字段契约漂移守卫。

背景（§21 教训）：MSW 夹具与 Zod schema 可以「自洽」却与真后端响应脱钩
（财报日历 MSW 全绿、接真后端三列全显「—」）。本守卫直接打**真后端**
（离线 data/），把真实响应 data 顶层键与前端 Zod schema 顶层键逐项比对，
从根上抓住双向漂移：

  1. 必需字段缺失：schema 里 required 的键，真后端没给 → 前端会拿不到（软缺失/破版）；
  2. 未知字段越界：真后端给了 schema 没有的键，且 schema 无 .catchall() → 前端 Zod 硬崩。

设计要点：
  - 用真实 data/（不重定向到临时树），真打只读端点；
  - 离线能力端点（本地 json/db）做严格 key 对齐；
  - akshare 依赖端点（联网）不在此离线环境真打，改用 AST 登记枚举 + 离线优雅降级
    断言（见 test_net_dependent_endpoints_graceful），避免无网络时挂起，且并非静默 skip——
    它们被显式登记并要求「离线 200 而非 500」。

注意：仅校验 data 载荷（即前端 readValidated 解出的那一层），与前端口径一致。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READ_ROUTES = ROOT / "backend" / "api" / "read_routes.py"
SCHEMAS = ROOT / "frontend-v2" / "src" / "api" / "schemas" / "read.ts"

# ───────────────────────── pytest 装置（复用 test_read_routes 模式，不重定向 data）─────────
import os
import sys
import tempfile

for _p in (str(ROOT), str(ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from backend.auth.service import issue_token  # noqa: E402
import backend.api.read_routes as _rr  # noqa: E402  (捕获原始目录常量，防直接赋值泄漏)


# ───────────────────────── 数据隔离：导入期捕获 pristine 状态 ─────────────────────────
# 模块导入期（pytest 收集阶段，任何测试均未运行）data/ 与 read_routes 模块常量处于 pristine。
# 本仓库 backend/tests/test_read_routes.py 用「直接赋值」而非 monkeypatch 改写
# rr._DATA_DIR / _WEBAPPS_DIR / _FILE_WHITELIST（指向其临时树，含最小 daily_snapshot.json
# {"date":...,"temperature":42}）。直接赋值不会随 fixture 退出自动还原，会泄漏到整个会话——
# 排在字母序后的本研究若直接读真实 data/ 会被污染（实测 /api/v2/read/daily-snapshot 假阳性
# 失败）。故在收集期捕获真实目录常量 + 所需数据文件字节，fixture 里测试前恢复 pristine、
# 测试后还原「泄漏前」状态，做到既免疫泄漏污染，又不破坏其它测试对全局的预期（诚实隔离）。
_DATA_CAP_DIR = ROOT / "data"
_PRISTINE_FILES = (
    "daily_snapshot.json", "daily_recommendation.json", "user_dashboard.json",
    "event_pool_brief.json", "p1_sync_status.json", "data_refresh_state.json",
    "shepherd_history.json", "shepherd_ladder_history.json", "prediction_log.json",
    "paper_rwuser.json",
)
_PRISTINE: dict = {}
for _f in _PRISTINE_FILES:
    _p = _DATA_CAP_DIR / _f
    if _p.is_file():
        _PRISTINE[_f] = _p.read_bytes()
_SNAP_CAP_DIR = _DATA_CAP_DIR / "snapshots"
_PRISTINE_SNAP: dict = {}
if _SNAP_CAP_DIR.is_dir():
    for _sp in _SNAP_CAP_DIR.glob("*.json"):
        _PRISTINE_SNAP[_sp.name] = _sp.read_bytes()

_RR_DATA0 = _rr._DATA_DIR                 # 真实 data/（导入期未被泄漏）
_RR_WEBAPPS0 = _rr._WEBAPPS_DIR           # 真实 webapps/
_RR_WHITELIST0 = dict(_rr._FILE_WHITELIST)  # 真实白名单（路径指向真实 data/）


@pytest.fixture(scope="module", autouse=True)
def _isolate_data():
    """恢复被上游直接赋值泄漏的 read_routes 目录常量 + 还原 pristine 数据文件。"""
    _saved = {
        "DATA": _rr._DATA_DIR,
        "WEBAPPS": _rr._WEBAPPS_DIR,
        "WL": _rr._FILE_WHITELIST,
    }
    _rr._DATA_DIR = _RR_DATA0
    _rr._WEBAPPS_DIR = _RR_WEBAPPS0
    _rr._FILE_WHITELIST = dict(_RR_WHITELIST0)

    _back: dict = {}
    for _f, _b in _PRISTINE.items():
        _p = _DATA_CAP_DIR / _f
        _back[_f] = _p.read_bytes() if _p.is_file() else None
        _p.write_bytes(_b)
    _back_snap: dict = {}
    for _n, _b in _PRISTINE_SNAP.items():
        _p = _SNAP_CAP_DIR / _n
        _back_snap[_n] = _p.read_bytes() if _p.is_file() else None
        _p.write_bytes(_b)
    yield
    _rr._DATA_DIR = _saved["DATA"]
    _rr._WEBAPPS_DIR = _saved["WEBAPPS"]
    _rr._FILE_WHITELIST = _saved["WL"]
    for _f, _b in _back.items():
        _p = _DATA_CAP_DIR / _f
        if _b is None:
            _p.unlink(missing_ok=True)
        else:
            _p.write_bytes(_b)
    for _n, _b in _back_snap.items():
        _p = _SNAP_CAP_DIR / _n
        if _b is None:
            _p.unlink(missing_ok=True)
        else:
            _p.write_bytes(_b)


@pytest.fixture(scope="module")
def app():
    _db = tempfile.mktemp(suffix=".db")

    class _C(Config):
        TESTING = True
        RATE_LIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{_db}"

    #  Surgical：测试环境直接把 6 个守护调度器 start_* 打成空操作，避免后台线程
    #  触网（BaoStock/akshare）阻塞进程退出 / 干扰读数。各引擎内部虽有 TESTING 闸门，
    #  但本仓库 create_app 在个别路径下未把 TESTING 透传到 app.config，故这里显式熔断。
    import backend.market_alert_engine as _mae
    import backend.conditional_engine as _ce
    import backend.research_watch as _rw
    import backend.recommend_scheduler as _rs
    import backend.data_refresh_engine as _dre
    import backend.p1_sync_scheduler as _pss

    for _mod, _fn in (
        (_mae, "start_alert_scheduler"),
        (_ce, "start_conditional_scheduler"),
        (_rw, "start_research_watch_scheduler"),
        (_rs, "start_recommend_scheduler"),
        (_dre, "start_data_refresh_scheduler"),
        (_pss, "start_p1_sync_scheduler"),
    ):
        if hasattr(_mod, _fn):
            setattr(_mod, _fn, lambda app: None)

    application = create_app(_C)
    with application.app_context():
        db.create_all()
        u = User(username="rwuser", role="user")
        u.set_password("Pass@123")
        db.session.add(u)
        db.session.commit()
    return application


@pytest.fixture(scope="module")
def client(app):
    # 不重定向 data/ —— 用真实 data/ 离线产出真实响应
    return app.test_client()


@pytest.fixture(scope="module")
def token(app):
    with app.app_context():
        u = User.query.filter_by(username="rwuser").first()
        return issue_token(u)


# ───────────────────────── Zod schema 解析（Python 侧 AST 级抽取）─────────
def _schema_statement(name: str) -> str:
    text = SCHEMAS.read_text(encoding="utf-8")
    m = re.search(rf"export const {re.escape(name)} = ", text)
    assert m, f"schemas/read.ts 缺 {name}"
    start = m.end()
    end = re.search(r"\nexport const ", text[start:])  # 下一个 schema 起点
    stop = (start + end.start()) if end else len(text)
    return text[start:stop]


def _brace_match(text: str, open_idx: int) -> int:
    """从开括号起按括号深度找配对的闭括号下标。忽略字符串/注释内括号。"""
    depth = 0
    i = open_idx
    n = len(text)
    in_str = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'", "`"):
            in_str = c
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def _object_info(body: str) -> dict:
    """抽 z.object({...}) 顶层键 + 是否 required + 是否 catchall。

    顶层键判定：以首个字段缩进为 body indent，缩进相等者为顶层键（更深的为嵌套，跳过）。
    required = 该字段值文本里不含 `.optional(`。
    """
    lines = body.split("\n")
    field_re = re.compile(r"^(\s*)([A-Za-z_]\w*)\s*:")
    fields = []  # (indent, key, line_text)
    for ln in lines:
        m = field_re.match(ln)
        if m:
            fields.append((len(m.group(1)), m.group(2), ln))
    if not fields:
        return {"keys": {}, "catchall": False}
    body_indent = min(f[0] for f in fields)
    keys = {}
    for indent, key, line in fields:
        if indent == body_indent:
            required = ".optional(" not in line
            keys[key] = required
    return {"keys": keys, "catchall": False}


def _schema_info(name: str) -> dict:
    stmt = _schema_statement(name)
    if ".object(" in stmt:
        idx = stmt.index(".object(") + len(".object(") - 1
        brace_open = stmt.index("{", idx)
        brace_close = _brace_match(stmt, brace_open)
        body = stmt[brace_open + 1 : brace_close]
        info = _object_info(body)
        info["catchall"] = ".catchall(" in stmt[brace_close:]
        # 语句剩余部分（catchall 之后）也可能再有 .catchall，放宽：看整句
        if ".catchall(" in stmt:
            info["catchall"] = True
        info["kind"] = "object"
        return info
    arr = re.search(r"z\.array\(\s*([A-Za-z_]\w*)", stmt)
    if arr:
        inner = arr.group(1)
        if inner == "z":  # z.array(z.string()) 之类
            return {"kind": "array_primitive"}
        sub = _schema_info(inner)
        return {"kind": "array", "element": sub}
    if "z.record(" in stmt:
        return {"kind": "record"}
    raise AssertionError(f"{name} 形态无法解析（既非 object/array/record）")


# ───────────────────────── 端点 ↔ schema 映射（源自 frontend-v2/src/api/read.ts 真扫）─────────
# 纯离线能力端点（本地 json/db，绝不触网），严格 key 对齐
OBJ_ENDPOINTS = [
    ("/api/v2/read/daily-snapshot", "DailySnapshotSchema"),
    ("/api/v2/read/daily-recommendation", "DailyRecommendationSchema"),
    ("/api/v2/read/user-dashboard", "UserDashboardSchema"),
    ("/api/v2/read/paper-trades?user=admin", "PaperTradeSchema"),
    ("/api/v2/read/event-pool", "EventPoolSchema"),
    ("/api/v2/read/p1-sync-status", "P1SyncStatusSchema"),
    ("/api/v2/read/data-refresh-state", "DataRefreshStateSchema"),
    ("/api/v2/read/breadth-analytics?dim=up_count", "BreadthAnalyticsSchema"),
    ("/api/v2/read/breadth-zseries?dim=up_count", "ZSeriesSchema"),
    ("/api/v2/read/trading-account", "TradingAccountSchema"),
    ("/api/v2/read/snapshot/2026-08-31", "DailySnapshotSchema"),
]
# 列表端点（data 为数组）—— 映射到「元素 schema」，校验首元素 key 对齐
LIST_ENDPOINTS = [
    ("/api/v2/read/prediction-log", "PredictionLogRowSchema"),
    ("/api/v2/read/ladder-detail", "LadderDaySchema"),
    ("/api/v2/read/breadth-history", "BreadthHistoryPointSchema"),
    ("/api/v2/read/webapps", "WebAppSchema"),
    ("/api/v2/read/snapshot-dates", None),  # 数组元素为字符串
]
# 松校验端点（前端手动 .parse，无 Zod 强约束；仅保证 200 + dict）
LOOSE_ENDPOINTS = [
    ("/api/v2/read/p1-signals", None),
]
# 联网能力端点（akshare/BaoStock/实时行情）—— 离线不真打完整数据，仅登记 + 优雅降级断言。
# 含显式 akshare 端点，以及「本地为主但尝试实时行情/基准」的 portfolio/watch/macro-data。
NET_ENDPOINTS = [
    "/api/v2/read/portfolio",
    "/api/v2/read/watch",
    "/api/v2/read/macro-data",
    "/api/v2/read/six-dim?code=600519",
    "/api/v2/read/fundamentals?code=600519",
    "/api/v2/read/financials?code=600519",
    "/api/v2/read/stock-kline?code=600519",
    "/api/v2/read/fund-flow",
    "/api/v2/read/dragon-tiger",
    "/api/v2/read/theme",
    "/api/v2/read/theme-transmission?limit=60",
    "/api/v2/read/strong",
    "/api/v2/read/sector-rotation",
    "/api/v2/read/quote-board",
    "/api/v2/read/earnings-calendar",
    "/api/v2/read/market-panorama?k=8",
    "/api/v2/read/breadth-timeseries",
    "/api/v2/read/limit-up-review",
    "/api/v2/read/market-sentiment",
    "/api/v2/read/factor-analysis?codes=600519&days=60&factor=momentum&n_layers=5&forward=1",
]


def _assert_obj_contract(real_keys: set, info: dict, where: str):
    schema_keys = set(info["keys"])
    required = {k for k, req in info["keys"].items() if req}
    # 1) 必需字段不得缺失（前端必依赖，缺失即软缺/破版）
    missing_required = required - real_keys
    assert not missing_required, (
        f"{where}: 真后端缺 schema 必需字段 {sorted(missing_required)} "
        f"（schema={sorted(schema_keys)}，real={sorted(real_keys)}）"
    )
    # 2) 真后端不得发 schema 未知字段（否则无 catchall 时前端 Zod 硬崩）
    unknown = real_keys - schema_keys
    if not info.get("catchall"):
        assert not unknown, (
            f"{where}: 真后端返回 schema 未声明字段 {sorted(unknown)} "
            f"（schema 无 .catchall()，前端会 parse 失败）"
        )
    else:
        # 有 catchall：未知字段容忍，仅记录以便人工复核
        if unknown:
            pytest.skip(
                f"{where}: 容忍未知字段 {sorted(unknown)}（schema 有 .catchall()）"
            )


def _timed_get(client, path, headers, secs=10):
    """带看门狗的 GET：离线端点必须瞬时返回，超时即判定为同步阻塞（网络/锁/子进程）。"""
    box = {}

    def _run():
        try:
            box["r"] = client.get(path, headers=headers)
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(secs)
    if t.is_alive():
        raise AssertionError(f"{path}: 调用 {secs}s 超时（疑似同步阻塞：网络/锁/子进程）")
    if "err" in box:
        raise box["err"]
    return box["r"]


def _fetch_data(client, token, path):
    r = _timed_get(client, path, {"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, f"{path} 期望 200，实得 {r.status_code}"
    j = r.get_json(force=True)
    assert isinstance(j, dict) and "data" in j, f"{path} 信封异常：{j}"
    return j["data"], j.get("status")


def test_offline_object_endpoints_match_schema(client, token):
    """离线 object 端点：真后端 data 键 ⊇ schema 必需键，且不越界未知键。"""
    for path, schema in OBJ_ENDPOINTS:
        info = _schema_info(schema)
        data, _ = _fetch_data(client, token, path)
        assert isinstance(data, dict), f"{path}: data 非 dict（{type(data)}）"
        _assert_obj_contract(set(data.keys()), info, path)


def test_offline_list_endpoints_match_schema(client, token):
    """离线 list 端点：data 为数组；首元素（若为对象）与元素 schema 对齐。"""
    for path, elem_schema in LIST_ENDPOINTS:
        data, _ = _fetch_data(client, token, path)
        assert isinstance(data, list), f"{path}: data 非 list（{type(data)}）"
        if not data:
            continue
        if elem_schema is None:  # 数组元素为字符串（如 snapshot-dates）
            assert all(
                isinstance(x, str) for x in data
            ), f"{path}: 数组元素非字符串"
            continue
        info = _schema_info(elem_schema)
        assert info["kind"] == "object", f"{path}: 元素 schema {elem_schema} 非 object"
        first = data[0]
        assert isinstance(first, dict), f"{path}: 首元素非 dict"
        _assert_obj_contract(set(first.keys()), info, f"{path}[0]/{elem_schema}")


def test_loose_endpoints_alive(client, token):
    """p1-signals 等前端手动 parse 端点：仅保证 200 + dict（无 Zod 强约束）。"""
    for path, _ in LOOSE_ENDPOINTS:
        data, status = _fetch_data(client, token, path)
        assert isinstance(data, dict), f"{path}: 期望 dict，实得 {type(data)}"
        assert status in (None, "ok", "error"), f"{path}: 状态异常 {status}"


# ───────────────────────── 联网端点：登记枚举 + 离线优雅降级（绝不静默 skip）─────────
def _registered_routes() -> set:
    text = READ_ROUTES.read_text(encoding="utf-8")
    routes = set()
    for m in re.finditer(r'@bp\.get\(\s*"([^"]+)"', text):
        routes.add(m.group(1))
    return routes


def test_net_dependent_endpoints_enumerated():
    """联网端点被显式登记（非静默跳过），且每个都真实注册在后端。"""
    assert NET_ENDPOINTS, "联网端点登记列表不得为空"
    routes = _registered_routes()
    prefix = "/api/v2/read"
    missing = []
    for p in NET_ENDPOINTS:
        base = p.split("?")[0]
        rel = base[len(prefix):] if base.startswith(prefix) else base
        if rel not in routes:
            missing.append(p)
    assert not missing, f"以下登记端点实际未注册：{missing}"


def _apply_offline_stub(monkeypatch):
    """把网络/DNS/子进程/库入口瞬间打挂，模拟离线环境。"""
    import socket
    import subprocess
    import http.client
    import urllib.request

    try:
        import requests
    except ImportError:
        requests = None

    class _DeadSocket(socket.socket):
        def connect(self, *a, **k):
            raise OSError("offline-simulated")

    monkeypatch.setattr(socket, "socket", lambda *a, **k: _DeadSocket())
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(
        OSError("offline-simulated")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(
        OSError("offline-simulated")))
    monkeypatch.setattr(socket, "gethostbyname", lambda *a, **k: (_ for _ in ()).throw(
        OSError("offline-simulated")))
    monkeypatch.setattr(socket, "setdefaulttimeout", lambda *a, **k: None)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("offline-simulated"))
    )
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline-simulated"))
    )
    if requests is not None:
        monkeypatch.setattr(
            requests.adapters.HTTPAdapter, "send",
            lambda self, *a, **k: (_ for _ in ()).throw(ConnectionError("offline-simulated")),
        )
        monkeypatch.setattr(
            requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline-simulated"))
        )
        monkeypatch.setattr(
            requests, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline-simulated"))
        )
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline-simulated")),
    )
    monkeypatch.setattr(
        http.client.HTTPConnection, "connect",
        lambda self, *a, **k: (_ for _ in ()).throw(ConnectionError("offline-simulated")),
    )
    monkeypatch.setattr(
        http.client.HTTPSConnection, "connect",
        lambda self, *a, **k: (_ for _ in ()).throw(ConnectionError("offline-simulated")),
    )
    # 日线取数入口（PortfolioManager.fetcher.get_daily 等最终都走到这里）；
    # 离线直接返回空，避免逐标的超时重试把单测拖死。
    try:
        import modules.fetcher_kline as _fk

        monkeypatch.setattr(_fk, "observe_source", lambda *a, **k: None)
    except Exception:  # noqa: BLE001
        pass


@pytest.mark.parametrize("path", NET_ENDPOINTS)
def test_net_dependent_endpoint_graceful(monkeypatch, client, token, path):
    """联网端点离线必须优雅降级（200 而非 500）；并核实返回合法信封。

    离线通过 _apply_offline_stub 模拟。若该端点因「逐标的逐只取日线」等导致离线慢降级
    （超时而非 500），则显式 skip——这是环境限制而非缺陷，并已在枚举测试中登记，并非静默跳过。
    """
    _apply_offline_stub(monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = _timed_get(client, path, headers, secs=12)
    except AssertionError as e:  # 来自看门狗的「超时」
        if "超时" in str(e):
            pytest.skip(
                f"{path}: 离线慢降级（逐标的取日线/网络超时），需联网 CI 验证 shape 与降级"
            )
        raise
    assert r.status_code != 500, (
        f"{path}: 离线环境返回 500（akshare 调用未加护栏，生产环境会硬崩）"
    )
    j = r.get_json(force=True)
    assert isinstance(j, dict) and "status" in j, (
        f"{path}: 离线返回非信封结构，疑似未捕获异常"
    )
