#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/shoot_styles.py — StockSignal 6 套界面风格 C4 视觉验收截图脚本
======================================================================

用途
----
对 6 套界面风格（classic / terminal / swiss / aurora / ink / cyber）分别抓取若干
代表性页面的截图，存放到 ``artifacts/shots/<style>/<page>.png``，供人工核对主题
（CSS 变量：--card / --brand-1 / --txt 等）是否正确生效。

本脚本 **不依赖沙箱浏览器**，由用户在本地运行（沙箱无 Chromium，无法截图）。

依赖（只需安装一次）
--------------------
    pip install playwright
    playwright install chromium

启动方式约定
------------
本项目前端是 Streamlit 多页应用（后端 Flask 仅提供 API / 登录，截图无需它，
但若想截取「已登录的真实页面内容」而非登录门禁页，则需要 Flask 后端并加 --login）。

两种运行前提：
  1) 你已自行启动 Streamlit（推荐）：
        streamlit run app.py --server.headless true --server.port 8899
     此时直接运行本脚本即可。
  2) 让本脚本顺带 headless 启动 Streamlit（结束自动关闭）：加 --start-app。

端口说明（重要）：
  本项目 ``.streamlit/config.toml`` 固定 ``port = 8899``，且 ``启动StockSignal.bat`` /
  ``startup_sim.py`` 等自带启动器均使用 8899。README 顶部的架构图曾写 8501，但实际
  配置与启动器以 8899 为准。因此本脚本 **默认基础地址 = http://localhost:8899**。
  若你用裸 ``streamlit run app.py``（不带本项目配置）启动，默认端口是 8501，请加：
        --base-url http://localhost:8501

风格切换 URL 构造方式（与 modules/top_nav.py 完全一致）
------------------------------------------------------
顶栏风格切换链接由 ``top_nav.py`` 生成：
    urlencode({"prefs": json.dumps({"ui_style": X}, ensure_ascii=False)})
落页由 ``modules/session.py`` 的 ``_restore_prefs_from_query_params()`` 读取
``st.query_params["prefs"]`` 并 ``json.loads``，写回 ``st.session_state["ui_style"]``，
最终由 ``modules/ui_theme.py`` 的 ``apply_theme()`` 把该风格的 ``:root{ --card:... }``
变量注入页面。本脚本用 **同样** 的 ``urllib.parse.urlencode`` + ``json.dumps`` 复刻，
确保编码与线上导航逐位一致（注意 JSON 默认在冒号后有空格，quote_plus 将其编码为 ``+``）。

示例 URL（默认 8899 端口）：
  classic : http://localhost:8899/行情看板?prefs=%7B%22ui_style%22%3A+%22classic%22%7D
  cyber   : http://localhost:8899/策略回测?prefs=%7B%22ui_style%22%3A+%22cyber%22%7D

就绪判定（主题已注入）
----------------------
每个页面 goto 后等待：
  * 硬条件：``getComputedStyle(document.documentElement).getPropertyValue('--card')``
    非空 —— 证明该风格的 CSS 变量已注入（classic 来自基础 dark/light :root；其余来自
    各自 preset 的 vars，均含 --card）。
  * 软条件（best-effort）：出现 ``.ss-topnav``（已登录）/ ``.ss-login-card``（登录门禁）
    / ``.stApp`` 任一，证明页面已渲染。未登录时受保护页会显示「主题化的登录门禁页」，
    此时没有 ``.ss-topnav``，但不影响 --card 判定与截图。

运行示例
--------
    # 默认（假设 Streamlit 已在 8899 运行）
    python scripts/shoot_styles.py

    # 顺带 headless 启动 Streamlit
    python scripts/shoot_styles.py --start-app

    # 自定义基础地址 / 端口
    python scripts/shoot_styles.py --base-url http://localhost:8501

    # 仅验收部分风格 / 页面（slug 即去掉数字前缀与 .py 的页面名）
    python scripts/shoot_styles.py --styles classic,terminal --pages 行情看板,登录

    # 后端已启动时自动登录 demo 账号，截取真实页面内容（默认关闭，仅需 Streamlit 时不登录）
    python scripts/shoot_styles.py --login

说明
----
不修改仓库任何其它文件，不推送。仅产出截图脚本与 artifacts/shots 下的图片。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger("shoot_styles")

# ── 路径与默认配置 ──
# 脚本位于 <repo>/scripts/shoot_styles.py，项目根 = 上级目录。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://localhost:8899"
DEFAULT_OUT = PROJECT_ROOT / "artifacts" / "shots"

# 6 套界面风格（与 modules/ui_theme.STYLE_PRESETS / top_nav.style_labels 的 key 完全一致）
STYLES = ["classic", "terminal", "swiss", "aurora", "ink", "cyber"]

# 代表性页面：(Streamlit 路由 slug, 源文件名(去 .py)，用于截图文件名)
# slug = pages/<NN>_<name>.py 去掉「数字_」前缀与 .py，再补前导 /
PAGES = [
    ("/星辰AI", "53_星辰AI"),
    ("/登录", "90_登录"),
    ("/行情看板", "10_行情看板"),
    ("/今日决策面板", "54_今日决策面板"),
    ("/个股研究", "24_个股研究"),
    ("/策略回测", "30_策略回测"),
]

# 自动登录用的演示账号（仅 --login 且 Flask 后端已启动时有意义）
DEMO_USER = "demo"
DEMO_PASS = "Demo@123"

# 截图视口与等待
VIEWPORT = {"width": 1440, "height": 900}
APP_SHELL_TIMEOUT_MS = 15000
THEME_TIMEOUT_MS = 30000
SETTLE_MS = 800  # 主题注入后稍作稳定（图表/字体回流）


# ── URL 构造（与 top_nav.py 逐位一致）──
def style_query(ui_style: str) -> str:
    """复刻 top_nav.py 的风格切换 query 串：urlencode({"prefs": json.dumps(...)})."""
    prefs = {"ui_style": ui_style}
    return urllib.parse.urlencode(
        {"prefs": json.dumps(prefs, ensure_ascii=False)}
    )


def build_page_url(base_url: str, slug: str, ui_style: str, auth_query: str = "") -> str:
    """构造单页截图 URL。

    - 未登录（默认）：query = style_query(ui_style)。
    - 已登录（--login）：在 auth_query（含 token/u/prefs）基础上改写 prefs.ui_style，
      以保持在各页面间维持登录态。
    """
    if auth_query:
        return f"{base_url}{slug}?{merge_style_into_query(auth_query, ui_style)}"
    return f"{base_url}{slug}?{style_query(ui_style)}"


def merge_style_into_query(auth_query: str, ui_style: str) -> str:
    """在已登录的 query（token/u/prefs）上改写 prefs.ui_style 并重新编码。"""
    parsed = urllib.parse.parse_qs(auth_query)
    flat: dict[str, str] = {}
    for k, v in parsed.items():
        flat[k] = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else "")
    prefs: dict = {}
    if flat.get("prefs"):
        try:
            prefs = json.loads(flat["prefs"])
        except Exception:
            prefs = {}
    prefs["ui_style"] = ui_style
    flat["prefs"] = json.dumps(prefs, ensure_ascii=False)
    return urllib.parse.urlencode(flat)


# ── 就绪判定 ──
def wait_theme_injected(page, timeout_ms: int = THEME_TIMEOUT_MS) -> None:
    """硬条件：--card 计算值非空 = 风格 CSS 变量已注入。"""
    page.wait_for_function(
        """() => {
            const v = getComputedStyle(document.documentElement)
                         .getPropertyValue('--card');
            return typeof v === 'string' && v.trim().length > 0;
        }""",
        timeout=timeout_ms,
    )


def wait_app_shell(page, timeout_ms: int = APP_SHELL_TIMEOUT_MS) -> None:
    """软条件：页面已渲染（已登录顶栏 / 登录门禁 / 通用 stApp 任一）。失败仅告警不中断。"""
    try:
        page.wait_for_selector(
            ".ss-topnav, .ss-login-card, .stApp",
            state="attached",
            timeout=timeout_ms,
        )
    except Exception as exc:  # noqa: BLE001 - 软条件，容错
        logger.warning("app shell 未在规定时间内出现（继续截图）：%s", exc)


# ── 可选：headless 启动 Streamlit ──
def start_streamlit(base_url: str, timeout: int = 120):
    """以 headless 方式在项目根启动 Streamlit，轮询端口就绪后返回 Popen。"""
    port = urllib.parse.urlparse(base_url).port or 8501
    logger.info("启动 Streamlit（headless）于端口 %s ...", port)
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(port)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base_url, timeout=2)
            logger.info("Streamlit 已就绪：%s", base_url)
            return proc
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            # 进程提前退出则直接失败
            if proc.poll() is not None:
                _out, _ = proc.communicate()
                raise RuntimeError(
                    f"Streamlit 进程异常退出（code={proc.returncode}）：\n{_out}"
                )
            time.sleep(1.0)
    raise RuntimeError(f"Streamlit 在 {timeout}s 内未就绪（最后错误：{last_err}）")


def stop_streamlit(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()
    except Exception as exc:  # noqa: BLE001
        logger.warning("关闭 Streamlit 子进程时出错：%s", exc)


# ── 可选：自动登录（需 Flask 后端）──
def try_login(page, base_url: str, timeout_ms: int = 20000) -> str:
    """尝试以 demo 账号登录，成功返回带 token/u/prefs 的 query 串，失败返回空串。"""
    login_url = f"{base_url}/登录?{style_query('classic')}"
    try:
        page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)
        # 等待登录表单（演示账号一键填入按钮）出现
        page.get_by_role("button", name="🧪 一键填演示账号").wait_for(
            state="visible", timeout=10000
        )
        page.get_by_role("button", name="🧪 一键填演示账号").click()
        page.get_by_role("button", name="立即登录").click()
        # 登录成功 → safe_switch_page("app.py") 把 URL 改写为含 token 的地址
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if "token=" in page.url or page.locator(".ss-topnav").count() > 0:
                logger.info("自动登录成功，已携带登录态")
                return urllib.parse.urlparse(page.url).query
            time.sleep(0.5)
        logger.warning("自动登录未确认（可能后端未启动或凭据变更），将仅截取登录门禁页")
        return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("自动登录失败（%s），将仅截取登录门禁页", exc)
        return ""


# ── 单个截图 ──
def capture_page(page, base_url: str, slug: str, style: str,
                 out_dir: Path, auth_query: str = "") -> bool:
    url = build_page_url(base_url, slug, style, auth_query)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=THEME_TIMEOUT_MS)
        wait_theme_injected(page, THEME_TIMEOUT_MS)
        wait_app_shell(page, APP_SHELL_TIMEOUT_MS)
        page.wait_for_timeout(SETTLE_MS)
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{slug.lstrip('/') or 'home'}.png"
        page.screenshot(path=str(dest), full_page=False, animations="disabled")
        logger.info("✅ %-8s %-14s -> %s", style, slug, dest)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ %-8s %-14s 失败：%s", style, slug, exc)
        return False


# ── 主流程 ──
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="StockSignal 六风格 C4 视觉验收截图（Playwright）",
    )
    p.add_argument(
        "--base-url", default=os.environ.get("STOCKSIGNAL_URL", DEFAULT_BASE_URL),
        help=f"Streamlit 基础地址（默认 {DEFAULT_BASE_URL}；裸 streamlit 启动为 8501）",
    )
    p.add_argument(
        "--out", default=str(DEFAULT_OUT),
        help="截图输出根目录（默认 <repo>/artifacts/shots）",
    )
    p.add_argument(
        "--styles", default=",".join(STYLES),
        help="逗号分隔的风格子集，如 classic,terminal",
    )
    p.add_argument(
        "--pages", default="",
        help="逗号分隔的页面 slug 子集（去数字前缀的页面名），如 行情看板,登录；留空=全部",
    )
    p.add_argument(
        "--start-app", action="store_true",
        help="顺带 headless 启动 Streamlit（结束自动关闭）",
    )
    p.add_argument(
        "--login", action="store_true",
        help="自动登录 demo 账号以截取真实页面内容（需 Flask 后端已启动）",
    )
    p.add_argument(
        "--timeout", type=int, default=THEME_TIMEOUT_MS,
        help="单页等待超时（毫秒）",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)

    base_url = args.base_url.rstrip("/")
    out_root = Path(args.out)
    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    pages = PAGES
    if args.pages.strip():
        want = {s.strip() for s in args.pages.split(",") if s.strip()}
        pages = [(slug, name) for slug, name in PAGES if slug.lstrip("/") in want]
        if not pages:
            logger.error("未匹配到任何页面，请检查 --pages 取值（应为页面名，如 行情看板）")
            return 2

    global THEME_TIMEOUT_MS
    THEME_TIMEOUT_MS = args.timeout

    proc = None
    if args.start_app:
        proc = start_streamlit(base_url)

    from playwright.sync_api import sync_playwright

    ok, fail = 0, 0
    auth_query = ""
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport=VIEWPORT)
            # 屏蔽外部字体 CDN，避免离线/慢网下等待，且不影响主题变量（内联 CSS）
            try:
                context.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if "fonts.googleapis" in route.request.url
                        or "fonts.gstatic" in route.request.url
                        else route.continue_()
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("设置字体拦截路由失败（忽略）：%s", exc)

            page = context.new_page()

            if args.login:
                auth_query = try_login(page, base_url)

            for style in styles:
                out_dir = out_root / style
                for slug, _name in pages:
                    if capture_page(page, base_url, slug, style, out_dir, auth_query):
                        ok += 1
                    else:
                        fail += 1

            browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.error("Playwright 运行异常：%s", exc)
        return 1
    finally:
        if proc is not None:
            stop_streamlit(proc)

    logger.info("完成：成功 %d 张，失败 %d 张，输出目录 %s", ok, fail, out_root)
    return 0 if fail == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
