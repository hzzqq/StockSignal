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
| V2 是否实现「全部」V1 提炼功能 | ❌ **否**，但覆盖率已大幅提升 | 74 个 V1 页面：✅63 已在 V2 有等价页（含 9 页 catalog 收口 + 16/91/99 三页真页面见 §19 + 65/67/68/69 四页离线广度统计真页面见 §20 + 50/62/70 三页实时/离线真页面见 §21）、🔒11 v1 保留（永久不迁，如实盘交易）、🟡0 仅关联只读数据、⬜0 待迁移 |
| V2 当前是否真能跑 | ✅ 是 | `tsc` exit 0；`vitest` 388 passed / 1 skipped；50 条 `AppPath` 全注册（截图脚本 `ROUTES` 51 条含深链变体，覆盖守卫 5/5） |
| 文档漂移 | ⚠️ `nav.manifest.json` 是过期 w0 死文件 | 未被任何代码 import，且其引用的 `IA-MIGRATION.md` 根本不存在 |

**核心判断**：V2 技术栈正确、质量高、已实现 v1 的**决策/广度·温度/个股研究/量化信号/连板/告警/晨报/模拟交易/六维评分/行情看板/资金流向/龙虎榜/持仓中心/市场全景/状态机/题材/强势榜/用户管理/财报猎手/自定义看板**等核心分析闭环。按四档诚实口径（详见 §3 / §4，单一真理源 `frontend-v2/src/features/catalog/v2Mapping.ts`）：**60 个 native（v2 有等价页，含 §20 四页离线广度统计）+ 3 个 data（v2 仅关联只读数据：50/62/70）+ 11 个 v1 保留（永久不迁，如实盘交易）+ 0 个待迁移（92 用户管理 / 77 财报猎手 / 73 自定义看板 / 95 数据导出已于 2026-11-11 迁 v2，路由 /users、/financial-hunter、/dashboard-custom、/export；另 63 温度回测 / 31·32 选股 / 34 体检 / 44·47·94 告警 / 60 事件 / 98 仓位落地等 9 页 2026-11-11 catalog 收口由 data 升 native，不新建页）**；v1 短期内**不能整体下线**（尤其 43 实盘交易等真实券商下单能力永久留 v1），只能作为只读兜底并存。

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

### 3.2 市场广度·温度（15 ✅ native + 0 🟡 data + 3 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 市场强弱 | 13 | 🔒 | v1 保留：与广度·温度簇高度重叠且依赖 v1 实时行情单例 |
| 市场驱动力 | 15 | 🔒 | v1 保留：实验性视图，v2 暂无等价计划 |
| 市场魔方 | 17 | 🔒 | v1 保留：展示性视图，v2 不做等价实现 |
| 市场情绪 | 50 | ✅ | `/market-sentiment`（实时情绪温度计，21 指标分 5 维 + 综合温度圆；端点 `/api/v2/read/market-sentiment`，单源失败优雅降级 + SQLite 缓存兜底，见 §21） |
| 市场温度计 | 59 | ✅ | `/breadth`（主卡） |
| 广度分化 | 61 | ✅ | `/breadth`（广度总览视图） |
| 动量广度共振 | 62 | ✅ | `/momentum-resonance`（纯离线共振矩阵 + 5×5 共振热力 + 轨迹，端点 `/api/v2/read/momentum-breadth`，见 §21） |
| 温度回测 | 63 | ✅ | `/backtest`（回测运行记录，2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 温度持续期与回归时长 | 69 | 🟡 | data：`/api/v2/read/breadth-history` |
| 市场状态机 | 56 | ✅ | `/regime` |
| 市场全景 | 57 | ✅ | `/panorama` |
| 事件对比分析 | 60 | ✅ | `/events`（事件因子池只读展示，2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 涨停复盘 | 70 | ✅ | `/limit-up-review`（实时涨停池复盘：涨停池/连板梯队/断层检测/市场上下文，端点 `/api/v2/read/limit-up-review` 东财涨停池 10 分钟缓存，见 §21） |
| 投机情绪周期时钟 | 65 | 🟡 | data：`/api/v2/read/breadth-timeseries` |
| 历史相似日聚类前向分布 | 67 | 🟡 | data：`/api/v2/read/breadth-history` |
| 情绪拐点扫描器 | 68 | 🟡 | data：`/api/v2/read/breadth-timeseries` |
| 财报日历 | 16 | ✅ | native：`/earnings-calendar`（§19 新建真页面，真实 akshare 披露日历只读端点） |
| 财报猎手 | 77 | ✅ | native：`/financial-hunter`（2026-11-11 迁移：逐股票三表 income/balance/cash 切换深挖，复用只读 `/api/v2/read/financials`；诚实红线——null 数值显「—」、date 为 null 显「暂无权威数据日」、note 为 null 显原文缺失说明，非跨股筛选器不伪造；含真人交互级 E2E 6 例） |

### 3.3 个股研究（✅ 全覆盖）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 个股分析 | 20 | ✅(并入24) | 被 `/stock/research` 的「深度分析」子视图吸收 |
| 个股研究 | 24 | ✅ | `/stock/research` |
| 多股对比 | 21 | ✅ | `/stock/compare` |
| 基本面分析 | 22 | ✅ | `/stock/fundamentals` |
| 六维评分 | 72 | ✅ | `/stock/six-dim` |

### 3.4 量化选股（6 ✅ native + 0 🟡 data + 2 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 每日荐股 | 36 | ✅ | `/recommend` |
| P1 量化信号 | 55 | ✅ | `/p1` |
| QuantAgent投研 | 25 | 🔒 | v1 保留：实验性 Agent 流程，留 v1 观察 |
| 策略回测 | 30 | ✅ | `/backtest` |
| 形态选股 | 31 | ✅ | `/recommend`（2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 智能选股 | 32 | ✅ | `/recommend`（同上） |
| ETF筛选 | 33 | 🔒 | v1 保留：小众筛选器，v2 暂无等价计划 |
| 因子分析 | 71 | ✅ | `/factor` |

### 3.5 持仓交易（6 ✅ native + 0 🟡 data + 1 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 自选股监控 | 46 | ✅ | `/watch`（v2 由自选股监控承接） |
| 仓位管理 | 40 | ✅ | `/portfolio` |
| 组合收益 | 41 | ✅ | `/portfolio` |
| 持仓中心 | 45 | ✅ | `/portfolio` |
| 实盘交易 | 43 | 🔒 | v1 保留：真实券商下单（QMT/同花顺）仅 v1；v2 仅有只读账户概览「交易账户（只读）」入口，不提供任何交易能力 |
| 模拟交易 | 42 | ✅ | `/paper` |
| 仓位落地 | 98 | ✅ | `/decision`（今日决策快照，2026-11-11 catalog 收口由 data 升 native，不新建页） |

### 3.6 工具与社区（10 ✅ native + 0 🟡 data + 5 🔒 pinned）
| V1 页面 | 编号 | V2 状态 | 备注 |
|---|---|---|---|
| 体检扫描 | 34 | ✅ | `/stock/six-dim`（六维评分，2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 价格预警 | 47 | ✅ | `/alerts`（告警规则只读展示，无设置能力，2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 数据导出 | 95 | ✅ | native：`/export`（2026-11-11 迁移：浏览归档快照 data/snapshots/*.json 并导出原始 JSON，纯前端只读，复用 useSnapshotDates/useSnapshot + SnapshotView 富视图；诚实红线——缺日显「该日期无归档快照」不回退今日快照） |
| 智能条件单 | 44 | ✅ | `/alerts`（告警规则只读展示，无设置能力，2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 网页作品集 | 86 | ✅ | `/webapps` |
| 自定义看板 | 73 | ✅ | native：`/dashboard-custom`（2026-11-11 迁移：勾选组件 + localStorage 持久化，聚合 5 个真实只读端点——今日决策快照/每日荐股/广度温度时序/事件因子池/回测运行记录；诚实渲染，缺失字段显「—」、回测收益为负如实红绿，不编造列表） |
| 告警引擎 | 74 | ✅ | `/alerts` |
| 数据时效性看板 | 82 | ✅ | `/ops`（数据与运维状态） |
| 自然语言选股 | 81 | 🔒 | v1 保留：实验性 NL 选股，v2 暂无等价计划 |
| 星辰 AI | 53 | 🔒 | v1 保留：独立 AI 对话，已在独立项目 `xingchen-ai` 实现 |
| 股吧 | 52 | 🔒 | v1 保留：社区抓取，低频遗留 |
| 消息中心 | 94 | ✅ | `/alerts`（告警日志只读展示，2026-11-11 catalog 收口由 data 升 native，不新建页） |
| 投研圆桌 | 64 | ✅ | `/predictions`（预测校准日志） |
| 分析规则库 | 83 | 🔒 | v1 保留：规则维护工具 |
| 语音事件 | 87 | 🔒 | v1 保留：语音采集低频功能 |

### 3.7 决策 / 工具入口 / 管理（12 ✅ native + 0 🟡 data）
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
| 我的 | 91 | ✅ | native：`/me`（§19 新建真页面：登录身份 + 自定义看板偏好，只读） |
| 用户管理 | 92 | ✅ | native：`/users`（2026-11-11 迁移：角色门控 + 用户列表/创建/操作日志三 Tab，复用只读 `/api/admin/*` 端点） |
| 决策问答 | 99 | ✅ | native：`/review-notes`（§19 新建真页面：逐日复盘笔记，本地无 .md 时诚实空态，不编造） |

### 3.8 V2 原生页（无 V1 等价，属新增能力）
`/predictions`(预测校准日志)、`/ops`(数据与运维状态)、`/diagnostics`(数据源与接口检测)、`/catalog`(v1 功能全景/目录)、`/data`(只读端点浏览器)。

---

## 4. 覆盖率统计

> 口径对齐 `frontend-v2/src/features/catalog/v2Mapping.ts`（单一真理源）；数量由真实清单实时统计，非写死。
> 旧版「✅21 / 🟡8 / ❌45」为 2026-11-09 基线快照，已被本轮漂移收口（大量已有 v2 等价页却低报的页升级为 native）取代。

| 类别 | 数量 | 占比 |
|---|---|---|
| ✅ native（v2 有等价路由页） | 63 | ~85% |
| 🟡 data（v2 无等价页，但有可查看的关联只读端点，非等价功能） | 0 | 0% |
| 🔒 v1 保留（永久不迁 v2） | 11 | ~15% |
| ⬜ 待迁移（v2 尚未迁移、但计划迁移） | 0 | 0% |
| V2 原生（无 v1 等价，属新增能力，不计入 74） | 5 | — |

**诚实结论**：按四档口径，V2 已对 74 个 v1 页面中的 **63 个给出等价路由页（native）**、**0 个仅提供关联只读数据端点（data）**、**11 个明确永久留 v1（v1 保留，含 43 实盘交易等真实下单能力）**、**0 个待迁移**（92 用户管理 / 77 财报猎手 / 73 自定义看板 / 95 数据导出已于 2026-11-11 迁 v2，路由 `/users`、`/financial-hunter`、`/dashboard-custom`、`/export`；另 63 温度回测 / 31·32 选股 / 34 体检 / 44·47·94 告警 / 60 事件 / 98 仓位落地等 9 页 2026-11-11 catalog 收口由 data 升 native，不新建页；50/62/70 三页 2026-11-11 末由 data 升 native 真页面，见 §21）。「约 45 个页面无任何 v2 支撑」的旧判断已不成立——实际彻底无 v2 支撑的仅 11 个，且已全部主动决策永久留 v1（含真实券商下单）。v1 短期内**不能整体退役**（尤其真实交易/低频遗留/实验性页面永久留 v1），只能作为只读兜底并存。

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
- [x] 已有等价/数据落点：投研圆桌 `64`（→ `/predictions` native）、我的 `91` → `/me` native、决策问答 `99` → `/review-notes` native、财报日历 `16` → `/earnings-calendar` native（均 §19 新建真页面）；体检扫描 `34` → `/stock/six-dim` native、价格预警 `47` / 智能条件单 `44` / 消息中心 `94` → `/alerts` native（告警规则/日志只读展示，无设置能力）、自定义看板 `73` → `/dashboard-custom` native、数据导出 `95` → `/export` native；34/44/47/94/73/95 均已于 2026-11-11 由 data 升 native（含 catalog 收口），不新建页
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
  - 34 / 47 / 44 / 94 → 已 data；73 / 95 → 已 native（95 由 data 升 native 见 §17）；
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

---

## 17. 验收补记（2026-11-11 晚，95 数据导出由 data 升 native 收口）

> 对应 §3.6 / §4 / §6 的本轮修订，以及 §13 末尾「95 仍 data」的更正。本轮把高价值 data 页 **95 数据导出** 做成真正 v2 交互页 `/export`，逼近「v2 可替代 v1」判定线。

### 选型决策（诚实口径）
- 摸底后判定：`47/44/94`（告警）已被 native `/alerts` 只读展示（能看不能设，仍属 data，不强行建重复页也不谎报 native）；`34 体检扫描` 已被 `/stock/six-dim` 覆盖（属误留 data，应归 native 但不新建）；`99 决策问答` 被 `/morning` 覆盖且本地 0 个 .md；`95 数据导出` 本地 `data/snapshots/` 有 33 个真实 JSON、无 native 重叠、是只读设计内能做的**唯一直立高价值页** → 选它升 native。

### 交付内容
- `frontend-v2/src/features/export/DataExport.tsx`（新建）：浏览归档快照（date 下拉来自 `useSnapshotDates` 只读端点）+ 选中后复用 `SnapshotView` 富视图 + 纯前端「导出 JSON」（`Blob`+`URL.createObjectURL`，环境无下载能力时 `typeof` 守卫 + try/catch 安全降级）。**诚实红线**：缺日显「该日期无归档快照」（后端 notFound 信封 `status!=ok` → `apiFetch` 抛 `ApiError` → `isError`，不回退今日快照冒充）。
- 接线：`router.tsx` 增 `LazyDataExport` 路由 `/export`；`nav.ts` 的 `AppPath` 联合类型 + `UTILITY_PATHS` 增 `/export`；`AppShell.tsx` 底部固定入口增「📤 数据导出」`<Link>`（绕过分组/图标守卫锁）；`v2Mapping.ts` 的 `NATIVE` 增 `95_数据导出.py → /export`，并从 `DATA` 删除该行。
- 同步 `scripts/shoot_frontend_v2.py` 的 `ROUTES` 元组增 `("/export","export")`（42→43），注释同步。

### 测试
- 新建 `frontend-v2/tests/e2e/w4-export.test.tsx`（4 例）：① 默认渲染标题 + 日期下拉（只读端点）；② 选「有归档」日期 → 快照富视图 + 导出按钮；③ 选「无归档」日期 → 诚实空态、不回退今日快照；④ 点击「导出 JSON」安全降级不崩溃。
- **踩坑与修正**（已写进测试，避免复发）：
  1. 早期 `findByRole('combobox')` 对原生 `<select>` 角色解析不稳 → 改用 `getByDisplayValue('— 请选择 —')` 取 select。
  2. `vi.stubGlobal('URL', {...URL, ...})` 替换**整个** `URL` 全局 → 剥掉构造器/静态方法，MSW 的 `fetch` 拦截（依赖 `new URL`）静默失效 → 快照 query 永不返回、下拉 option 不出现。**改法：只做方法级 stub**（`Object.defineProperty(URL,'createObjectURL'/'revokeObjectURL')`），保留 `URL` 构造器。
  3. `fireEvent.change` 紧跟 `getByDisplayValue` 在 `render()` 后**立即**调用 → act 时序抖动导致 query 不触发/button 不出现。**改法：先 `await findByText('2026-09-21')`（option 出现 = 日期清单 query 已落定）再 fireEvent**，对齐 `w4-dashboard` 的 settle-first 范式。
  4. ECharts 在 jsdom 无 canvas，`init/dispose` 抛错 → 与全站 E2E 约定一致，`vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))`。
  5. 锚点 `<a download>.click()` 在 jsdom 触发 "Not implemented: navigation" → `beforeEach` 中 `HTMLAnchorElement.prototype.click = () => {}`。

### 验证
- `npx vitest run` → **368 passed / 1 skipped**（新增 4 例，全量无回归）；
- `npx tsc --noEmit` → 0 错误；
- `pytest tests/test_frontend_v2_route_coverage.py` → 5/5（ROUTES 43 条对齐 AppPath）；
- `pytest tests/test_public_numbers_consistency.py` → 74 总数守恒（native 44 / data 19 / pinned 11 / v1-only 0）。
- 四档口径更新：**44 native + 19 data + 11 v1-pinned + 0 v1-only = 74**（§3.6 / §4 / §6 已同步）。
- 仅 stage `frontend-v2/` + `scripts/shoot_frontend_v2.py`；`backups/`、`thesis/`、`docs/welcome.html`、`artifacts/`、`.trae/` 不动。ks 父仓库 submodule 指针留痕不推。
- v1 弃用：仍按用户「等 v2 做好了再说」本次不碰。

---

## 18. 验收补记（2026-11-11 末，catalog 收口：9 页由 data 升 native，不新建页）

> 对应「继续推 v2 → 收口 catalog（推荐）」方向。本轮**只改目录口径，不新建任何 v2 页面**：把已被现有 native 路由**真实覆盖、却仍被误标为 data** 的 9 个 v1 页重新归为 native，使功能全景不再低估 v2 覆盖。单一真理源 `frontend-v2/src/features/catalog/v2Mapping.ts` 的两处编辑：① 从 `DATA` 字典移出 9 页，仅保留 10 个边界 data 页（广度·温度专项 50/62/65/67/68/69/70、财报日历 16、我的 91、决策问答 99）；② 在 `NATIVE` 字典新增 9 条映射。

### 收口清单（data → native，全部复用既有路由，不新建页）
| V1 页 | 编号 | 收口目标 | 说明 |
|---|---|---|---|
| 形态选股 | 31 | `/recommend` | 每日荐股结果只读展示 |
| 智能选股 | 32 | `/recommend` | 同上 |
| 体检扫描 | 34 | `/stock/six-dim` | 六维评分，非新建页 |
| 智能条件单 | 44 | `/alerts` | 告警规则只读展示，无设置能力（符合 v2 只读红线） |
| 价格预警 | 47 | `/alerts` | 同上 |
| 事件对比分析 | 60 | `/events` | 事件因子池只读展示 |
| 温度回测 | 63 | `/backtest` | 回测运行记录，非新建页 |
| 消息中心 | 94 | `/alerts` | 告警日志只读展示 |
| 仓位落地 | 98 | `/decision` | 今日决策快照 |

### 边界保留 data（不夸等价，v2 确无完整页面）
- **广度·温度专项**（50/62/65/67/68/69/70）：v2 `/breadth` 是整合概览，非这些逐页专项分析 → 保留 data（只查只读端点，不谎称等价功能）。
- **16 财报日历**：v2 `/financial-hunter` 是财报三表，非日历视图 → 保留 data。
- **91 我的 / 99 决策问答**：v2 无独立 native 路由（user-dashboard / review-notes 为只读端点）→ 保留 data。

### 验证（全部本地通过）
- `npx tsc --noEmit` → 0 错误（纯目录改动，无类型影响）。
- `npx vitest run` → **368 passed / 1 skipped**（与 §17 完全一致，**零回归**，纯 catalog 口径变更）。
- `pytest tests/test_public_numbers_consistency.py` → 74 总数守恒，四档 **53 native / 10 data / 11 v1-pinned / 0 v1-only**（§17 为 44/19/11/0，本次 +9 native / −9 data）。
- `pytest tests/test_frontend_v2_route_coverage.py` → 5/5（ROUTES 仍为 43，本次未新增路由）。
- 守卫前置核查：无测试断言四档拆分比例；9 个新 native 目标（`/recommend`、`/stock/six-dim`、`/alerts`、`/events`、`/backtest`、`/decision`）均为 `AppPath` 已注册路由，路由覆盖守卫只校验 `ROUTES` vs `AppPath`，不红。

### 四档口径（§18 当时；现已被 §19 的 56/7 取代）
**53 native + 10 data + 11 v1-pinned + 0 v1-only = 74**（总数守恒，§18 收口时的快照）。
- 仅 stage `frontend-v2/src/features/catalog/v2Mapping.ts` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`backups/`、`thesis/`、`docs/welcome.html`、`artifacts/`、`.trae/` 不动。ks 父仓库 submodule 指针留痕不推。
- v1 弃用：仍按用户「等 v2 做好了再说」本次不碰。


---

## 19. 补记（2026-11-11，3 个边界 data 页 → native 真页面 + 财报日历列契约漂移修复）

> 用户选择「收口边界 data 页→native」；v1 降级/退役评估按用户要求**挂起**，等 v2 做好再说。
> 四档由 §18 的 **53 / 10 / 11 / 0** 收口为 **56 native + 7 data + 11 v1-pinned + 0 v1-only = 74**（总数守恒）。

### 19.1 三页真实落地（非「仅改标签」）

| V1 页 | v2 路由 | 数据来源 | 诚实边界 |
|---|---|---|---|
| 16 财报日历 | `/earnings-calendar` | **新增**只读端点 `/api/v2/read/earnings-calendar`，包装 `modules.fundflow.get_disclosure_calendar`（真实 akshare 东方财富年报预约披露日历） | 数据源限流/未披露 → `unavailable=true` + 空 rows，前端显「暂时取不到」，不编造行；仅年报可得，季报/中报 best-effort 映射已在页面注明 |
| 91 我的 | `/me` | 既有 `/api/v2/read/user-dashboard`（真实 `data/user_dashboard.json`）+ `getCurrentUser()` | 无登录态显「请重新登录」，不编造角色；偏好缺失显「暂无默认组件」；纯只读无写能力 |
| 99 决策问答 | `/review-notes` | 既有 `/api/v2/read/review-notes`（`review_notes_<date>.md`） | 全仓**无任何** `review_notes_*.md` → 端点恒 `not_found` → 页面显「该日期暂无复盘笔记」，**不编造内容**；日后若生成文件会自动显示 |

接线全链路：`nav.ts`（AppPath + UTILITY_PATHS）、`router.tsx`（`lazyRouteComponent` + routeTree）、`AppShell.tsx`（底部固定入口，绕过 NAV 守卫）、`api/schemas/read.ts`、`api/read.ts`、`lib/queries.ts`、`mocks/handlers.ts`、`mocks/fixtures.ts`；`scripts/shoot_frontend_v2.py` 的 `ROUTES` 补 3 条（44→47，含 1 条 `/stock/compare?codes=` 深链变体；`AppPath` 46 条全部被覆盖）。

### 19.2 真缺陷：财报日历列契约漂移（本轮取证发现并修复）

**取证**（隔离库 Flask test_client + 真实 akshare，2026-11-11）：端点返回 5483 行，但 `date=None`；真实列名为
`股票代码 / 股票简称 / 首次预约 / 初次变更 / 二次变更 / 三次变更 / 实际披露`（ISO 日期串），
而 `modules/fundflow.get_disclosure_calendar` 的 docstring 与 v2 表格按 `报告期 / 披露时间 / 披露状态` 读取。
→ **接真后端时披露时间/状态/报告期三列全显「—」**；`v2Mapping` 旧注释「无等价日历页」也不实（fundflow 早有真实日历函数）。
MSW 夹具因使用「预约披露日期/披露日期」旧列名而全绿，**掩盖了漂移**。

**修复**（不动 v1 遗留模块，避免外溢到 5 个 v1 测试文件）：
- 后端端点边界新增纯函数 `_normalize_disclosure_rows(rows, period)`：确定性派生 `报告期`（=请求期，事实非补零）、
  `披露时间`（实际披露 > 首次预约 > 旧列名，截 YYYY-MM-DD）、`披露状态`（已披露 / 预约待披露 / None），
  **保留 akshare 原始列**、兼容旧列名；`date` 取「实际披露」最大值，取不到即 `None`。
- 前端 `pickDisclosure` 扩为 6 个候选列（含 `披露时间`/`实际披露`/`首次预约`），`pickStatus` 空值显「—」，
  `pickReportPeriod` 回落请求期；MSW 夹具改为**对齐真端点规整后的契约形态**。
- 复验：`date` `None → 2026-08-06`；5483 行 **100% 带齐 5 个契约列**；状态分布 `已披露 5482 / 预约待披露 1`（真实派生）。

### 19.3 守卫诚实化（两条阈值随口径调整，非放宽）

- `test_v1_pages_catalog.py::test_data_mapping_paths_are_real_read_endpoints`：data 条目由 10 降至 7、去重端点仅 2 个
  （breadth-timeseries / breadth-history），原 `>=12` 阈值改为 `条目>=5 且 去重端点>=2`，仍逐条校验端点真实注册。
- `test_required_query_data_deeplinks_are_usable`：16/99 升 native 后 catalog 不再持有需参端点深链；
  改为钉死**真正要防的跨文件契约**——数据浏览器经 diagnostics `sample_query` 自动填参（`schema`/`view` 4 处断言保留），
  并校验 catalog 若仍有需参深链则必须落在已注册端点。诚实理由：需参端点均已升 native，原生页自行处理 query，不再依赖 `/data` 深链。

### 19.4 验证（全绿）

| 项 | 结果 |
|---|---|
| `npx tsc --noEmit` | 0 错误 |
| `npx vitest run` | **378 passed / 1 skipped**（50 文件；§18 基线 368 + 本轮 10） |
| 新增 `tests/e2e/native-boundary.test.tsx` | 10 例：三页加载/空/错误三态 + **真实 akshare 列名**回归（锁死三列不全显「—」） |
| 新增 `tests/test_earnings_calendar_contract.py` | 4 例：真实列名规整 / 旧列名兼容 / 无日期不编造 / 空表安全 |
| `pytest` 5 个守卫文件 | 全绿（catalog / route-coverage / public-numbers / earnings-contract / diagnostics-contract） |
| `python -m backend.tests.test_security`（隔离库） | **12/12**，新端点带 `@jwt_required`，未登录 401 `missing_token` |
| 真端点联调（隔离库 test_client） | 鉴权 401 / 200 `ok` / 5483 行 / 契约列齐全 / `market=BAD` 回落沪深京 |
| 文档数字同步 | `gen_portfolio_page.py` 重跑（端点 136→137、测试 4612→4616、测试文件 499→500、顺带修正「0 个交易日」坏占位→4821）；README + promo×2 + publish-kit×4 同步 |

**四档最终口径**：**56 native + 7 data + 11 v1-pinned + 0 v1-only = 74**。剩余 7 个 data 页全为广度·温度专项
（50/62/65/67/68/69/70），v2 `/breadth` 是整合概览、非逐页专项，不夸等价。
v1 退役评估仍按用户要求挂起；43 实盘交易红线不碰。

---

## 20. 离线可靠广度统计四页升 native 真页面（2026-11-11，56/7/11/0 → 60/3/11/0）

> 对应「接着做 v2」。本轮把 §19 剩余 7 个 data 页中**纯 Python、零 Streamlit 依赖、共用同一真值口径**的
> 65/67/68/69 四页做成 v2 真页面；50/62/70 三页仍留 data（50 页 1218 行且依赖实时多指标、
> 62 依赖 `momentum_breadth_resonance` 实时取数、70 页 511 行复盘逻辑），**不硬凑换皮页、不夸等价**。

### 20.1 后端：一个聚合端点 + 一个按需端点

| 端点 | 内容 | 诚实约束 |
|---|---|---|
| `GET /api/v2/read/breadth-analytics?window=N` | 包装 4 个纯模块：`speculative_clock`（当前相位 + 归一化时序）、`similar_day_cluster`、`inflection_scanner`、`regime_duration` | `window` 白名单 60/120/250/750/2000，非法 **400 validation_error**（不静默兜底）；`data_as_of` 取 `breadth_features.data_as_of()` 权威数据日 **2026-08-21**，不是 `now()` |
| `GET /api/v2/read/breadth-zseries?dim=&window=` | 68 页单维度滚动 z-score 轨迹（独立按需取，不把全历史 4771 点塞进聚合包） | `dim` 必须是 `REAL_FEATURES` 白名单；截尾后 `dates/z/raw` 等长、`markers` 下标重映射并带 `truncated` 标记 |

- **逐段独立降级**：`_analytics_section(fn)` 对异常/非 dict/`available=False` 只让该段
  `available=False + reason`（异常类型与消息如实带出），其余段照常返回，**绝不整包 500、不补零、不编造统计**。
- **真值口径单一来源**：`modules.breadth_features.REAL_FEATURES` 6 个可靠字段（约 100% 非空），
  `OFFLINE_MISSING` 10 个离线缺真值维度逐条下发给前端披露，**绝不进入任何距离/分位/z-score 计算**。
- 隔离库真跑取证：`NO_TOKEN 401 missing_token`；四段 `ALL_AVAILABLE True`（相位中性 / 250 日时序 /
  15 个相似日 / 4 个拐点事件 / 5 个温度档）；`window=60/2000` 分别回 60/2000 点；
  `window=999/abc` → 400；`dim` 缺参/注入 → 400；`json.dumps(allow_nan=False)` 通过。

### 20.2 前端契约层：夹具由真端点 dump 生成（防 §19.2 漂移重演）

先隔离库 dump 真响应结构，再写 Zod/read/queries/MSW —— 实测后端键与 schema 完全一致：
`phase.current.reason`、`forward_stats` 键为字符串 `"5"/"10"/"20"`、`durations` 键为 `"0".."4"`、
`recovery` 为对象、`offline_missing` 为 10 项字典。MSW 夹具直接由真响应裁末 60 日生成（**真实数据子集，非编造演示数**），
handler 按 `window` 截尾并把 `window` 如实回显为**实际点数**，不假装拿到更长历史。

**诚实修正（v1 遗留缺陷）**：v1 67/69 页柱状图用 `.get(off, 0)` / `m if m is not None else 0`
把无样本窗口补成 0；v2 一律送 `null`（ECharts 不画该柱）并显式提示「无足够前向样本 / 不补 0」。
`show()` 把 `0` 当真实数值显示（`n=0` 是统计事实），只把 `null/undefined/NaN` 显「—」。

### 20.3 四页与路由

| v1 页 | v2 路由 | 主体内容 |
|---|---|---|
| 65 投机情绪周期时钟 | `/sentiment-clock` | 当前相位五档 KPI + 5 维 min–max 归一化时序（窗口可切，参数真传后端） |
| 67 历史相似日聚类 | `/similar-days` | top-15 相似日表 + 后 5/10/20 日红盘占比经验分布 + 信息族重叠警告 |
| 68 情绪拐点扫描器 | `/inflection-scan` | 近期拐点事件表 + 维度切换 + z-score 折线（拐点标注 / ±1±2 阈值线） |
| 69 温度持续期 | `/regime-duration` | 五档持续中位柱状图 + 逐档明细 + 冰点回归中性磨底时长 |

四页共用 `features/analytics/shared.tsx`：`AnalyticsHeader`（权威数据日 + 非预测声明）、
`SectionState`（段级降级）、`DataBoundary`（6 个可靠字段 + 10 个缺真值维度 + 方法学）。
接线：`nav.ts`（AppPath + UTILITY_PATHS）、`router.tsx`（4 个 `lazyRouteComponent` + routeTree）、
`AppShell.tsx`（底部 4 入口）、`v2Mapping.ts`、`scripts/shoot_frontend_v2.py` ROUTES **47→51**（`AppPath` 46→50，AST 实测）。

### 20.4 守卫诚实化（4 处，均非放宽）

1. `test_v1_pages_catalog.py`：data 条目 7→3 → 阈值 `>=5` 改 `>=3`（去重端点 `>=2` 不变，仍逐条验真注册）；
   顺手修掉 `test_required_query_data_deeplinks_are_usable` 里**未定义的 `registered`**（过去因交集为空、
   generator 不迭代而侥幸不报 `NameError`）→ 就地真扫 + 数量兜底。
2. `test_diagnostics_endpoint_contract.py`：analytics 的 `window` 可选、缺参不 400 → 加入
   `_VALIDATION_ONLY_400` 豁免（符合该集合既有语义）；zseries 缺 `dim` 真 400 → 登记
   `_DIAG_REQUIRED_QUERY` 并同步 `diagnosticsEndpoints` 夹具两条。
3. 新增 `tests/test_breadth_analytics_contract.py`（6 例，零网络零 DB）：window 白名单、
   `_zseries_slice` 不变量、逐段隔离、端点鉴权/需参登记、**后端 data 键 == Zod schema 键 == MSW 夹具键**三重比对。
4. 新增 `frontend-v2/tests/e2e/breadth-analytics.test.tsx`（10 例）：四页三态、窗口/dim 参数真传、
   段级降级、缺样本显「—」、10 个离线维度披露。

### 20.5 验证（全绿）

| 项 | 结果 |
|---|---|
| `npx tsc --noEmit` | 0 错误 |
| `npx vitest run` | **388 passed / 1 skipped**（51 文件；§19 基线 378 + 本轮 10） |
| 前端守卫 | `honest-data`（抓到并修掉 4 处 `?? 0`）/ `echarts-setup`（markLine/markPoint 已注册）/ `route-lazy` 全绿 |
| pytest 6 个守卫文件 | catalog / route-coverage / diagnostics-contract / public-numbers / earnings-contract / breadth-analytics-contract 全绿 |
| `python -m backend.tests.test_security`（隔离库） | **12/12**，两个新端点均带 `@jwt_required`、未登录 401 |
| 隔离库真端点联调 | 401 / 四段全 available / window 60·250·2000 / 非法 window·dim 400 / zseries 三数组等长 + markers 合法 / 信封无 NaN |
| 四档守恒 | **60 native + 3 data + 11 v1-pinned + 0 v1-only = 74**（`count_tiers` 实测） |
| 数字同步 | `gen_portfolio_page.py` 重跑：端点 137→**139**、测试 4616→**4622**、测试文件 500→**501**、护栏 102→**103**、源码 101,849→**101,994 行**；README + promo×2 + publish-kit×4 同步 4622/501 |

**当前口径**：剩 3 个 data 页 = 50 市场情绪 / 62 动量广度共振 / 70 涨停复盘（均需实时源或复杂复盘逻辑，
下一轮评估，不硬凑换皮页）。按用户要求，**v1 降级/退役评估继续挂起**；43 实盘交易红线不碰，
v2 不提供任何真实券商下单能力。

---

## 21. 验收补记（2026-11-11 末，50/62/70 三页 data → native 真页面，60/3/11/0 → 63/0/11/0）

> 对应「都做 / 请继续完成未完成的任务」。把 §20 末尾剩余的 3 个 data 页（50 市场情绪 / 62 动量广度共振 / 70 涨停复盘）做成 v2 **真页面**，彻底清零 data 档，逼近「v2 可替代 v1」判定线。v1 降级/退役评估仍按用户要求**挂起**；43 实盘交易红线不碰。

### 21.1 三页真实落地（非「仅改标签」）

| V1 页 | v2 路由 | 数据来源 | 诚实边界 |
|---|---|---|---|
| 50 市场情绪 | `/market-sentiment` | **新增**只读端点 `/api/v2/read/market-sentiment`，包装 `market_drivers.get_market_drivers`（21 指标分 5 维：资金/情绪/估值/宏观/技术）+ 综合温度圆 | 单源失败优雅降级 + SQLite 缓存兜底；样本不足→维度 value=null 显「—」、不补零；`available=false`→诚实空态带 reason |
| 62 动量广度共振 | `/momentum-resonance` | **新增**只读端点 `/api/v2/read/momentum-breadth`，包装 `momentum_breadth_resonance`（纯离线共振矩阵） | 纯离线确定性；`red_ratio==null`→显「—」；`available=false`→诚实空态，不编造 |
| 70 涨停复盘 | `/limit-up-review` | **新增**只读端点 `/api/v2/read/limit-up-review`，包装 `shepherd_temperature._zt_pool_detail_cached`（东财涨停池，10 分钟缓存） | 池 `available=false`→诚实降级空态带 reason；连板梯队/断层检测/市场上下文均据真数据渲染，不虚构 |

接线全链路：`nav.ts`（AppPath + UTILITY_PATHS）、`router.tsx`（`lazyRouteComponent` + routeTree）、`AppShell.tsx`（底部固定入口 🌀/🏆/⚖️，绕过 NAV 4 组 / 第 3 组 12 项守卫）、`api/schemas/read.ts`（新增 `MomentumBreadthSchema` / `LimitUpReviewSchema` / `MarketSentimentSchema`，`MarketSentimentSchema` 含 `reason` 可选字段对齐后端不可用态）、`api/read.ts`、`lib/queries.ts`、`mocks/handlers.ts`、`mocks/fixtures.ts`（`diagnosticsEndpoints` 三追加，`needs_params=false` 与后端 `_diag_endpoints()` 自动枚举一致）；`scripts/shoot_frontend_v2.py` 的 `ROUTES` 补 3 条（51→54，`AppPath` 50→53）。

### 21.2 守卫诚实化（3 处，均非放宽）

- `test_diagnostics_endpoint_contract.py`：`market-sentiment` 的 `days` 可选（缺省 180、仅显式非法才 400）→ 加入 `_VALIDATION_ONLY_400` 豁免（与 breadth-analytics 的 window 同款口径），不再被接口检测当成需参端点。
- `test_v1_pages_catalog.py`：DATA 档归零后，原 `条目>=3` 下限断言无意义 → 放宽为 `>=0`（保留「任何 DATA 条目必须指向真实端点」的真校验）。
- `test_public_numbers_consistency.py`：`docs/index.html` 声明端点数（139）与生成器实测（142）失配 → `python scripts/gen_portfolio_page.py` 重生成（74 页 / 142 端点），消除失配。

### 21.3 验证（全绿）

| 项 | 结果 |
|---|---|
| `npx tsc --noEmit` | 0 错误 |
| `npx vitest run` | **395 passed / 1 skipped**（53 文件）；全量跑捕获 1 个沙箱 worker 启动超时（TradingAccount.test.tsx，非用例失败），三新页 12 例在隔离重跑全绿 |
| 三新页单测 | `MomentumResonance.test.tsx` / `LimitUpReview.test.tsx` / `MarketSentiment.test.tsx` 各 4 例（loading/error/ok/不可用）共 **12 例全绿** |
| 前端守卫 | `route-lazy`（5）/ `honest-data` / `w4e-pages` / `w4f-pages`（30，NAV 4 组 + 第 3 组 12 项 + 图标唯一 + UTILITY_PATHS 单一真理源）全绿 |
| pytest 守卫文件 | diagnostics-contract / v1-pages-catalog / public-numbers 全绿（catalog + route-coverage + earnings-contract + breadth-analytics-contract 随口径同步） |
| `python -m backend.tests.test_security`（隔离库） | **12/12**，三个新端点均带 `@jwt_required`、未登录 401 `missing_token` |
| 四档守恒 | **63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（`count_tiers` 实测，`DATA` 现为 `{}` 空） |
| 数字同步 | `gen_portfolio_page.py` 重跑：端点 139→**142**、页面 74；README + promo×2 + publish-kit×4 同步（仅 `docs/` 下历史评估文档有旧 139，属历史快照非活动物料，不改） |

**当前口径**：四档 **63 / 0 / 11 / 0 = 74**，data 档彻底归零；剩余 11 个 v1 保留全部为永久不迁（含 43 实盘交易等真实券商下单能力）。按用户要求，**v1 降级/退役评估继续挂起**；43 实盘交易红线不碰，v2 不提供任何真实券商下单能力。

---

## 22. 收口补记（2026-11-11 末，/p1-construction 诚实红线 + 路由 + 测试，修 breadth 守卫解析）

> 对应「都做 / 请继续」收尾：把已登记路由但半成品的 **P1 组合构建诊断页 `/p1-construction`** 收口为可用页，并修两处守卫缺陷。
> 该页是 **v2 原生新增页**（P1 组合构建诊断），**不在 `v2Mapping.ts` 四档 74 目录内**（与 `/diagnostics`、`/catalog`、`/data` 同类），故四档口径**不变：63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。

### 22.1 交付内容

| 文件 | 变更 | 说明 |
|---|---|---|
| `features/p1/ConstructionDiagnostics.tsx` | 新建 | 本地 JSON `data/constructionDiag.json` **直读**、零网络零写入；新增 `netX(v)` helper 防御缺失值（`undefined/null/NaN` → 显「—」，不补零） |
| `features/p1/constructionDiag.ts` | 新建 | `ConstructionDiagSchema`（Zod 严格解析）+ `useConstructionDiag()` hook（`staleTime: Infinity`） |
| `features/p1/data/constructionDiag.json` | 新建（**`git add -f` 强加入**） | 页面必需源数据；被 `.gitignore` 第 23 行 `data/` 规则命中，未强加入则全新 `clone`/`build` 页面崩 |
| `app/router.tsx` | 改 | 登记 `p1ConstructionRoute`（`/p1-construction`，`lazyRouteComponent` + routeTree 入 `p1Route` 之后） |
| `nav/nav.ts` | 改 | `AppPath` 联合类型加 `'/p1-construction'`；`NAV` 加 `{ to:'/p1-construction', label:'P1 组合构建诊断', icon:'📐' }` |
| `scripts/shoot_frontend_v2.py` | 改 | `ROUTES` 元组补 `("/p1-construction","p1_construction")`（满足路由覆盖守卫） |
| `features/breadth/LimitUpReview.test.tsx` | 改 | 修 `tsc` 抓到的元组类型错误：`ladder.distribution` 字面量加 `as [number, number]` 断言 |
| `tests/e2e/ConstructionDiagnostics.test.tsx` | 新建（4 例） | loading(`加载中…`) / error(`role=alert`+文案) / empty(`暂无组合构建诊断数据`) / ok(标题+诊断结论+诚实边界+KPI) |
| `tests/unit/constructionDiag.test.ts` | 新建（4 例） | `ConstructionDiagSchema.parse(raw)` 通过 / `headline.rf===10` / `headline.buffer===0` / 三条曲线等长 |
| `tests/test_breadth_analytics_contract.py` | 改 | 修解析缺陷（见 §22.3）|

### 22.2 抓到的真实缺陷（4 处，均已修复）

1. **部署级缺失**：`constructionDiag.json` 被 `.gitignore` 的 `data/` 规则命中而**未自动追踪**；本仓 `frontend-v2/src` 下零 json 被追踪 → 页面在全新 `clone/build` 会崩。**修复**：`git add -f` 强制加入，并在 commit message 标注此例外。
2. **路由覆盖守卫**：`/p1-construction` 进 `nav.ts` 的 `AppPath` 后，`scripts/shoot_frontend_v2.py` 的 `ROUTES` 漏覆盖 → 守卫红。**修复**：`ROUTES` 补该条。
3. **breadth 守卫解析（`JSONDecodeError: Extra data`）**：§21 新增 `breadthZSeries` 夹具后 `breadthZSeries` 非末位 `const`，旧 `_fixture_object` 简单 `json.loads(剩余)` 因后续多对象 + 注释而失败。**修复**：新增 `_extract_balanced_braces(text, open_idx)` 按括号深度解析（跳过字符串/注释内括号），彻底解耦 const 间注释与后续多对象 → 6/6 绿。
4. **`tsc` 元组类型错误**：`LimitUpReview.test.tsx` 的 `number[][]` vs `[number,number][]` → 加断言。

### 22.3 诚实红线

`honest-data.test.tsx` 守卫抓到 `ConstructionDiagnostics.tsx` 用 `?? 0` 补零 → 新增 `netX()` 显「—」并替换三处（long_only_net / long_short_net / benchmark_gross），与全站零兜底原则一致。

### 22.4 验证（全绿，本地复跑确认）

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | 0 错误 |
| `vitest run` | **408 passed / 1 skipped**（56 文件；§21 基线 395 + 本轮 13：ConstructionDiagnostics 4 + constructionDiag 4 + LimitUpReview 修复相关） |
| pytest 守卫 | `test_breadth_analytics_contract` / `route-coverage` / `public-numbers` / `v1-pages-catalog` **36 例全绿** |
| `python -m backend.tests.test_security`（隔离库） | **12/12**（本轮未动后端产品代码，三端点契约不变） |

### 22.5 提交与推送

- commit `645e0eb`（msg: `fix(v2): 收口 /p1-construction 诚实红线+路由+测试，修 breadth 守卫解析`），**10 files changed, +1489/−5**。
- ff-only 推 `origin/main`：`882dab8..645e0eb`，复校 `LOCAL==REMOTE==645e0eb…` → **SYNCED_OK**（submodule 本体 `origin/main` 最新）。
- 仅 stage `frontend-v2/` + `scripts/shoot_frontend_v2.py` + 相关 `tests/`；`backups/`、`thesis/`、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- ks 父仓库 submodule 指针按红线留痕不推。
- 四档口径：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（未变）。v1 降级/退役评估继续挂起；43 实盘交易红线不碰。

## 23. 质量加固补记（2026-11-12，nz() 隐藏补零诚实红线漏洞收口）

> 对应「接着开发 v2 / 质量加固 + 真实缺陷排查」方向：审计发现 `honest-data.test.tsx` 守卫只抓 `?? 0` / `|| 0` / `new Date()`，而 6 个组件各定义了一个局部 `nz()` helper（`v => 非数 ? 0 : v`），把 schema 里 `nullable` 字段的 `null` 伪装成真实「0 / 0.0 / 0 条」直接进用户可见文本，**绕过守卫**。属系统性诚实红线漏洞。

### 23.1 发现路径
- `grep nz\(` 全 `frontend-v2/src` → Strong / Theme / Watch / SectorRotation / QuoteBoard / DragonTiger 共 6 处局部定义。
- 逐一甄别：图表坐标（bar 条宽、`tileColor` 颜色、`Math.abs(nz(net))` 散点、过滤/排序 `nz(x) > 0`）属合法派生用法，保留；**用户可见文本**用法为真实缺陷。

### 23.2 修复的真实缺陷（4 处，均为「缺失字段显 — 而非补零 0」）

| 文件 | 位置 | 旧（缺陷） | 新（诚实） |
|---|---|---|---|
| `features/strong/Strong.tsx` | 行内评分 + 榜首评分 Stat | `const score = nz(it.score)` 后 `{score.toFixed(1)}`；`topScore = nz(filtered[0].score)` | 直接用原始 `it.score`/`filtered[0].score`，`== null ? '—' : x.toFixed(1)`（`scoreColor` 仍用 nz 判定缺失色，合法） |
| `features/theme/Theme.tsx` | 传导结果条数 | `{nz(tx.data.n_titles)} 条` / `{nz(tx.data.n_concepts)} 个` | 新增 `fmtInt()`（非有限数显 `—`）替换；tooltip `市值 ${nz(pp.value)}` 改为直接用 `pp.value`（treemapValue 恒有限，去掉 nz） |
| `features/watch/Watch.tsx` | 汇总卡四项统计 | `String(nz(summary?.watch_count))` 等 | `summary?.x == null ? '—' : String(summary.x)`（schema `watch_count` 等均为 `.nullable()`，缺失真会发生） |
| `features/sector-rotation/SectorRotation.tsx` | treemap tooltip | `_chg: nz(it.chg_pct)` / `_net: nz(it.net)` → 经 `fmtPct`/`fmtYi` 把 null 显成 `+0.00%`/`+0.0 亿` | 存原始值（`Number.isFinite ? v : null`），`fmtPct`/`fmtYi` 接收 `unknown` 自动显 `—` |

### 23.3 守卫加固（honest-data.test.tsx）
- 新增 `findNzDisplayViolations(text)`：先剥注释、把合法图表 prop `={nz(...)}`（如 ScoreBar 条宽）改写成 `={ATTR(` 排除，再扫 `String(nz(` 与 `{nz(`（含 `${nz(` 模板文本）。
- 「全 src 诚实红线」describe 新增断言：**全 `frontend-v2/src` 无 `String(nz(` 与文本 `{nz(` 残留** → 防 `nz` 再次进可见文本。

### 23.4 回归测试（新增 tests/unit/nz-display-honest.test.tsx）
- 用真 MSW 夹具（缺失字段显式 `null`）+ `<Providers>` 渲染：
  1. Strong：`score=null` 的标的与榜首评分显 `—`，`queryByText('0.0')` 为 null。
  2. Watch：summary 四项计数为 `null` → 四项 Stat 值均 `—`（按 label → `.rounded-tile` → `.text-kpi` 取数断言）。
  3. Theme：传导 `n_titles/n_concepts=null` → 显 `—`，`/新闻标题 0 条/` `/命中概念 0 个/` 均不存在（桩掉 EChart 避免 jsdom canvas）。

### 23.5 验证（全绿，本地复跑确认）

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | 0 错误 |
| `vitest run` | **412 passed / 1 skipped**（57 文件；§22 基线 408 + 本轮 4：honest-data 守卫 1 + nz-display 回归 3） |
| 守卫覆盖 | `honest-data` 12 例 + `nz-display-honest` 3 例全绿 |

### 23.6 提交与推送
- commit（msg: `fix(v2): 收口 nz() 隐藏补零诚实红线漏洞（Strong/Theme/Watch/SectorRotation）+ 守卫加固 + 回归测试`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/`（`src` 4 文件 + `tests` 2 文件）+ `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。v1 降级/退役评估继续挂起；43 实盘交易红线不碰。

## 24. 只读端点 ↔ 前端 Zod schema 字段契约漂移守卫（2026-11-12，task #2 收口）

> 背景（§21 教训）：MSW 夹具与 Zod schema 可「自洽」却与真后端脱钩（财报日历 MSW 全绿、接真后端三列全显「—」）。本次把「端点↔schema 字段契约」抽成**真后端离线双盲守卫**，从根上抓双向漂移。

### 24.1 新增守卫
- `tests/test_read_contract_drift.py`（**~19KB，新文件**）：三重守卫
  1. **离线 object 端点**：真打只读端点取 `data` 顶层键，与前端 Zod schema 顶层键比对——必需字段缺失即 fail（软缺失/破版），未知字段越界（schema 无 `.catchall()`）即 fail（Zod 硬崩）。
  2. **离线 list 端点**：首元素键对齐元素 schema（如 `webapps→WebAppSchema` 元素而非数组 schema）。
  3. **联网端点枚举 + 优雅降级**：20 个 akshare/实时行情端点离线不打真数据，AST 登记枚举 + 离线 stub（`socket`/`subprocess`/`requests`/`urllib`/`http.client` + `modules.fetcher_kline.observe_source` 打挂），断言「离线 200 而非 500」，超时显式 `pytest.skip`（登记「需联网 CI」，非静默）。

### 24.2 端点分类（实测真后端 + 真 data/）
- **纯离线（本地 json/db，严格对齐，11）**：daily-snapshot、daily-recommendation、user-dashboard、paper-trades、event-pool、p1-sync-status、data-refresh-state、breadth-analytics、breadth-zseries、trading-account、snapshot/<date>。
- **列表（元素 schema 对齐，5）**：prediction-log、ladder-detail、breadth-history、webapps、snapshot-dates（字符串数组）。
- **松校验（前端手动 parse，无 Zod，1）**：p1-signals。
- **联网能力（akshare/实时，离线优雅降级，20）**：portfolio、watch、macro-data、six-dim、fundamentals、financials、stock-kline、fund-flow、dragon-tiger、theme、theme-transmission、strong、sector-rotation、quote-board、earnings-calendar、market-panorama、breadth-timeseries、limit-up-review、market-sentiment、factor-analysis。

### 24.3 关键根因发现（重要）+ 隔离修复
- **发现**：`backend/tests/test_read_routes.py` 用**直接赋值** `rr._DATA_DIR = data.resolve()`（而非 `monkeypatch.setattr`）改写 `read_routes` 的 `_DATA_DIR`/`_REPORTS_DIR`/`_WEBAPPS_DIR`/`_FILE_WHITELIST` 指向其临时树（含最小 `daily_snapshot.json {"date":...,"temperature":42}`）。直接赋值**不随 fixture 退出自动还原**，泄漏到整个 pytest 会话——排在它后面的本研究首跑时读取该泄漏临时树 → `/daily-snapshot` 返回 `{date,temperature}` → 契约守卫**假阳性失败**。
- **上游根治（2026-11-12）**：`backend/tests/test_read_routes.py` 的 `client` fixture 改为「保存原始目录常量 + `request.addfinalizer` 在测试模块结束后还原」，四枚常量不再泄漏，整 pytest 会话恢复干净（实证：同进程跑完该模块后 `rr._DATA_DIR` 还原为真实值 `E:/project/ks/StockSignal/data` → LEAK_GONE）。
- **本守卫防御性恢复**：本守卫 fixture 仍捕获真实目录常量 + 数据文件字节，测试前恢复 pristine、测试后还原「泄漏前」状态，既免疫任何未来全局泄漏，又不破坏其它测试预期（诚实隔离，非悄悄改全局）。

### 24.4 验证
- 隔离态 `pytest tests/test_read_contract_drift.py -q`：**exit=0**（22 passed / 1 skipped）。
- 针对性复现（元凶 `test_read_routes.py` 先跑触发泄漏 + 本守卫）：**exit=0** → 双重恢复生效。
- 全量回归 `pytest backend/tests tests/ -q`：**本守卫 test 在全集下转绿**；其余 **16 个失败均为 baseline 已有（与本次新增文件无关）**——分布在 `test_public_numbers_consistency`(3) / `test_thesis_numbers_ch6_v2`(2) / `test_quality_numbers_sync`(2) / `test_research_watch`(2) / `test_no_silent_swallow` / `test_component_vocabulary` / `test_page91_prefs_slim` / `test_silent_return_audit` / `test_t239_bare_silent_audit` / `test_ui_design_system`，均属无关文件（生成文档/论文数据/调度交易时段/组件词汇状态等），排除本文件后全量仍 exit=1 → 证实 preexisting，超出本任务范围，未动。

### 24.5 提交与推送
- commit（msg: `test(v2): 新增只读端点↔Zod schema 字段契约漂移守卫 + 双重隔离修复（防 read_routes 常量泄漏污染）`）。
- ff-only 推 `origin/main`；仅 stage `tests/test_read_contract_drift.py` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（纯后端测试，不触前端页面计数）。v1 降级/退役评估继续挂起；43 实盘交易红线不碰。

### 24.6 根因根治提交与推送（2026-11-12）
- 把 `backend/tests/test_read_routes.py` 四枚 `read_routes` 目录常量由「直接赋值」改为「保存+`request.addfinalizer` 恢复」式隔离；本守卫注释同步说明上游已根治、保留防御性恢复。
- commit（msg: `test(v2): 根治 read_routes 测试目录常量会话级泄漏（保存+恢复式隔离）+ 守卫注释同步`）。
- ff-only 推 `origin/main`；仅 stage `backend/tests/test_read_routes.py` + `tests/test_read_contract_drift.py`（注释同步）+ `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- 实证：同进程跑完 `test_read_routes.py` 后 `rr._DATA_DIR` 还原为真实值（LEAK_GONE）；组合 `test_read_routes.py` → 本守卫同会话 `pytest` exit=0。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。v1 降级/退役评估继续挂起；43 实盘交易红线不碰。

## 25. 真后端集成冒烟 + market-sentiment 优雅降级 500 真缺陷修复（2026-11-12，v2 接着开发）

> 背景（补 deferred 项）：§24 契约守卫只离线对键、MSW 夹具不能证明「真后端真能正确吐信封」。本轮用**真实 Flask app + 真实 JWT** 打离线可达端点做集成冒烟，并借此抓到一个**高频真实 500 缺陷**。

### 25.1 真实缺陷（market-sentiment 缓存过期即 500）
- **现象**：`GET /api/v2/read/market-sentiment` 在底层 `modules.market_drivers.get_market_drivers` 因**进程缓存过期**返回的 `meta` 含非维度注入键（`_swr_stale`=bool / `_swr_age_s`=int / `_swr_note`=str）时，`api/read_routes.py::_flatten_unavailable` 对每条 `meta.items()` 都调 `.get("unavailable")`，遇到字符串 `_swr_note` → `AttributeError` → 端点 **500**，违背「优雅降级」契约。
- **触发频率**：进程缓存过期在生产中**高频**（缓存 TTL 一过即触发）——即「只要缓存过期，`/market-sentiment`（v2 native 页）必定 500」。其余联网端点（momentum-breadth / limit-up-review / earnings-calendar）均正确降级为 200 ok，唯独本端点挂掉。
- **根因定位**：`modules/market_drivers.py` 第 136-139 行在 SWR 缓存过期时往 `meta` 注入 `_swr_stale/_swr_age_s/_swr_note`；`_flatten_unavailable` 未区分「维度 dict」与「注入键」，对后者调 `.get` 崩溃。
- **修复**（`backend/api/read_routes.py`）：`_flatten_unavailable` 改为——
  1. `meta` 非 dict → 直接返回空；
  2. `info` 非 dict（即 `_swr_*` 注入键）→ 跳过；
  3. `info["unavailable"]` 非 list/tuple，或元素非 2 元组 → 跳过（兜底，绝不二次崩溃）。

### 25.2 新增守卫（两文件，共 7 例，全绿）
- `backend/tests/test_market_sentiment_degradation.py`（4 例）：① 直接单测 `_flatten_unavailable` 对 `_swr_*` 注入键 / 非 dict / None / `unavailable` 非列表 的健壮性；② 集成测试 monkeypatch `get_market_drivers` 返回带 `_swr_*` 注入键的 meta（精确复现缓存过期触发条件），断言端点 **200 ok（非 500）** 且 `unavailable` 正确拍平（`north_flow`/`pe_median` 入场，`_swr_*` 跳过）——旧代码下断言必失败，确为有效锁。
- `backend/tests/test_read_routes_integration.py`（3 例）：真 app + 真 token 打 13 个**离线可达端点**（本地真数据，不联网），断言统一信封（200 + status/code/message/data 四字段 + data 类型正确：8 个 object / 5 个 list）；鉴权门（无 token → 401 `missing_token`）；非法参数（breadth-analytics?window=999 → 400；six-dim?code=BAD → 400）。即 §24 离线对键之外的**第二道真后端防线**。

### 25.3 回归核验
- 新两文件：`pytest` 全绿（4 + 3）。
- `backend/tests/test_read_routes.py`（泄漏根治版）：55/55 全绿（无回归）。
- `python -m backend.tests.test_security`：**12/12**（与 read_routes 改动无关，独立确认）。
- 前端无需改动：`MarketSentiment.tsx` 早已按 `available=false` 诚实空态 + `unavailable[]` 渲染，`data_refresh_state` 等不受影响。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（纯后端测试，不触前端页面计数）。v1 降级/退役评估继续挂起；43 实盘交易红线不碰。

### 25.4 提交与推送
- commit（msg: `fix(v2): 修 market-sentiment 缓存过期 500 真缺陷 + 新增真后端集成冒烟守卫`）。
- ff-only 推 `origin/main`；仅 stage `backend/api/read_routes.py` + `backend/tests/test_market_sentiment_degradation.py` + `backend/tests/test_read_routes_integration.py` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`frontend-v2/`、`thesis/`、`backups/`、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage（本轮无前端改动）。
- ks 父仓库 submodule 指针留痕不推。

## 26. 在线端点「上游失败绝不 500」确定性守卫（2026-11-12，继续 v2）

> 延续 §25 教训：market-sentiment 的 500 根因是「后处理未接住模块返回的异常结构」；在线端点（akshare/实时行情）还有一类更广的风险——**上游网络 / akshare 调用抛异常时若未被 try/except 接住，整个端点 500**。生产环境网络抖动、数据源限流、akshare 改版都会触发。本轮把这一类做成确定性守卫。

### 26.1 守卫设计
- 新文件 `backend/tests/test_online_endpoints_graceful.py`（parametrize 27 个在线端点 + 合法参数）。
- 用 `monkeypatch` 把 `requests.get/post/put`、`requests.Session.get/post/put/request`、`urllib.request.urlopen` **立即抛 ConnectionError**（模拟离线/超时/数据源不可达）；**不 patch socket**，避免误伤 in-process 测试客户端。
- 断言：① 任意在线端点 `status_code != 500`（核心契约：上游失败 → 200 优雅信封，而非 500；400 属参数校验亦合法）；② 若 200，响应必为统一信封（含 status/code/message/data 四字段）。
- **确定性无网可复现**：网络层打挂使 akshare 调用瞬间失败（无真实超时等待），命中端点若未接住异常 → 500 → 断言失败，精准暴露真实缺陷。

### 26.2 实证结论（负结果 = 无新缺陷，但已锁类）
- 27 个在线端点在上游失败下**全部 200 或 400，零 500**；其中 market-sentiment 修复后稳定通过（该端点降级路径亦被本守卫覆盖）。
- 与本会话另两守卫（§25 的 integration / degradation）同跑共 88 例全绿，无交叉干扰。
- 价值：把「在线端点不得因上游失败 500」从口头契约固化为回归锁，防止未来新增端点重犯 market-sentiment 同类错误。

### 26.3 提交与推送
- commit（msg: `test(v2): 在线端点上游失败绝不 500 确定性守卫（27 端点 monkeypatch 网络层）`）。
- ff-only 推 `origin/main`；仅 stage `backend/tests/test_online_endpoints_graceful.py` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`frontend-v2/`、`thesis/`、`backups/`、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage（纯后端测试，无前端改动）。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。v1 降级/退役评估继续挂起；43 实盘交易红线不碰。

## 27. 前端未测高价值 native 页 组件级测试补缺（2026-11-12，继续 v2）

> 延续「锐评迭代：找真实缺陷→修复→验证→提交」套路，本轮转回前端侧补 E2E/组件测试覆盖缺口。基线核验：`tsc --noEmit` 0 错；`vitest run` **412 passed / 1 skipped**，MSW 注册 48 端点；但 `features/` 内仅 18 个 `.test.tsx`，且大量高价值 native 页（MarketPanorama / WebApps / P1Signals / PaperTrades / Recommendation / Alerts）**完全无组件测试**——仅 E2E 6 个 `w4-*.test.tsx` 覆盖主干流。

### 27.1 补缺目标与写法
- 新 6 个 `.test.tsx`（共 **26 例**，全绿），严格沿用 `MarketSentiment.test.tsx` 模板：
  - `vi.mock('@/api/read', () => ({ getX: vi.fn() }))` 桩对应 API 函数；
  - `QueryClientProvider` 包裹 + `retry:false` 隔离；
  - 覆盖 **loading / error / ok / 空态（或不可用语义）** 四态。
- `MarketPanorama.test.tsx` 含 `<EChart>`（两张图）→ 额外 `vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))` 桩掉，规避 jsdom 无 canvas 崩溃（与 `Portfolio/Backtest` 等既有测试同手法）。
- 诚实红线断言重点：
  - 广度字段 null → 显「—」而非补零（MarketPanorama 5 个 Stat）；
  - 数据源缺失字段 `shepherd_unavailable` 原样带出（不为空态隐瞒）；
  - `regime.latest` 缺失 → 诚实空态「暂无市场全景数据」；
  - `Recommendation` `status==='unavailable'` → 如实展示 reason（不编造推荐）；
  - `Alerts` / `PaperTrades` 数据缺失 → 诚实空态「暂无…」。

### 27.2 踩坑与守卫经验（防回归）
1. **标题不是加载完成信号**：`findByText` 若 await 页面常驻标题（如「网页作品集」始终渲染），会在 loading 态立即 resolve，导致后续数据态断言时序错位。必须 await **仅数据态才出现的元素**（如「市场状态」/「作品A」/「signal_h10」/「100,000」/「状态：ok」/`/rule1/`）。
2. **React Query 拒绝 `undefined` 作成功结果**：`mockResolvedValue(undefined)` 会让查询进入 error 而非空态，致 `findByText('暂无数据')` 超时。空态须用 `null`（已注释进测试）。
3. **多查询组件 loading 用 `findAllByText`**：`Recommendation`/`Alerts` 双查询同步挂起时两个「加载中…」并存，`getByText` 报多重匹配 → 改用 `findAllByText`。
4. **`getByText` 不匹配子串**：`后5日红盘率 55.3%` 在同文本节点，`getByText('55.3%')` 失败 → 改 `getByText(/55\.3%/)` 正则。同名多出现（如「浦发银行」跨持仓/成交两表）→ 改 `getAllByText`。
5. **Schema 类型须忠实**：`RegimeAnalogSchema.metrics` 在 Zod 中标为非可选，fixture 必须带 `metrics:{}` 否则 `tsc` 报错（即便运行时组件不读该字段）。

### 27.3 实证结论
- 新 6 文件 26 例全绿；全量 `vitest run` → **438 passed / 1 skipped**（纯增量 +26）；`tsc --noEmit` 0 错。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（纯前端测试，不触页面计数）。
- 仍存质量债（未本轮覆盖）：`dashboard/decision/morning/calendar/catalog/admin/settings/ops/review/matrix/guide/me/auth/analytics/export` 等目录无组件测试——属后续迭代候选，本次先补最高价值 6 页。

### 27.4 提交与推送
- commit（msg: `test(v2): 补 6 个未测高价值 native 页组件测试（26 例，四态+诚实降级）`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/{market/MarketPanorama,webapps/WebApps,p1/P1Signals,paper/PaperTrades,recommend/Recommendation,alerts/Alerts}.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`（本轮非本任务改动）、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 28. 前端未测高价值 native 页 组件级测试补缺（第二批，2026-11-12，继续 v2）

> 第一批（§27）收口 6 页 26 例后，剩余未测高价值 native 页仍多。本轮续补 4 个**依赖干净、无 getCurrentUser / SnapshotView / 过重诊断**的页：`EarningsCalendar`（财报日历）、`MorningReport`（复盘笔记）、`LeadLagMatrixView`（领先滞后矩阵）、`InflectionScan`（拐点扫描）。排除 `Me`（依赖 `getCurrentUser`）、`DataExport`（依赖 `SnapshotView`）、`DiagnosticsView`（过重）。

### 28.1 补缺目标与写法
- 新 4 个 `.test.tsx`（共 **16 例**，全绿），沿用 §27.1 模板 + 四态覆盖：
  - `EarningsCalendar.test.tsx`（5 例）：直接用 `Loading/EmptyState/ErrorState`（非 QueryState）；`getEarningsCalendar(date, market)` 双参 hook；断言 `加载披露日历…`/`披露日历加载失败`/`沪深京 · 2025年报（1 条）`（数据态 Card 标题作加载信号）+ `浦发银行`/`600000`；unavailable → `财报披露日历暂时取不到`+`数据源限流`；空 rows → `该市场/报告期暂无披露日历数据`。fixture 用 `as EarningsCalendarData` 转型。
  - `MorningReport.test.tsx`（4 例）：默认未选日期 → `未选择日期，不发起查询`（不把查不到伪装成今天数据）；date input 用 `document.querySelector('input[type="date"]')` 触发（label 未用 `htmlFor`，`getByLabelText` 无法关联）。ok `复盘笔记 2026-03-01`+`今日复盘：市场震荡。`；error `笔记加载失败`；空 → `暂无数据`（mock `null`）。
  - `LeadLagMatrixView.test.tsx`（3 例）：`getBreadthHistory` 返回 `BreadthHistoryPoint[]`；纯 QueryState。断言 `加载中…`/`广度历史加载失败`/空 `有效样本不足，未计算矩阵`（mock `[]`）。
  - `InflectionScan.test.tsx`（4 例）：引入 `./shared`（`AnalyticsHeader/DataBoundary/SectionState/show`）；`getBreadthAnalytics` hook；fixture 仅填组件读取字段，`as unknown as BreadthAnalytics` 转型。断言 `加载拐点扫描结果…`/`拐点扫描结果加载失败`/`暂无拐点扫描结果`(null)/`无可用广度维度生成拐点扫描`(okNoDims，数据态信号)。

### 28.2 踩坑与守卫经验（第二批增量）
1. **`getByLabelText` 失败（label 无 htmlFor）**：`MorningReport` 日期输入用 `<label>` 包裹 `<input>` 但无 `htmlFor`/`id` 关联，`fireEvent.change(getByLabelText(/日期/))` 报「Found a label ... however no form control was found associated」。改 `document.querySelector('input[type="date"]')` 直接拿 DOM 节点触发。
2. **`null` 不赋 `ReviewNotes`（tsc）**：`getReviewNotes` 返回 `Promise<ReviewNotes>`，`mockResolvedValue(null)` 触发 `TS2345`。修复：`null as unknown as ReviewNotes`（顶部 `import type { ReviewNotes } from '@/api/schemas/read'`）。

### 28.3 实证结论
- 新 4 文件 16 例全绿；全量 `vitest run` → **454 passed / 1 skipped**（纯增量 +16）；`tsc --noEmit` 0 错。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（纯前端测试，不触页面计数）。
- 仍存质量债（未本轮覆盖）：`dashboard/decision/catalog/admin/settings/ops/review/guide/auth/export`（`Me`/`DataExport`/`DiagnosticsView` 等）仍无组件测试——属后续迭代候选。

### 28.4 提交与推送
- commit（msg: `test(v2): 补第二批 4 个未测高价值 native 页组件测试（16 例，四态+诚实降级）`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/{calendar/EarningsCalendar,morning/MorningReport,matrix/LeadLagMatrixView,analytics/InflectionScan}.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`（本轮非本任务改动）、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 29. 决策闭环展示核心诚实红线守卫（2026-11-12，继续 v2）

> 连补两批四态测试后纯堆覆盖价值递减，本轮换套路：**先按锐评「找真实缺陷」读源码取证**，找到就修 + 加守卫；没有则把高价值页的诚实语义锁成确定性守卫。目标锁定未测目录中价值最高的 `decision/`（决策可解释归因 F3，3 组件全零测试）。

### 29.1 找缺陷取证链（结论：零真缺陷，诚实记录不硬凑）
逐文件读源码核验诚实红线，全部已守住：
- `lib/format.ts::fmtNum` → `null/undefined → '—'`，数字原样/浮点两位，**无 `?? 0` 兜底**；`SnapshotView` 12 个盘面指标 + 3 个 Stat 全走它。
- `lib/queries.ts::useSnapshot` → `enabled: !!date`，未选日期不发起请求（与 §28 MorningReport 同红线）。
- `lib/freshness.ts` → `freshnessFromStatus(undefined) → 'unknown'`；`freshnessLevelFromAge` 对 `null/NaN/负数` 均归 unknown，**绝不把「未知」兜底成「新鲜」**。
- `shared/charts/PositionGauge.tsx` → `pct` 非有限数时返回 `role=status / aria-label=暂无仓位建议数据` 的「—」空态，注释明确旧实现 `pct ?? 0` 会伪造「建议空仓 0%」。
- `shared/charts/ScenarioChart.tsx` → `prob` 缺失 → ECharts `value: null`（不画柱）+ 页面提示「不按 0% 计算」。
- `DecisionPanel/DecisionReplay` → `?? '—'` / `!= null` 占位、`QueryState` 四态、`emptyLabel` 语义齐备，前端不重算仓位（PLAN §5）。

**结论**：`decision/` 三页源码质量过关，无真缺陷可修；但决策闭环展示核心 `SnapshotView`（同时服务 54 今日决策面板 / 97 决策回放）**零测试守卫**，上述诚实语义全靠人工守着，无任何回归锁。→ 本轮转为补确定性守卫，属真实收益（防回归），非「为覆盖而覆盖」。

### 29.2 补缺内容（3 文件 22 例，全绿）
- `decision/SnapshotView.test.tsx`（**13 例，本轮核心**）：纯展示组件直接传 props，无需 QueryClientProvider；仅 `vi.mock('@/shared/charts/EChart')` 桩掉 canvas，PositionGauge 空态 / ScenarioChart 缺失提示均为纯 DOM 仍真实渲染。
  - **结构性精准断言**：`container.querySelectorAll('.text-base.font-medium')` 取 12 个指标值节点，断言 `toHaveLength(12)` 且全部 `=== '—'`，无一 `'0'/'0.00'`——比文字计数更不可绕过。
  - **「真 0 vs 缺失」区分**（最高价值一条）：`indicators: { up_count: 0, down_count: null }` → 第 0 项显 `'0'`（真值不吞）、第 1 项显 `'—'`（缺失不补零），直接锁死 `fmtNum` 语义。
  - position 缺失 → `getByLabelText('暂无仓位建议数据')` + 断言无 `0%`/「建议空仓」；`available:false` 时即便 `long_count:99` 也不渲染「多头」。
  - 新鲜度全缺 → 「新鲜度未知」+「无新鲜度明细」，且 `queryByText('数据新鲜')` 为 null；`age` 缺失但 `status=stale` → 仍判「数据陈旧」；参数化 `age=10/6/2` → 陈旧/偏旧/新鲜。
  - 全字段正向对照、scenario prob 缺失提示、数据源 `lag_days/status` 缺失显「— · —」。
- `decision/DecisionPanel.test.tsx`（4 例）：54 页四态（loading/error/ok/空），标题常驻不作完成信号，await 数据态「权威数据日」。
- `decision/DecisionReplay.test.tsx`（5 例）：97 页默认未选日期 → `expect(getSnapshotByDate).not.toHaveBeenCalled()`（enabled 守卫实证）；日期清单失败原样带出；选中日期 → 断言 `toHaveBeenCalledWith('2026-03-01')` + SnapshotView 复用；该日无归档 → `该日期无归档快照`；快照失败 → 错误态不回退成空数据。

### 29.3 实证结论
- 新 3 文件 22 例全绿；全量 `vitest run` → **476 passed / 1 skipped**（70 文件，纯增量 +22）；`tsc --noEmit` 0 错。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（纯前端测试，不触页面计数）。
- 质量债收敛：`decision/` 由 0 测试 → 3 组件全覆盖。剩余未测目录：`admin/auth/catalog/dashboard/export/guide/me/ops/review/settings`（+ `analytics` 5 组件仅 1 测试、`stock` 5 组件仅 1 测试）。

### 29.4 提交与推送
- commit（msg: `test(v2): 决策闭环展示核心诚实红线守卫（decision 3 组件 22 例）`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/decision/{SnapshotView,DecisionPanel,DecisionReplay}.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`pages/54_*.py`、`pages/55_*.py`、`modules/p1_portfolio_diag.py`（其他任务改动）、`.trae/`、`artifacts/`、`docs/welcome.html` 一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 30. 95 数据导出「失败伪装成无数据」真缺陷修复（2026-11-12，继续 v2）

> 本轮继续按锐评「找真实缺陷→修复→验证→提交」，扩大勘察面到剩余未测目录（`admin/auth/catalog/dashboard/export/guide/me/ops/review/settings`）。**啃出一个可复现、有对照证据的真缺陷**，并经历一次「过度修正→全量回归报警→回查契约→正确修复」的自我纠错。

### 30.1 全站扫描：补零类缺陷零命中（诚实负结果）
全局扫 `?? 0 / || 0 / Math.random / catch` 与逐文件读源码，确认已守住：`analytics/shared.tsx` 的 `show/showPct/showNum` 三重 `null/undefined/!Number.isFinite` 检查；`PositionGauge`(pct 缺失→「—」)、`ScenarioChart`(prob 缺失→`value:null`)；`ops/PredictionLogView` 的 `rate` 只可能是 number|null；`BreadthAnalyticsSchema` 的 `reliable_labels/offline_missing` 为必填（Zod 保证 `DataBoundary` 的 `Object.values` 不崩）；`DataExport/DashboardCustom/DataSourceView/GuideView` 的 `catch` 均为带注释的能力降级或如实带出错误。**无补零/兜底假数据缺陷**。

### 30.2 真缺陷（可复现 + 对照证据）
`export/DataExport.tsx` 旧实现把 `snapQ.isError` 也塞进「无数据」分支：
```tsx
{selected && !snapQ.isLoading && !snapQ.data && (
  <EmptyState label="该日期无归档快照"
    hint={snapQ.isError ? errorMsg : 'data/snapshots 中无该日期归档'} />
)}
```
→ **网络 500 / 鉴权过期 / 信封解析失败会被主文案伪装成「该日期无归档快照」**，只在 hint 里塞原因。对照 `DecisionReplay`(97) 用 `QueryState` 正确把 `isError` 分派到 `ErrorState`。
- 复现：先写 `DataExport.test.tsx` 失败用例 → `vitest run` **5 passed / 1 failed**，失败证据 `expected ... to be null` 收到 `<div>该日期无归档快照</div>`，缺陷坐实非臆想。

### 30.3 ⚠️ 自我纠错：第一次修复过度，被全量 E2E 拦下
首次修复把**所有** `isError` 一律改成 `ErrorState`（错误态）→ 单文件 6/6 绿，但**全量 `vitest run` 报 1 failed**：既有 `tests/e2e/w4-export.test.tsx > 选中「无归档」日期 → 诚实显空态` 超时。
- 回查取证：`src/mocks/handlers.ts:108-112` 与后端 `read_routes.py` 对**该日无归档**返回 `{status:'error', code:'not_found', data:null}` 信封——即 `not_found` 本来就是 `isError` 路径，**显示空态是正确契约**，我把它误判成缺陷一并改掉了。
- 教训（防回归）：**改错误语义前先查后端信封契约**；「单文件绿」不等于「全量绿」，全量回归是硬闸门。

### 30.4 正确修复：按 `ApiError.code` 分流
`api/client.ts::ApiError(code, reason)` 注释即写明「便于上层按 code 分流」。改为：
```tsx
const notFound = snapErr instanceof ApiError && snapErr.code === 'not_found'
const showEmpty = selected && !isLoading && !data && (!isError || notFound)
const showError = selected && !isLoading && isError && !notFound
```
- `code === 'not_found'` → 诚实空态「该日期无归档快照」+ hint（既有 E2E 恢复通过）；
- 其余任何失败（`http_error` / `unauthorized` / `validation_error` / ZodError / 普通 Error）→ `ErrorState(role=alert)` 原样带出原因，**绝不伪装成无数据**；
- 查询成功但 `data=null` → 空态，不回退今日快照。
- 全站缺陷族排查（grep 所有 `isError`）：`DataExport` 是**唯一**把错误混进空态的页面，其余组件要么 `QueryState` 统一分派、要么 `{q.isError && ...}` + `!q.isError && !data` 显式分离。单点收口。

### 30.5 已知设计性局限（如实记录，本轮不硬改）
`review/ReviewNotes.tsx` 把 `q.isError` 一律显示「该日期暂无复盘笔记」；后端 `/review-notes` 对 `_not_found` / `validation_error` / `invalid_data` 共用 error 信封，前端无法区分，网络失败同样被说成「暂无笔记」。与 `MorningReport`(用 `QueryState` 显示 error message) 对同端点语义不一致。**要精确区分需前后端共同约定错误码契约（跨层改动），本轮不改、不包装成已修复**；已加测试锁住「hint 不吞异常」的当前真实行为并在测试注释标注局限。

### 30.6 补缺测试（3 文件 17 例）
- `export/DataExport.test.tsx`（**8 例**）：四态 + `enabled` 守卫 + 导出按钮 jsdom 安全降级 + **分流对照**（`not_found`→空态无 alert / `http_error`→alert 无空态 / 普通 Error/ZodError→alert）。
- `dashboard/Dashboard.test.tsx`（5 例）：首页三查询聚合；`p1Latest` 按数据日取最大（非 mtime/顺序）；全失败 4 个 Stat 显「—」；score 缺失不补零；加载中态。桩掉 `Link`/`IndexQuotes`/`ProjectIntro`/`EChart` 聚焦自身逻辑。
- `review/ReviewNotes.test.tsx`（4 例）：ok 原文、error 空态 hint、改日期重查、加载中。

### 30.7 实证结论
- `tsc --noEmit` **0 错**；全量 `vitest run` → **493 passed / 1 skipped**（73 文件，纯增量 +17）；既有 E2E `w4-export.test.tsx` 4/4 恢复通过。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 剩余质量债：`admin/auth/catalog/guide/me/ops/settings` 无组件测试；`analytics`(5/1)、`stock`(5/1) 覆盖偏薄。

### 30.8 提交与推送
- commit（msg: `fix(v2): 95 数据导出按 error code 分流，失败不再伪装成「无归档」`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/export/DataExport.tsx`、`export/DataExport.test.tsx`、`dashboard/Dashboard.test.tsx`、`review/ReviewNotes.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 31. ops/ 运维诊断页诚实红线守卫（2026-11-12，继续 v2）

> 承接 §30 的教训（改错误语义前先查后端契约、全量回归是硬闸门），本轮钻 `ops/`（4 组件全零测试：诊断 / 事件池 / 预测日志 / 系统状态）。**结论：零真缺陷，诚实记录不硬凑**；转补确定性守卫，把运维页的诚实降级语义一次性锁死。

### 31.1 找缺陷取证链：三个疑似候选全部排除（附证据）
| 疑似点 | 排除证据 |
|---|---|
| `DiagnosticsView::runEndpointProbe` catch 里 `setEndpointResults([])` → UI 显示「没有可自动探测的端点」，疑似「失败伪装成无数据」（§30 同族） | `api/diagnostics.ts::probeOne` 把每个异常都收敛成 `ok:false + detail` 的 `EndpointProbeResult`，**`probeEndpoints` 实际不抛错**；且 `autoPaths.length===0` 时按钮 `disabled`，点不了 → 该分支**不可达**。 |
| `statusText('fresh') → '正常'`，但汇总统计把 `fresh` 计入「滞后」、`statusClass` 把非 ok 当警告色，三处口径矛盾 | 后端 `_diag_freshness()` → `modules.data_health.health_rows()` → `modules.decision.assess_freshness()`，其 status 值域显式为 **`ok/warn/stale/unknown`**，**永不返回 `fresh`** → `fresh` 是死代码分支。记为**潜在技术债**（若未来新增该状态须同步三处口径），本轮不包装成缺陷修复。 |
| `SystemStatusView::signed()` / `DashboardCustom::Signed()` 无 `Number.isFinite` 检查，`NaN.toFixed()` 会输出 `"NaN"` | JSON 序列化不产生 `NaN`（`null` 代替），Zod 已保证数值域；属边缘防御，非当前真实缺陷。 |

另有全局扫描复核：`EventPoolView` 的 `count ?? rows.length` 用的是**同份数据实际明细行数**（诚实派生值，非补 0）；`PredictionLogView` 的 `rate` 只可能 number|null；`DiagnosticsView` 未探测时 `okEndpoints` 保持 `null` 显「未检测」（注释明确禁补 0）。

### 31.2 补缺内容（4 文件 28 例，全绿）——ops/ 由 0 测试 → 4 组件全覆盖
- `ops/DiagnosticsView.test.tsx`（**9 例**）：mock `@/api/diagnostics`（`getDiagnostics/probeEndpoints/mocksEnabled`）。锁「默认零网络」`getDiagnostics(false)` + `probeEndpoints` 未调用 + `probe=null` 显「尚未探测」；MSW 环境警示「全部检测结果均为模拟数据」+「四源网络探测（模拟数据）」；未探测显「未检测」且断言无 `0/0`；`available=false`/`levels=[]` 独立降级不包装成全部正常；sources/freshness 分区独立降级；状态文字 ok→正常 / stale→滞后 / unknown→未知 + 缺失 `as_of` 显「—」；点击「开始检测」→ `probeEndpoints` 参数与 `1/1`、`42 ms` 实记录。
- `ops/PredictionLogView.test.tsx`（6 例）：**命中率口径**——4 条日志 / 2 已兑现 / 1 命中 → `50.0%` + `分母 2 条`，未兑现不计分子分母（断言无 `25.0%`）；全部未兑现 → 「—」+「无可统计样本」，绝不补 `0.0%`；口径说明与「不构成未来预测」如实带出。
- `ops/EventPoolView.test.tsx`（6 例）：免责 note 原文原样带出；`fmtNum` 浮点两位（`88.50`/`0.12`）；逐条字段全缺失 → 「—」且无 `0.00`；`count` 缺失用实际明细行数（不补 0）。
- `ops/SystemStatusView.test.tsx`（7 例）：三独立数据源**任一失败不连带整页空白**；负收益 `-12.50` / 负回撤 `-8.25` / 负 Sharpe `-0.85` 原样带符号、断言无 `+12.50`；字段缺失一律「—」；绝对路径类字段（fixture 故意塞 `target_dir`）**绝不渲染**；健康明细 达标/超 SLA/未通过；三源全空 → 3 个独立空态。

### 31.3 写测试踩坑（本轮增量，防回归）
1. **常驻元素不能当加载完成信号**（§27.2 老坑再现）：`DiagnosticsView` 的 MSW 警示横幅、`SystemStatusView` 的章节标题都在 `QueryState` 外/常驻，await 它们会在 loading 态立即 resolve → 必须 await 仅数据态才出现的元素（Card 标题 / `2026-03-01 08:00`）。
2. `fmtNum` 浮点一律 `toFixed(2)`：`88.5 → '88.50'`、`0.1234 → '0.12'`，断言别写原值。
3. 同名文本跨区块重复（「命中」「正常」）→ `getAllByText(...)[0]` 或断言数量。
4. `expect(await findByText(x)).resolves` 语法错：`await` 已拿到元素，直接 `.toBeTruthy()`。

### 31.4 实证结论
- 新 4 文件 28 例全绿；全量 `vitest run` → **521 passed / 1 skipped**（77 文件，纯增量 +28）；`tsc --noEmit` 0 错。全量回归硬闸门通过，既有 E2E 无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 剩余质量债：`admin/auth/catalog/guide/me/settings` 无组件测试；`analytics`(5/1)、`stock`(5/1)、`dashboard`(3/1) 覆盖偏薄。

### 31.5 提交与推送
- commit（msg: `test(v2): ops 运维诊断 4 页诚实红线守卫（28 例，零缺陷取证）`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/ops/{DiagnosticsView,EventPoolView,PredictionLogView,SystemStatusView}.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 32. stock/ 分时均价累计口径真缺陷修复（2026-11-12，继续 v2）

> 连啃几轮展示页后按老板指令**换方向到 `stock/` 计算密集处**（5 组件仅 1 测试）。命中一个**可复现、有确定性数值证据**的真缺陷，并顺手把整个纯计算模块 `klineMath.ts` 从零测试补到 12 例守卫。

### 32.1 真缺陷定位与取证（先跑红再修）
`features/stock/charts/klineMath.ts::intradayAvg`（分时均价 = 累计成交额 / 累计成交量）旧实现**分别判空、分别累加**：
```ts
if (p.amount !== null) cumAmount += p.amount
if (p.volume !== null) cumVolume += p.volume
out.push(cumVolume > 0 && cumAmount > 0 ? cumAmount / cumVolume : null)
```
→ 某分钟 **amount 或 volume 单点缺失**时「分子没加、分母照加」（或反之），累计口径错位，算出被稀释/放大的错误均价；且该缺失点**照样输出一个看似精确的数字**，违反「缺失不编造」红线。`toFiniteNumber` 会把 NaN/Inf 洗成 null，故缺失是真实场景（非空想）。

先写单测跑红，证据（**10 passed / 2 failed**）：
- `amount` 缺失点 → `expected null, received 6.666666666666667`（1000/150，被稀释）；
- `volume` 缺失点 → `expected null, received 16`（1600/100，被放大）；
- 后续点也随之错位（修复前 `8`，应为 `1600/150≈10.67`）。

### 32.2 修复：金额与成交量必须成对有效
```ts
if (p.amount === null || p.volume === null) { out.push(null); continue }
cumAmount += p.amount; cumVolume += p.volume
out.push(cumVolume > 0 && cumAmount > 0 ? cumAmount / cumVolume : null)
```
任一缺失 → 该点显 `null`（断线）、两者都不累加，保证后续累计的分子分母始终配对。`IntradayChart` 本就按「null 断线、不拿收盘价冒充均价」设计，无需改动，引用面仅此一处。

### 32.3 疑似候选排除（诚实负结果，避免误改）
| 疑似点 | 结论 |
|---|---|
| `KLineChart.tsx:134` `chgPct = chg / b.open * 100` 用**今开**作基准，与 `IntradayChart` 用 `prevClose` 不一致 | `KlineBar` 接口只有 open/high/low/close/volume，**无昨收字段**；K 线 tooltip 的「涨跌」是开→收实体口径，与分时「较昨收」本就是不同指标。属数据限制下的合理选择，非缺陷（若日后要改成较昨收需后端补 prev_close）。 |
| `IndexQuotes.tsx:39` `up = change >= 0` 把平盘 0 染涨色并加 `+` | 全站 **十几处统一用 `>= 0 ? up : down`**（`Backtest`/`FactorAnalysis`/`FundFlow`/`DragonTiger` 等），是全站口径而非该页独有缺陷 → 按 §30/§31 教训**不单独改**，避免制造不一致。记为统一口径现状。 |

### 32.4 补缺：`klineMath.ts` 纯计算模块由 0 测试 → 12 例守卫
`features/stock/charts/klineMath.test.ts`（纯函数单测，无需 jsdom/QueryClientProvider）：
- `intradayAvg` 5 例：标准累计 `[10, 10.67]`、**amount/volume 单点缺失成对处理**、全缺失全 null、`volume=0`→null、零成交保持上一均价。
- `rollingMean` 2 例：前 `window-1` 根 null、窗口内任一缺失该点 null、`window<=0` 全 null，**不补 0**。
- `emaSeries` 2 例：首值取前 period 个样本 SMA、其后 `Y = v*2/(N+1) + prev*(N-1)/(N+1)`；**遇 null 断链**，需重新攒够 period 才出值。
- `macdSeries` 1 例：slow=26 未就绪前 DIF 全 null，DEA/HIST 需再攒 signal=9 个连续 DIF，未就绪段绝不补 0。
- `parseKlineRows` / `intradayLabel` 2 例：date 缺失行丢弃、NaN/Inf/字符串数值洗成 null（真 0 保留）、时刻解析。

### 32.5 实证结论
- 新 12 例全绿；`tsc --noEmit` **0 错**；全量 `vitest run` → **533 passed / 1 skipped**（78 文件，+12）。
- ⚠️ 首次全量曾出现一次瞬时 `Errors 1 error`（新文件未被收集、计数 528/77 文件），**独立复跑两次均干净**（533/78、新文件 12 tests 被收集、EXIT=0）→ 归因 tsc 与 vitest 串行同命令时的 worker 启动抖动，非 flaky 测试失败，如实记录。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 剩余质量债：`admin/auth/catalog/guide/me/settings` 无组件测试；`analytics`(5/1)、`stock` 其余 4 组件（`FinancialHunter`/`FundamentalsView`/`ResearchView`/`SixDimView`）仍无组件级测试。

### 32.6 提交与推送
- commit（msg: `fix(v2): 修分时均价单点缺失累计错位 + klineMath 纯计算 12 例守卫`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/stock/charts/klineMath.ts`、`klineMath.test.ts` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 33. stock/ K 线「缺失 OHLC 却臆断涨跌方向」真缺陷修复（2026-11-12，继续 v2）

> 承 §32 换方向到 `stock/` 计算密集处。本轮扫 `stock/charts/` 剩余组件，命中第二个**可复现**真缺陷：数据缺失时**颜色仍在表达方向**。§32 管「数值不得编造」，本轮管「视觉编码不得编造」——同一条诚实红线的另一面。

### 33.1 真缺陷定位与取证（先跑红再修）
`features/stock/charts/KLineChart.tsx` 两处把「缺失」折叠成 `false`，再按 `false` 落到某个方向色：
1. `lastUp = lastBar.close !== null && lastBar.open !== null && lastBar.close >= lastBar.open` —— OHLC 缺失时 `lastUp=false` →「最新收盘」数值显 `--`，却仍被染**跌色** `var(--ss-down-ink)`。
2. `volumeData` 的 `b.close !== null && b.open !== null && b.close < b.open ? dir.down : dir.up` —— `close/open` 缺失但 `volume` **有效**时条件为 false → 成交量柱被染**涨色**，凭空宣称该日收阳。

`parseKlineRows` 会把 NaN/Inf/字符串数值洗成 null，故「OHLC 缺失但成交量有值」是真实取数场景，非空想。先写 `KLineChart.test.tsx` 跑红，证据（**4 passed / 2 failed**）：
- `expected '#ff4d4f' to be '#7c86a3'`：缺失行成交量柱拿到 `CHART.up`（涨红），期望中性 `CHART.ink3`；
- `expected 'color: var(--ss-down-ink);' to be falsy`：「最新收盘」显示 `--` 却带跌色 inline style。

### 33.2 对照证据：同目录 `IntradayChart` 本就守住
`IntradayChart.tsx:139`：
```tsx
const volumeColor = (close: number | null) => {
  if (!hasBase || close === null) return CHART.ink3
  return close >= (prevClose as number) ? dir.up : dir.down
}
```
无昨收基准 / 无收盘价 → 中性色。故这不是新口径，而是 **KLineChart 单组件漏守**；修复按同目录既有口径对齐，不引入新令牌、不改其它页面。

### 33.3 修复：方向三态化（涨 / 跌 / 未知）
```tsx
// 组件 Stat
const { close: lastClose, open: lastOpen } = lastBar
const lastUp = lastClose !== null && lastOpen !== null ? lastClose >= lastOpen : null
color={lastUp === null ? undefined : lastUp ? ink.up : ink.down}

// buildKlineOption · volumeData
const volumeData = bars.map((b) => {
  if (b.volume === null) return null
  const { open, close } = b
  return {
    value: b.volume,
    itemStyle: {
      color: open !== null && close !== null ? (close < open ? dir.down : dir.up) : CHART.ink3,
    },
  }
})
```
- `lastUp=null` 表示「方向未知」；`Stat` 的 `style={color ? { color } : undefined}` 自然不染色。
- 成交量柱仅当 `open/close` **成对有效**才分阴阳；`volume` 缺失仍为 null（不补 0）。
- 用局部解构让 TS 收窄，无 `as number` 断言；顶部诚实红线注释补一条。

### 33.4 6 例守卫（`features/stock/charts/KLineChart.test.tsx`）
桩 `@/shared/charts/EChart`（jsdom 无 canvas），空态/Stat 为纯 DOM 仍真实渲染：
1. ⚠️ OHLC 缺失但成交量有效 → 柱用 `CHART.ink3`，绝不染涨色（修复前红）；
2. ⚠️ 最新一根收盘缺失 → 「最新收盘」显 `--` 且 `style` 为空（修复前红）；
3. 缺失行蜡烛 null、MA5 前 4 根全 null、MACD 未就绪段全 null，不补 0；
4. 正常行分阴阳：收≥开涨色 / 收<开跌色（保证修复没把正常着色一起改坏）；
5. 双套价格域：market 红涨绿跌 / report 绿涨红跌，且不设默认值；
6. `rows=[]` → 诚实空态「K 线图暂无数据可绘制」，不画空图表。

### 33.5 实证结论
- 单文件 **6/6**；`tsc --noEmit` **0 错**；全量 `vitest run` → **539 passed / 1 skipped**（79 文件，+6）。本轮 tsc 与 vitest **串行分跑**，无 §32 那次瞬时 worker 抖动；既有 E2E 无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- **未改** `IntradayChart`（本就正确）；**未改** `macdData`（hist=0 染涨色属有效数值的方向约定，非缺失）；`candleData` 本就对缺 OHLC 行置 null，无需动。
- 剩余质量债：`admin/auth/catalog/guide/me/settings` 无组件测试；`analytics`(5/1)、`dashboard`(3/1) 偏薄；`stock` 其余 4 组件（`FinancialHunter`/`FundamentalsView`/`ResearchView`/`SixDimView`）仍无组件级测试。

### 33.6 提交与推送
- commit（msg: `fix(v2): K 线缺失 OHLC 不再臆断涨跌方向 + 6 例诚实红线守卫`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/stock/charts/KLineChart.tsx`、`KLineChart.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 34. 个股研究页「分时数据静默省略」真缺陷修复（2026-11-12，继续 v2）

> 承 §33，继续啃 `stock/` 剩余业务组件（老板点名的个股对比 / 六维 / 财报猎手一带）。在 `ResearchView` quick 子视图命中 §30 同族缺陷：**独立数据源失败/无数据时整块消失，页面不作任何告知**。

### 34.1 缺陷定位与契约取证（先查后端，再跑红）
`features/stock/ResearchView.tsx::QuickView` 对分时数据只有一条分支：
```tsx
{intraday.data && intraday.data.rows.length > 0 && <IntradayChart ... />}
```
→ `isLoading` / `isError` / 成功但 `rows=[]` 三种状态**全部静默省略整块图表**，用户无法区分「没有分时数据」「接口失败」「还在加载」与「页面本来就没有分时图」。

**按 §30 教训先核后端契约**（`backend/api/read_routes.py::stock_intraday:1983-2021`）：
> 「底层源存在，故不走 not_found；仅当整取数失败/空时诚实返回 `rows=[]`、`date=null`（status 仍 ok，绝不 500 / 编造）」

即**生产后端「无分时数据」= `status:ok + rows:[]`**，是正常业务态，必须显式空态；接口失败则必须走错误态，绝不伪装成「无数据」。
⚠️ MSW 夹具 `mocks/handlers.ts:323-329` 对未知 code 返回 `notFound`，与后端不一致（mock 差异，本轮不改夹具）；新测试对两端点均显式注入响应，只测前端契约，不依赖该差异。

先写 `ResearchView.test.tsx` 跑红，证据（**3 passed / 3 failed**），三条失败全是「元素根本不存在」：
- `Unable to find an element with the text: 暂无分时数据`；
- `Unable to find an element with the text: 分时接口 500`；
- `Unable to find an element by: [data-testid="intraday-section"]`。

### 34.2 修复：分时独立四态，主数据源不受连累
把裸条件渲染换成带归属标题的独立区块 + `QueryState` 四态分发：
```tsx
<div className="mt-4" data-testid="intraday-section">
  <div className="text-label text-sf-ink-3 mb-2">分时走势</div>
  <QueryState
    isLoading={intraday.isLoading}
    isError={intraday.isError}
    error={intraday.error}
    isEmpty={!intraday.data || intraday.data.rows.length === 0}
    emptyLabel="暂无分时数据"
    emptyHint="分时 rows 为空数组，未做填充或补零"
  >
    {intraday.data && intraday.data.rows.length > 0 ? <IntradayChart ... /> : null}
  </QueryState>
</div>
```
- `isLoading` → `Loading`；`isError` → `ErrorState(role=alert)` 显示真实错误；`rows=[]` / 无 data → 空态；有数据 → 图。
- **不按 `ApiError.code` 分流**：后端明确不走 `not_found`，此处 `not_found`（仅 MSW 夹具会返回）按真实失败处理更诚实，避免 §30 的「失败伪装成无数据」。
- K 线的 `QueryState` 与分时区块并列，任一失败不连带整页空白（与 `FundamentalsView` 三源独立、`SystemStatusView` 三源独立同款）。
- 顶部组件诚实红线注释补一条。

### 34.3 6 例守卫（`features/stock/ResearchView.test.tsx`）
MSW `setupServer` + `<Providers>`，桩 `@tanstack/react-router` 的 `Link` 与 `@/shared/charts/EChart`（沿用既有 W4-B E2E 范式），显式注入 K 线/分时响应：
1. ⚠️ 后端真实「无分时数据」`ok + rows=[]` → 显式空态 + hint，K 线表照常、无 alert；
2. ⚠️ 分时接口失败 → `role=alert` 显示「分时接口 500」，且**不得**出现「暂无分时数据」；
3. 分时加载中 → 独立区块内显示「加载中…」，不是整块消失；
4. 分时成功 → K 线 + 分时两张图都在，无空/错态；
5. K 线 `rows=[]` 但分时有数据 → 「暂无 K 线数据」与分时图各自独立；
6. `prev_close=null` → 分时图仍渲染并如实标注「暂无昨收基准」。

**踩坑**：`findByText` 默认超时 1s，React Query 重试 + MSW 往返会超时（曾误判为修复无效，实际 DOM 停在 loading）→ 与既有 W4-B E2E 一致统一 `FIND={timeout:5000}` 后全绿。

### 34.4 疑似候选排除（诚实负结果，避免后人重复挖）
| 疑似点 | 结论 |
|---|---|
| `FundamentalsView` 用 `fmtNum(data.name)` / `fmtNum(data.spot_date)`，字符串会不会被显示成 `—` | `lib/format.ts::fmtNum` 对非 number 走 `String(v)` 原样输出 → 名称/行业/日期正常显示，**非缺陷**。 |
| `SixDimView` `radarValues` 用 `typeof === 'number'`，明细用 `v === null` 判缺失，口径不一 | `SixDimSchema` 用 `z.number().nullable()`（z.number() 拒绝 NaN），两处永远一致；`coverage` 由后端按 dims 计算。**非缺陷**。 |
| `FinancialHunter` / `FundamentalsView` 的 `FinancialTable` 只取首行 keys，后续行多出的列被静默丢弃 | 后端 `rows` 为同构 `list[dict]`，注释明写「列名来自后端原始响应，不做重排」；属透传口径，记潜在技术债，**本轮不改**（若后端演进为异构需另议）。 |
| `FundamentalsView` 外层 `QueryState isEmpty={false}` | 主数据成功但全字段 null 时页面仍渲染「—」+ 降权横幅，是刻意设计（不把「全缺失」误判成「无响应」）。**非缺陷**。 |

### 34.5 实证结论
- 单文件 **6/6**；`tsc --noEmit` **0 错**；全量 `vitest run` → **545 passed / 1 skipped**（80 文件，+6），既有 W4-B / 深链 E2E 全绿无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 剩余质量债：`admin/auth/catalog/guide/me/settings` 无组件测试；`analytics`(5/1)、`dashboard`(3/1) 偏薄；`stock` 仍有 `FinancialHunter` / `FundamentalsView` / `SixDimView` 3 个组件无组件级测试（本轮已做源码取证但零缺陷命中）。

### 34.6 提交与推送
- commit（msg: `fix(v2): 个股研究分时数据独立四态，失败/无数据不再静默省略`）。
- ff-only 推 `origin/main`；仅 stage `frontend-v2/src/features/stock/ResearchView.tsx`、`ResearchView.test.tsx` + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 35. stock/ 最后 3 组件：覆盖前提纠偏 + 15 例边界守卫（2026-11-12，继续 v2）

> **先纠正一个此前的表述口径**：§31–§34 记的「`stock` 5 组件仅 1 测试」指的是**没有 colocated 组件级测试**，并非零覆盖。实勘 `frontend-v2/tests/e2e/` 发现 `w4-six-dim.test.tsx`(4)、`w4-financial-hunter.test.tsx`(6)、`w4b-pages.test.tsx`(FundamentalsView 6 + ResearchView 8) 早已覆盖主链路。按「不为覆盖而覆盖」原则，**不重造已有断言**，本轮只锁它们确实没碰到的边界；三项既有 E2E 基线先跑 **25/25 绿**。

### 35.1 零真缺陷（诚实负结果，业务代码零改动）
逐行复核 `SixDimView` / `FinancialHunter` / `FundamentalsView`：`QueryState` 四态齐备、null→「—」/「缺失」、date 无兜底、note 原文、错误态 `role=alert`、非法 code `enabled=false`、副数据源独立 `QueryState` 均已守住。**本轮不改任何业务代码**，不把「补测试」包装成「修缺陷」。
另记两条技术债（非缺陷，未改）：三处 `FinancialTable` / `KlineTable` 重复实现可抽公共组件；`FinancialTable` 只取首行 keys，后端 rows 同构时无碍，若异构会静默丢列。

### 35.2 15 例确定性守卫（3 个 colocated 新文件）
| 文件 | 例数 | 锁住的**新增**边界 |
|---|---|---|
| `src/features/stock/SixDimView.test.tsx` | 6 | ⚠️ **捕获 EChart option**：缺维 `radar.value` 必须是 `null`，绝不补 0 分（DOM 显「缺失」不代表图形没补 0）；`coverage=0` 全缺失空态且不画雷达；`overall=null`→「暂无综合分」；`note=null`→「原始响应未提供口径说明」；`date=null` 时 Stat「最新数据日」显「—」且真实数据日不得被借用；非法 code → 零新请求 + 「未发起请求」空态。 |
| `src/features/stock/FinancialHunter.test.tsx` | 5 | 非法输入按钮 disabled 且点击零请求；**Enter 键提交**；深链 `search.code` 首帧预选（不回落 600519）；⚠️ 查询失败 → `ErrorState(alert)` 显真实原因，绝不伪装「暂无财报数据」；切 tab 时 `report=cash` **真的透传到 API**（既有 E2E 只断言 UI 回显）。 |
| `src/features/stock/FundamentalsView.test.tsx` | 4 | ⚠️ 财报源独立失败 → 错误 alert 只在财报卡，主数据/9 项指标照常；`spot_date`/`kline_date` 双 null 各自显「—」不互兜底；非法 `search.code` 回落默认且首帧只按 600519 请求；`fin.rows=[]` 空态不连累主数据。 |

测试手法：`vi.hoisted` 捕获 `EChart` 的 `option` 与 MSW 请求参数（断言「零请求 / 参数透传」）；MSW handler 显式注入响应，避免依赖默认夹具的 `notFound` 差异；沿用 `Providers` + `Link` 替身范式；统一 `FIND={timeout:5000}`（React Query 重试会超过 `findBy*` 默认 1s）。

### 35.3 踩坑（测试桩自身，非业务缺陷）
「切 tab → 报表 cash」用例首次超时 5s：自写 handler 固定返回 `financialsFull`（`report` 恒 `income`），而页面显示的是**后端回显的 `data.report`**，故「报表 cash」永不出现。改为按请求参数回显 `report`（与真实 handler 一致）后通过。教训：桩必须复刻后端的**回显行为**，否则会把测试桩缺陷误判成组件缺陷。

### 35.4 实证结论
- 3 新文件 **15/15**；既有 3 个 E2E **25/25**；`tsc --noEmit` **0 错**；全量 `vitest run` → **560 passed / 1 skipped**（83 文件，+15），无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- `stock/` 目录至此收敛：`CompareView`(既有 2) + `ResearchView`(6) + `KLineChart`(6) + `klineMath`(12) + 本轮 3 文件(15)，且 W4-A/W4-B/W4-C 三组 E2E 全绿。
- 剩余质量债：`admin/auth/catalog/guide/me/settings` 仍无组件测试；`analytics`(5/1)、`dashboard`(3/1) 偏薄；`charts/KLineModal.tsx`、`components/IndexQuotes.tsx` 无独立测试。

### 35.5 提交与推送
- commit（msg: `test(v2): stock 三组件 15 例边界守卫（图形层不补 0 / 错误隔离 / 交互参数透传）`）。
- `git fetch origin main` → `merge-base --is-ancestor` → **`git push --dry-run origin main`** → 正式推送 → 复校 local/remote SHA。
- 仅 stage 3 个新测试文件 + `docs/frontend-v2/V2-STATUS-PLAN.md`；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 36. stock/ K 线弹窗 + 主要指数：首次真实组件级覆盖（2026-11-12，继续 v2）

> 承接 §35「剩余质量债」中的 `charts/KLineModal.tsx`、`components/IndexQuotes.tsx`。先勘实情：二者此前**无任何真实组件级测试**——`Dashboard.test.tsx` 把 `IndexQuotes` 整体 `vi.mock(() => null)` 掉了，KLineModal 也仅被该 mock 间接「覆盖」。本轮回填这一空白。

### 36.1 源码取证结论：零真缺陷（诚实负结果，业务代码零改动）
逐行复核 `IndexQuotes.tsx` 与 `KLineModal.tsx`：
- 诚实红线齐备：`current/change/change_pct === null → "—"`；`change === null` 走中性色 `var(--color-sf-ink-2)`，绝不把缺失误判为跌；交易屏语义涨红(`--ss-up`)/跌绿(`--ss-down`)正确。
- `KLineModal` 始终调用 `useStockKline` + `useIndexKline`（`enabled` 各自拦截非法 code，不破坏 hooks 顺序）；按 `isIndex` 选数据源；`QueryState` 四态：`isLoading`/`isError(role=alert)`/`isEmpty(!loading && !error && rows.length===0)`/`children`。
- `IndexQuotes` 的 `isEmpty={!!data && items.length===0}` 看似有「`data:null` 但 ok」缺口，但 `IndexQuotesSchema` 用 zod 强约束，**解析失败即抛 → `isError`**，故 `data` 在 `!isError` 时恒为已解析对象，`isEmpty` 缺口在契约上不可达——非缺陷。
- 结论：两个组件设计已合规，**本轮不改业务代码**，只补确定性守卫把上述行为**锁死**，避免后续重构回退。

### 36.2 16 例确定性守卫（2 个 colocated 新文件）
| 文件 | 例数 | 锁住的边界 |
|---|---|---|
| `src/features/stock/components/IndexQuotes.test.tsx` | 7 | 加载中→「加载中…」；取数失败→`role=alert` 显真实原因（不静默空白）；`items=[]`→诚实空态「暂无指数数据」；成功渲染全部 5 指数且**涨红跌绿**按 `--ss-up`/`--ss-down` 着色；⚠️ `current/change/change_pct` 全 null → 显「—」且方向中性色（不含 `ss-up`/`ss-down`）；`note` 非空才展示；**集成**：点击卡片 → 打开 `KLineModal` 且请求对应指数 K 线（`echart` 桩出现）。 |
| `src/features/stock/charts/KLineModal.test.tsx` | 9 | `open=false`/`code=null` → 不渲染 dialog 且不发请求（`enabled` 拦截，resolver 零触达）；`open=true+name` 标题为 name、`EChart` 渲染；无 name → 标题回落 code；关闭三件套（按钮 / **Esc** / **点遮罩**）各触发 `onClose` 一次；取数失败→`role=alert`；`rows=[]`（000003 夹具）→诚实空态；`note` 非空才展示。 |

测试手法：沿用 `Providers` + `EChart` 桩（`data-testid="echart"`）+ MSW 显式注入；统一 `FIND={timeout:5000}`；颜色断言读 DOM **属性** `el.innerHTML`（非 `getAttribute('innerHTML')`，后者对 `innerHTML` 恒返回 `null`，是本轮踩到的测试桩自身坑）；标题「 · K 线详情」用正则 `/K 线详情/` 匹配（精确串匹配会被 span 前缀打断）。

### 36.3 实证结论
- 2 新文件 **16/16**；`tsc --noEmit` **0 错**；全量 `vitest run` → **576 passed / 1 skipped**（85 文件，+16），无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 剩余质量债更新：`admin/auth/catalog/guide/me/settings` 仍无组件测试；`analytics`(5/1)、`dashboard`(3/1) 偏薄。`stock/` 全目录至此收敛（含 W4-A/W4-B/W4-C E2E 全绿）。

### 36.4 提交与推送
- commit（msg: `test(v2): 指数报价与 K 线弹窗 16 例确定性守卫（四态/中性色/关闭三件套/集成）`）。
- `git fetch origin main` → `merge-base --is-ancestor` → `git push --dry-run origin main` → 正式推送 → 复校 local/remote SHA。
- 仅 stage 2 个新测试文件 + `docs/frontend-v2/V2-STATUS-PLAN.md`；红线目录与他人的未提交改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 37. analytics 三组件（温度持续期/情绪时钟/相似日）：首次真实组件级覆盖（2026-11-12，继续 v2）

> 承接 §36「剩余质量债」中的 `analytics`(5 组件仅 1 测试)。先勘实情：`InflectionScan` 已有 `InflectionScan.test.tsx`(4)；**`RegimeDuration` / `SentimentClock` / `SimilarDays` 此前零组件级测试**。三组件与 `shared.tsx` 骨架均严格守诚实红线（`show/showPct/showNum` → `—`、`SectionState` 独立降级、图表送 `null` 不补 0、`DataBoundary` 逐条披露缺真值维度）。

### 37.1 源码取证结论：零真缺陷（诚实负结果，业务代码零改动）
逐行复核三组件 + `shared.tsx`：
- `show(v)` 对 `null/undefined/''/NaN` → `—`，且注释明令「0 是真实数值，不能被当成缺失」——已实现。
- `SectionState`：段 `!available` → 只该段显「暂无数据」+ reason；但**注意**：`RegimeDuration` 与 `SimilarDays` 把 `DataBoundary` 嵌套在 `SectionState` 内，段不可用时整段（含披露）一起隐藏（设计特性，记此非缺陷）；`SentimentClock` 的 `DataBoundary` 在 `SectionState` 外，恒显示。
- 图表数据：三组件的 `barOption/lineOption` 对缺失一律送 `null`（ECharts 不画），`SimilarDays` 还显式标「部分前向窗口无足够样本，对应柱不绘制（不补 0）」。
- 结论：设计已合规，**本轮不改业务代码**，只补确定性守卫把上述行为**锁死**。

### 37.2 20 例确定性守卫（3 个 colocated 新文件）
| 文件 | 例数 | 锁住的边界 |
|---|---|---|
| `src/features/analytics/RegimeDuration.test.tsx` | 7 | 四态 loading/error(alert)/空数据/有数据；duration 段 unavailable → 仅该段显「暂无数据」、柱状图/统计不渲染；**median=null → Stat 显「—」且柱状图该柱 `null`（捕获 EChart option 验证图形层不补 0）**；**median=0 → 显「0 天」真实零值（零≠缺失）**；离线缺真值维度逐条披露。 |
| `src/features/analytics/SentimentClock.test.tsx` | 7 | 四态；phase 段 unavailable → 当前相位段显「暂无数据」、DataBoundary 仍在（段外）；时序段 dates 空 → 时序图区域显「暂无足够广度历史生成时序图」不画图；**red_ratio=null → 显「—」不补 0**（真实 46.67 → 「46.67%」）；5 档时间窗口可选项齐全。 |
| `src/features/analytics/SimilarDays.test.tsx` | 6 | 四态；similar 段 unavailable → 仅该段显「暂无数据」、图表/样本卡不渲染；**前向窗口 n=0 → 该柱 `null`（捕获 EChart option 验证 data[0]===null 绝非 0）+ 显「部分前向窗口无足够样本」警告 + Stat 显「—」**；真实 up_ratio(86.7%) 如实展示。 |

测试手法：沿用 `InflectionScan.test` 范式——`vi.mock('@/api/read')` 直接替 `getBreadthAnalytics`（规避 MSW/zod），`vi.hoisted` 捕获 `EChart` 的 `option` 与请求，断言「图形层不补 0」；用真实离线夹具 `breadthAnalytics`（含全段真实数据）作 happy path，边缘用结构最小化 payload；统一 `retry:false, staleTime:0` 的 `QueryClient`，`findBy*` 统一 `FIND={timeout:5000}`。

### 37.3 踩坑（测试桩自身，非业务缺陷）
- **`Card` 标题是「离线数据边界（务必阅读）」，不是「离线数据边界」**：`getByText` 精确串匹配失败 → 改正则 `/离线数据边界/`。同理 `DataBoundary` 列出的缺真值维度文本是「连板高度（离线…）」整节点，需正则 `/连板高度/`。
- **`SentimentClock` 的 `normalize()` 入参必须是数组**：自造边缘数据把 `phase.series` 写成对象导致 `vals.filter is not a function` 崩溃；修正为 `series:{dates,labels,series:{维度:number[]}}` 正确形态。

### 37.4 实证结论
- 3 新文件 **20/20**；`tsc --noEmit` **0 错**；全量 `vitest run` → **596 passed / 1 skipped**（88 文件，+20），无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- `analytics` 至此 5/5 全收敛（含既有 `InflectionScan.test`）。剩余质量债：`admin/auth/catalog/guide/me/settings` 无组件测试；`dashboard`(3/1 偏薄，且 `Dashboard.test` 把 `IndexQuotes` mock 掉，真测 dashboard 需先解除该 mock)。

### 37.5 提交与推送
- commit（msg: `test(v2): analytics 三组件 20 例确定性守卫（四态/不补 0/零值≠缺失/独立降级）`）。
- `git fetch origin main` → `merge-base --is-ancestor` → `git push --dry-run origin main` → 正式推送 → 复校 local/remote SHA。
- 仅 stage 3 个新测试文件 + `docs/frontend-v2/V2-STATUS-PLAN.md`；红线目录与他人的未提交改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 38. dashboard 质量债收口：DashboardCustom / ProjectIntro 首次真实组件级覆盖（2026-11-12，继续 v2）

> 承接 §37「剩余质量债」中的 `dashboard`(3/1 偏薄，且 `Dashboard.test` 把 `IndexQuotes` mock 掉)。先勘实情：`DashboardCustom.tsx` 是 dashboard 逻辑最重的组件（localStorage 持久化、`?widgets=` URL 覆盖、`Signed` 带符号着色、5 个 widget 四态分发），此前**零组件级测试**——`Dashboard.test.tsx` 只把 `IndexQuotes`/`ProjectIntro` mock 成 `null`，`DashboardCustom` 根本没被独立覆盖；`ProjectIntro.tsx` 是纯静态 v1 Hero 1:1 移植、无任何动态数值。本轮回填这一空白。

### 38.1 源码取证结论：零真缺陷（诚实负结果，业务代码零改动）
逐行复核 `DashboardCustom.tsx` + `ProjectIntro.tsx` + 依赖（`Signed`/`WidgetBreadth`/`WidgetEventPool`/`WidgetBacktestRuns`/`BacktestBody`/`QueryState`）：
- `LS_KEY='ss-dashboard-widgets-v1'`；`WIDGETS` 固定 5 个（snapshot/recommendation/breadth/event/backtest）。`loadEnabled()` 对 localStorage 损坏 JSON / 非数组 / 缺省三种异常，均**回落默认全开**——已实现，无兜底造假。
- URL `?widgets=` 覆盖优先且不回写：存在时 `setEnabled(urlWidgets)` 且 useEffect 中跳过 `localStorage.setItem`，编辑面板被抑制（`editing && !urlWidgets`）。合法 id 过滤：只保留 5 个内的 id，非法值丢弃。
- `toggle` 增删；`active.length===0` 显「请在「管理组件」中至少启用一个面板」——诚实空态，非崩溃。
- `Signed` 三色：>0 → `#ff4d4f`(红涨) / <0 → `#00d486`(绿跌) / ===0 → `#9aa0b5`(中性灰) / `null|undefined` → `—`；后缀默认 `%`，`value.toFixed(2)`——守 A 股反向色，无取绝对值造假。
- 诚实空态：breadth 空数组 → 「breadth-timeseries 为空数组，未做填充」；event pool 空 → 「事件因子池为空」；backtest 空 runs → 「暂无回测运行记录」；无 summary → 「无可用回测摘要」；`snapshot`/`recommendation` 用 `isEmpty={false}` 不显空提示。
- `median_chg=null` → 显示 `—`（不补 0）；`median_chg=0` → 显示 `0.00%`（零≠缺失）。回测 `total_return_pct=-10.50%` 如实绿跌 `rgb(0,212,134)`，**不取绝对值**。
- `ProjectIntro` 全静态文案（「凭感觉」「当初为什么买？」「情绪温度计」「事件驱动信号」「决策闭环回测」等），无动态数值——已确认。
- 结论：设计已合规，**本轮不改业务代码**，只补确定性守卫把上述行为**锁死**。

### 38.2 25 例确定性守卫（2 个 colocated 新文件）
| 文件 | 例数 | 锁住的边界 |
|---|---|---|
| `src/features/dashboard/DashboardCustom.test.tsx` | 24 | 块1（8，持久化/覆盖/清单）：空→全 5 渲染；损坏 JSON→回落全开；非数组→回落全开；`[]`→空态(「至少启用一个面板」)；`?widgets=` URL 覆盖优先且不回写且抑制编辑；`foo,bar` 非法→回落全开；初始写回 5 项 + 取消 snapshot 写回 4 项；`[]` 起步勾选 breadth 写回 `['breadth']`。块2（16，各 widget 四态+诚实）：snapshot 成功(等「中高」再断言)/loading/error(alert)；recommendation 成功(`/推荐状态：ok/`+市场中性+免责)；breadth 成功(红盘比 60%/3000/2000/50/10/+1.20%)、`median_chg=null`→`—`、`=0`→`0.00%`、空数组→「暂无广度时序数据」、error(alert)；event 成功(`/P1-v40/`+600000+`/0\.90/`+`/long/`)、空 pool→「事件因子池为空」；backtest 成功(`+12.34%` `rgb(255,77,79)`/`-5.60%` `rgb(0,212,134)`)、负收益 `-10.50%` `rgb(0,212,134)` 不取绝对值、零收益 `0.00%` `rgb(154,160,181)`、空 runs→「暂无回测运行记录」、无 summary→「无可用回测摘要」。 |
| `src/features/dashboard/ProjectIntro.test.tsx` | 1 | 渲染冒烟：主标题 `/凭感觉/`、三痛点卡、三能力卡；断言 `body` 不含 `\d+%` 与「综合评分」（证明无动态数值）。 |

测试手法：沿用 `vi.mock('@/api/read')` 替 5 个 widget 对应函数（`getDailySnapshot`/`getDailyRecommendation`/`getBreadthTimeseries`/`getEventPool`/`getBacktestRuns`），配合真实夹具（snapshot/rec/breadth/eventPool/backtest 结构与 zod schema 对齐），不必拉 MSW；`localStorage.clear()` 于 before/afterEach；统一 `retry:false, staleTime:0` 的 `QueryClient`，`findBy*` 统一 `FIND={timeout:5000}`。

### 38.3 踩坑（测试桩自身，非业务缺陷）
- **jsdom 颜色归一化**：内联 `style="color:#ff4d4f"` 被 jsdom 归一化为 `style="color: rgb(255, 77, 79);"`（空格分隔）。原 `toContain('ff4d4f')` 必败；新增 `colorTriplet(el)` 抽 `rgb(r, g, b)` 三元组并断言 `255,77,79` / `0,212,134` / `154,160,181`。
- **内嵌裸文本精确匹配必败**：「推荐状态：ok」的 `ok`、`数据日 … · 模型 P1-v40 · 数量 2` 的 `P1-v40`、回测 `0.90`、`long` 都内嵌于大文本节点，独立元素不存在；改正则 `/推荐状态：ok/` `/P1-v40/` `/0\.90/` `/long/`（600000 是独立 span 故仍用精确串）。
- **时序**：断言成功态数据前必须先 `await findByText(<仅成功态出现的字段>)`（如「中高」「市场中性」「60%」「P1-v40」）等数据 resolve，否则仍是「加载中…」。

### 38.4 实证结论
- 2 新文件 **25/25**；`tsc --noEmit` **0 错**；全量 `vitest run` → **621 passed / 1 skipped**（90 文件，+25 例 +2 文件），无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- `dashboard` 至此 3 组件基本收敛（`DashboardCustom` 24 + `ProjectIntro` 1 + `Dashboard` 集成层既有 5 例）。注意 `Dashboard.test` 仍把 `IndexQuotes`/`ProjectIntro` mock 掉，dashboard 集成路径对 `IndexQuotes` 的真实覆盖仍依赖 §36 的 `IndexQuotes.test`——如实记此，非缺陷。剩余质量债：`admin/auth/catalog/guide/me/settings` 仍无组件测试。

### 38.5 提交与推送
- commit（msg: `test(v2): dashboard DashboardCustom(24)+ProjectIntro(1) 首次真实组件级守卫（持久化/URL覆盖/Signed三色/五widget四态/诚实空态）`）。
- `git fetch origin main` → `merge-base --is-ancestor` → `git push --dry-run origin main` → 正式推送 → 复校 local/remote SHA。
- 仅 stage 2 个新测试文件 + `docs/frontend-v2/V2-STATUS-PLAN.md`；红线目录与他人的未提交改动一律不 stage。
- ks 父仓库 submodule 指针留痕不推。

## 39. guide/me/auth(LoginWelcome)/catalog 四组件：首次真实组件级覆盖（2026-11-12，继续 v2）

> 承接 §38 末「剩余质量债：admin/auth/catalog/guide/me/settings 无组件测试」。实勘：这 8 个组件此前**零测试引用**（grep 确认无 mock/E2E/colocated）。本回先收口较小/偏静态的 4 个（guide / me / auth·LoginWelcome / catalog·CatalogView），交互重的 4 个（admin·UserManagement / auth·LoginPage / catalog·DataSourceView / settings·SettingsView）留 §40。

### 39.1 源码取证结论：零真缺陷（诚实负结果，业务代码零改动）
逐行复核 4 组件：
- `GuideView`：纯静态引导 + localStorage 进度（`STORAGE_KEY='ss_guide_steps'`，`readDone()` 损坏/非数组→回落 `[]`）；FAQ 搜索过滤；无动态行情数字。合规。
- `Me`：`getCurrentUser()`（localStorage `ss_user`，解析失败/null→显示「请重新登录」，不编造角色）；`useUserDashboard()` 四态（loading / error / 空 widgets（「暂无默认组件」）/ 有数据）；`created_at ?? '—'`；`WIDGET_LABELS[w] ?? w`（未知 widget 显原始 id）。合规。
- `LoginWelcome`：纯品牌门禁，`onLogin` 回调；演示账号 `demo / Demo@123`（与后端 seed 一致）真实展示；无未验证数字。合规。
- `CatalogView`：v1 功能全景，三档状态由 `mappingOf` 实时计算，清单来自 `v1Pages.generated`（磁盘实扫非手写）；搜索/状态筛选联动；无匹配→「没有匹配的功能页。」诚实空态。合规。

### 39.2 22 例确定性守卫（4 新 colocated 文件）
| 文件 | 例数 | 锁住的边界 |
|---|---|---|
| `src/features/guide/GuideView.test.tsx` | 6 | 渲染全部区块（无动态数字）；初始 0/4·0%；勾选→1/4·25% 且写回 localStorage；损坏 JSON→回落 0/4；FAQ 搜索命中（「同步」）/ 无命中（诚实空态）。 |
| `src/features/me/Me.test.tsx` | 8 | 未登录→「请重新登录」；admin / 普通用户徽章；`created_at=null`→「—」；空 widgets→「暂无默认组件」；已知 + 未知 widget 标签；loading→Loading；error→ErrorState（不伪装成无数据）。 |
| `src/features/auth/LoginWelcome.test.tsx` | 4 | 品牌主标题 / 平台名；演示账号 `demo / Demo@123`；脚注免责；点击「去登录」→ `onLogin` 一次。 |
| `src/features/catalog/CatalogView.test.tsx` | 4 | 五档 Stat 标签 + 诚实声明「列出 ≠ 已实现」；搜索无命中→空态；状态筛选联动（native 命中 / v1-only 下消失，用真实生成数据驱动）；按钮 `aria-pressed` 切换。 |

测试手法：`vi.mock('@tanstack/react-router')` 把 `Link` 透传为 `<span>`/`<a>`；`Me` 额外 `vi.mock('@/lib/auth')` + `vi.mock('@/lib/queries')` 直接替 `getCurrentUser`/`useUserDashboard` 控制四态；`CatalogView` 直接 import 真实 `V1_PAGES`/`mappingOf` 驱动确定性断言（断言依赖四档口径 63 native 成立）。**重要坑**：本仓**未装 `@testing-library/jest-dom`、无 setup 注册**——故「存在断言」改用 `getByText(...)` 抛错 + `toBeTruthy()`，绝不用 `toBeInTheDocument()`（全量 621 例的既定约定）。

### 39.3 踩坑（测试桩自身，非业务缺陷）
- **本仓无 jest-dom**：`toBeInTheDocument` 一律报 `Invalid Chai property: toBeInTheDocument`。改用 `expect(screen.getByText(x)).toBeTruthy()`（getByText 缺失即抛错，等价于存在断言）；`getByRole('alert')` / `queryByText(x)` 为 RTL/vitest 原生，照常。
- **Stat 标签与筛选按钮文字撞车**：`CatalogView` 的「已实现」「v1 保留」「待迁移」既是 Stat `label` 也是筛选 `button` 文案 → `getByText` 报「Found multiple elements」。按钮改用 `getByRole('button', { name: 'x' })` 定位；Stat 标签用 `getAllByText(x).length>=1` 去歧义。

### 39.4 实证结论
- 4 新文件 **22/22**；`tsc --noEmit` **0 错**；全量 `vitest run` → **643 passed / 1 skipped**（94 文件，+22 例 +4 文件），无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 剩余质量债（最后一批）：`auth·LoginPage` / `admin·UserManagement` / `catalog·DataSourceView` / `settings·SettingsView` 仍无组件测试（§40 收口）。

### 39.5 提交与推送
- commit（msg: `test(v2): guide/me/LoginWelcome/catalog 22 例确定性守卫（localStorage进度/账户四态/品牌回调/三档筛选）`）。
- ff-only 推送（fetch → ancestor → dry-run → push → SHA 复校）；仅 stage 4 个新测试文件 + docs。
- ks 父仓库 submodule 指针留痕不推。

## 40. 最后一批 4 个交互重组件：UserManagement / DataSourceView / LoginPage / SettingsView 首次真实组件级覆盖（2026-11-12，v2 收官）

> 承接 §39 末「剩余质量债：最后一批 4 个」。`UserManagement`/`DataSourceView`/`LoginPage`/`SettingsView` 此前**零测试引用**（grep 确认）。本回把 v2 前端组件级测试治理**收官**——至此 8 个目录全部收敛。

### 40.1 源码取证结论：零真缺陷（诚实负结果，业务代码零改动）
逐行复核 4 组件：
- `UserManagement`（574 行）：非 admin（`getCurrentUser` 返回 `null` 或 role≠admin）→ `EmptyState`「无访问权限」（不泄露任何用户数据）；三 tab（list/create/logs）；`listUsers` 四态（loading / error(alert) / 空 `[]`「暂无用户」/ 有数据）；删除保护（`deleteUser` 对自己与初始 admin 按钮 `disabled`）；创建空表单按钮 disabled、`createUser` 成功→「创建成功」；`listLogs` 成功渲染（`<b>{username}</b> → {action} → <code>{target}</code>`）。合规。
- `DataSourceView`（292 行）：`useDiagnostics` 枚举端点（过滤含 `<` 的路径参数端点）；`fetchRead` 真实 GET + 诚实 HTTP/信封/耗时/错误披露；`DataRenderer` 对 null/空数组/空对象/数组(前 50 行截断)/对象 各自诚实空态；`cell()` 缺失显 `—`。合规。
- `LoginPage`（352 行）：双态（welcome→`LoginWelcome`，form→左行情台 `MarketDesk` + 右表单）；`login()` 端到端（写 `ss_token`/`ss_refresh`/`ss_user` + `navigate`）；`MarketDesk` 用 `useQuery(getDailySnapshot)` 取温度/涨跌/AI 信号，缺失显 `—`（诚实红线）；演示账号一键填充。合规。
- `SettingsView`（223 行）：外观（主题/密度 radiogroup）；数据源与连接（`mocksEnabled()` 标识 MSW、真实 `fetch /health` 连通性检测、v1 地址保存）；账户（退出登录）；关于（`V1_PAGES_TOTAL` 磁盘实扫、构建模式、配色说明）。密度用 `getDensity`/`setDensity`（localStorage `ss_density`），v1 地址用 `getV1Base`/`setV1Base`（localStorage `ss_v1_base`，去尾部斜杠）。合规。

### 40.2 29 例确定性守卫（4 新 colocated 文件）
| 文件 | 例数 | 锁住的边界 |
|---|---|---|
| `src/features/admin/UserManagement.test.tsx` | 9 | 非管理员 / 登录失效→无权限空态；管理员→三标签 tablist；列表成功（用户名+计数）/ 取数失败 alert / 空数据「暂无用户」；删除保护（self/admin 按钮禁用）；创建空表单禁用 + 填后成功「创建成功」；操作日志成功。 |
| `src/features/catalog/DataSourceView.test.tsx` | 6 | 标题 + 返回入口；诊断失败 alert（不编造端点）；含 `<` 端点排除出下拉；选择+读取成功（HTTP 200 + 数据表）；读取失败诚实披露（不包装成功）；需参数端点示例占位。 |
| `src/features/auth/LoginPage.test.tsx` | 5 | 欢迎态→点「去登录」切表单态；一键填演示账号预填；空提交本地校验报错且未调 `login`；登录成功（写 token + `navigate` + 行情台真实温度 55 + 「事件因子信号暂无数据」）；登录失败（`clearAuth` + 错误态披露）。 |
| `src/features/settings/SettingsView.test.tsx` | 9 | 标题 + 「本机偏好」副标题；密度 radiogroup 初始「标准」→切「紧凑」写回 `ss_density` + `aria-checked` + 文案；v1 地址保存→「已保存」回显 + 持久化；当前模式 真实后端 / 开发模拟数据(MSW) 双分支；连通性检测成功（HTTP 200 + 「后端健康检查通过」）/ 失败（诚实「无法连接」）；退出登录（`clearAuth` + `navigate`）；关于区 `V1_PAGES_TOTAL=74` + 构建模式。 |

测试手法：`vi.mock('@tanstack/react-router')`（透传 `Link`/`useNavigate`/`useSearch`）；`UserManagement` 额外 `vi.mock('@/lib/auth')` + `vi.mock('@/api/admin')`；`DataSourceView` 额外 `vi.mock('@/lib/queries')` + `vi.stubGlobal('fetch', ...)` 桩真实 GET；`LoginPage` 额外 `vi.mock('@/api/endpoints')` + `vi.mock('@/app/guards')` + `vi.mock('@/api/read')`；**`LoginPage`/`MarketDesk` 依赖 `useQuery` → 渲染必须包 `QueryClientProvider`**（默认 `retry:false, staleTime:0`）；`SettingsView` 用**真实** `@/lib/preferences`（localStorage 真写回，断言 `localStorage.getItem` 验证持久化）。统一沿用「本仓无 jest-dom」约定：`getByText(...).toBeTruthy()` + `getByRole` + `queryByText(...).toBeNull()`。

### 40.3 踩坑（测试桩自身，非业务缺陷）
- **`vi.fn(() => vi.fn())` 的 `useNavigate` 每次调用返回全新内部 mock** → 在测试里再调 `mNavigate()` 断言的是「第二次调用得到的空 mock」，永远未被组件使用；且 `vi.mocked(...)` 强转后 `mNavigate()` 触发 TS2348（Mock 不可调用）。改为**稳定 `const mockNavigate = vi.fn()` + 工厂 `useNavigate: () => mockNavigate`**，直接断言 `mockNavigate` 被调用——组件与测试指向同一函数。
- **`UserManagement` 的「admin」多义**：列表行同时渲染 用户名 `admin` 与 角色 `admin`（且当前用户徽章也可能显 `admin`）→ `getByText('admin')` 报「Found multiple elements」。改用 `getAllByText('admin').length > 0` 去歧义。
- **`create_user` 是日志行内的分裂文本节点**（`<b>u2</b> → create_user → <code>newu</code>`）→ 精确串 `getByText('create_user')` 报「broken up by multiple elements」。改用 `getByText('create_user', { exact: false })`（子串命中 `<li>` 即可证明存在）。
- **`资金温度 55` 跨元素分裂**：「资金温度」在 `<span>`、「55」在独立 `<div>` → 精确串必败。拆成 `getByText('资金温度')` + `getByText('55')` 各自断言。
- **`LoginPage` 漏包 `QueryClientProvider`** → `MarketDesk` 的 `useQuery` 抛「No QueryClient set」。补 `QueryClientProvider` 包裹后通过。

### 40.4 实证结论
- 4 新文件 **29/29**；`tsc --noEmit` **0 错**；全量 `vitest run` → **672 passed / 1 skipped**（98 文件，+29 例 +4 文件），无回归。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- **v2 前端组件级测试治理收官**：`stock/` `analytics/` `dashboard/` `guide/` `me/` `auth`(LoginWelcome+LoginPage) `catalog`(CatalogView+DataSourceView) `admin`(UserManagement) `settings`(SettingsView) 全部收敛。零真缺陷、业务代码零改动（§33–§40 全程仅新增测试，未动任何 `.tsx`/`.ts` 业务实现）。
- 持续挂起项（非本轮范围）：v1 降级 / 退役评估；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 等红线目录与他人的未提交改动一律未 stage、未碰。

### 40.5 提交与推送
- commit（msg: `test(v2): 最后一批 4 组件 29 例确定性守卫（用户管理/数据源浏览器/登录页/设置 收官）`）。
- ff-only 推送（fetch → ancestor → dry-run → push → SHA 复校）；仅 stage 4 个新测试文件 + `docs/frontend-v2/V2-STATUS-PLAN.md`。
- ks 父仓库 submodule 指针留痕不推。

## 仍存质量债（后续迭代候选，已修正）
v2 前端组件级测试治理已于 §40 **收官**：`stock/`、`analytics/`、`dashboard/`、`guide/`、`me/`、`auth`(LoginWelcome+LoginPage)、`catalog`(CatalogView+DataSourceView)、`admin`(UserManagement)、`settings`(SettingsView) 全部收敛，全量 **672 passed / 1 skipped**（98 文件）。**v1 降级 / 退役评估已于 §41 + `V1-RETIREMENT-PLAN.md` 成文**（结论：v1 不能整体下线，43 实盘交易真实券商下单永久留 v1，其余 10 个 pinned 为实验性/低频/展示性页面作只读兜底并存）；`thesis/`、`backups/`、`scripts/`、`.trae/`、`artifacts/`、`docs/welcome.html` 及他人未提交改动不在本轮范围。
⚠️ 工作区有**其他任务改动**：`thesis/`、`backups/`、`scripts/`、`pages/54_*.py`、`55_*.py`、`modules/p1_portfolio_diag.py`、`.trae/`、`artifacts/`、`docs/welcome.html` —— 一律不 stage、不碰。

## 41. v1 退役评估 + 生产构建 smoke（2026-11-13，v2 开发收官）

> 承接 §40 收官后的两件收尾：① 实证 v2 能生产构建上线；② 把长期 parked 的「v1 降级 / 退役评估」落成文档，给出共存策略与退役路线图。

### 41.1 生产构建 smoke（确认真能上线）
- 命令 `npm run build` → **EXIT 0**，`✓ 935 modules transformed`，`✓ built in 950ms`。
- 主包 `index` **283.77 kB / gzip 85.01 kB**（实测优于此前估算的 342 kB）；`tanstack` 119.20 / 39.53；`schemas` 91.72 / 26.00；`echarts` 697.39 / **231.93**（**独立懒加载 chunk，不进首屏**）。
- 唯一警告：`echarts` 单 chunk > 500 kB（已通过路由级 `lazyRouteComponent` 规避首屏，可接受）。
- 类型与测试：`tsc --noEmit` 0 错；`vitest run` 672 passed / 1 skipped（98 文件）。
- 结论：v2 **已具备生产构建与上线条件**（日常分析浏览可全面由 v2 承担）。

### 41.2 v1 退役评估（成文于 `V1-RETIREMENT-PLAN.md`）
- 四档口径实测：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**（由 `v2Mapping.ts` 的 `statusCounts()` 实时统计，非写死）。
- 11 个 `v1-pinned` 逐项理由 + 处置建议（见文档 §3 表）：**仅 `43_实盘交易` 是红线性的真实券商下单能力（永久留 v1，v2 绝不碰）**；其余 10 个（`13/15/17/25/33/52/53/81/83/87`）为实验性 / 低频 / 展示性 / 社区类，v2 暂无等价计划，作只读兜底并存。
- 能力边界（诚实红线）：v2 不提供任何真实交易能力（`TradingAccount` 仅只读概览）；只读端点只查不写；未接入功能不造假；实时源不可用时优雅降级。
- 退役路线图：Phase A 已完结（对齐 + 测试治理 + 构建 smoke）；Phase B 建议 v1 进入冻结/只读兜底、不再新增 v1 页；Phase C 未来可选（把可替代 pinned 迁 v2 只读聚合，v1 仅留 `43` 一个进程）。
- 风险与回滚：双前端互为兜底（v2 故障 v1 仍可独立运行），不是负担。

### 41.3 实证结论
- v2 开发状态：**功能对齐完成 + 组件测试收官 + 生产构建验证通过**，达到生产级闭环。
- 四档口径不变：**63 native + 0 data + 11 v1-pinned + 0 v1-only = 74**。
- 文档交付：`docs/frontend-v2/V1-RETIREMENT-PLAN.md`（v1 退役评估与共存策略全文）+ 本 §41 指针。
- 红线目录与他人的未提交改动一律未 stage、未碰；ks 父仓库 submodule 指针留痕不推。

### 41.4 提交与推送
- commit（msg: `docs(v2): v1 退役评估与共存策略 + 生产构建 smoke 验证（v2 开发收官）`）。
- ff-only 推送（fetch → ancestor → dry-run → push → SHA 复校）；仅 stage `docs/frontend-v2/V1-RETIREMENT-PLAN.md` + `docs/frontend-v2/V2-STATUS-PLAN.md`。
- ks 父仓库 submodule 指针留痕不推。

## 42. v2 真实浏览器验收（2026-11-13，CDP 目检）

> 承接 §41 收官后老板指令"接着做 v2 开发验收"：用真实浏览器（而非单元桩 / 构建产物）验证 v2 跑起来是否真能用。

### 42.1 工具与口径
- 工具：`scripts/shoot_frontend_v2.py`（**CDP 直驱本机 headless Chrome，零 Playwright**，仅依赖 `websocket-client`；`--start-app` 自起 Vite，dev 模式 MSW 免真后端；覆盖暗/亮双主题 + 深链 + 六维缺维真实画布 + Zen）。
- 产物：`artifacts/shots/frontend-v2/report.json`（本地目检，不提交仓库）。
- 诚实红线：登录态由本地注入演示 token 驱动；采样缺失记 `null` 判失败、禁止补默认；截图必须 >1KB；跨主题比对若单主题/缺首页采样则如实标 `evaluated=false`，不伪装成通过。

### 42.2 验收结果（report.json 实测）
- **126 / 126 成功、0 失败；18 项红线检查全 PASS；跨主题比对 `evaluated=true`**（双主题 + 首页采样齐全）。
- 覆盖 **57 个路由态**：53 页 ×2 主题 + 6 深链 ×2 + 六维缺维 ×2 + Zen ×2。

### 42.3 关键红线在真实计算样式层面成立
1. **主题真生效**：dark `--color-sf-bg=#0f0f23` ≠ light `#f0f3f9`。
2. **A 股双套语义两主题恒等**：`ss-up=#ff4d4f`(红涨) / `ss-down=#00d486`(绿跌) / `doc-up=#009e6…` 在暗、亮两主题完全一致（交易屏红涨绿跌、报告体绿涨红跌互不串、light 块绝不覆盖）。
3. **W4-A 六维缺维诚实降级**：切到 `000001` 后缺维显「**缺失**」而非补 0；真实 ECharts 画布 1126×300；覆盖条「仅 4/6 维有效」；`date=null` 显「暂无权威数据日」；降级说明「逐维独立取数、独立降级」—— 单元桩测不到的"真实画布不画 0"在浏览器里坐实。
4. **W4-B 深链契约全部命中**：custom code 透传 `000001`（不硬编码 600519）、`view=deep` 首帧预选、中文 `hub_gyj_view` 映射 deep、`pick_stock` 单参落 quick、非法 code 不入 search。
5. **Zen 模式真实收起**：侧栏/顶栏 `display:none` 真实折叠、主区去边距、浮动开关「退出专注」可见且点击可退出。

### 42.4 结论与边界
- v2 前端在真实浏览器中暗/亮双主题全部真正渲染，所有设计红线、深链契约、诚实降级语义在真实计算样式层面成立 → **v2 开发验收通过**，可进入"v2 主用 + v1 冻结兜底并存"生产运营阶段。
- 本次验收**未改动任何业务代码**，仅产出本地目检快照 + report.json；红线目录与父仓库 submodule 指针均不动，无需提交代码。
- 本 §42 仅补记验收结论到状态文档（与 §41 同批文档文件），不 stage 任何代码/产物。

### 42.5 提交与推送
- commit（msg: `docs(v2): 补充 §42 真实浏览器验收结论（126/126 通过，18 红线全 PASS）`）。
- ff-only 推送；仅 stage `docs/frontend-v2/V2-STATUS-PLAN.md`；ks 父仓库 submodule 指针留痕不推。
