#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
backend/run.py
==============
StockSignal 后端一键启动文件。

与 `python -m flask --app backend.app:app run` 相比，本文件多做几件省心的事：
  1. 启动前自动、幂等地初始化数据库（建表 + 历史列迁移 + 种子账号），
     无需再单独跑 `python -m backend.scripts.init_db`。
  2. host / port 可由环境变量或命令行参数覆盖，默认 127.0.0.1:5050。
  3. 启动前检测端口是否被占用，被占用时给出明确提示而不是 Flask 默认静默失败。
  4. 打印启动横幅、访问地址、默认账号、健康检查地址。
  5. `--check` 模式：仅初始化数据库 + 进程内自检（不绑定端口、不常驻），
     方便 CI / 部署前验证。

运行方式：
  python backend/run.py                      # 初始化 DB 并启动（默认 127.0.0.1:5050）
  python -m backend.run                      # 等价（包导入方式）
  STOCKSIGNAL_PORT=8080 python backend/run.py  # 环境变量换端口
  python backend/run.py --host 0.0.0.0 --port 8080   # 命令行换 host/port
  python backend/run.py --no-init            # 跳过 DB 初始化（库已就绪时加速）
  python backend/run.py --check              # 仅初始化 + 自检，不常驻

说明：
  - 开发 / 演示用 Werkzeug 开发服务器（单进程多线程）。生产请改用 gunicorn：
      gunicorn -w 4 -b 127.0.0.1:5050 "backend.app:create_app()"
  - 本文件不强制设置 no_proxy：后端若需经代理抓取外部行情（akshare 等），
    全局 no_proxy 会破坏该能力；如需对 localhost 探测绕过代理，请在调用方环境设置。
"""
from __future__ import annotations

import argparse
import os
import socket
import sys

# ── 路径准备：让 `python backend/run.py` 与 `python -m backend.run` 都能工作 ──
HERE = os.path.dirname(os.path.abspath(__file__))          # .../StockSignal/backend
PROJECT_ROOT = os.path.dirname(HERE)                       # .../StockSignal
for _p in (PROJECT_ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _parse_host_port() -> tuple[str, int]:
    host = os.environ.get("STOCKSIGNAL_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("STOCKSIGNAL_PORT", "5050"))
    except (TypeError, ValueError):
        port = 5050
    return host, port


def _init_db() -> None:
    """幂等初始化数据库：建表 + 历史列迁移 + 种子账号 / 系统配置。"""
    from backend.scripts.init_db import main as init_main
    init_main()


def _port_in_use(host: str, port: int) -> bool:
    """检测端口是否已被占用（仅用于本地启动前的友好提示）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except OSError:
        # 无法探测时不阻塞启动，交由 Flask 自己报错
        return False


def _self_check(host: str, port: int) -> bool:
    """进程内自检：初始化 DB 后用 test_client 打 /api/health。

    不绑定真实端口、不发起网络请求，纯内存验证路由与 DB 连通性。
    """
    from backend.app import create_app
    from backend.utils.response import ok  # noqa: F401  # 确保响应工具可用

    app = create_app()
    with app.test_client() as client:
        resp = client.get("/api/health")
        ok_health = resp.status_code == 200
        try:
            payload = resp.get_json(silent=True) or {}
            data = payload.get("data", {}) or {}
            components = data.get("components", {}) or {}
            db_status = components.get("database", "unknown")
            overall = data.get("status", "unknown")
        except Exception:
            db_status = "unknown"
            overall = "unknown"
        print(f"  健康检查 HTTP={resp.status_code}  status={overall}  db={db_status}")
        return ok_health and db_status == "ok"


def _print_banner(host: str, port: int) -> None:
    line = "=" * 56
    print(line)
    print("  StockSignal 后端启动")
    print(f"  管理界面:    http://{host}:{port}/admin")
    print(f"  API 根:      http://{host}:{port}/api")
    print(f"  健康检查:    http://{host}:{port}/api/health")
    print("  默认账号:    admin / Admin@123  (admin)")
    print("               demo  / Demo@123   (user)")
    print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="StockSignal 后端一键启动")
    parser.add_argument("--host", default=None, help="监听地址（覆盖 STOCKSIGNAL_HOST）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（覆盖 STOCKSIGNAL_PORT）")
    parser.add_argument("--no-init", action="store_true", help="跳过数据库初始化")
    parser.add_argument("--check", action="store_true", help="仅初始化 + 自检，不常驻")
    args = parser.parse_args()

    # 解析 host/port：命令行 > 环境变量 > 默认
    host, port = _parse_host_port()
    if args.host:
        host = args.host
    if args.port is not None:
        port = args.port

    if not args.no_init:
        print("[1/2] 初始化数据库（幂等）...")
        try:
            _init_db()
        except Exception as exc:  # 建库失败不应让服务以半成品状态跑起来
            print(f"[错误] 数据库初始化失败：{type(exc).__name__}: {exc}")
            return 1
    else:
        print("[1/2] 跳过数据库初始化（--no-init）")

    if args.check:
        print("[2/2] 进程内自检 /api/health ...")
        ok_check = _self_check(host, port)
        print("自检结果:", "通过 ✅" if ok_check else "未通过 ❌")
        return 0 if ok_check else 1

    if _port_in_use(host, port):
        print(f"[错误] 端口 {host}:{port} 已被占用。请先停止旧服务或更换端口。")
        return 1

    print("[2/2] 启动服务 ...")
    _print_banner(host, port)

    from backend.app import app
    # threaded=True：支持并发请求（CORS 联调 / 多标签页）。
    # 不使用 debug=True（避免代码重载 + 公网暴露调试器）。
    app.run(host=host, port=port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
