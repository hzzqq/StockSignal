# 财务语义契约（Finance Contract）

> 本文档固化 StockSignal 持仓 / 盈亏计算的**核心财务语义**，作为日后重构的对照基线。
> 代码层对应 `modules/finance_contract.py`（机器可校验的 schema 契约）与
> `modules/portfolio.py` 的 `allocate_fifo` / `compute_realized_fifo` / `calc_pnl` / `summary`。
> 任何改动若偏离本文档，必须先改文档 + 改 `PNL_OUTPUT_COLUMNS` 常量 + 同步测试。

---

## 1. 核心不变式（Invariants）

### 1.1 分批建仓 → 同一 ticker 多行
`add_position` 每买一次就 **append 一行**，所以 A 股最常见的「加仓」操作会让
**同一只股票出现多行**（`buy_date` / `buy_price` 不同）。所有核算必须面向「多行」建模，
不能假设「一票一行」。

### 1.2 FIFO 剩余股数契约（allocate_fifo）
- 每只股票的累计卖出股数按 **买入日期升序** 摊到各买入批次：先买的批次先被卖出。
- 逐行分配后满足：

  ```
  Σ(各行 remaining_shares) == 整票(总买入股数 - 总卖出股数)   # 严格相等
  ```

- ❌ 错误旧实现：`df["remaining_shares"] = df["ticker"].map(整票剩余)`
  会把「整票剩余」原样写进**每一行**，两批建仓时两行都是 300 →
  市值 / 成本 / 总盈亏成倍虚增（实测 2.0× / 1.98×）。
- 脏数据兜底：股数缺失 / 非数字按 0；`buy_date` 无法解析的排到批次末尾；卖出超买部分静默钳 0。

### 1.3 FIFO 已实现盈亏契约（compute_realized_fifo）
- 与 1.2 **同一套 FIFO 语义**：买入批次按时间升序、卖出交易按时间升序，先买的批次先被卖。
- 整票已实现盈亏：

  ```
  realized = Σ_over_sell_trades (卖价 - 该批次买入价) × 该笔卖出实际吃货股数
  ```

- ❌ 错误旧实现：用**平均成本** `avg_cost = Σ(buy_price×shares)/Σshares` 计算
  `realized = 卖价×卖出股数 - avg_cost×卖出股数`。当批次买价不同（加仓）时系统性算错：
  例 `100@10 + 100@20`、FIFO 卖最早批 `@20`、卖价 `25` →
  真实已实现 = `(25-10)×100 = 1500`，平均成本法算得 `(25-15)×100 = 1000`（误差 100%）。
- `calc_pnl` 中**逐行**的 `realized_pnl` 不是整票金额照抄，而是按该批次
  `实际被 FIFO 卖出的股数 / 整票已卖出股数` 占比摊分，保证
  `Σ(各行 realized_pnl) == 整票已实现盈亏`（不重复计数）。

### 1.4 remaining_shares 派生列契约
- `get_positions()` 在落盘列之外**必须**产出派生列 `remaining_shares`（逐行 FIFO 结果）。
- 任何消费方（持仓页、市值加权、汇总）都应读 `remaining_shares` 而非 `shares`
  来表示「当前还持有多少」。

### 1.5 calc_pnl 输出列契约（PNL_OUTPUT_COLUMNS）
固定 12 列，顺序如下，**任何重构不得增删**：

```
ticker, name, buy_date, buy_price, shares,
remaining_shares, cost, current_price, market_value,
realized_pnl, pnl, pnl_pct
```

- `cost` 为按 `remaining_shares / shares` 比例分摊后的**当前持仓成本**（非整票买入成本）。
- `pnl` = `current_price × remaining_shares - cost`（未实现盈亏）。
- `market_value` = `current_price × remaining_shares`。
- `current_price` 行情取数失败 / 返回 NaN / inf 时**静默回退到买入价**，不产生 NaN。

### 1.6 summary 总盈亏契约
- `summary().total_pnl = Σ(pnl + realized_pnl)`：**含已实现盈亏**。
  > 早期实现只 `Σ(pnl)`，漏算已平仓收益，账户有卖出时总盈亏整体低估全部已实现部分。
- `total_pnl_pct` 仍以当前持仓成本 `total_cost`（= `Σ cost`）为分母，已实现部分无独立成本
  基准，属近似（已在 `portfolio.py` 注释说明）。

---

## 2. 原始数据落盘 schema

### 2.1 持仓表（portfolio.csv）
必需列（缺失即 `validate_position_schema` 抛 `FinanceContractError`）：

| 列 | 类型 | 说明 |
|---|---|---|
| `ticker` | str(6位) | 股票代码，`add_position` 内 `zfill(6)` |
| `name` | str | 名称（可空，自动查） |
| `buy_date` | str(YYYY-MM-DD) | 买入日期，**FIFO 排序键** |
| `buy_price` | float>0 | 买入价 |
| `shares` | int>0 | 买入股数（该行批次） |
| `cost` | float | `buy_price × shares`（该行批次成本） |

派生列：`remaining_shares`（由 `get_positions` 产出，非落盘）。

### 2.2 卖出记录表（portfolio_trades.csv）
必需列：`ticker`, `sell_date`, `sell_price`, `sell_shares`（另 `name`/`proceeds`/`note` 可选）。

---

## 3. 为什么不用「平均成本」统算已实现盈亏

平均成本法（移动加权平均）是中国券商对**单账户持仓成本**的通用展示口径，适合「我不想分清批次」
的场景。但本项目 `allocate_fifo` 已承诺**按批次 FIFO** 建模剩余股数，若已实现盈亏另用平均成本，
两套语义打架：同一笔卖出，剩余股数说「卖的是最早那批」，盈亏却按「全票均价」算，
批次买价不同时结果矛盾（见 1.3 的 100% 误差例）。

**决策：已实现盈亏与剩余股数统一走 FIFO**，保证「哪批被卖」与「那批赚多少」一致。
平均成本法仅作为可选展示口径保留，不作为 `calc_pnl` 的计算内核。

---

## 4. 契约守护方式（替代正则守门）

- `get_positions()` 入口：`validate_position_schema(df)` fail-fast。
- `calc_pnl()` 出口：`validate_pnl_output(out)` 严格校验列 == `PNL_OUTPUT_COLUMNS`。
- 测试：`tests/test_finance_contract.py` 断言上述不变式 + 真实 `calc_pnl` 输出符合契约。
- 源码级防回退（历史遗留）：`tests/test_portfolio_fifo_allocation.py` 的 tokenize 守卫确保
  不回退到 `df["ticker"].map(剩余)` 写法。

---

## 5. 已知边界 / TODO

- `summary().total_pnl_pct` 分母不含已实现成本，近似（见 1.6）。
- `calc_pnl` 逐行取最新价走网络（`fetcher.get_daily`），离线 / 接口异常时回退买入价，
  因此离线环境下 `current_price` 全部 == `buy_price`，`pnl` 恒为 0（预期行为，非 bug）。
- 分红 / 拆股未建模，分红再投场景的 FIFO 成本调整不在本期契约内。
