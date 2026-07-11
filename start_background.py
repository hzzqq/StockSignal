#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StockSignal 后台启动器
====================
作用：替代 VBS，让启动脚本无需 wscript.exe 也能在后台运行，
      关闭启动命令行窗口后 Flask(5050) + Streamlit(8501) 仍继续运行。

运行方式：
  pythonw start_background.py          # 用户双击启动文件时调用
  python  start_background.py          # 前台调试用

逻辑：
  1) 解析 pythonw.exe（优先 venv，其次 workbuddy 预置环境）
  2) 使用 CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP 启动 startup_sim.py
  3) 轮询后端 /api/health 与前端首页，确认服务就绪
  4) 将状态写入 logs/background_startup_status.log
  5) 本进程退出，子服务继续运行
"""
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(HERE, "logs")
STATUS_FILE = os.path.join(LOGS_DIR, "background_startup_status.log")


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _resolve_pythonw() -> str:
    candidates = [
        os.path.join(HERE, "venv", "Scripts", "pythonw.exe"),
        r"C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe",
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    py = sys.executable
    if py.endswith("python.exe"):
        pw = py.replace("python.exe", "pythonw.exe")
        if os.path.exists(pw):
            return pw
    return py


def _probe(url: str, timeout: int = 2) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 600
    except Exception:
        return False


def main() -> int:
    _log("start_background.py 启动")
    pythonw = _resolve_pythonw()
    _log(f"使用解释器: {pythonw}")

    if not os.path.exists(pythonw):
        _log("[错误] 找不到可用的 pythonw.exe")
        return 1

    # 启动 startup_sim.py；使用 CREATE_NO_WINDOW 避免弹窗，
    # CREATE_NEW_PROCESS_GROUP 让子进程独立于启动 CMD。
    try:
        proc = subprocess.Popen(
            [pythonw, "startup_sim.py", "--keep", "--no-browser"],
            cwd=HERE,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        _log(f"startup_sim.py 已启动 PID={proc.pid}")
    except Exception as e:
        _log(f"[错误] 启动 startup_sim.py 失败: {type(e).__name__}: {e}")
        return 1

    # 轮询健康检查
    be_url = "http://127.0.0.1:5050/api/health"
    fe_url = "http://127.0.0.1:8501"
    ok = False
    for i in range(60):
        be_ok = _probe(be_url)
        fe_ok = _probe(fe_url)
        if be_ok and fe_ok:
            _log("[OK] 后端+前端均已就绪")
            ok = True
            break
        if i % 5 == 0:
            _log(f"健康检查第 {i}s：后端={be_ok} 前端={fe_ok}")
        time.sleep(1)

    if not ok:
        _log("[错误] 健康检查未通过，请查看 logs/startup_sim.log 和 .err 文件")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
