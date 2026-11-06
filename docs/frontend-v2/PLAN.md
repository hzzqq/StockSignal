# StockSignal 前端 V2 · 完整规划书（PLAN）

> 版本：2026-11-06 · 阶段：**只出规划，不写码**
> 文档族：`PLAN.md`（总纲/架构/契约/排期/验收）· `DESIGN.md`（视觉与图表规范）· `IA-MIGRATION.md`（信息架构与 74 页迁移）
> 配套进度：`.workbuddy/progress/frontend-v2.md`

---

## 0. 结论先行

老板三条要求 → 三条落地口径：

| 老板原话 | 落地口径 |
|---|---|
| 「用最新，最好用的技术」 | 采用 2026 主流共识栈（§2）。**版本冲突项不硬编**，给核实方法而非拍脑袋数字 |
| 「先做规划，不着急」 | 本阶段**只产出文档**，`frontend-v2/` 代码目录不创建，仓库现有文件零改动 |
| 「争取替代原版，要好上加好」 | 按**可逐步接管生产**设计：契约完整、灰度可切、可回滚、数据零编造；「好上加好」拆成 §8 的可评判指标，不接受形容词验收 |

**一句话架构**：`frontend-v2/` 独立 SPA 跑 5173，通过 Vite proxy 复用现有 Flask 后端（5050）；原 Streamlit 前端跑 8899 **一行不改**；两版吃同一份数据、同一套仓位真理源，靠端口隔离 → 路径灰度 → 逐页切流逐步替代。

**最大阻碍（唯一需要后端小改的地方）**：12 / 74 页绕过 API 直读本地 JSON。不补只读端点，新前端只能做空壳。详见 §4。

---

## 1. 真扫事实基线（2026-11-06，全部实测，非记忆）

| 项 | 实测值 | 取证方式 |
|---|---|---|
| 原前端页面文件 | **74 个 `.py`** | `ls pages/*.py` |
| 后端路由装饰器 | **93 个** | 35 `@bp.get` / 30 `@bp.post` / 12 `@bp.delete` / 5 `@bp.put` / 4 `@bp.route` / 6 `@app.get` / 1 `@app.route` |
| 蓝图 | **16 个** | `backend/app.py:96-110` `register_blueprint` |
| 导航一级类目 | **6 个** | `modules/widgets.py:673-778` `_NAV_GROUPS` |
| 绕过 API 直读本地文件 | **12 页** | 精确清单见 §4.1 |
| 响应信封 | `{status, code, message, data}` | `backend/utils/response.py`、`openapi.py:11-16` |
| CORS | `r"/api/*"`，`origins` 默认 `*` | `backend/app.py:75` |
| 认证 | JWT + refresh；公开白名单 `/api/auth/login\|register\|refresh` | `backend/openapi.py:41-46`、`backend/tests/test_auth_*` |
| 现有色板 | `UP=#ff4d4f`（红涨）`DOWN=#00d486`（绿跌）`SF_BG=#0f0f23` `SF_CARD=#1a1a2e` `SF_TXT=#e2e8f0` `SF_BORDER=#2d2d44` `SF_GRID=#23233c` | `modules/ui_theme.py:29-41` |
| 主题规则 | `finpro/terminal/aurora/cyber → dark`；`swiss/ink → light` | `modules/ui_theme.py:106` |
| 图表现状 | Plotly + 自定义 `starfield_dark` 模板 | `modules/ui_theme.py:56-66` |

**两处纠偏（重要，勿沿用旧记忆）**：

1. **端点是 93 不是 75**。`backend/openapi.py:6` 注释里的「75 个端点」是骨架阶段旧口径，已漂移。规划书一律以 93 为基线；实施前应以 `openapi` 实跑结果去重后再钉死。
2. **OpenAPI 只是骨架，不是完整契约**。`openapi.py:6-15` 自述：「路径全集 + 方法 + 分组 + 鉴权 + 统一信封」，**逐端点请求/响应字段 schema 待补**，且鉴权标注是「自动推断……文档下限而非权威」。因此**不能直接生成可信的 TS 类型客户端**（§4.3）。

**已内嵌、勿作独立页**：`11_股票选取` / `20_个股分析` 已内嵌进 `24_个股研究`（`widgets.py:726-728`）；`46_自选股监控` / `40_仓位管理` / `41_组合收益` 已内嵌进 `45_持仓中心`（`widgets.py:748`）。V2 路由表须沿用此收敛，别把重复入口搬回来。

---

## 2. 技术选型（2026-11-06 核实）

### 2.1 确凿项（可写进 `package.json`）

| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | **React 19.x** | 2026 主流；并发渲染、`use()`、Actions |
| 语言 | **TypeScript 5.9+ `strict: true`** | 契约不完整的项目尤其需要编译期约束 |
| 构建 | **Vite**（版本见 §2.3 待核） | 2026 共识：登录后内部工具 / dashboard 用 Vite SPA，优于 Next.js App Router |
| 样式 | **Tailwind CSS 4.3.4** | 2026-11-02 发布；CSS-first 配置 `@import "tailwindcss"` + `@tailwindcss/vite` |
| 组件 | **shadcn/ui**（Radix/Base UI  primitives） | 源码复制进仓、可完全改造，不是黑盒依赖 |
| 路由 | **TanStack Router** | 类型安全路由、文件式 `routeTree.gen.ts`、`.lazy.tsx` 按路由分包 |
| 服务端状态 | **TanStack Query v5** | 缓存/重试/失效/`staleTime` 分层，替代手写 `useEffect` |
| 客户端状态 | **Zustand** | 主题、导航折叠、深链预选等轻量 UI 态 |
| 校验 | **Zod** | 运行时校验（见 §4.3，本项目关键） |
| 包管理 / 运行时 | **pnpm 10 + Node 20+** | 2026 主流 |
| 测试 | **Vitest + React Testing Library + Playwright + MSW** | 单测 / 组件 / E2E / API mock 四层 |
| 图表 | **Apache ECharts 主 + Lightweight Charts 补** | 选型依据与 bundle 预算见 `DESIGN.md` §4 |

### 2.2 明确不选

- **不选 Next.js App Router**：本项目是登录后内部工具，无 SEO/SSR 需求；后端已是 Flask，再引入 Node BFF 多一层部署与鉴权边界，收益为负。
- **不选 Redux**：服务端状态由 TanStack Query 承担，客户端态用 Zustand 足够。
- **不选 CRA**：2023 起停止维护。
- **不选微前端（qiankun/Module Federation）**：双前端是**端口级隔离**，不是同一壳内共存，无需微前端复杂度。

### 2.3 ⚠️ 待核实项（诚实标注，不硬编）

WebSearch 2026-11-06 结果里 **Vite 版本口径互相冲突**：同时出现「Vite 5.4 终端输出」「Vite 6.0 已成默认」「Vite 官方 Migration from v7 文档」。因此规划书**不锁死 Vite 大版本**。

实施前用以下命令定稿并写回本节：

```bash
npm view vite version && npm view @vitejs/plugin-react version && npm view @tailwindcss/vite version
npm view react version && npm view typescript version && npm view tailwindcss version
```

**判定规则**：取 npm `latest` 稳定版（非 `next`/`rc`/`beta`），且 `@vitejs/plugin-react` 与 Tailwind Vite 插件的 peer range 必须兼容该 Vite 大版本；三者不一致时降 Vite 到插件共同支持的最高版本，并把结论记入本文件。

---

## 3. 架构与目录

### 3.1 双前端并存与灰度路径

```
现在                          阶段 A                        阶段 B                     阶段 C
8899 Streamlit (原版)         8899 原版  +  5173 V2         nginx / 路径分流          逐页切流
     │                            │                        /     → 8899 原版            │
     └── 5050 Flask ◄─────────────┴── Vite proxy /api       /v2  → 5173 V2            └── 全量 V2，原版保留可回滚
```

- **零竞争**：两版不同端口；V2 开发期 `vite.config.ts` 里 `server.proxy['/api'] → http://127.0.0.1:5050`，同源免跨域；生产期 Flask CORS 已开 `/api/*`。
- **可回滚**：原版代码与 8899 服务全程不动，切流开关（配置/路由表）一改即回。
- **运维红线**：不重启、不杀老板的 8899 服务。

### 3.2 目录（规划，尚未创建）

```
StockSignal/
├── app.py  pages/  modules/  backend/     ← 原版，全程零改动（backend 仅按 §4.2 新增只读端点）
├── docs/frontend-v2/                      ← 本次规划文档
└── frontend-v2/                           ← 【阶段 A 才创建，本阶段不建】
    ├── package.json  pnpm-lock.yaml  vite.config.ts  tsconfig.json
    ├── components.json                    # shadcn/ui 配置
    ├── src/
    │   ├── app/          router.tsx  providers.tsx  guards.tsx
    │   ├── api/          client.ts        # fetch 封装 + 统一信封解包 + 401 刷新队列
    │   │                 schema.ts        # Zod schemas（契约补齐后由 openapi 生成骨架再人工补）
    │   │                 endpoints/       # 按 16 蓝图分组的 query/mutation
    │   ├── features/     decision/ market/ breadth/ stock/ screener/ portfolio/ tools/
    │   │                 └── {components, hooks, queries, schema, types}.ts(x)
    │   ├── shared/ui/    # shadcn 组件 + 项目自定义 KPI 卡 / 决策卡 / 降权标记
    │   ├── shared/charts/# ECharts/Lightweight 封装，统一主题与涨色注入
    │   ├── styles/tokens.css             # 设计令牌（DESIGN.md §2）
    │   └── nav/nav.manifest.json         # ★ 单一真理源：导航/路由/深链
    └── tests/            unit/ e2e/ visual/
```

### 3.3 双份维护的治本解法

原版导航硬编码在 `modules/widgets.py::_NAV_GROUPS`，V2 若再抄一份必然漂移。

**方案**：新建 `frontend-v2/src/nav/nav.manifest.json` 作为 V2 侧唯一清单，描述 6 大类 / 子簇 / 路由 / 图标 / 深链参数 / 所需权限；`router.tsx` 与侧栏组件**都从它生成**。同时写一个只读校验脚本，把 manifest 与 `widgets.py::_NAV_GROUPS` 做名称比对，差异以告警输出（不自动改原版，避免污染）。这是护栏，不是同步器。

---

## 4. 契约层（P0，决定项目成败）

### 4.1 12 个绕过 API 的页面 · 精确清单

真扫 `grep -rlE "open\(|read_json|json\.load|daily_snapshot|sqlite3|pd\.read_" pages/`：

| # | 页面 | 推测依赖 | 现有 API 覆盖 | 处理 |
|---|---|---|---|---|
| 1 | `54_今日决策面板.py` | `data/daily_snapshot.json` | ❌ | 新增只读端点 |
| 2 | `97_决策回放.py` | 决策历史快照 | ❌ | 新增只读端点 |
| 3 | `98_仓位落地.py` | 决策快照 + 仓位 | ❌ | 新增只读端点 |
| 4 | `51_每日晨报.py` | 本地生成报告/事件情绪 | ⚠️ 部分 | 新增只读端点 |
| 5 | `36_每日荐股.py` | 荐股结果文件 | ⚠️ 有 `/junk-stocks` 等前缀但不等价 | 逐项核对 |
| 6 | `42_模拟交易.py` | 本地交易状态 | ✅ `/trade/orders`、`/trade/account` | 核对后直连 |
| 7 | `47_价格预警.py` | 本地预警配置 | ✅ `/price-alerts` | 核对后直连 |
| 8 | `73_自定义看板.py` | 本地布局配置 | ✅ `/config` | 核对后直连 |
| 9 | `74_告警引擎.py` | 本地告警规则 | ⚠️ 部分 | 逐项核对 |
| 10 | `86_网页作品集.py` | 静态 HTML 索引 | ✅ `/webapps/<path:filename>` | 直连 |
| 11 | `90_登录.py` | session/本地态 | ✅ `/api/auth/*` | 直连 |
| 12 | `93_系统配置.py` | 配置文件 | ✅ `/config`、`/admin/config` | 直连 |

> ⚠️ 上表「现有 API 覆盖」是基于真扫到的**蓝图内相对路径前缀**（`/watchlist`、`/price-alerts`、`/trade/orders`、`/config`、`/posts`、`/users`、`/admin/config`、`/user-scores`、`/junk-stocks`、`/cond-orders`、`/conversations`、`/history`、`/summary`、`/stats`、`/today`、`/token-info`、`/webapps/<path:filename>` 等）做的**初步判断，不是结论**。实施第一步必须逐页核对真实取数字段，标「⚠️」的尤其不能想当然。

### 4.2 建议新增的只读端点（**提案，非既有事实**）

命名统一 `/api/v2/read/`，语义**只读、不改业务、不写库**：

| 建议路径 | 返回 | 服务页面 |
|---|---|---|
| `GET /api/v2/read/snapshot/daily` | 当日决策快照（含 `date` 权威数据日、仓位建议、归因贡献） | 54 |
| `GET /api/v2/read/snapshot/history?from&to` | 历史快照序列 | 97 / 98 |
| `GET /api/v2/read/decision/replay?date` | 单日决策回放明细 | 97 |
| `GET /api/v2/read/report/morning?date` | 晨报正文与事件情绪 | 51 |
| `GET /api/v2/read/p1/signals` | P1 信号 `latest_date` 与内容 | 55 / 59 |

**硬约束**：
- 端点必须带出**权威数据日**（`row["date"][:10]` 之类），不是 `now()`；新鲜度判定依赖它。
- 遵守统一信封与中文错误文案；取不到返回 `null` / 「无数据」，**禁止补零或造占位**。
- 后端现有业务代码零改动，只在 `backend/api/` 新增一个蓝图并在 `app.py` 注册。

### 4.3 契约补齐三步走

1. **盘点**：实跑 openapi 生成器导出 `openapi.json`，得到**权威路径全集**（替代记忆里的 75 和静态扫出的 93），与 §4.1 的 12 页字段需求逐项比对，产出「已有 / 需补 / 需扩字段」三张清单。
2. **补端点**：按 §4.2 实施，后端测试 `backend/tests/test_security.py`（12 项）必须全过，并用独立库 `DATABASE_URL="sqlite:///E:/tmp/ss_probe/app.db"` 跑全量回归，**不要占用正在运行的后端数据库**。
3. **型安全**：基于 `openapi.json` 生成 TS 客户端**路径与方法**骨架；**响应字段一律用 Zod schema 运行时校验**（因为 openapi 自述字段 schema 待补、鉴权为推断）。校验失败 → 渲染错误态，绝不 `?? 0` 兜底。

### 4.4 认证

- 登录 → `POST /api/auth/login` 拿 access + refresh；access 存内存、refresh 按后端实际支持选择 httpOnly Cookie 或安全存储。
- `client.ts` 统一拦截 401 → **单飞刷新队列**（并发 401 只发一次 refresh，其余排队等待）→ 重放原请求；失败则跳登录并保留来源路由。
- 路由守卫读 `nav.manifest.json` 的权限字段；公开白名单只有 3 个 auth 端点 + 登录页。
- ⚠️ **Vite 陷阱**：任何 `VITE_` 前缀变量都会打进客户端 bundle，**密钥绝不放在 `VITE_*`**；本项目无第三方密钥需求，API 地址走相对路径 `/api`。

---

## 5. 数据语义红线（比技术栈更重要）

| 红线 | 规则 |
|---|---|
| **仓位真理源** | `modules/decision.derive_position(...)` 是**唯一**决策规则（clamp 5~95、`overall_promo=None` 不加不减）。V2 **只渲染后端算好的仓位，禁止在前端复制或重算规则** |
| **新鲜度** | `FRESH_WARN_DAYS=4 → 封顶 60%`、`FRESH_STALE_DAYS=8 → 封顶 40%`，判定基于**权威数据日**。前端只负责把降权状态**可见化**（虚线/灰化/角标），不参与计算 |
| **双套涨跌色** | 全站/交易屏 `--ss-up` 红涨绿跌；报告体/个股页价格域例外 `--doc-up:#009e60` 绿涨红跌。详见 `DESIGN.md` §3 |
| **强弱信号灯** | ▲/▼ 形状 + 颜色双编码，与价格域两套语义，**不得混用** |
| **缺失数据** | 返回 `null` → 渲染「无数据」态。**禁止编造、补零、插值填充** |
| **诚实表达** | 实验/回测差异如实展示（含负向结果），不得包装成碾压式领先 |

---

## 6. 迁移排期（按 6 大导航类目分波，不搞 74 页齐步走）

| 波次 | 范围 | 关键目标 | 退出条件 |
|---|---|---|---|
| **W0 地基** | 脚手架 + 契约盘点 + 登录 + `client.ts` + 令牌体系 | 打通 JWT 全链路 | 能用 demo 账号登录并拿到任一受保护数据；`test_security` 12/12 |
| **W1 决策中枢** | 54 决策面板 / 97 回放 / 98 仓位落地 / 51 晨报 / 55 P1 信号 | 最高光功能 + §4.2 只读端点全部落地 | 与原版**同日快照逐字段一致**（§8 一致性校验） |
| **W2 行情与板块** | 📈 类目（行情 7 + 板块 3） | 验证 K线/图表库选型与实时刷新 | 图表规范全项通过；首屏预算达标 |
| **W3 广度·温度** | 🌐 类目（5 子簇，页数最多） | 验证热力矩阵/时钟/聚类等复杂可视化 | ≥12 类图表映射全部落地 |
| **W4 个股研究** | 🔎 类目（4）+ 深链契约 | 验证 `hub_gyj_view` / `pick_stock` 深链等价 | 深链用例 100% 通过 |
| **W5 量化选股** | 🧪 类目（8） | 验证表单/筛选/回测交互 | — |
| **W6 持仓交易** | 💼 类目（4） | 验证写操作与乐观更新 | 与后端事务一致，无幽灵状态 |
| **W7 工具与社区 + Admin** | 🛠 类目（15）+ 92/93 + 90/91/96 | 长尾收口 | 6 类目全覆盖 |
| **W8 切流** | 灰度开关 / 回滚演练 / 原版保留 | 逐步接管 | 回滚演练成功 |

**每波固定验收**：①与原版同屏数据比对 ②空/错/降权态齐全 ③守卫测试 ④`git` 仅 FF 提交、只 add 本波文件。

---

## 7. 性能与工程约束

- **分包**：`manualChunks` 把 `@tanstack`、`echarts`、`react-vendor`、`ui` 拆独立 vendor chunk；路由级 `.lazy.tsx` 懒加载；图表库**按页异步 import**，不进主包。
- **bundle 预算**：首屏 JS gzip ≤ 200 KiB；单个图表页增量 ≤ 180 KiB（ECharts 全量 153–173 KiB，尽量按需引入图表类型）。
- **缓存分层**：实时行情 `staleTime 15s`；决策快照 `5min`；历史数据 `30min`；静态字典 `Infinity`。刷新策略服从后端数据日，不用 `now()` 兜底。
- **测试**：Vitest（Zod schema / 决策渲染纯函数）+ RTL（空/错/降权态）+ Playwright（登录、深链、灰度切换）+ MSW（API mock，mock 数据必须结构真实，不编造业务结论）。
- **代码卫生**：ESLint(ts) + Prettier + `strict`；禁用 `any`；中文文案集中 `i18n/zh-CN.ts`。

---

## 8. 验收标准 ·「好上加好」怎么算数

不接受形容词，全部可测：

| 指标 | 原版基线 | V2 目标 | 测法 |
|---|---|---|---|
| 首屏可交互 | Streamlit 整页重连，实测基线待测 | ≤ 1.5s（本地/局域网） | Playwright Lighthouse 或 Performance API，先测原版取真基线 |
| 切页体验 | 整页 rerun | 客户端路由，无可感知白屏 | Playwright 切页计时 |
| 数据一致性 | 真理源 | **逐字段 100% 一致**（同一 `date` 的快照/仓位/归因） | W1 起每波跑对比脚本，双端取同一 API |
| 空/错/降权态 | 覆盖不全 | 100% 数据型组件覆盖 | RTL 用例清单逐项核 |
| 可访问性 | 未系统评估 | WCAG 2.1 AA：键盘可达、颜色外编码、对比度 ≥4.5:1 | axe-core + 人工键盘走查 |
| 双套涨跌色 | 已有但易混 | 0 处误用 | AST/CSS 扫描 + 视觉回归 |
| 决策规则 | Python 单一真理源 | **前端 0 处复制实现** | 源码扫 `derive_position` 等价逻辑 |
| 回滚 | 无 | 配置一键回原版，演练成功 | W8 实测 |

> 首屏基线**尚未实测**，上表「原版基线」如实留空待测，禁止先填一个好看的数字。

---

## 9. 风险分级

| 级别 | 风险 | 影响 | 缓解 |
|---|---|---|---|
| 🔴 P0 | 12 页直读本地文件无 API | 新前端拿不到核心决策数据 → 空壳 | §4.2 补只读端点，W1 前完成 |
| 🔴 P0 | 双套涨跌色语义误用 | 误导交易决策 | `DESIGN.md` §3 边界表 + 令牌分离 + 自动扫描 |
| 🟡 P1 | OpenAPI 只是骨架 | 生成的 TS 类型不可信 | Zod 运行时校验；openapi 增量补 schema |
| 🟡 P1 | 双前端双份维护 | 导航/权限/文案漂移 | `nav.manifest.json` 单一清单 + 差异告警脚本 |
| 🟡 P1 | 前端偷偷重算仓位 | 两套决策口径 | §5 明令禁止 + 源码扫描 |
| 🟡 P1 | 数据陈旧被当新鲜 | 违反诚实红线 | 权威数据日 + 可见降权标记 |
| 🟢 P2 | Vite 版本口径冲突 | 选型反复 | §2.3 实测定稿 |
| 🟢 P2 | 双机/多 AI 重复劳动 | 改动互相覆盖 | 只 add 本任务文件、FF 推送、改前 `fetch`；原版目录全程只读 |

---

## 10. 本阶段做什么、不做什么

**做**：本文件 + `DESIGN.md` + `IA-MIGRATION.md` 三份规划；真扫事实基线；风险与验收口径。

**不做**（明确划界）：
- ❌ 不创建 `frontend-v2/` 代码目录、不写 `.ts/.tsx/.css`、不装依赖
- ❌ 不修改 `app.py` / `pages/` / `modules/` / `backend/` 任何现有文件
- ❌ 不动 8899 / 5050 正在运行的服务
- ❌ 不 `git add -A`、不提交（规划文档为 untracked，等老板验收后再按 FF 纪律决定）
- ❌ 不编造任何未实测的性能数字、API 字段或回测结论

**下一步待老板拍板**：①技术栈是否照 §2 定稿 ②W0 是否开工 ③规划文档是否提交。
