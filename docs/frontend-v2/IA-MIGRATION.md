# StockSignal 前端 V2 · 信息架构与 74 页迁移（IA-MIGRATION）

> 配套 `PLAN.md` §3.3 / §6，`DESIGN.md` §4。
> 所有分组名与页面名取自真扫 `modules/widgets.py:673-779` 与 `ls pages/*.py`（74 个文件），非推测。

---

## 1. 现有信息架构（真值）

`modules/widgets.py::_NAV_GROUPS` 定义 **6 个一级类目**，另有 `_NAV_HERO`(54)、`_NAV_ADMIN`(92/93)：

| # | 一级类目 | 子簇 | 登记页数 |
|---|---|---|---|
| 1 | 📈 行情与板块 | 行情(7) / 板块(3) | 10 |
| 2 | 🌐 市场广度·温度 | 广度温度核心(8) / 状态机·全景(4) / 事件·连板(4) / 情绪扫描器(4) / 财报日历(2) | 22 |
| 3 | 🔎 个股研究 | 无子簇 | 4 |
| 4 | 🧪 量化选股 | 无子簇 | 8 |
| 5 | 💼 持仓交易 | 无子簇 | 4 |
| 6 | 🛠 工具与社区 | 工具(5) / 数据治理(4) / 社区与AI(6) | 15 |
| — | Hero 常驻 | `54_今日决策面板` | 1 |
| — | Admin | `92_用户管理` / `93_系统配置` | 2 |
| — | 独立页（未登记导航） | `90_登录` / `91_我的` / `96_新手教程` | 3 |
| — | **已内嵌，勿作独立页** | `11_股票选取`、`20_个股分析` → `24_个股研究`；`40_仓位管理`、`41_组合收益`、`46_自选股监控` → `45_持仓中心` | 5 |

合计 74。原版注释明确写了收敛理由：「三者看起来是同一件事，重复入口才是『乱』的根源」（`widgets.py:726-728`）。**V2 必须沿用这个收敛，不许把重复入口搬回来**。

现有硬约束：一级类目 = 6 且顺序固定、图标全局唯一、子簇 ≤8（`tests/test_sidebar_nav.py` 锁）。V2 的 `nav.manifest.json` 保持同样的结构约束并写进校验脚本。

---

## 2. V2 路由表（按 6 类目一一对应）

| 类目 | 路由前缀 | 代表页 |
|---|---|---|
| Hero | `/decision` | `/decision`（54 今日决策面板，默认落地页） |
| 📈 行情与板块 | `/market` | `/market/board`(10) `/market/monitor`(14) `/market/fundflow`(35) `/market/morning`(51) `/market/strong`(76) `/market/macro`(84) `/market/dragon-tiger`(85) `/market/rotation`(12) `/market/cube`(17) `/market/themes`(75) |
| 🌐 市场广度·温度 | `/breadth` | `/breadth/strength`(13) `/breadth/driver`(15) `/breadth/sentiment`(50) `/breadth/thermometer`(59) `/breadth/divergence`(61) `/breadth/momentum`(62) `/breadth/temp-backtest`(63) `/breadth/temp-duration`(69) `/breadth/regime`(56) `/breadth/panorama`(57) `/breadth/replay`(97) `/breadth/qa`(99) `/breadth/events`(23) `/breadth/event-compare`(60) `/breadth/ladder`(58) `/breadth/limit-review`(70) `/breadth/clock`(65) `/breadth/lead-lag`(66) `/breadth/similar-days`(67) `/breadth/turning-point`(68) `/breadth/earnings-calendar`(16) `/breadth/earnings-hunter`(77) |
| 🔎 个股研究 | `/stock` | `/stock/research`(24) `/stock/compare`(21) `/stock/fundamentals`(22) `/stock/six-dim`(72) |
| 🧪 量化选股 | `/screener` | `/screener/daily`(36) `/screener/smart`(32) `/screener/pattern`(31) `/screener/etf`(33) `/screener/quant-agent`(25) `/screener/backtest`(30) `/screener/p1-signal`(55) `/screener/factors`(71) |
| 💼 持仓交易 | `/portfolio` | `/portfolio`(45) `/portfolio/live`(43) `/portfolio/sim`(42) `/portfolio/landing`(98) |
| 🛠 工具与社区 | `/tools` | `/tools/scan`(34) `/tools/price-alert`(47) `/tools/export`(95) `/tools/cond-order`(44) `/tools/showcase`(86) `/tools/custom-board`(73) `/tools/alert-engine`(74) `/tools/freshness`(82) `/tools/nl-stock`(81) `/tools/ai`(53) `/tools/forum`(52) `/tools/messages`(94) `/tools/roundtable`(64) `/tools/rules`(83) `/tools/voice-event`(87) |
| Admin | `/admin` | `/admin/users`(92) `/admin/config`(93) |
| 独立 | `/login` `/me` `/guide` | 90 / 91 / 96 |

**内嵌页不设路由，改为子视图参数**：
- `24_个股研究` 的 `快速选取` / `深度分析` → `/stock/research?view=quick|deep`
- `45_持仓中心` 的 `自选股监控` / `仓位管理` / `组合收益` → `/portfolio?tab=watchlist|position|returns`

---

## 3. 深链契约（必须等价，否则老链接全断）

### 3.1 原版机制（真值）

- `safe_switch_page(page)` **只透传 `st.query_params`**，不带额外 kwargs；要传参必须**先** `st.query_params['k']=v` 再跳转。
- 消费方在 radio / 控件**之前**读 `query_params.get()` 预选 + 回填 `session_state`。
- 24 页深链 = **`hub_gyj_view`** + **`pick_stock`**。

### 3.2 V2 映射

| 原参数 | V2 等价 | 消费方式 |
|---|---|---|
| `hub_gyj_view` | `/stock/research?view=<quick\|deep>` | 路由 loader 读 `view`，在渲染 radio **之前**写入初始 state |
| `pick_stock` | `/stock/research?code=<6位>&view=deep` | loader 校验 6 位数字，预选个股并触发查询 |
| 旧链接整体 | `/legacy?hub_gyj_view=...&pick_stock=...` → 302 到新路由 | **兼容层必须保留**，避免收藏/分享链接失效 |

**W4-B 执行态更正（2026-11-07，以旧页源码 + 真实浏览器实跑为准）**：上表是 W0 规划态，下列 3 项已被推翻，验收以本段为准（保留上表作为规划历史，不作验收依据）：

1. 旧版 `pages/22_基本面分析.py:864-866` 的跳转**只带 `pick_stock`、不带 `hub_gyj_view`**，实际落到「⚡ 快速选取」。故 **只带 `pick_stock` → `view=quick`**；只有 `hub_gyj_view='🔬 深度分析'` 才 `view=deep`。实现见 `frontend-v2/src/lib/deeplink.ts::resolveLegacySearch`。
2. 纯 SPA + Vite dev proxy 产生不了 3xx；`/legacy` 是 TanStack Router `beforeLoad` 抛 `redirect({replace:true})` 触发的**客户端 `history.replace`**，不是 HTTP 302。
3. 首帧预选由 `validateSearch`（同步、早于渲染）完成，不用 loader、不用 `useEffect`；上表「路由 loader」措辞不准确。
4. `nav.manifest.json` 仍不 revival，活真理源是 `frontend-v2/src/nav/nav.ts` + `frontend-v2/src/app/router.tsx`。

**关键顺序红线**：URL 参数预选必须发生在控件挂载之前（W4-B 实跑：`validateSearch` 同步早于渲染即满足）；不要在 `useEffect` 里补——那会产生「先渲染默认再跳变」的闪烁，也是原版踩过的坑。

### 3.3 `nav.manifest.json` 结构（单一真理源）

```jsonc
{
  "groups": [
    {
      "id": "market", "label": "行情与板块", "icon": "trending-up", "order": 1,
      "clusters": [
        { "id": "quotes", "label": "行情", "items": [
          { "path": "/market/board", "label": "行情看板", "icon": "monitor",
            "legacy": "pages/10_行情看板.py", "permission": "user", "wave": 2,
            "dataDay": true, "priceDomain": "market" }
        ]}
      ]
    }
  ],
  "deepLinks": { "hub_gyj_view": "view", "pick_stock": "code" }
}
```

`router.tsx` 与侧栏组件**都从这里生成**；`legacy` 字段用于兼容层与迁移比对；`priceDomain` 直接喂给 `DESIGN.md` §3 的组件，从清单层面杜绝双套色误用。

---

## 4. 74 页迁移分波（对齐 `PLAN.md` §6）

| 波次 | 页面 | 数量 |
|---|---|---|
| **W0** | 90 登录 + 91 我的 + 96 新手教程 + 脚手架/契约 | 3 |
| **W1 决策中枢** | 54 / 97 / 98 / 51 / 55 / 99 | 6 |
| **W2 行情与板块** | 10,14,35,76,84,85,12,17,75（51 已在 W1） | 9 |
| **W3 广度·温度** | 13,15,50,59,61,62,63,69,56,57,23,60,58,70,65,66,67,68,16,77（97/99 已在 W1） | 20 |
| **W4 个股研究** | 24,21,22,72（+ 11/20 作为 `?view=` 子视图） | 4 |
| **W5 量化选股** | 36,32,31,33,25,30,71（55 已在 W1） | 7 |
| **W6 持仓交易** | 45,43,42（+ 40/41/46 作为 `?tab=` 子视图；98 已在 W1） | 3 |
| **W7 工具社区+Admin** | 34,47,95,44,86,73,74,82,81,53,52,94,64,83,87,92,93 | 17 |
| **内嵌合并** | 11,20,40,41,46 → 无独立路由 | 5 |
| 合计 | | **74** |

> 波次划分依据：W1 是产品最高光且**必须先解决 §4 只读端点**；W3 页数最多且图表最复杂，排在图表库已验证的 W2 之后；W7 长尾收口。

---

## 5. 交互流程与状态

### 5.1 全局状态分层

| 层 | 工具 | 内容 |
|---|---|---|
| 服务端状态 | TanStack Query | 所有 API 数据、缓存、失效、重试 |
| 客户端 UI 态 | Zustand | 主题、侧栏折叠、深链预选、对比篮 |
| URL 状态 | TanStack Router search params | 深链、筛选、分页、tab（**可分享**） |
| **禁止** | — | 把服务端数据复制进 Zustand；把仓位规则放进前端 |

### 5.2 页面模板（每个数据页必守）

```
页标题 + 数据日条（权威数据日 / 新鲜度状态）
  ↓
决策结论区（若该页有结论）
  ↓
Bento 卡片区（KPI / 图表 / 表格）
  ↓
归因 / 明细 / 展开区
```

**数据日条不可省**。缺它就无法判断数据陈旧，违反诚实红线。

### 5.3 四类必备状态

每个数据型组件必须实现 `loading | empty | error | degraded`，语义与 `DESIGN.md` §7 一致。`degraded` 由后端返回的权威数据日驱动（4 天 / 8 天阈值），前端只呈现不计算。

### 5.4 写操作（W6 持仓交易）

乐观更新 + 失败回滚 + 冲突提示；涉及订单/条件单/实盘的提交一律二次确认；提交后使相关 queryKey 失效并重取，**不信任本地推测值**。

---

## 6. 响应式与无障碍

- 断点与列数遵循 `DESIGN.md` §4；侧栏在 <1200px 收为抽屉，<600px 用底部导航承载 6 大类入口。
- 移动端降级策略：**决策结论与数据日条优先保留**，复杂图表降级为摘要卡 + 「查看完整图表」入口，不横向滚动整个页面。
- 键盘：侧栏、tab、下拉、对话框、图表 tooltip 全可达；焦点可见。
- 涨跌/强弱颜色之外必须有形状或符号（`DESIGN.md` §8）。
- 每个图表提供等价数据表。

---

## 7. 迁移验收清单（每波逐项核）

- [ ] 与原版同日数据**逐字段一致**（同一 API / 同一 `date`）
- [ ] 深链参数 `hub_gyj_view` / `pick_stock` 及旧链接兼容层通过
- [ ] 四态（加载/空/错误/降权）齐全，无编造数据
- [ ] `priceDomain` 显式传入，双套涨跌色零误用
- [ ] 数据日条存在且显示权威数据日
- [ ] 导航 manifest 与 `widgets.py::_NAV_GROUPS` 差异告警为零（或有书面豁免）
- [ ] 空悬 HOT/NEW、🟢🔴 强弱灯等已知缺陷未回归
- [ ] 图表库按需分包，首屏预算达标
- [ ] 仅 FF 提交、只 add 本波文件、原版目录零改动

---

## 8. 明确不做

- ❌ 不把 11/20/40/41/46 恢复成独立页
- ❌ 不改一级类目数量（6）与顺序
- ❌ 不在 V2 复刻 Streamlit 的整页 rerun 语义
- ❌ 不做微前端（双前端是端口隔离，见 `PLAN.md` §3.1）
- ❌ 不写任何应用代码（本阶段只出规划）

---

## 9. V2 前端落地进度追踪（执行态，2026-11-06 起）

> 本表记录 `frontend-v2` **实际已落地**的页面与数据来源，替代纯规划。规划波次见 §4。

| 波次 | 页面 | V2 状态 | 数据来源 | 备注 |
|---|---|---|---|---|
| W0 | 90 登录 | ✅ 已落地 | auth 契约 | `06aef06` |
| W0 | 91 我的 / 96 教程 | ⬜ | — | 待排 |
| W1 | 54 今日决策面板 | ✅ | getDailySnapshot | 含图表 `4995e23` |
| W1 | 97 决策回放 | ✅ | getSnapshotByDate | 日期下拉 |
| W1 | 51 每日晨报 | ✅ | getReviewNotes + getDailySnapshot | review 缺失诚实「无数据」 |
| W1 | 55 P1 信号 | ✅ | getP1Signals | |
| W1 | 99 QA | ⬜ | — | 待排 |
| W2 | 行情与板块 10/14/35/76/84/85/12/17/75 | ⬜ | 需补 read 端点 | 下一簇 |
| W3 | 广度·温度首簇 56/57/59/13/15… | ✅ 已落地 | `breadth-timeseries` + `breadth-history` | 广度总览 `/breadth`：近期时序 + 2007→2026 长周期双轴 |
| W3 | 58 连板梯队 | ✅ 已落地 | `ladder-detail` | 连板梯队共振 `/ladder`：强度趋势 + 板位分布 |
| W3 | 后续簇 · 事件因子 | ✅ 已落地 | `event-pool` | `/events`：原样带出「统计意义上的超额收益概率排序，非买卖指令」 |
| W3 | 后续簇 · 预测校准 | ✅ 已落地 | `prediction-log` | `/predictions`：命中率分母只算已兑现样本，`hit=null` 不计入 |
| W3 | 后续簇 · 数据与运维 | ✅ 已落地 | `p1-sync-status` + `backtest-runs` + `data-refresh-state` | `/ops`：三数据源独立四态；绝对路径递归脱敏；负收益/负 Sharpe 如实带符号 |
| W4 | 个股研究 24/21/22/72 | 🟡 W4-A 六维评分(72) + W4-B 24/22 已落地 | `six-dim` + `fundamentals` / `financials` / `stock-kline` | 21 多股对比待 W4-C |
| W5 | 量化选股 36/32/31/33/25/30/71 | 🟡 36 荐股已落地 | getDailyRecommendation | 其余待 |
| W6 | 持仓交易 45/43/42 | 🟡 42 模拟盘已落地 | getPaperTrades | 其余待 |
| W7 | 工具社区+Admin 34…93 | 🟡 74/86 已落地 | alert-rules(空)/webapps | 其余待 |

**数据来源策略（诚实红线）**：已落地页全部走 `/api/v2/read/*` 端点 + MSW 演示数据；缺失数据诚实「无数据」，绝不编造填充。
截至 2026-11-07，只读端点共 **24 个**（W1 12 + W3 首簇 2 + 长周期广度 1 + W3 后续簇 5 + W4-A 六维评分 1 + W4-B 个股域 3）；
`frontend-v2/spec/openapi.json` 静态基线 W4-B 实跑为 **88 paths / 111 operations**（W4-B 新增 `fundamentals` / `financials` / `stock-kline` 三个 GET，四个个股域 GET 全带 BearerAuth）；历史实跑值：W0 64/87、W3 首簇后 79/102、W3 收口 84/107、W4-A 85/108、W4-B 88/111 —— 均为各自时点读取文件真值，非笔误。
**后续簇（W2/W4/W5/W6/W7 多数）** 需先在 `backend/api/read_routes.py` 补对应只读端点，再按本表逐页迁移；
W3 的广度时序、连板明细、长周期广度 3 个端点**已落地**，不再是待办。
**导航**：当前 V2 侧栏保持 **4 组**：「量化与工具」组 **7 项**（含 W4-A 六维评分 / W4-B 个股研究 / 基本面分析），
「市场广度·温度」组 **5 项**（广度总览 / 连板梯队共振 / 事件因子池 / 预测校准日志 / 数据与运维状态），
图标全局唯一、子簇 ≤8；本轮**不收敛** §2 的 6 类目结构（待后续波次按真实页面量再评估）。

### W4-A 非等价迁移 · 书面豁免（2026-11-07）

**结论先行：W4-A 六维评分（旧 72 页 → `/stock/six-dim`）不是逐字段等价迁移，不得对外表述为「与原版一致」。**
评分纯逻辑 `modules/six_dim.compute_dims` 仍为唯一真理源（六维等权、缺维为 `null` 且不参与 `overall` 平均），
但**取数链路**有 4 处经源码取证的口径差异，均已写入端点注释与守卫测试：

| # | 旧 72 页 | W4-A `/api/v2/read/six-dim` | 影响 |
|---|---|---|---|
| 1 | `ak.stock_zh_a_hist()` 返回中文列 | `get_fetcher().get_kline(period='daily')` 实际走 `get_daily()`，返回英文列 `date/open/close/...` | 端点内仅做 `close → 收盘` **列名映射**，不改数值、不补 0 |
| 2 | 周期维调用 `market_regime.regime_report()` | `state_fn=None`，不臆造状态机函数名 | 周期维只由 `pos60` 出分；`raw.state` 恒为 `null`，属**能力收缩**，非等价 |
| 3 | 先探测 `get_realtime_quote()` 找「换手率 / 量比 / 市盈率-动态 / 市净率」 | 已核实该接口字段为 `ticker/name/open/prev_close/current/high/low/volume/amount/bid/ask/datetime`，**不含**上述四项 | 删除永不命中的探测分支，省掉每次白跑新浪实时接口（内部 10s 超时） |
| 4 | 资金 / 价值维使用 `ak.stock_zh_a_spot_em()` | **同源**，仍用 `ak.stock_zh_a_spot_em()` | 差异不是「取数源不同」，而是该快照成为**唯一来源**并收敛掉 #3 的实时接口探测 |

**耗时边界**：三源由串行改为 `modules/fetch_parallel.fetch_many` 并发，整批硬边界
`CALL_TIMEOUT_CAP=12s`（满足 `REQ_TIMEOUT 10 < CALL_TIMEOUT_CAP 12` 不变量）；实测最坏 **12.01s**
（串行三源最坏 40s+）。超时 / 异常源按 `None` / `{}` 降级，绝不 500、绝不补 0。
`backend/tests/test_read_routes.py` 已加 `parallel_source_failure_degrades` /
`parallel_timeout_degrades` 两条并发路径缺维用例。

**契约**：`raw.state` 为 `str|null`（后端 `str()` 归一），前端 `SixDimRawSchema.state = z.string().nullable()`；
`date` 必须来自 K 线最后一根，取不到返回 `null`，禁止 `datetime.now()` 兜底。
静态 OpenAPI 实跑 **85 paths / 108 operations**。

> 该豁免只覆盖 W4-A 这一页。W4-B 已落地 `24 个股研究` / `22 基本面分析` 两页并接入深链契约
> `hub_gyj_view` / `pick_stock`，其非等价项与能力收缩见下方 W4-B 豁免章节；`21 多股对比` 仍未迁移，不得计入已落地。


### W4-B 非等价迁移 · 书面豁免（2026-11-07）

**结论先行：W4-B 迁移了旧 `22 基本面分析` → `/stock/fundamentals` 与旧 `24 个股研究` → `/stock/research` 两页，并接入 `hub_gyj_view` / `pick_stock` 深链；这不是逐字段等价迁移，且 `21 多股对比` 仍未迁移，不得计入已落地。**

#### 1. 为什么是「实时计算型只读 GET」（P2），不是 W1/W3 的本地 JSON 路线

真扫三页（`pages/24_个股研究.py`、`pages/21_多股对比.py`、`pages/22_基本面分析.py`）：全部是实时联网 / 后台任务计算，`data/` 下**零对应本地 JSON 真源**。W1/W3 的 `_FILE_WHITELIST` 文件读取器路线无米下锅，故沿用 W4-A `six-dim` 先例，新增 3 个端点：

| 端点 | 用途 | 前端消费 |
|---|---|---|
| `GET /api/v2/read/fundamentals` | 名称 / 行业 / 现价 / PE / 总市值 + 9 项业绩 + 3 个数据日 | `FundamentalsView` |
| `GET /api/v2/read/financials` | 多期财报 `rows`（三表合并） | `FundamentalsView` |
| `GET /api/v2/read/stock-kline` | `daily` / `weekly` / `monthly` OHLC `rows` | `ResearchView`（quick） |

3 个端点均 `@jwt_required`、统一 `ok/fail` 信封（`code` 为字符串业务码）、`_sanitize()` 清洗 NaN/Inf、`fetch_many` 并发且整批硬边界 `CALL_TIMEOUT_CAP=12s`（满足 `REQ_TIMEOUT 10 < 12`）。`read_routes.py` 采用**单一末尾 hunk 纯增量**，既有 21 端点一字未动。不复用 `/api/kline`：该端点未过 `_sanitize()`，原生 float NaN 会裸奔。旧 22 页 `_industry_pe_sample` 里硬编码的 `timeout=60` **不得复制**。

#### 2. 旧版补 0 / 中性默认 → V2 一律诚实缺失

| 旧版行为 | W4-B V2 |
|---|---|
| 旧 24 deep 有 31 个数值字段 `None/NaN → 0.0` | `null` / `[]` /「缺失」，禁 0 / 50 /「持有」/ 中性默认 |
| 旧 21 页失败补 `scores=50` / `chg_pct=0.0` / `signal="持有"` | **本波不迁移 21**；W4-C 亦须沿用 null 口径 |
| 数据日用当前日期兜底 | 必须是权威数据日；取不到 `null`，页面显示「暂无权威数据日」，禁 `datetime.now()` / 文件 mtime |
| `_calc_perf` 缺键直接 pop | 9 字段全 `null` 字典（全源失败态）或 `perf:null`；Zod 两种都兼容，逐字段显示「缺失」，绝不补 0 |

#### 3. 已拍板的契约张力（不掩盖）

- **`financials.report` 仅回显**：`rows` 恒为利润表 / 资产负债表 / 现金流量表**三表合并**指标，不支持单表切换；前端**不暴露 report 切换控件**，卡片标题为「多期财报（三表合并）」，口径说明原文写明「暂不支持单表切换（report 固定 income）」。
- **`yoy` 语义**：`revenue_yoy` / `profit_yoy` 字段名沿用旧页，但语义是**「与上一报告期比」的相邻期口径，非同比 / 去年同期**。V2 标签已由「营收同比(%) / 净利同比(%)」如实改为「营收(较上一报告期 %) / 净利(较上一报告期 %)」。财报表格列名（如 `营业总收入_同比`）是后端原始列回显、未改写，属非等价项。
- **数据日不标「今日」**：`date` / `spot_date` / `kline_date` 均为数据自带时间戳，可能来自过期缓存（旧交易日），页面分行展示且不出现「今日」措辞。
- **`priceDomain`**：22 页按交易屏口径固定 `"market"`，页面原文可见。本波新页**零涨跌色**（只用 `sf-warn` / `sf-accent` 状态色），避免 A 股双套语义误用。旧 24 deep 页内**价格域报告体（绿涨红跌）+ 业绩域交易屏（红涨绿跌）并存**，需字段域级区分，留 W4-C，不能整页一刀切。

#### 4. 深链契约与 `/legacy` 兼容层

- 真值：`hub_gyj_view` 为**中文** `⚡ 快速选取` / `🔬 深度分析`；旧 22:864-866 的跳转只带 `pick_stock`，落 **quick**。§3.2 规划态「`pick_stock` → `view=deep`」已按上文更正。
- `frontend-v2/src/lib/deeplink.ts` 为唯一归一真源（路由与单测共用）；非法 / 非 6 位 code **不写键**，不 `?? ''` / `?? 0` 兜底。
- `/legacy` 挂在 `rootRoute` 下（不能放 `appRoute`，否则未登录先被 `requireAuth` 跳 `/login` 且 query 被吞），用 `beforeLoad` 抛 `redirect({replace:true})` 做**客户端 `history.replace`，不是 HTTP 302**。
- 首帧预选由 `validateSearch` 同步完成，**不用 `useEffect`**；输出全 optional，避免 `AppShell.tsx` 泛化 `<Link to={it.to}>` 因 search 必填而 tsc 失败。

#### 5. 全站序列化契约变更（影响面已真扫）

**缺陷**：TanStack Router `1.170.46` 默认 `parseSearch = parseSearchWith(JSON.parse)`（`@tanstack/router-core/dist/esm/searchParams.js:5/22/26-29`）会把 6 位纯数字代码 `'600519'` 解析成 **number**，被 `validateSearch` 与 `pickCode` 的 `typeof === 'string'` 拒收，导致 `/legacy` 重定向后 URL 丢 `code`；`'000001'` 因前导零令 `JSON.parse` 抛错而保持字符串，**恰好绕过缺陷**；直达 URL 因浏览器地址栏不被 `commitLocation` rewrite 而看似正常。
**修复**：`frontend-v2/src/app/router.tsx` 为 `createRouter` 增配基于 `URLSearchParams` 的 `parseSearchAsStrings` / `stringifySearchAsStrings`，query 一律按字符串契约处理，并导出 `searchSerialization` 供运行时测试复用（零配置漂移）。后者同样必要：默认 `stringifySearchWith(JSON.stringify, JSON.parse)` 会把 `'600519'` 写成 `"600519"`，令 URL 出现 `%22`。
**影响面真扫**：全站 `validateSearch` / `search={{...}}` 使用点仅 `loginRoute.from`、`guards.tsx:13`、`AppShell.tsx:19`、两新页，**全部为字符串**，零数字 / 数组 / 布尔依赖，故无既有页面被破坏。新增 `tests/e2e/w4b-legacy-redirect.test.tsx` 8 例运行时集成测试（`createMemoryHistory` + 生产 `searchSerialization` + `RouterProvider`）锁死该契约。

#### 6. 明确的能力收缩（不得表述为「已完成」）

- **24 页 deep 子视图仅占位**：如实显示「深度分析子视图待 W4-C 迁移，当前仅完成深链预选」+ 已预选 code，不造假数据、不画空 K 线图；quick 子视图只有 OHLC 表格，**本波不做 ECharts K 线图**。
- 旧 22 页第三个按钮跳 `pages/20_个股分析.py`（V2 无该路由），已**并入** `/stock/research?view=deep`；`20` 页完整内容留 W4-C。
- `21 多股对比` 未迁移；剩余 4 个端点、多系列对比色板、24 deep 完整内容均留 W4-C。
- 浏览器侧**只打 MSW dev fixtures，未走 5050 真后端**（CORS 边界另见 `VISUAL-AUDIT.md`）。

#### 7. 规模（真读文件，非沿用摘要）

静态 OpenAPI **88 paths / 111 operations**（W4-B 新增 3 path，四个个股域 GET 全带 BearerAuth）；只读端点 **24 个**；导航 **4 组**，`量化与工具` 组 **7 项**，`市场广度·温度` 组 **5 项**，图标全局唯一。
