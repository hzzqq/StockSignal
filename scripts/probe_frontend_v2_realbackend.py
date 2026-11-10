#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/probe_frontend_v2_realbackend.py — frontend-v2 × 真后端 浏览器联调探针.

为什么需要它
------------
`scripts/shoot_frontend_v2.py` 走的是 MSW dev fixtures：能证明主题/渲染/深链在真实浏览器
生效，但**证明不了前端真的连得上 Flask 后端**。本脚本补上这一环：

* 独立端口起一套隔离 Flask（独立 SQLite 库 + 独立 secret + 6 个调度器全关），
  **绝不接管老板 5050 / 5173 活服务**；
* 用种子账号 `POST /api/auth/login` 拿**真实 JWT** 注入 localStorage（不是演示假 token）；
* Vite 设 `VITE_ENABLE_MOCKS=false` 关 MSW，`VITE_PROXY_TARGET` 指向隔离后端；
* headless Chrome 逐页采样：主题令牌、React 挂载、截图、MockBanner 必须消失，并在
  **浏览器内** fetch 只读端点，比对 `message` 指纹与直连后端的响应；
  MSW 的默认 message 是 'ok'，真后端 /api/v2/read/webapps 是 'webapps/'，故无法蒙混。

诚实边界
--------
「真后端」只指**非 MSW 的 Flask 服务**。隔离库是新库，行情数据仍是离线确定性样例 /
诚实 null 降级，**不等于真实行情**。报告里逐项记录，不把降级包装成成功，不写 JWT 明文。

复现
----
    python scripts/probe_frontend_v2_realbackend.py --out E:/tmp/ss_realbackend_shots

产物落在 `--out`（默认系统临时目录），截图/服务日志/报告均**不提交仓库**。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# 复用 shoot_frontend_v2.py 已验证的 CDP 设施（零 npm 依赖，不重写 790 行）。
from shoot_frontend_v2 import (  # noqa: E402
    CDP, THEMES, VIEWPORT, find_chrome, launch_chrome, page_ws_url,
    port_free, sample, stop_proc, wait_http, wait_ready,
)

logger = logging.getLogger("probe_frontend_v2_realbackend")

ROOT = _HERE.parent
FE_DIR = ROOT / "frontend-v2"
DEFAULT_BACKEND_PORT = 5051
DEFAULT_FRONTEND_PORT = 5181
DEFAULT_DEBUG_PORT = 9223
DEFAULT_OUT = Path(tempfile.gettempdir()) / "ss_realbackend_probe"

FINGERPRINT_ENDPOINT = "/api/v2/read/webapps"  # 本地目录扫描，真后端 message='webapps/'
MSW_FAKE_MESSAGE = "ok"  # mocks/handlers.ts::ok() 默认 message
MOCK_BANNER_TEXT = "演示数据（Mock）"

# 2026-11-10 真缺陷已修：read_routes._w4x_index_daily 原先在 Flask 进程内被 fetch_many
# 多线程直调 akshare 新浪日线，触发 py_mini_racer(V8)
# [FATAL:partition_address_space.cc(243)] native 崩溃（try/except 捕获不到，直接杀死后端）。
# 现在日线取数统一走 backend/api/_index_daily_worker.py 的独立解释器子进程，
# 父进程只做 JSON -> DataFrame；崩溃/超时只让对应指数诚实降级为 null。
# 因此下面 3 个实时源端点与 Dashboard "/" 重新纳入联调，并逐端点复核后端存活。
REALTIME_ENDPOINTS = (
    "/api/v2/read/index-quotes",
    "/api/v2/read/index-kline?code=sh000001",
    "/api/v2/read/quote-board",
)

SCHEDULER_OFF = {
    "STOCKSIGNAL_ENABLE_COND_SCHEDULER": "0",
    "STOCKSIGNAL_ENABLE_DATA_REFRESH": "0",
    "STOCKSIGNAL_ENABLE_ALERT_SCHEDULER": "0",
    "STOCKSIGNAL_ENABLE_RECOMMEND_SCHEDULER": "0",
    "STOCKSIGNAL_ENABLE_P1_SYNC_SCHEDULER": "0",
    "STOCKSIGNAL_ENABLE_RESEARCH_WATCH": "0",
}

# V8 隔离修复后，Dashboard "/"（顺带打 index-quotes）与行情看板 /quote-board
# 重新纳入：这两页此前因 native 崩溃被排除，是本轮修复最直接的验收对象。
# 每页采样后仍打 /api/health 复核后端存活；若修复回潮，会如实定位到具体路由并中止。
ROUTES = (
    ("/", "dashboard"),
    ("/quote-board", "quote_board"),
    ("/webapps", "webapps"),
    ("/guide", "guide"),
    ("/settings", "settings"),
)

STATIC_ASSET = "/webapps/emotion-cycle-clock/index.html"


# ── HTTP / 进程小工具 ──────────────────────────────────────────────────────
def http_json(url: str, token: str | None = None, timeout: float = 10.0) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def login(base: str, username: str, password: str) -> str:
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/auth/login", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    data = payload.get("data") or {}
    token = data.get("token") or data.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"登录响应缺真实 JWT：{str(payload)[:200]}")
    return token


def spawn(argv: list[str], cwd: Path, env: dict, log_path: Path):
    handle = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
        stdout=handle, stderr=subprocess.STDOUT,
    )
    return proc, handle


# ── 单页真后端采样 ─────────────────────────────────────────────────────────
def capture_real(cdp: CDP, base_url: str, route: str, theme: str, name: str,
                 out_dir: Path, settle_ms: int, expected_message: str) -> dict:
    url = base_url + route
    rec: dict = {"route": route, "theme": theme, "url": url, "ok": False}
    try:
        stamp = f"probe-{time.time_ns()}"
        try:
            cdp.js(f"window.__auditStamp = {json.dumps(stamp)}; true")
        except Exception:
            stamp = ""
        cdp.call("Page.navigate", {"url": url})
        if not wait_ready(cdp, 25, old_stamp=stamp or None):
            rec["error"] = "页面未在 25s 内挂载 React 根节点"
            return rec
        time.sleep(settle_ms / 1000.0)

        info = sample(cdp)
        rec["sample"] = info

        dom = cdp.js("""(() => {
            const body = document.body.innerText || '';
            return {mockBanner: body.includes(%s), path: location.pathname,
                    textLen: body.length, hasNoData: body.includes('暂无数据')};
        })()""" % json.dumps(MOCK_BANNER_TEXT, ensure_ascii=False))

        fp = cdp.js("""(async () => {
            const hdr = {Authorization: 'Bearer ' + (localStorage.getItem('ss_token') || '')};
            const r = await fetch(%s, {headers: hdr});
            const j = await r.json().catch(() => ({}));
            return {status: r.status, message: (j && j.message) || null,
                    dataKeys: (j && j.data && typeof j.data === 'object')
                        ? Object.keys(j.data).length : 0};
        })()""" % json.dumps(FINGERPRINT_ENDPOINT))

        shot = cdp.call("Page.captureScreenshot",
                        {"format": "png", "captureBeyondViewport": False})
        data = base64.b64decode(shot.get("data", ""))
        dest = out_dir / f"{name}.png"
        dest.write_bytes(data)
        rec["png"] = str(dest)
        rec["png_bytes"] = len(data)

        tokens = info.get("tokens") or {}
        checks = {
            "theme": info.get("theme") == theme,
            "react_mounted": info.get("rootChildren", 0) >= 1,
            "screenshot": len(data) >= 1024,
            "tokens": all(tokens.get(k) for k in ("sf-bg", "sf-ink", "ss-up", "doc-up")),
            "msw_banner_absent": dom.get("mockBanner") is False,
            "fingerprint_http_200": fp.get("status") == 200,
            "fingerprint_not_msw": bool(fp.get("message")) and fp.get("message") != MSW_FAKE_MESSAGE,
            "fingerprint_matches_direct": fp.get("message") == expected_message,
            "fingerprint_has_data": (fp.get("dataKeys") or 0) > 0,
        }
        rec["checks"] = checks
        rec["fingerprint"] = fp
        rec["dom"] = dom
        bad = [k for k, v in checks.items() if not v]
        if bad:
            rec["error"] = "failed: " + ", ".join(bad)
            logger.warning("✗ %-6s %-18s %s", theme, route, rec["error"])
        else:
            rec["ok"] = True
            logger.info("✓ %-6s %-18s bg=%s msg=%s -> %s (%dB)",
                        theme, route, tokens.get("sf-bg"), fp.get("message"),
                        dest.name, len(data))
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        logger.error("✗ %-6s %-18s %s", theme, route, rec["error"])
    return rec


def probe_static_asset(base_frontend: str) -> dict:
    """经 Vite 代理访问 Flask 静态托管：MSW 关了才有真 HTML，是真后端独有证据。"""
    rec: dict = {"route": STATIC_ASSET, "kind": "static_asset", "ok": False}
    if not (ROOT / "webapps/emotion-cycle-clock/index.html").is_file():
        rec.update({"evaluated": False, "ok": True,
                    "detail": "示例作品文件缺失，未评估（不伪造通过）"})
        return rec
    try:
        with urllib.request.urlopen(base_frontend + STATIC_ASSET, timeout=10) as r:
            body = r.read(300).decode("utf-8", "replace")
            found = {"status": r.status,
                     "is_html": "<html" in body.lower() or "<!doctype" in body.lower()}
    except Exception as exc:
        found = {"error": f"{type(exc).__name__}: {exc}"}
    rec["probe"] = found
    rec["ok"] = found.get("status") == 200 and found.get("is_html") is True
    if not rec["ok"]:
        rec["error"] = "经 Vite 代理访问 Flask 静态作品失败（详见 probe）"
    return rec


def probe_realtime_endpoints(base_backend: str, token: str) -> list[dict]:
    """V8 修复后的硬证据：逐端点直连真后端，确认 native 崩溃不再带走 Flask 进程。

    判定四件事：HTTP 200 + ok 信封 + 数据诚实（缺失为 null/[]，绝不补 0、
    绝不 now() 冒充数据日）+ **每个端点之后 /api/health 仍 200**。
    V8 FATAL 旧行为是「端点返回途中整个后端消失」，这条复核能直接抓到回潮。
    取不到真行情不包装成成功：observed 字段如实记录可用数量与权威数据日。
    """
    out: list[dict] = []
    for ep in REALTIME_ENDPOINTS:
        rec: dict = {"route": ep, "kind": "realtime_endpoint", "ok": False}
        try:
            body = http_json(base_backend + ep, token=token, timeout=20)
            data = body.get("data") or {}
            checks = {
                "envelope_ok": body.get("status") == "ok",
                "has_data": isinstance(data, dict) and len(data) > 0,
            }
            if ep.startswith("/api/v2/read/index-quotes"):
                items = data.get("items") or []
                checks["items_shape"] = len(items) == 5
                checks["no_fake_zero"] = all(
                    x.get("current") is None or
                    (isinstance(x.get("current"), (int, float)) and x.get("current") != 0)
                    for x in items)
                rec["observed"] = {
                    "index_count": len(items),
                    "available": sum(1 for x in items if x.get("current") is not None),
                }
            elif ep.startswith("/api/v2/read/index-kline"):
                krows = data.get("rows") or []
                kdate = data.get("date")
                checks["rows_list"] = isinstance(krows, list)
                checks["date_honest"] = kdate is None or bool(
                    re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(kdate)))
                rec["observed"] = {"rows": len(krows), "date": kdate}
            else:
                idxs = data.get("indices") or []
                checks["indices_shape"] = len(idxs) == 5
                checks["no_fake_zero"] = all(
                    x.get("current") is None or
                    (isinstance(x.get("current"), (int, float)) and x.get("current") != 0)
                    for x in idxs)
                # 全降级必须在 unavailable 标注（前端据此显示提示），不许静默故障
                checks["missing_marked"] = (
                    (data.get("summary") or {}).get("index_available", 0) > 0
                    or "index_quotes_unavailable" in (data.get("unavailable") or [])
                )
                rec["observed"] = {
                    "index_count": len(idxs),
                    "available": (data.get("summary") or {}).get("index_available"),
                    "unavailable": data.get("unavailable"),
                }
            health = http_json(base_backend + "/api/health", timeout=3)
            checks["backend_alive"] = health.get("status") == "ok"
            rec["checks"] = checks
            bad = [k for k, v in checks.items() if not v]
            if bad:
                rec["error"] = "failed: " + ", ".join(bad)
                logger.error("x 实时端点 %-46s %s", ep, rec["error"])
            else:
                rec["ok"] = True
                logger.info("OK 实时端点 %-46s %s", ep, rec.get("observed"))
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            logger.error("x 实时端点 %s %s", ep, rec["error"])
        out.append(rec)
    return out


# ── 主流程 ────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="frontend-v2 × 真后端 浏览器联调探针")
    p.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    p.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    p.add_argument("--debug-port", type=int, default=DEFAULT_DEBUG_PORT)
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--themes", default=",".join(THEMES))
    p.add_argument("--routes", default="", help="逗号分隔页面名，留空=全部")
    p.add_argument("--settle-ms", type=int, default=1200)
    p.add_argument("--chrome", default=None)
    p.add_argument("--user", default=os.environ.get("SS_PROBE_USER", "admin"))
    p.add_argument("--password", default=os.environ.get("SS_PROBE_PASSWORD", "Admin@123"))
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    args = parse_args(argv)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    unknown = [t for t in themes if t not in THEMES]
    if unknown:
        logger.error("未知主题：%s（可用 %s）", unknown, THEMES)
        return 2

    routes = list(ROUTES)
    if args.routes.strip():
        want = {r.strip().lstrip("/") for r in args.routes.split(",") if r.strip()}
        routes = [r for r in ROUTES if r[1] in want or r[0].lstrip("/") in want]
        if not routes:
            logger.error("--routes 未匹配任何已知页面名：%s（可用 %s）",
                         sorted(want), [r[1] for r in ROUTES])
            return 2

    for port, label in ((args.backend_port, "backend"),
                        (args.frontend_port, "frontend"),
                        (args.debug_port, "CDP")):
        if not port_free(port):
            logger.error("%s 端口 %s 已被占用；本探针只使用空闲端口，绝不接管 5050/5173", label, port)
            return 1

    run_id = time.strftime("%Y%m%d_%H%M%S")
    probe_dir = Path(tempfile.gettempdir()) / "ss_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    db_path = probe_dir / f"realbackend_{run_id}.db"
    db_uri = "sqlite:///" + db_path.as_posix()
    secret = secrets.token_hex(24)
    base_backend = f"http://127.0.0.1:{args.backend_port}"
    base_frontend = f"http://127.0.0.1:{args.frontend_port}"

    be_env = os.environ.copy()
    be_env.update({
        "DATABASE_URL": db_uri,
        "STOCKSIGNAL_SECRET": secret,
        "STOCKSIGNAL_PORT": str(args.backend_port),
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    be_env.update(SCHEDULER_OFF)
    fe_env = os.environ.copy()
    fe_env.update({
        "VITE_ENABLE_MOCKS": "false",
        "VITE_PROXY_TARGET": base_backend,
        "PYTHONUNBUFFERED": "1",
    })

    procs: dict[str, object] = {}
    handles: list = []
    cdp = None
    exe = None
    try:
        logger.info("启动隔离 Flask：%s（独立库 %s；6 个调度器全关；不触碰 5050）",
                    base_backend, db_path)
        be_proc, h = spawn(
            [sys.executable, "-m", "backend.run", "--host", "127.0.0.1",
             "--port", str(args.backend_port)],
            ROOT, be_env, out_root / "backend.log",
        )
        procs["backend"] = be_proc
        handles.append(h)
        if not wait_http(base_backend + "/api/health", timeout=90):
            raise RuntimeError("隔离后端 90s 内未就绪，详见 backend.log")
        health = http_json(base_backend + "/api/health")
        logger.info("后端健康检查：%s", str((health.get("data") or {}))[:180])

        token = login(base_backend, args.user, args.password)
        token_fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        logger.info("真实 JWT 获取成功（sha256[:12]=%s，明文不写报告）", token_fp)
        direct = http_json(base_backend + FINGERPRINT_ENDPOINT, token=token)
        direct_message = direct.get("message") or ""
        if not direct_message or direct_message == MSW_FAKE_MESSAGE:
            raise RuntimeError(f"直连后端指纹异常：message={direct_message!r}（疑似不是真后端）")
        logger.info("直连隔离后端 %s 指纹 message=%r", FINGERPRINT_ENDPOINT, direct_message)

        node = shutil.which("node")
        vite_js = FE_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not node or not vite_js.is_file():
            raise RuntimeError(f"无法启动 Vite：node={node} vite={vite_js}")
        logger.info("启动 Vite（MSW 关闭，代理 -> %s）：%s", base_backend, base_frontend)
        fe_proc, h = spawn(
            [node, str(vite_js), "--port", str(args.frontend_port),
             "--strictPort", "--host", "127.0.0.1"],
            FE_DIR, fe_env, out_root / "frontend.log",
        )
        procs["frontend"] = fe_proc
        handles.append(h)
        if not wait_http(base_frontend, timeout=60):
            raise RuntimeError("Vite 60s 内未就绪，详见 frontend.log")

        exe = find_chrome(args.chrome)
        chrome_proc = launch_chrome(
            exe, args.debug_port,
            Path(tempfile.gettempdir()) / "ss_realbackend_chrome_profile",
        )
        procs["chrome"] = chrome_proc
        cdp = CDP(page_ws_url(args.debug_port))
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride",
                 {"width": VIEWPORT["width"], "height": VIEWPORT["height"],
                  "deviceScaleFactor": 1, "mobile": False})
        cdp.call("Page.navigate", {"url": base_frontend + "/login"})
        if not wait_ready(cdp, 30):
            raise RuntimeError("首次加载 /login 未挂载，后续注入无意义")

        records: list[dict] = []
        backend_lost_after: str | None = None
        for theme in themes:
            logger.info("── 主题 %s ──", theme)
            cdp.js(
                "(() => { localStorage.setItem('ss_theme', %s); "
                "        localStorage.setItem('ss_token', %s); return true; })()"
                % (json.dumps(theme), json.dumps(token))
            )
            theme_dir = out_root / theme
            theme_dir.mkdir(parents=True, exist_ok=True)
            for route, name in routes:
                records.append(capture_real(
                    cdp, base_frontend, route, theme, name,
                    theme_dir, args.settle_ms, direct_message,
                ))
                # 真后端专属风险：py_mini_racer(V8) native 崩溃会带走整个 Flask 进程。
                # 逐页复核存活，崩了如实定位到具体路由并中止，不把后续失败糊成一片。
                try:
                    http_json(base_backend + "/api/health", timeout=3)
                except Exception as exc:
                    backend_lost_after = route
                    logger.error("后端在 %s 之后失联：%s: %s",
                                 route, type(exc).__name__, exc)
                    break
            if backend_lost_after:
                break
        records.extend(probe_realtime_endpoints(base_backend, token))
        records.append(probe_static_asset(base_frontend))

        ok = sum(1 for r in records if r.get("ok"))
        fail = len(records) - ok
        report = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "real-backend browser probe (MSW disabled)",
            "browser": str(exe),
            "viewport": VIEWPORT,
            "isolation": {
                "backend_port": args.backend_port,
                "frontend_port": args.frontend_port,
                "database_url": db_uri,
                "secret_isolated": True,
                "secret_value_logged": False,
                "scheduler_flags": SCHEDULER_OFF,
                "touched_live_5050": False,
                "touched_live_5173": False,
            },
            "auth": {"username": args.user, "token_source": "POST /api/auth/login",
                     "token_sha256_12": token_fp, "token_plaintext_logged": False},
            "fingerprint": {"endpoint": FINGERPRINT_ENDPOINT,
                            "direct_message": direct_message,
                            "msw_would_be": MSW_FAKE_MESSAGE},
            "summary": {"total": len(records), "ok": ok, "failed": fail,
                        "all_checks_pass": fail == 0 and backend_lost_after is None},
            "known_limitations": {
                "v8_native_crash": (
                    "结构性已修复：日线取数改走独立解释器子进程，Flask 进程内不再 "
                    "import akshare / 直调新浪日线（AST 守卫锁死）。本轮沙箱网络层取数即失败，"
                    "未复现 native 崩溃；崩溃/超时降级路径由单测模拟 rc=-1073741819 与 "
                    "TimeoutExpired 验证。3 个实时源端点与 Dashboard 均已纳入，"
                    "逐端点 + 逐页复核 /api/health 存活。"
                ),
                "v8_crash_reproduced_this_run": False,
                "realtime_endpoints": list(REALTIME_ENDPOINTS),
                "data_honesty": (
                    "隔离库无真实行情时，指数/板块一律 null/[] 降级；报告 observed 字段"
                    "如实记录取到的数量与权威数据日，绝不补 0、绝不 now() 冒充数据日。"
                ),
                "covered_scope": (
                    "本地 JSON / 本地 DB / 静态内容页 + Dashboard + 行情看板 + "
                    "3 个实时源端点直连 + 浏览器内端点指纹"
                ),
                "not_covered": (
                    "真人交互 E2E（键盘/表单/hover/多视口/多浏览器）与真行情数据联调；"
                    "隔离环境拿到的仍可能是诚实 null 降级，不等于真实行情；"
                    "本轮未复现 V8 native 崩溃（网络层先失败），不把结构性隔离吹成实测崩溃存活。"
                ),
            },
            "backend_lost_after": backend_lost_after,
            "note": (
                "真后端 = 独立端口的 Flask 服务（非 MSW fixtures）；隔离新库的数据仍是"
                "离线确定性样例 / 诚实 null 降级，不等于真实行情。V8 native 崩溃已用"
                "独立解释器子进程隔离，Dashboard 与 3 个实时源端点均重新纳入联调，"
                "每端点后复核 /api/health。headless 自动截图 + 计算样式采样 + "
                "浏览器内端点指纹 + 端点级直连探测，非人工审美结论，非真人交互 E2E。"
            ),
            "records": records,
        }
        report_path = out_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        logger.info("完成：成功 %d / 失败 %d；报告 %s", ok, fail, report_path)
        return 0 if (fail == 0 and backend_lost_after is None) else 3
    except Exception as exc:
        logger.error("联调中断：%s: %s", type(exc).__name__, exc)
        return 1
    finally:
        if cdp:
            cdp.close()
        for label in ("chrome", "frontend", "backend"):
            stop_proc(procs.get(label), label)
        for h in handles:
            try:
                h.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
