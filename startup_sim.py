#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StockSignal 启动模拟器 / 预检脚本
================================
作用：在"真实双击 启动StockSignal.bat"之前，用 Python 把启动流程完整跑一遍，
      每一步的成功/失败都写进 logs/startup_sim.log，方便无头环境排查启动问题。

覆盖步骤（与 启动StockSignal.bat 一一对应）：
  1) 解析 Python 解释器（优先 envs/default，其次 PATH 中 --version 实测可用的）
  2) 检查/初始化数据库（backend.scripts.init_db，幂等）
  3) 探测并清理 5050 / 8501 端口占用
  4) 后台拉起 Flask 后端 (5050)
  5) 后台拉起 Streamlit 前端 (8501)
  6) 用 urllib 探测两端健康（不依赖 curl.exe）
  7) 汇总报告 + 写日志；默认探测后清理进程（--keep 可保留）

用法：
  python startup_sim.py                 # 默认端口 5050/8501，探测后清理
  python startup_sim.py --be 5088 --fe 8588   # 指定端口，避免与正在运行的服务冲突
  python startup_sim.py --keep          # 探测成功后不清理，留着给你手动看
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(HERE, "logs")
DIAG = os.path.join(LOGS_DIR, "startup_sim.log")

DEFAULT_VENV = r"C:\Users\24995\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

# ---------------------------------------------------------------- 日志
_lines = []


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _lines.append(line)
    print(line, flush=True)


def flush_log():
    try:
        if not os.path.isdir(LOGS_DIR):
            os.makedirs(LOGS_DIR, exist_ok=True)
        with open(DIAG, "a", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  startup_sim 运行\n")
            f.write("\n".join(_lines) + "\n")
    except Exception as e:  # noqa
        print(f"[warn] 写日志失败: {e}")


# ---------------------------------------------------------------- 1) 解析 Python
def _decode(b):
    if isinstance(b, bytes):
        return b.decode("utf-8", "replace")
    return b or ""


def resolve_python():
    candidates = [DEFAULT_VENV, "python", "python3"]
    for cand in candidates:
        try:
            r = subprocess.run(
                [cand, "--version"], capture_output=True, timeout=15
            )
            if r.returncode == 0:
                ver = _decode(r.stdout or r.stderr).strip().replace("\n", " ")
                log(f"[OK] Python 解析成功: {cand}  ({ver})")
                return cand
            else:
                log(f"[跳过] {cand} 返回非0: {_decode(r.stderr).strip()[:80]}")
        except Exception as e:  # noqa
            log(f"[跳过] {cand} 不可用: {type(e).__name__}: {e}")
    log("[错误] 未找到可用 Python 解释器")
    return None


# ---------------------------------------------------------------- 2) 数据库
def check_db(python):
    log("--- [2/6] 检查数据库 ---")
    try:
        r = subprocess.run(
            [python, "-m", "backend.scripts.init_db"],
            cwd=HERE, capture_output=True, timeout=120,
        )
        if r.returncode == 0:
            out = _decode(r.stdout)
            last = [l for l in out.splitlines() if l.strip()][-1:]
            log(f"[OK] 数据库检查/初始化成功 ({last if last else 'done'})")
            return True
        else:
            log(f"[错误] init_db 失败 rc={r.returncode}")
            log("  stdout: " + _decode(r.stdout).strip()[:300])
            log("  stderr: " + _decode(r.stderr).strip()[:300])
            return False
    except Exception as e:  # noqa
        log(f"[错误] init_db 异常: {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------- 3) 端口探测
def port_in_use(port, host="127.0.0.1"):
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status < 600
    except Exception:  # noqa
        return False


def kill_port(port):
    """Windows: 用 netstat 找到占用端口的 PID 并 taskkill。失败则忽略。"""
    try:
        out = _decode(subprocess.run(
            ["netstat", "-aon"], capture_output=True, timeout=15
        ).stdout)
        pids = set()
        for ln in out.splitlines():
            if f":{port} " in ln:
                parts = ln.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            if pid.isdigit():
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F", "/T"],
                    capture_output=True, timeout=10,
                )
                log(f"  已清理占用端口 {port} 的进程 PID={pid}")
    except Exception as e:  # noqa
        log(f"  [warn] 清理端口 {port} 失败: {e}")


# ---------------------------------------------------------------- 4/5) 拉起服务
def launch_service(python, kind, args, log_path, err_path):
    log(f"--- 拉起 {kind} ---")
    try:
        with open(log_path, "wb") as lf, open(err_path, "wb") as ef:
            proc = subprocess.Popen(
                [python, *args],
                cwd=HERE,
                stdout=lf,
                stderr=ef,
                # 注意：不要使用 DETACHED_PROCESS —— 在部分沙箱/环境下
                # 会让子进程被回收、路由未就绪即返回 404。普通后台启动即可。
            )
        log(f"  [OK] {kind} 进程已拉起 PID={proc.pid}")
        return proc
    except Exception as e:  # noqa
        log(f"  [错误] {kind} 拉起失败: {type(e).__name__}: {e}")
        return None


def probe(port, path="/api/health", host="127.0.0.1", timeout=45, interval=2,
          accept_any=False):
    """探测端口是否就绪。
    accept_any=False（后端健康）：只有 2xx 才算就绪，404/5xx 视为未就绪继续重试
    accept_any=True（前端首页）：任意 HTTP 响应即视为进程已起
    """
    url = f"http://{host}:{port}{path}"
    deadline = time.time() + timeout
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if accept_any or 200 <= resp.status < 300:
                    return True, resp.read(512).decode("utf-8", "ignore")
                # 非 2xx 且非 accept_any：视为未就绪，继续等
                if attempts % 5 == 0:
                    log(f"    探测 {port}{path} 第{attempts}次返回 {resp.status}，继续等…")
        except urllib.error.HTTPError as e:
            if accept_any:
                return True, f"HTTP {e.code}"
            if attempts % 5 == 0:
                log(f"    探测 {port}{path} 第{attempts}次返回 HTTP {e.code}，继续等…")
        except Exception as e:  # noqa
            if attempts % 5 == 0:
                log(f"    探测 {port}{path} 第{attempts}次仍连不上: {type(e).__name__}")
        time.sleep(interval)
    return False, ""


def cleanup(proc, port):
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:  # noqa
        pass
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/F", "/T"],
            capture_output=True, timeout=10,
        )
    except Exception:  # noqa
        pass


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--be", type=int, default=5050, help="后端端口")
    ap.add_argument("--fe", type=int, default=8501, help="前端端口")
    ap.add_argument("--keep", action="store_true", help="探测成功后保留进程不清理")
    args = ap.parse_args()

    # 绕过可能的 HTTP 代理（沙箱环境常劫持 127.0.0.1，导致 localhost 探测误报 404）
    os.environ.setdefault("no_proxy", "*")
    os.environ.setdefault("NO_PROXY", "*")
    urllib.request.install_opener(
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
    )

    log("=" * 60)
    log("StockSignal 启动模拟器 (startup_sim)")
    log(f"目标端口: 后端={args.be}  前端={args.fe}  keep={args.keep}")
    log(f"项目目录: {HERE}")

    # 1) Python
    log("--- [1/6] 解析 Python 解释器 ---")
    python = resolve_python()
    if python is None:
        log("[结论] 启动模拟失败：无可用 Python")
        flush_log()
        return 1

    # 2) DB
    if not check_db(python):
        log("[结论] 启动模拟失败：数据库检查未通过（但端口/进程可能仍可用）")
        flush_log()
        return 1

    # 3) 端口
    log("--- [3/6] 检查端口占用 ---")
    for port in (args.be, args.fe):
        if port_in_use(port):
            log(f"  端口 {port} 已被占用，尝试清理旧进程…")
            kill_port(port)
            time.sleep(2)
        else:
            log(f"  端口 {port} 空闲")

    # 4) 后端
    be_log = os.path.join(LOGS_DIR, f"sim_backend_{args.be}.log")
    be_err = os.path.join(LOGS_DIR, f"sim_backend_{args.be}.err")
    be_args = [
        "-m", "flask", "--app", "backend.app:app", "run",
        "--host", "127.0.0.1", "--port", str(args.be),
    ]
    be_proc = launch_service(python, "Flask 后端", be_args, be_log, be_err)

    # 5) 前端
    fe_log = os.path.join(LOGS_DIR, f"sim_frontend_{args.fe}.log")
    fe_err = os.path.join(LOGS_DIR, f"sim_frontend_{args.fe}.err")
    fe_args = [
        "-m", "streamlit", "run", "app.py",
        "--server.port", str(args.fe),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "poll",
    ]
    fe_proc = launch_service(python, "Streamlit 前端", fe_args, fe_log, fe_err)

    if be_proc is None or fe_proc is None:
        log("[结论] 启动模拟失败：进程未能拉起，详见上方错误")
        flush_log()
        return 1

    # 6) 探测健康
    log("--- [6/6] 探测健康 ---")
    be_ok, be_data = probe(args.be, "/api/health", accept_any=False)
    if be_ok:
        log(f"[OK] 后端健康响应: {be_data.strip()}")
    else:
        log(f"[错误] 后端在 {args.be} 未就绪；看 {be_err}")

    # 前端首页返回任意 HTTP 响应即视为就绪
    fe_ok, _ = probe(args.fe, "/", accept_any=True)
    if fe_ok:
        log(f"[OK] 前端已在 {args.fe} 就绪 (返回首页)")
    else:
        log(f"[错误] 前端在 {args.fe} 未就绪；看 {fe_err}")

    # 7) 汇总
    log("=" * 60)
    if be_ok and fe_ok:
        log("[结论] 启动模拟成功 ✅  后端+前端均可正常拉起")
        if not args.keep:
            cleanup(be_proc, args.be)
            cleanup(fe_proc, args.fe)
            log("（已清理模拟进程；请用真实 启动StockSignal.bat 正式启动）")
    else:
        log("[结论] 启动模拟发现问题 ❌ —— 请查看上方对应 .err 日志")
        if not args.keep:
            cleanup(be_proc, args.be)
            cleanup(fe_proc, args.fe)

    flush_log()
    return 0 if (be_ok and fe_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
