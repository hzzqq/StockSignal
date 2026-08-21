# westock-mcp × StockSignal 混合数据方案评估

> 本文档评估「腾讯自选股 MCP（westock-mcp）」与 StockSignal 的集成方式，
> 并给出可落地的混合方案与未来扩展路径。

## 结论速读

- ✅ **标准行情/财报/资金流**这类「别人也有的数据」，westock-mcp 完全可以替代 StockSignal 当前的 akshare/BaoStock 爬虫——更稳、更规范、不用维护反爬
- ❌ **替代不了**：StockSignal 的定制逻辑（事件追踪、信号规则、业务加工）、长尾数据、对数据源的控制权
- 🎯 **推荐混合模式**：westock 灌库（数据管道）+ StockSignal 原有降级链兜底，**两套并存、取长补短**

## 能力盘点（westock-mcp 实际验证 2026-08-21）

| 能力 | 工具 | 实测质量 | 替代 StockSignal 哪部分 |
|---|---|---|---|
| 实时行情快照 | `data_quote` | ⭐⭐⭐⭐⭐ 极规范（含 PE/PB/股息率/52周高低/多周期涨跌） | `get_realtime_quote` / `data_source_health` |
| K 线（日/周/月/季/年） | `data_kline` | ⭐⭐⭐⭐⭐ 前复权规范，limit 可控 | `get_daily` 主路径 |
| 个股资金流 | `data_fund_flow` | ⭐⭐⭐⭐ A 股最全 | F_资金流向页面 |
| 三大报表 | `data_finance` | ⭐⭐⭐⭐ type=income/balance/cashflow | `get_financial` |
| 研报/公告/财报日历/板块/龙虎榜/事件 | 多工具 | ⭐⭐⭐⭐ 待集成 | 各专题页 |

实测返回（600519）：`{"price":1273.87, "pe_ratio":19.56, "pb_ratio":6.34, "dividend_ratio_ttm":4.08, "chg_5d":-5.08, "chg_20d":-1.81, ...}`

## 集成方式

### 方案 A：westock → StockSignal 缓存灌库（**推荐** ✅ 已落地）

**原理**：在 WorkBuddy 会话中调 westock-mcp 工具 → 将结构化数据标准化 → 写入 StockSignal 的 SQLite 缓存（`data/cache.db`）→ 页面/降级链自动读到。

**优势**：
- 零侵入：不动 StockSignal 现有任何代码
- 即时受益：westock 字段（PE/PB/股息率/52周）自动出现在页面
- 兼容现有降级链：akshare 挂了仍能读 westock 灌入的缓存

**实现示例**（已验证）：

```python
# 数据从 westock data_quote 拉取（会话内）
quote = mcp_call("data_quote", {"code": "sh600519", "date": "2026-08-21"})
# 标准化后写入 StockSignal 缓存
import sqlite3, json
from datetime import datetime
conn = sqlite3.connect("data/cache.db")
conn.execute("""CREATE TABLE IF NOT EXISTS rt_quote_cache
                (cache_key TEXT PRIMARY KEY, data_json TEXT, updated_at TEXT)""")
conn.execute("INSERT OR REPLACE INTO rt_quote_cache VALUES (?,?,?)",
             ("rt_quote_600519", json.dumps(quote), datetime.now().isoformat()))
conn.commit()
```

**可落地的定时自动化**（下一步）：
- WorkBuddy 自动化：每日 9:25 / 12:00 / 15:30 触发，调 westock 拉取自选股 + 常用票的行情/资金流/财报日历，灌入 cache.db
- 数据保鲜：akshare 全挂时回退到 westock 灌的最新数据，不至于"全空"

### 方案 B：westock HTTP API（待验证）

若 westock-mcp 背后提供 HTTP 接口（需查官方文档），可在 StockSignal 后端加一个适配器 `modules/_westock_io.py`，作为 akshare 后的新一路降级源。**前提**：有公开 HTTP endpoint + token 注入方式（用户凭据不进项目代码）。

### 方案 C：完全替代 akshare（**不推荐** ❌）

- 失去对数据源的控制权
- westock-mcp 凭据绑定用户账号，换用户/换机器失效
- westock 接口变更时全栈断裂

## 落地清单

- [x] 评估 westock-mcp 能力（本文档）
- [x] 验证 data_quote / data_kline 实际返回质量
- [x] 演示 westock → cache.db 灌库可行（已写入 600519 实时行情）
- [ ] **下一步**（推荐）建定时自动化：每日 3 次灌入自选股 + 重点关注列表
- [ ] **可选** `modules/_westock_io.py` 适配层（若有 HTTP API 时做）
- [ ] **可选** 在 `data_source_health` 中标注 westock 渠道
