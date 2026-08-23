"""StockSignal MCP Server — 零依赖实现。

把 StockSignal 的核心能力（行情 / 技术面 / 选股 / 回测 / 资金流 / 新闻 /
风险 / 条件单 / 实盘查询）通过 MCP（Model Context Protocol）协议暴露给任意
AI 助手（Claude / Cursor / OpenClaw / Trae 等），实现「自然语言操控 StockSignal」。

设计原则：
1. **零依赖**：仅用 Python 标准库实现 JSON-RPC 2.0 over stdio，不引入 fastmcp
   等第三方包，避免污染 managed venv、保证可审计、离线可用。
2. **薄网关**：所有工具只是对 `modules.*` / `backend.*` 已有函数的转发，
   不重复造轮子，不绕开既有安全基线（risk_check / 只读优先）。
3. **安全红线**：
   - 行情 / 分析 / 选股 / 回测 / 资金流 / 新闻 / 风险 全部只读。
   - 条件单「查询」只读；「创建/撤销」需显式 dry_run=False 且经 risk_check。
   - 实盘「下单」工具默认不开放（返回指引），真实下单走后端 order_routes
     的鉴权 + risk_check + 人工确认链路，绝不在 MCP 层裸奔。

协议细节：
- 传输：stdin 逐行读取 JSON-RPC 请求，stdout 逐行写回响应。
- 支持通知（无 id 的请求不回包），支持批量请求（数组）。
- 工具调用结果统一包成 MCP content 数组（[{"type":"text","text":...}]）。
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# 工具注册表：name -> {description, input_schema, handler}
# handler 必须是 async 或 sync 均可，server 统一 await/调用。
# ---------------------------------------------------------------------------
TOOLS: Dict[str, Dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    handler: Callable[..., Any],
) -> None:
    """注册一个 MCP 工具。"""
    TOOLS[name] = {
        "name": name,
        "description": description,
        "input_schema": input_schema,
        "handler": handler,
    }


# ---------------------------------------------------------------------------
# JSON-RPC 基础结构
# ---------------------------------------------------------------------------
class McpError(Exception):
    """MCP 协议层错误，带 JSON-RPC error code。"""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# JSON-RPC 标准错误码
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _ok(result: Any, req_id: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(code: int, message: str, req_id: Any, data: Any = None) -> Dict[str, Any]:
    err_obj: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err_obj["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err_obj}


# ---------------------------------------------------------------------------
# 协议方法实现
# ---------------------------------------------------------------------------
def _handle_initialize(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """MCP handshake。"""
    return _ok(
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "stocksignal-mcp",
                "version": "1.0.0",
            },
        },
        req_id,
    )


def _handle_tools_list(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    tools = []
    for meta in TOOLS.values():
        tools.append(
            {
                "name": meta["name"],
                "description": meta["description"],
                "inputSchema": meta["input_schema"],
            }
        )
    return _ok({"tools": tools}, req_id)


async def _handle_tools_call(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name is None:
        return _err(INVALID_PARAMS, "missing 'name'", req_id)
    meta = TOOLS.get(name)
    if meta is None:
        return _err(METHOD_NOT_FOUND, f"unknown tool: {name}", req_id)
    try:
        handler = meta["handler"]
        if hasattr(handler, "__await__") or _is_async(handler):
            result = await handler(**arguments)
        else:
            result = handler(**arguments)
    except TypeError as e:
        return _err(INVALID_PARAMS, f"参数错误: {e}", req_id)
    except McpError as e:
        return _err(e.code, e.message, req_id, e.data)
    except Exception as e:  # noqa: BLE001
        # 业务异常统一转成文本返回，不 crash server
        tb = traceback.format_exc(limit=3)
        text = f"[StockSignal MCP] 工具 {name} 执行失败: {e}\n{tb}"
        return _ok({"content": [{"type": "text", "text": text}], "isError": True}, req_id)

    # 规范化结果为 MCP content
    if isinstance(result, dict) and "content" in result:
        payload = result
    else:
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2, default=str)
        payload = {"content": [{"type": "text", "text": text}]}
    return _ok(payload, req_id)


def _is_async(fn: Callable) -> bool:
    import asyncio

    return asyncio.iscoroutinefunction(fn)


# 方法分发
_METHODS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    # tools/call 是 async，单独处理
}


# ---------------------------------------------------------------------------
# stdio 传输循环
# ---------------------------------------------------------------------------
async def _dispatch(req_id: Any, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if method == "tools/call":
        return await _handle_tools_call(req_id, params)
    handler = _METHODS.get(method)
    if handler is None:
        return _err(METHOD_NOT_FOUND, f"method not found: {method}", req_id)
    try:
        return handler(req_id, params or {})
    except Exception as e:  # noqa: BLE001
        return _err(INTERNAL_ERROR, str(e), req_id)


async def _process_message(raw: str) -> Optional[List[Dict[str, Any]]]:
    """解析一条 JSON-RPC 消息（可能批量），返回需要写回的响应列表。

    通知（无 id）不回包，返回空列表。
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        return [_err(PARSE_ERROR, f"parse error: {e}", None)]

    if isinstance(msg, list):
        out = []
        for item in msg:
            r = await _process_one(item)
            if r is not None:
                out.append(r)
        return out

    r = await _process_one(msg)
    return [r] if r is not None else []


async def _process_one(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict) or "method" not in item:
        return _err(INVALID_REQUEST, "invalid request", item.get("id") if isinstance(item, dict) else None)
    method = item["method"]
    req_id = item.get("id")  # 通知无 id
    params = item.get("params") or {}
    if req_id is None:
        # 通知：仍执行（如 notifications/initialized），但不回包
        await _dispatch(None, method, params)
        return None
    return await _dispatch(req_id, method, params)


async def run_stdio() -> None:
    """主循环：从 stdin 逐行读 JSON-RPC，向 stdout 写回。"""
    reader = sys.stdin
    writer = sys.stdout
    # 优先使用 asyncio 流式读取，但为兼容简单起见用同步逐行。
    import asyncio

    loop = asyncio.get_event_loop()

    async def _readline() -> Optional[str]:
        return await loop.run_in_executor(None, reader.readline)

    while True:
        line = await _readline()
        if line is None:
            break
        line = line.strip()
        if not line:
            continue
        try:
            responses = await _process_message(line)
        except Exception as e:  # noqa: BLE001
            responses = [_err(INTERNAL_ERROR, f"dispatch error: {e}", None)]
        for resp in responses:
            writer.write(json.dumps(resp, ensure_ascii=False) + "\n")
            writer.flush()


def main() -> None:
    """命令行入口：python -m mcp_server.server"""
    import asyncio

    # 真正注册工具（延迟导入，避免循环依赖 / 重依赖在 import 时才加载）
    from . import tools as _tools  # noqa: F401  (注册副作用)

    try:
        asyncio.run(run_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
