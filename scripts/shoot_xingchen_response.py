#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/shoot_xingchen_response.py — 星辰 AI「真实浏览器」流式回应目检
=====================================================================
复用 shoot_frontend_v2 的 CDP 工具，真实提交一个问题到 /xingchen，分别在
「生成中」与「分析完成」两个时刻截图（暗/亮双主题），验证全面化外壳
（标题卡 + 三阶段步进器 + 多维研判维度卡 + 流式揭示）在真实浏览器里成立。
数据来自 dev 模式 MSW fixtures，无需真后端。产物写入 artifacts/（本地目检）。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("shoot_xingchen_response")

# 复用既有 CDP 工具，避免重复造轮子
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shoot_frontend_v2 import (  # noqa: E402
    AUTH_TOKEN,
    CDP,
    DEFAULT_BASE_URL,
    PROJECT_ROOT,
    VIEWPORT,
    find_chrome,
    launch_chrome,
    page_ws_url,
    start_vite,
    stop_proc,
    wait_http,
    wait_ready,
)

OUT_DIR = PROJECT_ROOT / "artifacts" / "shots" / "frontend-v2"
QUESTION = "分析贵州茅台 600519"
DEBUG_PORT = 9333


def capture_png(cdp: CDP, out_path: Path, full: bool = False) -> int:
    shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": full})
    data = __import__("base64").b64decode(shot.get("data", ""))
    out_path.write_bytes(data)
    return len(data)


def scroll_to_scaffold(cdp: CDP) -> bool:
    """把对话滚动到全面化外壳（标题卡/步进器/维度卡）所在的助手气泡顶部，
    避免之前滚动到对话底部而漏掉外壳。外壳唯一锚点：步进器文案「多维研判」。"""
    return bool(
        cdp.js(
            """(() => {
                const els = Array.from(document.querySelectorAll('div'));
                const e = els.find(x => (x.textContent || '').includes('多维研判'));
                if (!e) return false;
                e.scrollIntoView({ block: 'start', behavior: 'instant' });
                return true;
            })()"""
        )
    )


def body_text(cdp: CDP) -> str:
    return cdp.js("document.body.innerText || ''") or ""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    chrome_arg = sys.argv[1] if len(sys.argv) > 1 else None
    base_url = DEFAULT_BASE_URL
    themes = ["dark", "light"]

    vite_proc = chrome_proc = cdp = None
    try:
        if not wait_http(base_url, timeout=3):
            logger.info("Vite 未就绪，尝试自起")
            vite_proc = start_vite(base_url)
        if not wait_http(base_url, timeout=5):
            raise RuntimeError(f"前端未就绪：{base_url}")
        from shoot_frontend_v2 import port_free
        if not port_free(DEBUG_PORT):
            raise RuntimeError(f"CDP 端口 {DEBUG_PORT} 已被占用")
        from shoot_frontend_v2 import tempfile
        exe = find_chrome(chrome_arg)
        user_data = Path(tempfile.gettempdir()) / "ss_xingchen_chrome_profile"
        chrome_proc = launch_chrome(exe, DEBUG_PORT, user_data)
        cdp = CDP(page_ws_url(DEBUG_PORT))
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride",
                 {"width": VIEWPORT["width"], "height": VIEWPORT["height"],
                  "deviceScaleFactor": 1, "mobile": False})

        for theme in themes:
            logger.info("── 主题 %s ──", theme)
            # 首次落到目标 origin（无 token 可能被导到 /login，无妨），让 app 启动
            cdp.call("Page.navigate", {"url": f"{base_url}/xingchen"})
            if not wait_ready(cdp, 30):
                raise RuntimeError("/xingchen 初次加载未挂载")
            time.sleep(2.0)
            # 注入主题 + 登录态，再导航到 /xingchen（此时 token 已就绪，守卫放行）
            cdp.js(
                "(() => { localStorage.setItem('ss_theme', %s); "
                "localStorage.setItem('ss_token', %s); return true; })()"
                % (json.dumps(theme), json.dumps(AUTH_TOKEN))
            )
            cdp.call("Page.navigate", {"url": f"{base_url}/xingchen"})
            if not wait_ready(cdp, 30):
                raise RuntimeError("/xingchen 注入 token 后未挂载")
            time.sleep(2.0)

            # 开一个全新空白会话，避免 seeded 历史长消息把新回应挤出可视区
            new_clicked = cdp.js(
                """(() => { const b=[...document.querySelectorAll('button')]
                    .find(x=>(x.textContent||'').includes('新对话'));
                    if(b){b.click(); return true;} return false; })()"""
            )
            logger.info("  新建空白会话：%s", new_clicked)
            time.sleep(0.8)

            # 真实输入：React 受控 textarea 用原生 setter + input 事件，再点「发送」
            set_expr = """(() => {
                const ta = document.querySelector('textarea');
                if (!ta) return {ok:false, err:'textarea missing'};
                const setter = Object.getOwnPropertyDescriptor(
                    HTMLTextAreaElement.prototype, 'value').set;
                setter.call(ta, %s);
                ta.dispatchEvent(new Event('input', {bubbles:true}));
                const btns = Array.from(document.querySelectorAll('button'));
                const b = btns.find(x => (x.textContent||'').includes('发送'));
                if (b) b.click();
                return {ok:true, hasSend: !!b, val: ta.value};
            })()""" % json.dumps(QUESTION)
            res = cdp.js(set_expr)
            if not (isinstance(res, dict) and res.get("ok")):
                raise RuntimeError("无法驱动输入框/发送：%s" % (res,))

            # 1) 生成中截图（轮询期：后台任务执行中 + 外壳 + 维度分析中）
            time.sleep(2.0)
            scroll_to_scaffold(cdp)
            streaming = OUT_DIR / theme / "xingchen_streaming.png"
            streaming.parent.mkdir(parents=True, exist_ok=True)
            n1 = capture_png(cdp, streaming)
            txt1 = body_text(cdp)
            logger.info("  [streaming] %s (%dB) 含「正在分析」=%s 含「分析中」=%s 含「深度研究」=%s",
                        streaming.name, n1,
                        "正在分析" in txt1, "分析中" in txt1,
                        "深度研究" in txt1 or "快速研判" in txt1)

            # 2) 分析完成截图（等流式揭示结束）
            deadline = time.time() + 14.0
            done = False
            while time.time() < deadline:
                if "分析完成" in body_text(cdp):
                    done = True
                    break
                time.sleep(0.5)
            time.sleep(0.6)
            scroll_to_scaffold(cdp)
            done_path = OUT_DIR / theme / "xingchen_done.png"
            n2 = capture_png(cdp, done_path, full=True)
            txt2 = body_text(cdp)
            logger.info("  [done] %s (%dB) 完成态=%s 含「分析完成」=%s 含「已返回」=%s 含「结论生成」=%s",
                        done_path.name, n2, done,
                        "分析完成" in txt2, "已返回" in txt2,
                        "结论生成" in txt2)

        logger.info("完成：截图落在 %s", OUT_DIR)
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
