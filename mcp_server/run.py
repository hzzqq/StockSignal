"""启动 StockSignal MCP Server 的入口脚本。

用法：
    python mcp_server/run.py            # stdio 模式（供 MCP 客户端子进程调用）
    python mcp_server/run.py --self-test # 内置自检：列出工具并跑一次离线可用工具

stdio 模式：从 stdin 读 JSON-RPC 2.0 行，向 stdout 写回。由 Claude/Cursor/OpenClaw
等 MCP 客户端作为子进程拉起。
"""

from __future__ import annotations

import argparse
import sys

# 让项目根进入 sys.path（无论从哪调用）
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="StockSignal MCP Server")
    parser.add_argument("--self-test", action="store_true", help="列出工具并做离线自检")
    args = parser.parse_args()

    # 注册工具（导入副作用）
    from mcp_server import server as srv
    from mcp_server import tools as _t  # noqa: F401

    if args.self_test:
        print(f"StockSignal MCP Server v1.0.0 — 已注册 {len(srv.TOOLS)} 个工具：")
        for name, meta in srv.TOOLS.items():
            print(f"  - {name}: {meta['description'][:50]}")
        # 跑一个不依赖远端数据的工具
        try:
            import asyncio
            from mcp_server.tools import risk_assess

            r = risk_assess("不存在的代码XYZ")
            print("\n离线自检 risk_assess(无效代码) =>", r.get("error") or "OK")
        except Exception as e:  # noqa: BLE001
            print("自检异常:", e)
        return

    # stdio 模式
    import asyncio

    asyncio.run(srv.run_stdio())


if __name__ == "__main__":
    main()
