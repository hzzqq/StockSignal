#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/shoot_frontend_v2.py — frontend-v2 暗/亮主题「真实浏览器」目检
====================================================================

用途
----
对 React 新前端 ``frontend-v2/`` 的 dark / light 两套主题逐页截图，并在**真实浏览器
计算样式**层面采样 CSS 令牌，产出可核查的 ``report.json``。目的是补上单元测试 /
vite build / dist CSS 真扫都证明不了的一环：**浏览器里主题到底有没有真的生效**。

与 ``scripts/shoot_styles.py`` 的分工（不要混用、不要互相改造）
--------------------------------------------------------------
* ``shoot_styles.py``：服务**旧 Streamlit 前端**（8899），6 套 ui_style，
  用 ``prefs=`` query + ``--card`` 变量判就绪，Playwright 驱动。旧前端仍在运行，保留。
* 本脚本：服务**新 React SPA**（默认 5180），2 套主题，用 localStorage
  ``ss_theme`` / ``ss_token`` 驱动，CDP 驱动本机 Chrome/Edge。
  两者目标、URL 构造、就绪判据、登录方式、输出结构全不同。

为什么不用 Playwright
---------------------
本仓库未安装 Playwright/Puppeteer；本机已有 Chrome / Edge。本脚本通过 Chrome DevTools
Protocol 直接驱动本机浏览器，**零 npm 依赖**，只需 Python 的 ``websocket-client``
（缺库时会给出明确安装提示，不静默降级、不伪造截图）。

运行前提
--------
1) 推荐一键（脚本自己 headless 起 Vite 并在结束时关闭）::

       python scripts/shoot_frontend_v2.py --start-app

2) 或你已自行启动 Vite ::

       npx vite --port 5180 --strictPort --host 127.0.0.1
       python scripts/shoot_frontend_v2.py --base-url http://127.0.0.1:5180

   可选参数：``--themes dark,light`` / ``--routes login,dashboard,events`` / ``--out <dir>`` /
   ``--chrome <exe>`` / ``--debug-port <port>`` / ``--settle-ms <ms>``。

设计约束（诚实红线）
--------------------
* 登录态由 ``localStorage['ss_token']`` 判据驱动（见 src/app/guards.tsx），dev 模式
  MSW 自动接管 /api（见 src/main.tsx），因此**不需要真后端、不需要真账号、不改动产品代码**。
* 采样值缺失就如实记 ``null`` 并判失败，禁止补默认值、禁止把失败页当成功。
* 每张截图必须 >1KB，否则视为失败。
* 报告里明确标注这是「headless 自动截图 + 计算样式采样」，**不是人工审美结论**。
* 产出仅写入 ``artifacts/shots/frontend-v2/``（本地目检产物，不提交仓库）。
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("shoot_frontend_v2")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend-v2"
DEFAULT_BASE_URL = "http://127.0.0.1:5180"
DEFAULT_OUT = PROJECT_ROOT / "artifacts" / "shots" / "frontend-v2"

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

THEMES = ("dark", "light")

# (SPA 路由, 截图文件名)。与 src/nav/nav.ts 的 AppPath **严格对齐**：覆盖全部 39 条路由，
# 另保留 1 条多状态变体（/stock/compare?codes=...）。/login 单独保留未登录门禁形态。
# 改 nav.ts 新增/删除路由时，本元组必须同步，否则视觉审计会漏页（守卫见
# tests/test_frontend_v2_route_coverage.py）。
# 2026-11-09 补记：Tier1/Tier2 迁移新增的 14 页（factor/backtest/.../quote-board）
# 此前从未进入真浏览器审计，守卫 test_routes_cover_all_app_paths 报红后一并补齐。
ROUTES = (
    ("/login", "login"),
    ("/", "dashboard"),
    ("/decision", "decision"),
    ("/replay", "replay"),
    ("/morning", "morning"),
    ("/p1", "p1"),
    ("/recommend", "recommend"),
    ("/paper", "paper"),
    ("/alerts", "alerts"),
    ("/webapps", "webapps"),
    ("/breadth", "breadth"),
    ("/ladder", "ladder"),
    ("/events", "events"),
    ("/predictions", "predictions"),
    ("/ops", "ops"),
    ("/diagnostics", "diagnostics"),
    ("/settings", "settings"),
    ("/catalog", "catalog"),
    ("/data", "data"),
    ("/stock/six-dim", "sixdim"),  # W4-A 六维评分：暗/亮两主题真实验收
    ("/stock/research", "research"),          # W4-B 个股研究（旧 24）
    ("/stock/fundamentals", "fundamentals"),  # W4-B 基本面分析（旧 22）
    ("/stock/compare", "compare"),            # W4-C 多股对比（默认态）
    ("/stock/compare?codes=600519,000001", "compare_dual"),  # W4-C 多股对比（双码态）
    ("/factor", "factor"),                    # Tier2 因子分析
    ("/backtest", "backtest"),                # Tier2 策略回测
    ("/panorama", "panorama"),                # Tier2 市场全景
    ("/regime", "regime"),                    # Tier2 市场状态机
    ("/portfolio", "portfolio"),              # Tier2 持仓中心
    ("/fund-flow", "fund_flow"),              # Tier2 资金流向
    ("/trading-account", "trading_account"),  # Tier2 实盘交易（仅目检，不改页面代码）
    ("/macro-data", "macro_data"),            # Tier2 宏观数据
    ("/dragon-tiger", "dragon_tiger"),        # Tier2 龙虎榜
    ("/theme", "theme"),                      # Tier2 题材热点
    ("/strong", "strong"),                    # Tier2 实时强势榜
    ("/sector-rotation", "sector_rotation"),  # Tier2 板块轮动
    ("/watch", "watch"),                      # Tier2 智能盯盘
    ("/quote-board", "quote_board"),          # Tier2 行情看板（10 页 V2 化）
    ("/matrix", "matrix"),
    ("/guide", "guide"),
)

# W4-B 深链专项：/legacy 走客户端 history.replace（不是新 document），
# 不能复用 capture() 的 window.__auditStamp 就绪判据，否则会误判「仍是旧页面」。
# (route, name, expect_path, search 必须包含, search 禁止包含, 红线说明)
_LEGACY_ZH_DEEP = urllib.parse.quote("🔬 深度分析")
DEEPLINK_CASES = (
    ("/legacy?pick_stock=000001", "legacy_pick_custom",
     "/stock/research", ("view=quick", "code=000001"), ("600519",),
     "custom code passthrough (no hardcoded 600519)"),
    ("/stock/research?view=deep&code=600519", "deeplink_deep",
     "/stock/research", ("view=deep", "code=600519"), (),
     "深链直达 view=deep 首帧预选"),
    ("/legacy?hub_gyj_view=" + _LEGACY_ZH_DEEP + "&pick_stock=600519", "legacy_zh_deep",
     "/stock/research", ("view=deep", "code=600519"), (),
     "旧链接中文 hub_gyj_view 映射为 deep"),
    ("/legacy?pick_stock=600519", "legacy_pick_only",
     "/stock/research", ("view=quick", "code=600519"), (),
     "只传 pick_stock 落 quick（旧版 22:864-866 真值）"),
    ("/legacy?hub_gyj_view=quick&pick_stock=abc", "legacy_bad_code",
     "/stock/research", (), ("abc", "code="),
     "非法 code 不进入最终 search"),
    ("/stock/research?view=deep&code=600519", "deeplink_deep_w4c",
     "/stock/research", ("view=deep", "code=600519"), (),
     "24 深链直达 view=deep（W4-C 迁移后真实深度内容）"),
)

# 真实浏览器计算样式采样：既证明主题生效，也守 A 股双套语义红线。
PROBES = {
    "sf-bg": "--color-sf-bg",
    "sf-surface": "--color-sf-surface",
    "sf-ink": "--color-sf-ink",
    "sf-ok": "--color-sf-ok",
    "sf-line-strong": "--color-sf-line-strong",
    "ss-up": "--color-ss-up",
    "ss-down": "--color-ss-down",
    "doc-up": "--color-doc-up",
    "doc-down": "--color-doc-down",
}

VIEWPORT = {"width": 1440, "height": 900}
AUTH_TOKEN = "visual-audit-local-token"


# ── 小工具 ────────────────────────────────────────────────────────────────
def port_free(port: int) -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) != 0
    finally:
        s.close()


def http_json(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def wait_http(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def find_chrome(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise RuntimeError(f"--chrome 指向的文件不存在：{p}")
        return p
    for c in CHROME_CANDIDATES:
        p = Path(c)
        if p.is_file():
            return p
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    raise RuntimeError("未找到本机 Chrome/Edge，请用 --chrome 指定可执行文件绝对路径")


# ── Vite / Chrome 进程管理 ─────────────────────────────────────────────────
def start_vite(base_url: str):
    port = urllib.parse.urlparse(base_url).port or 5180
    node = shutil.which("node")
    vite_js = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite_js.is_file():
        raise RuntimeError(f"无法启动 Vite：node={node} vite={vite_js}")
    logger.info("启动 Vite dev server：127.0.0.1:%s", port)
    proc = subprocess.Popen(
        [node, str(vite_js), "--port", str(port), "--strictPort", "--host", "127.0.0.1"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    if not wait_http(base_url, timeout=60):
        stop_proc(proc, "Vite")
        raise RuntimeError(f"Vite 在 60s 内未就绪：{base_url}")
    logger.info("Vite 已就绪：%s", base_url)
    return proc


def launch_chrome(exe: Path, debug_port: int, user_data: Path):
    user_data.mkdir(parents=True, exist_ok=True)
    args = [
        str(exe),
        "--headless=new",
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={user_data}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=%d,%d" % (VIEWPORT["width"], VIEWPORT["height"]),
        "about:blank",
    ]
    logger.info("启动 headless 浏览器：%s", exe.name)
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    endpoint = f"http://127.0.0.1:{debug_port}/json/version"
    if not wait_http(endpoint, timeout=30):
        stop_proc(proc, "Chrome")
        raise RuntimeError("Chrome CDP 端点未就绪")
    return proc


def stop_proc(proc, label: str) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
        except Exception as exc:
            logger.warning("关闭 %s 失败：%s", label, exc)


# ── 极简 CDP 客户端 ───────────────────────────────────────────────────────
class CDP:
    def __init__(self, ws_url: str):
        try:
            import websocket  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "缺少 websocket-client：请运行 pip install websocket-client"
            ) from exc
        # suppress_origin：Chrome 111+ 对 CDP websocket 做 Origin 校验，不发 Origin 最稳。
        self.ws = websocket.create_connection(ws_url, timeout=40, suppress_origin=True)
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} 失败：{msg['error']}")
                return msg.get("result", {})
            # 事件消息直接忽略（就绪判定采用轮询，不依赖事件流）

    def js(self, expression: str):
        r = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS 执行异常：{r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def page_ws_url(debug_port: int) -> str:
    targets = http_json(f"http://127.0.0.1:{debug_port}/json")
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("CDP 未找到 page target")


def wait_ready(cdp: CDP, timeout: float = 25.0, old_stamp: str | None = None) -> bool:
    """等新 document 挂载 React 根节点。

    old_stamp 是导航前写入旧页面的标记：新 document 上该标记必然消失，
    以此区分「新页面已就绪」与「仍在读旧页面 DOM」，避免截图串页。
    """
    expr = (
        "(() => ({ready: document.readyState, "
        "kids: (document.getElementById('root')||{}).children?.length || 0, "
        "stamp: (typeof window.__auditStamp === 'undefined') "
        "        ? null : window.__auditStamp}))()"
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            v = cdp.js(expr)
            fresh = old_stamp is None or v.get("stamp") != old_stamp
            if v and v.get("ready") == "complete" and v.get("kids", 0) > 0 and fresh:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def sample(cdp: CDP) -> dict:
    probes = json.dumps(PROBES, ensure_ascii=False)
    expr = """(() => {
        const cs = getComputedStyle(document.documentElement);
        const tokens = {};
        for (const [k, v] of Object.entries(%s)) {
            const raw = cs.getPropertyValue(v);
            tokens[k] = (typeof raw === 'string' && raw.trim()) ? raw.trim() : null;
        }
        return {
            path: location.pathname,
            theme: document.documentElement.getAttribute('data-theme'),
            colorScheme: cs.colorScheme || null,
            bodyBg: getComputedStyle(document.body).backgroundColor || null,
            rootChildren: (document.getElementById('root')||{}).children?.length || 0,
            textLen: (document.body.innerText || '').length,
            interactive: document.querySelectorAll(
                'input,button,a,table,canvas,[role="status"],[role="img"]'
            ).length,
            tokens: tokens
        };
    })()""" % probes
    out = cdp.js(expr)
    if not isinstance(out, dict):
        raise RuntimeError("计算样式采样返回非对象")
    return out


# ── 单页截取 ──────────────────────────────────────────────────────────────
def capture(cdp: CDP, base_url: str, route: str, theme: str,
            name: str, out_dir: Path, settle_ms: int) -> dict:
    url = f"{base_url}{route}"
    rec: dict = {"route": route, "theme": theme, "url": url, "ok": False}
    try:
        # 导航前给旧 document 打标记，确保就绪判定落在新页面而非旧 DOM
        stamp = f"audit-{time.time_ns()}"
        try:
            cdp.js(f"window.__auditStamp = {json.dumps(stamp)}; true")
        except Exception:
            stamp = ""
        cdp.call("Page.navigate", {"url": url})
        if not wait_ready(cdp, 25, old_stamp=stamp or None):
            rec["error"] = "页面未在 25s 内挂载 React 根节点"
            return rec
        # 额外静置：等 MSW / TanStack Query / ECharts 懒加载与字体回流
        time.sleep(settle_ms / 1000.0)
        info = sample(cdp)
        rec["sample"] = info

        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{name}.png"
        shot = cdp.call(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
        )
        data = base64.b64decode(shot.get("data", ""))
        dest.write_bytes(data)
        rec["png"] = str(dest)
        rec["png_bytes"] = len(data)

        # 硬判定：主题、渲染、截图三者都不可含糊
        issues = []
        if info.get("theme") != theme:
            issues.append(f"data-theme={info.get('theme')!r} 期望 {theme!r}")
        if info.get("rootChildren", 0) < 1:
            issues.append("React 根节点为空（疑似白屏）")
        # 登录页文案天然很短（约 17 字），单看 textLen 会误报。
        # 组合判据：文本短 **且** 页面几乎没有可交互/内容元素，才判空壳。
        if info.get("textLen", 0) < 20 and info.get("interactive", 0) < 2:
            issues.append(
                "疑似空壳：正文仅 %s 字且可交互元素仅 %s 个"
                % (info.get("textLen"), info.get("interactive"))
            )
        if len(data) < 1024:
            issues.append(f"截图仅 {len(data)}B（疑似空白图）")
        for k in ("sf-bg", "sf-ink", "ss-up", "doc-up"):
            if not info.get("tokens", {}).get(k):
                issues.append(f"计算样式 {k} 缺失")
        if issues:
            rec["error"] = "；".join(issues)
            logger.warning("✗ %-6s %-16s %s", theme, route, rec["error"])
        else:
            rec["ok"] = True
            logger.info("✓ %-6s %-16s bg=%s -> %s (%dB)",
                        theme, route, info["tokens"]["sf-bg"], dest.name, len(data))
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        logger.error("✗ %-6s %-16s %s", theme, route, rec["error"])
    return rec


# ── 跨主题红线校验 ────────────────────────────────────────────────────────
# W4-A: six-dim partial-state browser assertion (real ECharts, real DOM)
def capture_sixdim_partial(cdp: CDP, theme: str, out_dir: Path,
                           settle_ms: int) -> dict:
    """Switch the six-dim page to code 000001 (MSW serves missing dims).

    Unit tests mock EChart as a placeholder, so they cannot prove that null
    dims are not drawn as 0 in a real ECharts canvas. This asserts, in a real
    browser: a real canvas exists, missing dims read "缺失" instead of 0,
    date=null shows no fabricated date, degraded banner and note are visible.
    """
    rec: dict = {"route": "/stock/six-dim#partial", "theme": theme,
                 "kind": "sixdim_partial", "ok": False}
    try:
        # React controlled input: native prototype setter + input event only
        set_expr = """(() => {
          const el = document.getElementById('six-dim-code');
          if (!el) return {ok: false, err: 'six-dim-code input missing'};
          const setter = Object.getOwnPropertyDescriptor(
              HTMLInputElement.prototype, 'value').set;
          setter.call(el, '000001');
          el.dispatchEvent(new Event('input', {bubbles: true}));
          return {ok: true, value: el.value};
        })()"""
        set_out = cdp.js(set_expr)
        if not (isinstance(set_out, dict) and set_out.get("ok")):
            rec["error"] = "cannot drive code input: %s" % (set_out,)
            return rec

        probe_expr = """(() => {
          const q = (s) => document.querySelector(s);
          const txt = (s) => ((q(s) && q(s).textContent) || '').trim();
          const body = document.body.innerText || '';
          const cs = Array.from(document.querySelectorAll('canvas')).map(
              c => ({w: c.width, h: c.height}));
          return {
            theme: document.documentElement.getAttribute('data-theme'),
            path: location.pathname,
            inputValue: q('#six-dim-code') ? q('#six-dim-code').value : null,
            dimCapital: txt('[data-testid="dim-capital"]'),
            dimGrowth: txt('[data-testid="dim-growth"]'),
            dimTechnical: txt('[data-testid="dim-technical"]'),
            coverageBar: body.includes('仅 4/6 维有效，缺失维未取到数据'),
            noDate: body.includes('暂无权威数据日'),
            noteShown: body.includes('逐维独立取数、独立降级'),
            canvasCount: cs.length,
            canvasSizes: cs,
            textLen: body.length
          };
        })()"""

        info = {}
        deadline = time.time() + 14.0
        while time.time() < deadline:
            info = cdp.js(probe_expr)
            if (isinstance(info, dict) and info.get("coverageBar")
                    and info.get("canvasCount", 0) >= 1):
                break
            time.sleep(0.4)
        rec["sample"] = info

        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / "sixdim_partial.png"
        shot = cdp.call("Page.captureScreenshot",
                        {"format": "png", "captureBeyondViewport": False})
        data = base64.b64decode(shot.get("data", ""))
        dest.write_bytes(data)
        rec["png"] = str(dest)
        rec["png_bytes"] = len(data)

        canvas_ok = any(c.get("w", 0) > 0 and c.get("h", 0) > 0
                        for c in (info.get("canvasSizes") or []))
        checks = {
            "input_is_partial_code": info.get("inputValue") == "000001",
            "theme": info.get("theme") == theme,
            "capital_missing_not_zero": info.get("dimCapital") == "缺失",
            "growth_missing_not_zero": info.get("dimGrowth") == "缺失",
            "technical_has_value": info.get("dimTechnical") not in (None, "", "缺失"),
            "coverage_bar": bool(info.get("coverageBar")),
            "date_null_honest": bool(info.get("noDate")),
            "note_verbatim": bool(info.get("noteShown")),
            "real_echarts_canvas": canvas_ok,
            "screenshot": len(data) >= 1024,
        }
        rec["checks"] = checks
        bad = [k for k, v in checks.items() if not v]
        if bad:
            rec["error"] = "failed: " + ", ".join(bad)
            logger.warning("X %-6s sixdim_partial %s", theme, rec["error"])
        else:
            rec["ok"] = True
            logger.info("OK %-6s sixdim_partial missing=缺失 / canvas=%s -> %s",
                        theme, info.get("canvasSizes"), dest.name)
    except Exception as exc:
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        logger.error("X %-6s sixdim_partial %s", theme, rec["error"])
    return rec



def capture_deeplink_case(cdp: CDP, base_url: str, case: tuple, theme: str,
                          out_dir: Path) -> dict:
    """W4-B deep-link / legacy redirect assertion in a real browser.

    Verifies the redirect target path, the normalized search params, the
    theme and CSS tokens after the client-side redirect, and a real screenshot.
    Single-page smoke runs (--routes) skip these cases.
    """
    route, name, expect_path, must, forbid, rule = case
    rec: dict = {"route": route, "theme": theme, "kind": "deeplink",
                 "rule": "%s（%s）" % (rule, theme), "ok": False}
    try:
        cdp.call("Page.navigate", {"url": base_url + route})
        probe = """(() => ({
            ready: document.readyState,
            path: location.pathname,
            search: location.search,
            kids: (document.getElementById('root')||{}).children?.length || 0,
            textLen: (document.body.innerText || '').length
        }))()"""
        info = {}
        deadline = time.time() + 16.0
        while time.time() < deadline:
            info = cdp.js(probe)
            srch = info.get("search") or ""
            if (info.get("ready") == "complete" and info.get("kids", 0) > 0
                    and info.get("path") == expect_path
                    and all(x in srch for x in must)
                    and not any(x in srch for x in forbid)):
                break
            time.sleep(0.4)
        rec["probe"] = info
        styled = sample(cdp)
        rec["sample"] = styled

        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / ("%s.png" % name)
        shot = cdp.call("Page.captureScreenshot",
                        {"format": "png", "captureBeyondViewport": False})
        data = base64.b64decode(shot.get("data", ""))
        dest.write_bytes(data)
        rec["png"] = str(dest)
        rec["png_bytes"] = len(data)

        srch = info.get("search") or ""
        checks = {
            "redirect_path": info.get("path") == expect_path,
            "search_must": all(x in srch for x in must),
            "search_forbid_clean": not any(x in srch for x in forbid),
            "react_mounted": info.get("kids", 0) > 0,
            "theme": styled.get("theme") == theme,
            "tokens": all(styled.get("tokens", {}).get(k)
                          for k in ("sf-bg", "sf-ink", "ss-up", "doc-up")),
            "screenshot": len(data) >= 1024,
        }
        rec["checks"] = checks
        bad = [k for k, v in checks.items() if not v]
        if bad:
            rec["error"] = "failed: " + ", ".join(bad)
            logger.warning("X %-6s %-16s %s", theme, name, rec["error"])
        else:
            rec["ok"] = True
            logger.info("OK %-6s %-16s %s%s -> %s",
                        theme, name, info.get("path"), srch, dest.name)
    except Exception as exc:
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        logger.error("X %-6s %-16s %s", theme, name, rec["error"])
    return rec


def cross_theme_checks(records: list[dict], themes: list[str]) -> list[dict]:
    """用真实浏览器计算样式复核两条设计红线，结果写入报告（不静默通过）。

    单主题运行无法做跨主题比对：显式标 evaluated=false，而不是判 PASS 或 FAIL，
    报告里如实说明「没测」，不把没测伪装成通过。
    """
    checks = []
    if len(themes) < 2:
        return [{
            "rule": "跨主题红线（表面色不同 / A 股价格变量两主题恒等）",
            "evaluated": False,
            "pass": True,
            "detail": f"仅运行单主题 {themes}，未做跨主题比对；全量验收请同时跑 dark,light",
        }]

    # --routes 定点复现可能不含首页 /：没有两主题 Dashboard 采样就无法比对。
    # 如实标「未评估」，既不伪装成 PASS，也不把「没测」误报成 FAIL / exit 3。
    has_dashboard = {
        t: any(r.get("theme") == t and r.get("route") == "/" and r.get("sample")
               for r in records)
        for t in ("dark", "light")
    }
    if not all(has_dashboard.values()):
        return [{
            "rule": "跨主题红线（表面色不同 / A 股价格变量两主题恒等）",
            "evaluated": False,
            "pass": True,
            "detail": (
                "本次 --routes 子集缺两主题首页 / 采样（dark=%s light=%s），未做跨主题比对；"
                "全量验收请跑全路由" % (has_dashboard["dark"], has_dashboard["light"])
            ),
        }]

    def tokens_of(theme: str, route: str) -> dict | None:
        for r in records:
            if r["theme"] == theme and r["route"] == route and r.get("sample"):
                return r["sample"].get("tokens") or None
        return None

    d, l = tokens_of("dark", "/"), tokens_of("light", "/")
    if not d or not l:
        checks.append({"rule": "两主题表面色必须不同", "pass": False,
                       "detail": "缺少 dark/light Dashboard 采样，无法判定"})
    else:
        checks.append({
            "rule": "两主题表面色必须不同（--color-sf-bg）",
            "pass": d.get("sf-bg") != l.get("sf-bg"),
            "detail": f"dark={d.get('sf-bg')} light={l.get('sf-bg')}",
        })
        same = []
        for k in ("ss-up", "ss-down", "doc-up", "doc-down"):
            same.append({"key": k, "dark": d.get(k), "light": l.get(k),
                         "equal": d.get(k) == l.get(k)})
        checks.append({
            "rule": "A 股 4 个价格变量两主题恒等（light 块绝不覆盖）",
            "pass": all(x["equal"] for x in same),
            "detail": same,
        })
    return checks


# ── 主流程 ────────────────────────────────────────────────────────────────
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="frontend-v2 暗/亮主题真实浏览器目检")
    p.add_argument("--base-url", default=os_env_url(), help=f"前端地址（默认 {DEFAULT_BASE_URL}）")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="截图与报告输出目录")
    p.add_argument("--themes", default=",".join(THEMES), help="逗号分隔主题子集")
    p.add_argument(
        "--routes", default="",
        help="逗号分隔页面名子集，如 login,dashboard,events；留空=全部。 用页面名而非 / 开头路由，避开 Git Bash 的 MSYS 路径转换。",
    )
    p.add_argument("--start-app", action="store_true", help="脚本自行 headless 启动 Vite 并在结束时关闭")
    p.add_argument("--chrome", default=None, help="Chrome/Edge 可执行文件绝对路径")
    p.add_argument("--debug-port", type=int, default=9222, help="CDP 调试端口")
    p.add_argument("--settle-ms", type=int, default=1500, help="每页额外静置毫秒数")
    return p.parse_args(argv)


def os_env_url() -> str:
    import os
    return os.environ.get("FRONTEND_V2_URL", DEFAULT_BASE_URL)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")
    out_root = Path(args.out)
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    routes = list(ROUTES)
    if args.routes.strip():
        want = {r.strip().lstrip("/") for r in args.routes.split(",") if r.strip()}
        if "" in want:  # 兼容把根路由写成 "/"
            want.discard("")
            want.add("dashboard")
        routes = [r for r in ROUTES if r[1] in want or r[0].lstrip("/") in want]
        if not routes:
            logger.error("--routes 未匹配任何已知页面名：%s（可用 %s）",
                         sorted(want), [r[1] for r in ROUTES])
            return 2

    # 深链专项只在全量运行时跑；--routes 单页冒烟不额外截 8 张
    run_deeplink_cases = len(routes) == len(ROUTES)
    unknown = [t for t in themes if t not in THEMES]
    if unknown:
        logger.error("未知主题：%s（可用 %s）", unknown, THEMES)
        return 2

    vite_proc = chrome_proc = cdp = None
    records: list[dict] = []
    partial_records: list[dict] = []
    try:
        if args.start_app:
            port = urllib.parse.urlparse(base_url).port or 5180
            if not port_free(port):
                raise RuntimeError(f"端口 {port} 已被占用，无法 --start-app")
            vite_proc = start_vite(base_url)
        elif not wait_http(base_url, timeout=3):
            raise RuntimeError(
                f"前端未就绪：{base_url}。请先启动 Vite 或加 --start-app"
            )

        if not port_free(args.debug_port):
            raise RuntimeError(f"CDP 端口 {args.debug_port} 已被占用")
        exe = find_chrome(args.chrome)
        # Chrome profile 放系统临时目录，避免把浏览器缓存写进仓库 artifacts/
        user_data = Path(tempfile.gettempdir()) / "ss_frontend_v2_chrome_profile"
        chrome_proc = launch_chrome(exe, args.debug_port, user_data)
        cdp = CDP(page_ws_url(args.debug_port))
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride",
                 {"width": VIEWPORT["width"], "height": VIEWPORT["height"],
                  "deviceScaleFactor": 1, "mobile": False})

        # 先落到目标 origin，才能写它的 localStorage（同源策略）
        cdp.call("Page.navigate", {"url": f"{base_url}/login"})
        if not wait_ready(cdp, 30):
            raise RuntimeError("首次加载 /login 未挂载，后续注入无意义")
        time.sleep(2.0)  # 给 MSW service worker 首次注册留时间

        for theme in themes:
            logger.info("── 主题 %s ──", theme)
            cdp.js(
                "(() => { localStorage.setItem('ss_theme', %s); "
                "        localStorage.setItem('ss_token', %s); return true; })()"
                % (json.dumps(theme), json.dumps(AUTH_TOKEN))
            )
            for route, name in routes:
                rec = capture(cdp, base_url, route, theme, name,
                              out_root / theme, args.settle_ms)
                records.append(rec)
                if name == "sixdim" and rec.get("ok"):
                    partial_records.append(capture_sixdim_partial(
                        cdp, theme, out_root / theme, args.settle_ms))
            if run_deeplink_cases:
                for case in DEEPLINK_CASES:
                    partial_records.append(capture_deeplink_case(
                        cdp, base_url, case, theme, out_root / theme))

        checks = cross_theme_checks(records, themes)
        for pr in partial_records:
            checks.append({
                "rule": pr.get("rule") or ("W4-A missing dims not zero + real ECharts canvas (%s)" % pr["theme"]),
                "pass": bool(pr.get("ok")),
                "detail": pr.get("error") or pr.get("checks"),
            })
        records.extend(partial_records)
        ok = sum(1 for r in records if r["ok"])
        fail = len(records) - ok
        report = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_url": base_url,
            "browser": str(exe),
            "viewport": VIEWPORT,
            "note": "headless Chrome 自动截图 + 真实计算样式采样；非人工审美结论。"
                    " 登录态为本地注入的演示 token，数据来自 MSW dev fixtures。",
            "summary": {"total": len(records), "ok": ok, "failed": fail,
                        "all_checks_pass": all(c["pass"] for c in checks),
                        # 单主题 / --routes 子集都会让 cross_theme_checks 标 evaluated=False，
                        # 报告必须如实说「没测」，不能仅凭 themes 数量谎称做了跨主题比对。
                        "cross_theme_evaluated": not any(
                            c.get("evaluated") is False for c in checks)},
            "cross_theme_checks": checks,
            "records": records,
        }
        out_root.mkdir(parents=True, exist_ok=True)
        report_path = out_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        logger.info("完成：成功 %d / 失败 %d；报告 %s", ok, fail, report_path)
        for c in checks:
            tag = ("NOT_EVALUATED" if c.get("evaluated") is False
                   else ("PASS" if c["pass"] else "FAIL"))
            logger.info("红线[%s] %s | %s", tag, c["rule"], str(c["detail"])[:180])
        if fail or not report["summary"]["all_checks_pass"]:
            return 3
        return 0
    except Exception as exc:
        logger.error("目检中断：%s: %s", type(exc).__name__, exc)
        return 1
    finally:
        if cdp:
            cdp.close()
        stop_proc(chrome_proc, "Chrome")
        stop_proc(vite_proc, "Vite")


if __name__ == "__main__":
    sys.exit(main())
