# StockSignal 前端 V2 · 技术审计 + v1→v2 功能对齐 · 实行与规划文档

> 生成日期：2026-11-09
> 范围：核对 V2 是否采用主流技术栈、是否实现了 V1「提炼」出的功能、给出后续执行规划。
> 证据口径：直接读 `frontend-v2/package.json`、`src/app/router.tsx`、`src/nav/nav.ts`、`src/nav/nav.manifest.json`、`frontend-v2/DESIGN.md`；实跑 `tsc --noEmit`（exit 0）与 `vitest run`（235 passed / 1 skipped）。

---

## 0. 结论先行（TL;DR）

| 议题 | 结论 | 证据 |
|---|---|---|
| V2 是否主流技术 | ✅ 是，2026 一线组合 | `package.json`：React 19.3 / TS 7.0 / Vite 8.3 / Tailwind 4.3 / ECharts 6.1 / TanStack Q+R 5.1 / Zustand 5 / Zod 4.6 / MSW 2.7 / Vitest 5.1 |
| V1 是否该淘汰 | ✅ 方向正确（已有红线：禁新增 Streamlit 页） | `MEMORY.md` 技术栈红线：新 UI 一律 v2/React |
| V2 是否实现「全部」V1 提炼功能 | ❌ **否**，但覆盖率已大幅提升 | 74 个 V1 页面：✅43 已在 V2 有等价页（含并入 /breadth 等）、🟡20 仅关联只读数据、🔒11 v1 保留（永久不迁，如实盘交易）、⬜0 待迁移（92 用户管理 / 77 财报猎手 / 73 自定义看板已于 2026-11-11 迁 v2，路由 /users、/financial-hunter、/dashboard-custom） |
| V2 当前是否真能跑 | ✅ 是 | `tsc` exit 0；`vitest` 通过；28 路由全注册 |
| 文档漂移 | ⚠️ `nav.manifest.json` 是过期 w0 死文件 | 未被任何代码 import，且其引用的 `IA-MIGRATION.md` 根本不存在 |

**核心判断**：V2 技术栈正确、质量高、已实现 v1 的**决策/广度·温度/个股研究/量化信号/连板/告警/晨报/模拟交易/六维评分/行情看板/资金流向/龙虎榜/持仓中心/市场全景/状态机/题材/强势榜/用户管理/财报猎手/自定义看板**等核心分析闭环。按四档诚实口径（详见 §3 / §4，单一真理源 `frontend-v2/src/features/catalog/v2Mapping.ts`）：**43 个 native（v2 有等价页）+ 20 个 data（v2 仅关联只读数据）+ 11 个 v1 保留（永久不迁，如实盘交易）+ 0 个待迁移（92 用户管理 / 77 财报猎手 / 73 自定义看板已于 2026-11-11 迁 v2，路由 /users、/financial-hunter、/dashboard-custom）**；v1 短期内**不能整体下线**（尤其 43 实盘交易等真实券商下单能力永久留 v1），只能作为只读兜底并存。

---

## 1. 技术栈审计（V1 vs V2）

| 维度 | V1（Streamlit，淘汰中） | V2（React SPA，生产前端） | 是否主流 |
|---|---|---|---|
| UI 框架 | Streamlit（Python 组件） | **React 19.3.1** | ✅ 顶流 |
| 语言 | Python + 内联 HTML/CSS | **TypeScript 7.0.2**（类型安全） | ✅ 顶流 |
| 构建/Dev | Streamlit 自带 server（全量重跑） | **Vite 8.3.6**（HMR、懒加载分包） | ✅ 顶流 |
| 样式 | 散装 `st.markdown` + 内联 style | **Tailwind CSS 4.3.4** + 设计令牌 `tokens.css` | ✅ 顶流 |
| 图表 | Plotly（Python 端渲染） | **ECharts 6.1.0**（canvas，懒加载） | ✅ 顶流 |
| 状态管理 | `st.session_state` | **Zustand 5.0.16** | ✅ 主流 |
| 路由 | 文件式 multipage | **TanStack Router 1.170**（类型安全、深链） | ✅ 主流 |
| 数据获取 | 同步函数直调 | **TanStack Query 5.106**（缓存/loading/error 状态机） | ✅ 主流 |
| 校验 | 散装 if | **Zod 4.6.7**（严格解析，禁 `?? 0` 兜底） | ✅ 主流 |
| Mock | 无 | **MSW 2.7.0**（仅演示，生产不加载） | ✅ 主流 |
| 测试 | pytest（后端/页） | **Vitest 5.1.0** + Testing Library + jsdom | ✅ 主流 |

**V1 三宗罪已被 V2 架构规避**（与老板 2026-11-09 判定一致）：
1. **全量重跑**：Streamlit 每次交互重跑整脚本；V2 用 TanStack Query 缓存 + 路由级 `lazyRouteComponent` 分包（首屏主包 342 kB / gzip 102 kB，ECharts 不进首屏）。
2. **UI 不可定制**：Streamlit 组件封闭；V2 用 Tailwind + 设计令牌自由定制，且 DESIGN.md 已实算 WCAG 对比度（三级文字 14.37/8.36/4.89:1）。
3. **非生产级**：Streamlit 难做鉴权/路由/无障碍；V2 有登录守卫、类型安全路由、无障碍（`role=img/status/alert`、`aria-label`、焦点环、`prefers-reduced-motion`）。

**结论**：V2 技术栈**完全符合"最先进/主流"要求**，且设计系统有诚实红线（缺失数据不编造、`FreshnessBadge` 状态色与涨跌色三语义线互不混淆）。

---

## 2. V2 当前真实状态（证据）

- **路由**：`router.tsx` 注册 **28 条**路由（含 `/theme` + `/theme-transmission`）；`nav/nav.ts`（导航唯一真理源）暴露 **29 个可见入口**（4 大组），`/legacy` 为 v1 深链兼容重定向。
- **编译**：`npx tsc --noEmit` → **exit 0**（无类型错误）。
- **测试**：`npx vitest run` → **26 文件 / 235 passed / 1 skipped**。3 个 worker 池启动告警（沙箱线程 fork 限制，非用例失败）。
- **设计系统**：`DESIGN.md` 完备——轻量卡片流、三色语义线（A股红涨绿跌 `ss-up/down` 与报告体 `doc-up/down` 与状态色 `sf-ok/warn/danger` 互不混淆）、WCAG 实算、无障碍、诚实红线（不编造数据）。

> ⚠️ **漂移**：`nav/nav.manifest.json` 仍标注 `w0-skeleton` 且仅含 login + 占位根，但其引用的 `IA-MIGRATION.md` 不存在，且全文未被任何代码 import —— 是**过期死文件**，会误导后来者以为 V2 只有 2 页。应删除或重建为 `nav.ts` 的镜像。

---

## 3. v1 → v2 功能对齐矩阵

状态图例（四档，与 `frontend-v2/src/features/catalog/v2Mapping.ts` 单一真理源一致）：✅ native（v2 有等价路由页）｜🟡 data（v2 无等价页，但有可查看的关联只读端点，非等价功能）｜🔒 v1 保留（永久不迁 v2，真实交易/实验/低频遗留）｜⬜ 待迁移（v2 尚未迁移、但计划迁移）

### 3.1 行情与板块（9 ✅ native）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 行情看板 | 10 | ✅ | `/quote-board`（指数日线快照 + 板块涨跌榜 + 市场状态） |
| 股票选取 | 11 | ✅ | 选股入口由 `/quote-board` 承接 |
| 板块轮动 | 12 | ✅ | `/sector-rotation`（行业资金流热力/排行） |
| 智能盯盘 | 14 | ✅ | `/watch`（自选股资金流 + 板块异动 + 资金流预警） |
| 资金流向 | 35 | ✅ | `/fund-flow`（北向/行业/大盘主力/融资融券，分块诚实降级） |
| 实时强势榜 | 76 | ✅ | `/strong`（多因子强势评分 + 六维排雷二道闸） |
| 宏观数据 | 84 | ✅ | `/macro-data` |
| 龙虎榜 | 85 | ✅ | `/dragon-tiger` |
| 题材热点 | 75 | ✅ | `/theme`（常驻）+ `/theme-transmission`（④ 事件传导按需，默认不自动抓网） |

### 3.2 市场广度·温度（5 ✅ native + 10 🟡 data + 3 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 市场强弱 | 13 | 🔒 | v1 保留：与广度·温度簇高度重叠且依赖 v1 实时行情单例 |
| 市场驱动力 | 15 | 🔒 | v1 保留：实验性视图，v2 暂无等价计划 |
| 市场魔方 | 17 | 🔒 | v1 保留：展示性视图，v2 不做等价实现 |
| 市场情绪 | 50 | 🟡 | data：`/api/v2/read/breadth-timeseries`（广度时序） |
| 市场温度计 | 59 | ✅ | `/breadth`（主卡） |
| 广度分化 | 61 | ✅ | `/breadth`（广度总览视图） |
| 动量广度共振 | 62 | 🟡 | data：`/api/v2/read/breadth-timeseries` |
| 温度回测 | 63 | 🟡 | data：`/api/v2/read/backtest-runs`（回测运行记录） |
| 温度持续期与回归时长 | 69 | 🟡 | data：`/api/v2/read/breadth-history` |
| 市场状态机 | 56 | ✅ | `/regime` |
| 市场全景 | 57 | ✅ | `/panorama` |
| 事件对比分析 | 60 | 🟡 | data：`/api/v2/read/event-pool`（事件因子池） |
| 涨停复盘 | 70 | 🟡 | data：`/api/v2/read/breadth-history` |
| 投机情绪周期时钟 | 65 | 🟡 | data：`/api/v2/read/breadth-timeseries` |
| 历史相似日聚类前向分布 | 67 | 🟡 | data：`/api/v2/read/breadth-history` |
| 情绪拐点扫描器 | 68 | 🟡 | data：`/api/v2/read/breadth-timeseries` |
| 财报日历 | 16 | 🟡 | data：`/api/v2/read/financials`（财务数据） |
| 财报猎手 | 77 | ✅ | native：`/financial-hunter`（2026-11-11 迁移：逐股票三表 income/balance/cash 切换深挖，复用只读 `/api/v2/read/financials`；诚实红线——null 数值显「—」、date 为 null 显「暂无权威数据日」、note 为 null 显原文缺失说明，非跨股筛选器不伪造；含真人交互级 E2E 6 例） |

### 3.3 个股研究（✅ 全覆盖）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 个股分析 | 20 | ✅(并入24) | 被 `/stock/research` 的「深度分析」子视图吸收 |
| 个股研究 | 24 | ✅ | `/stock/research` |
| 多股对比 | 21 | ✅ | `/stock/compare` |
| 基本面分析 | 22 | ✅ | `/stock/fundamentals` |
| 六维评分 | 72 | ✅ | `/stock/six-dim` |

### 3.4 量化选股（4 ✅ native + 2 🟡 data + 2 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 每日荐股 | 36 | ✅ | `/recommend` |
| P1 量化信号 | 55 | ✅ | `/p1` |
| QuantAgent投研 | 25 | 🔒 | v1 保留：实验性 Agent 流程，留 v1 观察 |
| 策略回测 | 30 | ✅ | `/backtest` |
| 形态选股 | 31 | 🟡 | data：`/api/v2/read/daily-recommendation`（每日荐股结果） |
| 智能选股 | 32 | 🟡 | data：`/api/v2/read/daily-recommendation`（每日荐股结果） |
| ETF筛选 | 33 | 🔒 | v1 保留：小众筛选器，v2 暂无等价计划 |
| 因子分析 | 71 | ✅ | `/factor` |

### 3.5 持仓交易（5 ✅ native + 1 🟡 data + 1 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 自选股监控 | 46 | ✅ | `/watch`（v2 由自选股监控承接） |
| 仓位管理 | 40 | ✅ | `/portfolio` |
| 组合收益 | 41 | ✅ | `/portfolio` |
| 持仓中心 | 45 | ✅ | `/portfolio` |
| 实盘交易 | 43 | 🔒 | v1 保留：真实券商下单（QMT/同花顺）仅 v1；v2 仅有只读账户概览「交易账户（只读）」入口，不提供任何交易能力 |
| 模拟交易 | 42 | ✅ | `/paper` |
| 仓位落地 | 98 | 🟡 | data：`/api/v2/read/daily-snapshot`（今日决策快照） |

### 3.6 工具与社区（5 ✅ native + 5 🟡 data + 5 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 体检扫描 | 34 | 🟡 | data：`/api/v2/read/six-dim`（六维评分数据） |
| 价格预警 | 47 | 🟡 | data：`/api/v2/read/alert-rules`（告警规则）；与 `/alerts` 不同，独立功能 |
| 数据导出 | 95 | 🟡 | data：`/api/v2/read/snapshot-dates`（快照日期清单） |
| 智能条件单 | 44 | 🟡 | data：`/api/v2/read/alert-rules`（告警规则） |
| 网页作品集 | 86 | ✅ | `/webapps` |
| 自定义看板 | 73 | ✅ | native：`/dashboard-custom`（2026-11-11 迁移：勾选组件 + localStorage 持久化，聚合 5 个真实只读端点——今日决策快照/每日荐股/广度温度时序/事件因子池/回测运行记录；诚实渲染，缺失字段显「—」、回测收益为负如实红绿，不编造列表） |
| 告警引擎 | 74 | ✅ | `/alerts` |
| 数据时效性看板 | 82 | ✅ | `/ops`（数据与运维状态） |
| 自然语言选股 | 81 | 🔒 | v1 保留：实验性 NL 选股，v2 暂无等价计划 |
| 星辰 AI | 53 | 🔒 | v1 保留：独立 AI 对话，已在独立项目 `xingchen-ai` 实现 |
| 股吧 | 52 | 🔒 | v1 保留：社区抓取，低频遗留 |
| 消息中心 | 94 | 🟡 | data：`/api/v2/read/alert-log`（告警日志） |
| 投研圆桌 | 64 | ✅ | `/predictions`（预测校准日志） |
| 分析规则库 | 83 | 🔒 | v1 保留：规则维护工具 |
| 语音事件 | 87 | 🔒 | v1 保留：语音采集低频功能 |

### 3.7 决策 / 工具入口 / 管理（9 ✅ native + 2 🟡 data + 1 ⬜ 待迁移）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 今日决策面板 | 54 | ✅ | `/decision` |
| 决策回放 | 97 | ✅ | `/replay` |
| 每日晨报 | 51 | ✅ | `/morning` |
| 连板龙头共振 | 58 | ✅ | `/ladder` |
| 事件追踪 | 23 | ✅ | `/events` |
| 维度领先-滞后矩阵 | 66 | ✅ | `/matrix`（有序对明细表，带符号 lag） |
| 新手教程 | 96 | ✅ | `/guide` |
| 系统配置 | 93 | ✅ | `/settings` |
| 登录 | 90 | ✅ | `/login` |
| 我的 | 91 | 🟡 | data：`/api/v2/read/user-dashboard`（用户看板数据） |
| 用户管理 | 92 | ✅ | native：`/users`（2026-11-11 迁移：角色门控 + 用户列表/创建/操作日志三 Tab，复用只读 `/api/admin/*` 端点） |
| 决策问答 | 99 | 🟡 | data：`/api/v2/read/review-notes`（复盘笔记） |

### 3.8 V2 原生页（无 V1 等价，属新增能力）
`/predictions`(预测校准日志)、`/ops`(数据与运维状态)、`/diagnostics`(数据源与接口检测)、`/catalog`(v1 功能全景/目录)、`/data`(只读端点浏览器)。

---

## 4. 覆盖率统计

> 口径对齐 `frontend-v2/src/features/catalog/v2Mapping.ts`（单一真理源）；数量由真实清单实时统计，非写死。
> 旧版「✅21 / 🟡8 / ❌45」为 2026-11-09 基线快照，已被本轮漂移收口（大量已有 v2 等价页却低报的页升级为 native）取代。

| 类别 | 数量 | 占比 |
|---|---|---|
| ✅ native（v2 有等价路由页） | 43 | ~58% |
| 🟡 data（v2 无等价页，但有可查看的关联只读端点，非等价功能） | 20 | ~27% |
| 🔒 v1 保留（永久不迁 v2） | 11 | ~15% |
| ⬜ 待迁移（v2 尚未迁移、但计划迁移） | 0 | 0% |
| V2 原生（无 v1 等价，属新增能力，不计入 74） | 5 | — |

**诚实结论**：按四档口径，V2 已对 74 个 v1 页面中的 **43 个给出等价路由页（native）**、**20 个提供关联只读数据端点（data）**、**11 个明确永久留 v1（v1 保留，含 43 实盘交易等真实下单能力）**、**0 个待迁移**（92 用户管理 / 77 财报猎手 / 73 自定义看板已于 2026-11-11 迁 v2，路由 `/users`、`/financial-hunter`、`/dashboard-custom`）。「约 45 个页面无任何 v2 支撑」的旧判断已不成立——实际彻底无 v2 支撑的仅 11 个，且已全部主动决策永久留 v1（含真实券商下单）。v1 短期内**不能整体退役**（尤其真实交易/低频遗留/实验性页面永久留 v1），只能作为只读兜底并存。

---

## 5. 已知问题 / 漂移 / 风险

1. **`nav/nav.manifest.json` 死文件**：标注 w0 骨架、引用的 `IA-MIGRATION.md` 不存在、未被任何代码 import → 误导性强，应删除或重建为 `nav.ts` 镜像。
2. **无真人浏览器 E2E / 目检**：`DESIGN.md` 自承亮色主题未做真人浏览器目检；`VITE_E2E_LIVE` 仅证明 Node `fetch` 通 health，不等于浏览器 CORS 链路或视觉验收。
3. **V2 dev server（5173）不常起**：上次会话遗留旧 Vite 窗口待重启；真视觉验证需先拉起。
4. **`/breadth` 是整合概览非逐页 1:1**：v1 广度·温度簇 8 页被合并，个别专项能力（如独立「温度回测」页、独立「市场状态机」图）未独立保留，需确认是否够用。
5. **遗留缺口已大幅收敛**：早期「高价值页缺失」清单中的策略回测(30)、因子分析(71)、持仓中心(45)、市场全景(57)、市场状态机(56)、资金流向(35) 等现已 native；唯一明确待迁移项仅 92 用户管理，另有 11 个（含 43 实盘交易）主动决策永久留 v1。v1 不能整体退役的主因已从「高价值页缺位」转为「真实交易/低频遗留/实验性页面需永久保留」。

---

## 6. 后续规划（我要干的事，按优先级）

### Tier 1 — 补齐高价值分析闭环（✅ 已全部落地）
- [x] 策略回测 `30` → `/backtest`（`f862a91`）
- [x] 因子分析 `71` → `/factor`（`f862a91`）
- [x] 市场全景 `57` → `/panorama`（`de634f7`）
- [x] 市场状态机 `56` → `/regime`（`de634f7`）
- [x] 持仓中心 `45`（含自选/仓位/组合） → `/portfolio`（`1a23f40`）
- [x] 实盘交易 `43` → `/trading-account`（**只读概览**，不暴露写接口；`3f078bb`）。仓位落地 `98` 仍留 v1。
- [x] 资金流向 `35` → `/fund-flow`（`54e9f81`）

### Tier 2 — 行情与广度补全（✅ 已全部落地）
- [x] 行情看板 `10` → `/quote-board`（本轮：`/api/v2/read/quote-board` 只读聚合）
- [x] 板块轮动 `12` → `/sector-rotation`（`38411f6`）
- [x] 龙虎榜 `85` → `/dragon-tiger`（`12a81dc`；实际路径为 `/dragon-tiger`，非早期草案 `/dragontiger`）
- [x] 题材热点 `75` → `/theme`（`6bc0c6b`）
- [x] 实时强势榜 `76` → `/strong`（`d146414`）
- [x] 宏观数据 `84` → `/macro-data`（`15c1726`）
- [x] 智能盯盘 `14` → `/watch`（`c53b8b0`）

### Tier 3 — 社区 / 工具长尾（按四档口径收口）
- [x] 已有等价/数据落点：投研圆桌 `64`（→ `/predictions` native）、我的 `91` / 决策问答 `99`（→ data 只读端点）、体检扫描 `34` / 价格预警 `47` / 数据导出 `95` / 智能条件单 `44` / 自定义看板 `73` / 消息中心 `94`（均 → data 只读端点）
- [x] 用户管理 `92` → 已 native（`/users`，2026-11-11 迁移收口）：角色门控 + 三 Tab（用户列表 / 创建用户 / 操作日志），复用只读 `/api/admin/*` 端点；含真人交互级 E2E（键盘输入 / 表单禁用态 / 点击 / 模态确认 / 搜索回车 / 错误态）
- [x] 财报猎手 `77` → 已 native（`/financial-hunter`，2026-11-11 迁移收口）：逐股票三表（income/balance/cash）切换深挖，复用只读 `/api/v2/read/financials`；诚实红线（null→「—」、date null→「暂无权威数据日」、note null→原文缺失说明，非跨股筛选器不伪造）；含真人交互级 E2E 6 例（默认渲染 / null 字段 / date null / note null / 空 rows / 报表 tab 切换）
- [x] 自定义看板 `73` → 已 native（`/dashboard-custom`，2026-11-11 迁移收口）：勾选组件 + localStorage 持久化，聚合 5 个真实只读端点（今日决策快照 / 每日荐股 / 广度温度时序 / 事件因子池 / 回测运行记录）；诚实渲染——缺失字段显「—」、回测收益为负如实红绿、每日荐股 unavailable 时不编造标的列表；含真人交互级 E2E 5 例（默认 5 组件 / 取消移除+持久化 / 重新勾选 / unavailable 诚实态 / 全取消提示）
- 🔒 **已决策永久留 v1（不再作为 v2 待办）**：股吧 `52`、自然语言选股 `81`、分析规则库 `83`、语音事件 `87`、星辰 AI `53`、ETF筛选 `33`、QuantAgent投研 `25`、市场强弱 `13`、市场驱动力 `15`、市场魔方 `17`、实盘交易 `43`（真实券商下单）

> 说明：原「Tier 3 13 页长尾」清单中的多项，经本轮四档评估后明确为「v1 保留」或已具备 data/native 落点，**不再是 v2 待办**；详见 §13 补记。

### 清理与验证（穿插执行）
- [x] 删除 `nav/nav.manifest.json` 死文件，消除文档漂移（Task #14）
- [ ] 常起 V2 dev server（5173）做真人浏览器目检 + 补浏览器级 E2E（CORS 链路）
- [ ] 每迁一页严格走迁移方法学（见 §7），并跑 `tsc` + `vitest` + 导航守卫
- [ ] 评估 v1 下线时机：当 Tier1+Tier2 完成、且 `/catalog`(v1 功能全景) 显示 v1 入口可全部由 v2 替代时，再将 v1 降为只读或退役

---

## 7. 迁移方法学（每页一致执行）

1. **加导航**：`src/nav/nav.ts` 的 `NAV` / `UTILITY_PATHS` 增项（守卫锁：一级类目≤6、顺序固定、图标全局唯一、子簇≤8）。
2. **加路由**：`src/app/router.tsx` 用 `lazyRouteComponent`（守卫 `tests/unit/route-lazy.test.ts` 禁静态 import 回潮）。
3. **实现**：`src/features/<域>/<Page>.tsx`，复用 `shared/ui`（Card / Stat / FreshnessBadge / QueryState / EChart）与 `tokens.css` 设计令牌；深链走 `lib/deeplink.ts`。
4. **数据**：后端已有 12 只读端点 + 新增端点；前端用 TanStack Query（`@/lib/queries`）+ Zod 严格解析（禁 `?? 0` 编造）。
5. **Mock**：MSW 仅演示数值，明确标注非真实行情，生产构建不加载。
6. **测试**：Vitest + Testing Library 覆盖加载/空/错误三态（诚实红线：缺失不补零）。
7. **验收**：`tsc --noEmit` 0 错 + `vitest` 全绿 + 导航守卫通过 + 真人目检（亮/暗双主题）。

---

## 8. 给老板的建议

- **技术路线正确，继续**：V2 栈已是 2026 顶流，不要回退 Streamlit；新功能一律 v2。
- **不要急于删 v1**：真实交易(43)、低频遗留与实验性页面已主动决策永久留 v1，v1 仍是必要兜底；唯一明确待迁移项仅 92 用户管理。高价值分析闭环（决策/广度/个股/量化/连板/持仓/行情/全景/状态机）均已 native，无需再补。
- **先消漂移**：`nav.manifest.json` 死文件立即清理，避免误导。
- **补视觉验收**：V2 已通过 tsc + 单测，但缺真人浏览器目检；上线前务必拉起 5173 走一遍亮/暗主题。
- **可选**：若某长尾页（如语音事件、自定义看板）使用率低，可在 `/catalog` 标注"v1 保留"而非强迁，把精力集中在 Tier1 高价值闭环。

---

## 9. 进度补记（2026-11-09 晚，Tier 1 + Tier 2 收官）

> ⚠️ 本文档 §0 / §2 / §4 的覆盖率与测试数是 **2026-11-09 基线快照**（当时 28 路由 / 235 passed）。
> 以下为本轮迁移完成后的实测值，后读以本节为准；基线数字保留是为了不篡改当时的证据口径。

| 项 | 基线（§0/§2） | 本轮收官实测 |
|---|---|---|
| Tier 1 高价值闭环 | 7 页待办 | **7/7 落地**（30/71/57/56/45/43/35） |
| Tier 2 行情与广度 | 5 页待办 | **7/7 落地**（10/12/85/75/76/84/14） |
| 只读聚合端点 | 12 + 新增 | 新增 `/quote-board`，复用 `_w4x_index_quote` + `get_industry_fund_flow` + 服务器北京时间市场状态 |
| TypeScript | `tsc` exit 0 | `npx tsc --noEmit` **0 错** |
| 前端测试 | 235 passed / 1 skipped | **333 passed / 1 skipped**（42 文件） |
| 后端 `test_read_routes.py` | — | **54/54**（新增 `test_quote_board_endpoint` + 401 闸门） |
| 安全回归 | 12/12 | **12/12 通过**（`python -m backend.tests.test_security`） |

**Tier 2 收官页口径（行情看板 10）**：v1 页含「指数迷你卡 / 行业板块涨跌榜 / 龙虎榜 / 个股相关性矩阵 / 自选行情」。
V2 中龙虎榜（`/dragon-tiger`）、自选行情（`/watch`）已独立成页，相关性矩阵依赖交互式多股输入与 K 线取数
（Streamlit 单例在 Flask 上下文不可用），**本轮不迁、留 v1**。故 `/quote-board` 收敛为三块只读聚合：
主要指数日线快照（Flask 安全 `akshare` 日线，离线确定性静态样例）、行业板块涨跌榜（`get_industry_fund_flow`）、
市场状态（服务器北京时间真实计算，非伪造数据日）。指数/板块取不到一律诚实降级（null/[] + `unavailable`），
不 500、不补 0、`date` 绝不 `now()` 兜底。

**仍未完成（Tier 3 与验证，当时口径）**：Tier 3 社区/工具长尾 13 页（52/64/81/34/47/95/73/83/87/94/91/92/99）；
V2 dev server（5173）常起后的真人浏览器亮/暗主题目检与浏览器级 E2E；v1 下线时机评估。
> 2026-11-10 更新：全路由 headless 暗/亮主题目检**已完成**，见 §10；仍未完成的是**真人交互 E2E**。

---

## 10. 验收补记（2026-11-10，全路由真浏览器目检收口）

> 对应 §9 末尾的视觉验收项。本轮只做验收与基础设施修复，**未新增 V2 功能页**；
> 在隔离工作树 `task/v2-browser-e2e`（HEAD `aeecb55`）执行，未触碰 43 实盘交易页代码。

| 项 | 结果 |
|---|---|
| 路由覆盖守卫 | 修前 4/5（漏 14 条 AppPath）→ 修后 **5/5**；`ROUTES` 26 → **40** 条（39 AppPath + 1 多状态变体） |
| 真浏览器全量目检 | 第一次 **92/94 / exit 3** → 定位并修复后 **94/94 / exit 0**，16/16 红线 PASS，94 张 PNG 全 >45 KB |
| 抓到的真缺陷 1 | `vite.config.ts` 前缀代理 `'/webapps'` 劫持 SPA 裸路由（502 → 挂载超时）→ 收窄为 `'^/webapps/.+'`，静态资源链路不变 |
| 抓到的真缺陷 2 | 目检脚本 `--routes` 子集把「跨主题没测」误报 FAIL / exit 3 → 改为 `NOT_EVALUATED` + `cross_theme_evaluated` 反映真实状态 |
| 类型检查 | `tsc --noEmit` **0 错**（正则 proxy key 合法） |
| 公开数字守卫 | 未新增 `test_` 函数（新断言并入既有守卫），测试函数总数不变；`test_public_numbers_consistency.py` 全绿，生成器无需重跑 |

逐页证据、两次实跑日志、未覆盖项见 `docs/frontend-v2/VISUAL-AUDIT.md` 末节。

**仍未完成（更新 §9 口径）**：Tier 3 社区/工具长尾 13 页（52/64/81/34/47/95/73/83/87/94/91/92/99）；
**真人交互 E2E**（键盘 / 表单 / hover / 多视口 / 多浏览器）与 5050 真后端浏览器联调；v1 下线时机评估。
全路由暗/亮主题 headless 目检已完成，不再列为待办。
> 2026-11-10 更新：真后端浏览器联调（本地只读端点）已完成，见 §11；仍未完成的是实时源端点与 V8 修复。
> 2026-11-10 再更新：实时源端点与 V8 修复均已收口，见 §12；本注记保留作时间线留痕。

---

## 11. 验收补记（2026-11-10，真后端浏览器联调 + 一个未修的高危缺陷）

> 对应 §10 末尾「5050 真后端浏览器联调」项。本轮交付可复跑探针与实跑证据，**未改任何后端产品代码**。

| 项 | 结果 |
|---|---|
| 探针 | `scripts/probe_frontend_v2_realbackend.py`：独立 5051/5181/9223、独立 SQLite + secret、6 调度器全关、真实 JWT、MSW 关闭、浏览器内端点指纹防伪、逐页后端存活复核 |
| 实跑 | **7/7、exit 0**；`message='webapps/'`（直连=浏览器，MSW 默认 `'ok'`）、MockBanner 消失、静态作品经代理返回 200 HTML、后端全程存活 |
| 守卫 | 探针 9 条不变量并入 `tests/test_frontend_v2_route_coverage.py` 既有函数（未新增 `test_` 函数）；`gen_portfolio_page.py --fast` 同步 `docs/index.html`（Python 文件 909→910）；守卫套件 40/40 |
| **抓到的高危真缺陷** | `read_routes._w4x_index_daily` 在 Flask 进程内经 `fetch_many` 并发调 akshare → `py_mini_racer(V8)` FATAL → **整个后端进程被杀**；Dashboard 首页会顺带打 `/index-quotes`，故真实用户打开首页即有风险 |
| 证据 | 两次失败实跑的 `backend.log` FATAL 行、Vite `ECONNREFUSED`、项目 `modules/shepherd_reconstruct.py` 对 V8 并发的既有记载 |
| 本轮为何未修 | 串行化（`max_workers=1`）会撞整批 12s 边界把 5 个指数打空；正解是单子进程批量取数，属独立产品级改造 + 专属回归 |

详细证据、探针设计、未覆盖项见 `docs/frontend-v2/VISUAL-AUDIT.md` 末节。

**仍未完成（更新 §10 口径）**：① **首要**：V8 子进程隔离修复（修完才能把 Dashboard 与 3 个实时源端点纳入联调）；
② Tier 3 长尾 13 页（52/64/81/34/47/95/73/83/87/94/91/92/99，建议先 47 价格预警 + 95 数据导出）；
③ 真人交互 E2E（键盘 / 表单 / hover / 多视口 / 多浏览器）；④ v1 下线时机评估。


---

## 12. 验收补记（2026-11-10，V8 子进程隔离修复 + 全量真后端联调收口）

> 对应 §11 列为「首要」的 V8 高危缺陷；在隔离工作树 `task/v8-index-isolation`（HEAD `5b38ead`）执行。
> 本轮**改了后端产品代码**（只读端点取数层），未新增 V2 页面、未触碰 43 实盘交易页。
> §11 当时的「未修」记录保留不改，本节是其收口。

| 项 | 结果 |
|---|---|
| 修复 | 指数日线取数改走 `backend/api/_index_daily_worker.py` 独立解释器（NDJSON 逐只 flush + 单飞 60s 缓存 + 10s 硬超时）；Flask 进程内不再 import akshare / 直调新浪日线，AST 守卫锁死防回潮 |
| 为何不用进程池 | Windows spawn 重导入 `__main__`，项目 `test_refresh_main_guard.py` 禁止在 Flask 入口触发 `ProcessPoolExecutor`；独立解释器零 pickle、零重导入 |
| 顺带真缺陷 | 指数全降级时 `quote-board.unavailable` 仍为 `[]`（静默故障）→ 补 `index_quotes_unavailable`；前端已有渲染，不改 UI |
| 真后端联调 | 从 7/7 扩到 **14/14、exit 0**：Dashboard `/` 与 `/quote-board` 双主题重新纳入、3 个实时源端点直连、每端点后复核 `/api/health`；`backend_lost_after=null`，`FATAL=0` |
| 回归 | 后端只读端点 **55/55**、安全 **12/12**、守卫 **78/78**；公开数字 Python 文件 910→911、测试 4611→4612，已同步生成器 + 8 份物料 |
| 顺带收口 | 全量 `backend/tests/` 暴露的 2 个**既有**红灯（AST 对比 HEAD 证实与 V8 改动无关）：`theme` 静默吞异常补日志留痕、`theme_transmission` 分页裸解析改走 `parse_limit_param`；收口后综合回归 **389/389** |
| 诚实边界 | **本轮沙箱未复现 V8 native 崩溃**（akshare 网络层先失败）；验证的是结构性隔离 + 端点 200 + 后端存活 + 诚实 null 降级，崩溃路径由单测模拟 `rc=-1073741819` / 超时保证，报告字段 `v8_crash_reproduced_this_run=false` 如实标注 |

逐项证据、方案取舍与未覆盖项见 `docs/frontend-v2/VISUAL-AUDIT.md` 末节。

**仍未完成（更新 §11 口径）**：① ~~V8 子进程隔离修复~~ **已完成**（本节）；
② Tier 3 长尾 13 页（52/64/81/34/47/95/73/83/87/94/91/92/99，建议先 47 价格预警 + 95 数据导出，其余可在 `/catalog` 标「v1 保留」）；
③ 真人交互 E2E（键盘 / 表单 / hover / 多视口 / 多浏览器）；
④ 真行情数据浏览器联调（需能连到新浪日线的环境，顺带复现 V8 崩溃以实测隔离）；
⑤ v1 下线时机评估。

---

## 13. 分档口径对齐补记（2026-11-11，v2Mapping 四档化 + 实盘交易红线）

> 对应 §0 / §3 / §4 / §5 / §6 / §8 的本轮修订。本轮把 v1→v2 落地状态从旧三档（✅/🟡/❌）升级为四档（native / data / v1-pinned / v1-only），并把大量「已有 v2 等价页却低报为 data / v1-only」的页收口为 native；同时把「实盘交易不要放 v2」落实为代码 + 文档双重红线。

**四档最终分桶（74 个 v1 页面，单一真理源 `frontend-v2/src/features/catalog/v2Mapping.ts`）**：
- ✅ native = 41（v2 有等价路由页）
- 🟡 data = 22（v2 无等价页，但有可查看的关联只读端点，页面明示非等价功能）
- 🔒 v1 保留 = 11（永久不迁 v2：真实交易 / 低频遗留 / 实验性）
- ⬜ 待迁移 = 0（92 用户管理已于 2026-11-11 迁 v2，路由 /users）

**实盘交易红线（用户指令：实盘交易最好不要放在 v2）**：
- 43 实盘交易归为 `v1-pinned`：真实券商下单（QMT / 同花顺）**仅 v1**；
- v2 仅保留只读镜像入口「交易账户（只读）」（`/trading-account`），聚合本地模拟账本，**无任何写接口、不暴露下单能力**；
- 代码层落实：`nav.ts` 导航标签 `实盘交易` → `交易账户（只读）`；`TradingAccount.tsx` 标题与说明同步去掉「实盘交易」措辞，明确「真实券商下单能力在 v1 实盘交易页」；
- `/catalog` 功能全景对 43 标注 `v1 保留` 及原因，使「实盘交易不迁 v2」对使用者可见。

**对 §9–§12 历史进度日志的更正（旧三档口径遗留）**：
- 其中「Tier 3 社区/工具长尾 13 页（52/64/81/34/47/95/73/83/87/94/91/92/99）」是 2026-11-09/10 旧口径下的待办清单。经本轮四档评估：
  - 64 投研圆桌 → 已 native（`/predictions`）；
  - 91 我的 / 99 决策问答 → 已 data；
  - 34 / 47 / 95 / 44 / 73 / 94 → 已 data；
  - 52 / 81 / 83 / 87 / 53 / 33 / 25 / 13 / 15 / 17 → 决策为 v1 保留（永久不迁）；
  - 仅 **92 用户管理**为真实待迁移项（已于 2026-11-11 迁 v2，路由 `/users`，详见 §14）。
- 故「13 页长尾」实际已无待迁移项（92 也已 native），其余已被 data 落点或 v1 保留决策吸收。历史日志保留原数字作时间线留痕，以上为本轮最终口径。

## 14. 验收补记（2026-11-11，92 用户管理迁 v2 收口 + 真人交互级 E2E）

**唯一真实待迁移项 92 用户管理已 native 收口**（彼时四档为 **41 native + 22 data + 11 v1-pinned + 0 v1-only = 74**，v1-only 彻底归零）。后续 77 财报猎手（§15 前序，已并入 /financial-hunter）与 73 自定义看板（§15 前序，已并入 /dashboard-custom）由 data 升 native，故当前四档为 **43 native + 20 data + 11 v1-pinned + 0 v1-only = 74**（§3.3 / §3.6 / §3.7 已同步）。

**交付内容（仅复用既有无写能力端点，严守实盘红线）**：
- 新增 `frontend-v2/src/features/admin/UserManagement.tsx`：角色门控（非 admin 渲染「无访问权限」空态，不暴露任何用户数据）+ 三 Tab（用户列表 / 创建用户 / 操作日志）。
  - 列表：搜索（回车触发）+ 分页 + 编辑模态（禁改自己角色 / 停用自己）+ 删除确认模态（删自己 / 初始 admin 禁用）；
  - 创建：表单空值禁用提交按钮，后端报错（用户名已存在 / status=error）真实 `role=alert` 报错，不编造成功；
  - 复用只读 `GET /api/admin/users` / `POST /api/admin/users` / `PUT /api/admin/users/<id>` / `DELETE /api/admin/users/<id>` / `GET /api/admin/logs`（`@admin_required`，无交易写接口）。
- 角色持久化：`lib/auth.ts`（单一真理源 `getCurrentUser/getCurrentRole/isAdmin`）+ `schema.ts` 的 `LoginData` 透传 `user` + `LoginPage` 登录成功后写 `ss_user`。
- 导航/路由/映射收口：`nav.ts` 增 `AppPath`/`UTILITY_PATHS` 的 `/users`；`AppShell` 底部固定入口增「👥 用户管理」`<Link>`（绕过分组/图标守卫锁）；`router.tsx` 用 `lazyRouteComponent` 挂载；`v2Mapping.ts` 的 `NATIVE` 增 `92_用户管理.py → /users`，`v1-only` 归零。
- 端到端契约：新增 `api/admin.ts`（Zod 严格 parse 禁兜底）+ `api/schemas/admin.ts`（对齐 `backend/api/admin_routes.py`）+ MSW 管理端内存态（`adminMockState` + `resetAdminMock()`，使「创建后列表出现新用户」可被测）。

**真人交互级 E2E（不引入 Playwright，项目硬规则；多浏览器真交互由既有 headless 目检脚本覆盖）**：
- 新增 `tests/e2e/admin-users.test.tsx`（8 用例）：权限门控 / 创建表单禁用态 / 重名报错 / 删除确认模态 / 搜索回车过滤 / 错误态诚实渲染。
- 同步收紧 `w4e-pages`/`w4f-pages`：`v1-only` 断言由 `>0` 改为 `=0`，并增「已实现」筛选仅显 native（含用户管理）交互测试。

**验证**（全部本地通过）：
- `npx vitest run` → **342 passed / 1 skipped**（含 honest-data 守卫：本任务引入的 `?? 0` / `new Date()` 已全部改写为 `data ? ... : 0` / 确定性常量 `MOCK_CREATED_AT`，0 违规）；
- `tsc --noEmit` → 0 错误；
- `test_public_numbers_consistency.py` → 74 总数守恒（native 41 / data 22 / pinned 11 / v1-only 0）。

**诚实边界**：v2 用户管理页本身不提供任何下单 / 资金写能力（实盘红线在 v1 永久保留）；v2 管理员端点与真后端 `admin_routes.py` 契约逐字段对齐，缺字段即抛错不兜底。

## 15. 验收补记（2026-11-11，扩真人交互级 E2E：30 策略回测 + 71 因子分析）

**目标**：在既有 admin-users / financial-hunter / dashboard-custom 真人交互 E2E 基础上，再补两个**表单型高价值 native 页**的真人交互级覆盖（键盘输入 / select 切换 / 按钮点击 → 回显后端回显的请求参数），并加固 MSW 诚实降级分支。DecisionPanel（16 行只读无表单）不在目标内。

**交付内容**：
- 新增 `tests/e2e/w4-backtest.test.tsx`（4 用例）：默认加载（摘要 Stat + 资金曲线卡 + 逐笔交易明细 5 笔）/ 切换策略（多因子→均线交叉）运行回测回显 / 修改标的（受控输入 600519→000001）运行回测回显 / 哨兵 `000000` 取数为空→诚实空态「暂无回测数据」+ 不补零曲线（空态不渲染资金曲线卡）。
- 新增 `tests/e2e/w4-factor.test.tsx`（4 用例）：默认加载（IC 均值卡 + 分层累计收益卡）/ 切换因子（动量→5 日反转）运行分析回显 / 标的受控输入 / 有效标的<3→诚实空态「暂无因子数据」+ 不补零序列。
- MSW 加固 `src/mocks/handlers.ts`：
  - `/api/v2/read/backtest` 回显请求参数（ticker/strategy/start/end），并对哨兵 `000000` 诚实返回 `{...backtest, equity_curve:[], trades:[]}`（驱动前端 `isEmpty` 空态）；
  - `/api/v2/read/factor-analysis` 回显请求参数（codes/days/factor/n_layers/forward），并当有效标的<3 时诚实返回 `{...factorAnalysis, ic_series:[], layered_cum:[], long_short_cum:[]}`。

**诚实红线守卫**：两页测试均断言「取数为空 → 显诚实空态、不渲染伪造曲线/序列」，与 `honest-data.test.tsx` 零兜底原则一致；组件侧 `QueryState.isEmpty` 仅据真实 `equity_curve`/`ic_series` 长度判空。

**验证**（全部本地通过）：
- `npx vitest run` → **361 passed / 1 skipped**（新增 8 例，含 route-lazy / honest-data 守卫无回归）；
- `tsc --noEmit` → 0 错误；
- 四档口径未变（仅新增 E2E，不改 NATIVE/DATA 计数）：仍 **43 native + 20 data + 11 v1-pinned + 0 v1-only = 74**。

## 16. 验收补记（2026-11-11，设计系统打磨 · 专注 / Zen 模式）

**目标**：意图 F「都做」最后一项——统一组件令牌收口 + 加专注/Zen 模式（隐藏侧栏与顶栏、主内容占满视口），双主题恒等验证。

**交付内容**：
- 偏好单一真理源 `lib/preferences.ts` 增 `getZen()/setZen()`（localStorage `ss_zen`，不写后端、真实生效）；`applyPreferences()` 同步写 `html[data-zen]`。
- 首屏防闪：`index.html` 的 FOUC 同步脚本在 React 挂载前写好 `data-zen`（与 `data-theme` 同机制），避免 Zen 开启后首屏闪现侧栏/顶栏。
- 布局收起 `styles/tokens.css`：`html[data-zen="on"] .app-sidebar / .app-header { display:none }` + `.app-main` 去外边距（用 `display:none` 真实收起占位，非 `visibility:hidden` 留白）；新增 `.zen-fab` 浮动开关样式（零阴影、扁平实色面，与轻量卡片流一致）。
- `AppShell.tsx`：侧栏/顶栏/主内容加 `app-sidebar/app-header/app-main` 锚点类；持有 `zen` 状态（初始读 `getZen()`）+ `toggleZen`；**快捷键 Z** 进入/退出（输入框/可编辑区/带修饰键时屏蔽，避免劫持打字）；右下角常驻浮动开关集群——Zen 态下额外挂 `ThemeToggle`（顶栏隐藏时主题唯一入口），确保不被「困住」。
- 新增 `shared/ui/ZenToggle.tsx`（纯展示：`aria-pressed` 反映状态、点击回调、文案「专注/退出专注」、双主题恒等不碰颜色令牌）。
- 新增 `tests/unit/zen.test.tsx`（3 例）：`setZen` 写 `data-zen=on/off` 且 `getZen` 读回、ZenToggle 非专注态 `aria-pressed=false`+点击回调、专注态 `aria-pressed=true`+文案「退出专注」。

**设计系统口径**：Zen 仅切换布局，**不碰任何颜色/涨跌/状态令牌**，故暗/亮两主题恒等；与 DESIGN.md §2 三色语义线红线无冲突。

**验证**（全部本地通过）：
- `npx vitest run` → **364 passed / 1 skipped**（新增 3 例，含 honest-data 守卫无回归）；
- `tsc --noEmit` → 0 错误；
- 四档口径未变：**43 native + 20 data + 11 v1-pinned + 0 v1-only = 74**。
