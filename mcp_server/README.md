# StockSignal MCP Server

把 StockSignal 的投研能力通过 **MCP（Model Context Protocol）** 开放给任意 AI 助手
（Claude Desktop / Cursor / OpenClaw / Trae 等），实现「自然语言操控 StockSignal」。

> 对应行业方案里的 **方案二：开源工具 + MCP 协议接入**——门槛适中、可深度定制，且
> 100% 复用 StockSignal 已有的行情/策略/实盘闭环，**本地优先、数据不出本机**。

## 架构

```
AI 助手 (Claude/Cursor/OpenClaw)
        │  JSON-RPC 2.0 over stdio (MCP)
        ▼
mcp_server/server.py   ← 零依赖协议层（仅标准库）
        ▼
mcp_server/tools.py    ← 9 个能力工具（薄转发）
        ▼
modules.* / backend.*  ← StockSignal 既有能力（行情/技术面/选股/回测/资金流/新闻/风险/条件单/实盘）
```

**零依赖**：不引入 `fastmcp` 等第三方包，只用 Python 标准库实现 JSON-RPC 2.0 over
stdio，符合项目 managed venv 隔离红线，可审计、离线可用。

## 开放的工具（9 个）

| 工具 | 能力 | 安全性 |
|------|------|--------|
| `get_kline` | 历史 K 线 | 只读 |
| `analyze_technical` | 四维技术面 + 评分 | 只读 |
| `smart_pick` | 每日选股 + 回测验证 | 只读 |
| `run_backtest` | 单标的策略回测 | 只读 |
| `fund_flow` | 资金流向（个股/市场/北向/行业） | 只读 |
| `stock_news` | 个股新闻与事件 | 只读 |
| `risk_assess` | 综合风险评估 | 只读 |
| `conditional_orders` | 条件单查询/创建/撤销 | **默认 dry_run 模拟**，真实登记需显式 `dry_run=False` 且仍过后端 risk_check |
| `portfolio_query` | 账户持仓与资金 | 只读 |

**安全红线**：所有行情/分析类工具只读；条件单创建默认只模拟校验；实盘裸下单**不开放**，
必须走后端 `order_routes`（鉴权 + risk_check + 人工确认）。MCP 层绝不做资金动作。

## 接入方式

### 1) 准备 Python 环境
使用项目 managed venv（已装 flask / akshare / pandas 等）：
```
C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe
```

### 2) 配置 MCP 客户端
把 `mcp_server/mcp_config.example.json` 的内容合并进你的客户端 MCP 配置：

**Claude Desktop**（`claude_desktop_config.json`）：
```json
{
  "mcpServers": {
    "stocksignal": {
      "command": "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
      "args": ["E:/project/ks/StockSignal/mcp_server/run.py"],
      "env": { "PYTHONPATH": "E:/project/ks/StockSignal" }
    }
  }
}
```

**Cursor / OpenClaw / Trae**：同样以 stdio 子进程方式指向 `run.py` 即可（原生支持 MCP）。

**Trae Work（推荐，零插件）**：项目根已提供 `.mcp.json`，Trae Work 打开本项目即自动识别并加载
`stocksignal` 服务器，无需任何插件。若需手动配置，把下面内容合并进 Trae 的 MCP 配置即可：
```json
{
  "mcpServers": {
    "stocksignal": {
      "command": "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
      "args": ["E:/project/ks/StockSignal/mcp_server/run.py"],
      "env": { "PYTHONPATH": "E:/project/ks/StockSignal", "STOCKSIGNAL_SSL_BYPASS": "0" }
    }
  }
}
```
加载后，在 Trae Work 里直接用自然语言驱动 StockSignal，例如：
> "帮我用双趋势策略选 5 只 A 股" / "回测一下 600519 的多因子策略" / "查一下我账户持仓和盈亏"
Trae 会自动路由到对应 MCP 工具并执行。

### 3) 自检
```bash
PYTHONPATH=E:/project/ks/StockSignal \
  C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe \
  E:/project/ks/StockSignal/mcp_server/run.py --self-test
```
应列出 9 个工具并跑通离线自检。

## 配套 Prompt

`mcp_server/prompts.py` 提供了开箱即用的指令体系：
- `SYSTEM_PROMPT`：直接粘到客户端的 system 指令（角色/能力边界/安全约束/输出规范）。
- `SCENARIO_TEMPLATES`：覆盖诊股/选股/回测/盯盘/条件单/持仓体检的高频场景模板。

```python
from mcp_server.prompts import SYSTEM_PROMPT, render_scenario
print(SYSTEM_PROMPT)
print(render_scenario("诊股", code="贵州茅台"))
```

## 与项目既有 AI 的关系

StockSignal 已有 `🌟_星辰AI.py`（站内对话页）和 `backend/api/chat_routes.py`（对话 API）。
MCP Server 是**对外的标准协议网关**，让站外任意 AI 助手也能复用同一套底层能力，三者
共用 `modules/ai_engine.py` + `modules/technical.py` + `modules/backtest.py` 等，
不重复造轮子。

**站内统一入口（🌟_星辰AI.py）**：该页已接入 `mcp_server.gateway`（同进程内工具网关，
不走 stdio、零序列化开销）。用户提问经 `detect_intent` 意图识别后，命中的结构化请求
（选股/回测/资金流/风险/新闻/持仓/条件单/技术面/行情）会**直接调用 MCP 工具拿真实数据**，
渲染为「数据透视」卡片，与后台 `ai_answer` 的自然语言回答并存、互为补充、可核验。
意图识别置信度 < 0.85 的模糊问句仍交给后台 AI 自由回答，不强行拦截。

## 测试

```bash
PYTHONPATH=E:/project/ks/StockSignal \
  C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe \
  -m pytest tests/test_mcp_server.py -q
```
