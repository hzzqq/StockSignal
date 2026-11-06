# W0 书面改动清单（开工前过目稿）

> 2026-11-06 16:55 · 状态：**待老板点头，尚未动第一行代码**
> 本轮只做只读勘查并产出本文件；`app.py`/`pages/`/`modules/`/`backend/` 及已提交的 3 份规划书**零改动**。
> 依据：`PLAN.md` §2.3（版本待核）、§4.3（契约盘点）、§6 W0。

---

## 0. 本轮真查结果（把「待核实」变成确定值）

| 核实项 | 真值 | 取证 |
|---|---|---|
| 本机 Node / npm | **v22.22.2 / 10.9.7** | `node -v` `npm -v` |
| pnpm | **未安装** | `pnpm -v` NOT FOUND |
| registry | `https://registry.npmjs.org/` | `npm config get registry` |
| `frontend-v2/` | **不存在** | `ls -d`（符合"只出规划"边界） |
| 后端配置口 | `DATABASE_URL` 环境变量生效，默认 `backend/data/app.db` | `backend/config.py:78-79` |
| 调度器开关 | `PYTEST_CURRENT_TEST` 或 `app.config['TESTING']` 或各 `STOCKSIGNAL_ENABLE_*_SCHEDULER=0` | `market_alert_engine.py:231-235`、`p1_sync_scheduler.py:47-51` |
| **OpenAPI 实跑** | **OpenAPI 3.0.3 / 64 paths / 87 operations** | 独立库 `DATABASE_URL=sqlite:///E:/tmp/ss_probe/fev2_openapi.db` + `PYTEST_CURRENT_TEST=1` 跑 `create_app()` → `build_spec(app)` |

**实跑安全性**：设了 `PYTEST_CURRENT_TEST=1` 与两个 `STOCKSIGNAL_ENABLE_*=0`，日志确认 5 个调度器全部「检测到测试环境，跳过」；用独立 SQLite 库，**未连、未锁、未重启 5050 在跑的后端**。

---

## 1. ⚠️ 端点口径纠偏（覆盖 `PLAN.md` §1）

| 口径 | 数 | 含义 |
|---|---|---|
| 静态 grep 装饰器 | **93** | 含非 `/api` 路由、文档自举端点、同路径多方法 |
| **OpenAPI 实跑契约面** | **64 paths / 87 operations** | 新前端真正能对接的**权威基线** |

差异来源已查清（`backend/openapi.py:74-78`）：

```python
if rule.rule in ("/api/openapi.json", "/api/docs"): continue   # 文档自举端点不进 paths
if not rule.rule.startswith("/api/"): continue                 # admin_ui 等非 API 路由不进契约面
```

**结论**：`PLAN.md` 里「93 端点」应改为**双口径表述**——静态装饰器 93 / 实跑契约面 64 路径 87 操作；`test_openapi_spec.py` 钉的是后者。W0 生成的 TS 客户端以 **64/87** 为准。

**顺带挖出一个既有问题（不在 W0 范围，需单独点头）**：`openapi.py` 的 `TAGS` 字典只有 **13** 项，实跑 operation 里实际出现 **16** 个 tag，其中 7 个走了 `bp.capitalize()` 兜底命名：`Trade` / `Stock_tags` / `Tasks` / `Stocks` / `Recommendations` / `Research_run` / `Root`。后果是 API 文档分组名风格不一（`Stock_tags` 带下划线、`Tasks` 复数），生成的客户端方法分组也会跟着丑。修法是给 `TAGS` 补 7 项，属**后端改动**，建议单开一轮，不混进 W0。

---

## 2. 版本定稿（覆盖 `PLAN.md` §2.1 / §2.3）

WebSearch 文章里的 Vite 5.4 / 6.0 / TS 5.9+ **全部滞后于 npm 实际**。`npm view <pkg> version` 实测 latest：

| 包 | 定稿版本 | 兼容性验证 |
|---|---|---|
| vite | **8.3.6** | engines `^20.19.0 \|\| >=22.12.0` → 本机 22.22.2 ✅ |
| @vitejs/plugin-react | **6.2.1** | peer `vite: ^8.0.0` ✅；另 3 个 peer 均为 **optional**（`peerDependenciesMeta` 已核实），不会阻塞安装 |
| @tailwindcss/vite | **4.3.4** | peer `vite: ^5.2.0 \|\| ^6 \|\| ^7 \|\| ^8` ✅ |
| tailwindcss | **4.3.4** | 与 Vite 插件同版本 ✅ |
| react / react-dom | **19.3.1** | TanStack Router peer `>=18 \|\| >=19` ✅、Query peer `^18 \|\| ^19` ✅ |
| typescript | **7.0.2** | engines `>=16.20.0` ✅ —— **但见下方风险** |
| vitest | **5.1.0** | peer `vite: ^6.4 \|\| ^7 \|\| ^8` ✅；engines `^22.12 \|\| ^24 \|\| >=26` → 本机 ✅ |
| @tanstack/react-router | **1.170.46** | engines `>=20.19` ✅ |
| @tanstack/react-query | **5.106.1** | peer `^18 \|\| ^19` ✅ |
| zustand | **5.0.16** | — |
| zod | **4.6.7** | — |
| echarts / lightweight-charts | 6.1.0 / 5.2.1 | W2 图表波才装，W0 不装 |

**⚠️ 唯一未闭合风险 —— TypeScript 7.0.2**：TS 7 是 native 重写的大版本，`npm view` 只能证明 engines 满足，**不能证明与 Vite 8 / Vitest 5 / TanStack Router 的类型解析兼容**。因此这是**验证项不是结论**：
- W0 装完立刻跑 `npx tsc --noEmit`；
- 若因 TS 7 报错且非我们代码问题，**降到 TS 5.9.x 最新补丁**并把结论回写本文件与 `PLAN.md`；
- 不允许"先装了再说、报错就忽略"。

---

## 3. W0 要动的文件（精确清单）

### 3.1 新建 —— 全部在 `frontend-v2/` 内，现有目录零影响

| 文件 | 内容 |
|---|---|
| `package.json` / `package-lock.json` | §2 定稿依赖；scripts: `dev` `build` `typecheck` `test` |
| `vite.config.ts` | React + Tailwind 插件；`server.proxy['/api'] → http://127.0.0.1:5050`；`manualChunks` 分包 |
| `tsconfig.json` / `tsconfig.node.json` | `strict: true`，路径别名 `@/*`，`noEmit` |
| `index.html` | 挂载点，中文 lang |
| `.gitignore` | `node_modules/` `dist/` `.env.local` `*.local`（**防止误提交 node_modules**） |
| `.env.example` | 只有 `VITE_API_BASE=/api` 之类**非密钥**项；注释写明「密钥禁放 `VITE_*`」 |
| `src/main.tsx` | 挂载 + Providers |
| `src/app/providers.tsx` | QueryClientProvider + RouterProvider + 主题 |
| `src/app/router.tsx` | 最小两根路由：`/login`、`/`（占位）；类型安全路由骨架 |
| `src/app/guards.tsx` | 未登录重定向，保留来源路由 |
| `src/api/client.ts` | fetch 封装 + 统一信封解包 + 401 单飞刷新队列 |
| `src/api/schema.ts` | Zod：信封 `EnvelopeResponse` + 登录响应（**字段逐个校验，禁止 `?? 0`**） |
| `src/styles/tokens.css` | `DESIGN.md` §2 令牌（含双套涨跌色） |
| `src/nav/nav.manifest.json` | 最小骨架：仅登录 + 占位根目录 |
| `src/features/auth/LoginPage.tsx` | 登录表单（中文文案、错误态） |
| `tests/unit/envelope.test.ts` | 信封/Zod 校验单测 |

### 3.2 不碰（红线）

- ❌ `app.py` / `pages/` / `modules/` / `backend/**`（含 `openapi.py` TAGS 补齐，单开一轮）
- ❌ 8899 Streamlit、5050 Flask **不重启、不杀**
- ❌ 不改已提交的 `PLAN.md` / `DESIGN.md` / `IA-MIGRATION.md`（口径回写列为 W0 的**第一个动作**，见 §6）
- ❌ 不写业务页面、不装图表库、不做 12 页只读端点（那是 W1）

---

## 4. 为什么

| 动作 | 理由 |
|---|---|
| 先定版本再装 | peer/engines 已全绿，避免装完返工；TS 7 单独设验证关卡 |
| 契约以 64/87 为准 | 静态 93 含非 API 路由，拿它生成客户端会多出无效方法 |
| W0 只做登录链路 | JWT + refresh + 401 刷新队列是**全站数据入口的地基**，不打通后面每页都要返工 |
| 独立目录 + 端口 | `PLAN.md` §3.1 灰度路径的前提，原版零改动、随时可回滚 |

---

## 5. 怎么验证（每条可判定，红了即停）

| # | 检查 | 通过标准 |
|---|---|---|
| 1 | `npm install` | 成功，无 peer 冲突报错 |
| 2 | `npx tsc --noEmit` | **0 error**（TS 7 兼容性判定点，失败按 §2 降级或停） |
| 3 | `npm run build` | 成功产出 `dist/`，首屏 JS gzip ≤200 KiB |
| 4 | `npm run dev` | 5173 可访问；`/api/health` 经 proxy 返回 200（**复用现有 5050，不重启**） |
| 5 | 登录链路 | demo 账号走通 `/api/auth/login`，拿到 token；登出/过期跳登录且保留来源路由 |
| 6 | Vitest | `tests/unit/envelope.test.ts` 通过（含畸形信封、缺字段 → 错误态，不兜底） |
| 7 | 守卫回归 | `test_public_numbers_consistency.py` 等不因新增目录变红 |
| 8 | 污染检查 | `git status` 显示现有文件零改动；`node_modules/` 未进暂存区 |
| 9 | 后端安全 | 全程用独立库跑 Python 回归，不碰运行中的 `backend/data/app.db` |

---

## 6. 点头后的执行顺序（严格按序，每步留检查点）

1. **口径回写**：把 §1 双口径、§2 版本定稿写回 `PLAN.md` §1/§2（单独一次提交，不混代码）
2. 建 `frontend-v2/` 骨架与配置文件
3. `npm install` → `tsc --noEmit`（TS 7 关卡，不过就停）
4. `client.ts` + Zod + 登录页
5. 跑 §5 全部 9 项验证
6. 密钥/大文件扫描（重点 `node_modules` 未被暂存）
7. 只 add `frontend-v2/` 本波文件 + 口径回写 → FF 提交推送，回报 SHA

---

## 7. 三个待你点头项

| # | 决策 | 我的推荐 | 另一选项 |
|---|---|---|---|
| 1 | **包管理器** | **npm 10.9.7**（本机现成、零额外步骤）。`PLAN.md` 写的 pnpm 10 本机没装，改用 npm 只需将来删 lockfile 重装，成本低 | `corepack enable pnpm` 保持与规划一致，但多一个变量 |
| 2 | **TypeScript** | **7.0.2 + `tsc --noEmit` 关卡**，不兼容就降 5.9.x 并如实回写 | 直接保守用 5.9.x（放弃"最新"） |
| 3 | **openapi TAGS 补 7 项** | **W0 不做，单开一轮**（会动后端，避免混入本波） | 并进 W0 一起改 |

---

## 8. 显式暴露的风险

- **双机重复劳动**：Trae 同在主区。本波只 add `frontend-v2/` 相关文件，改前 `fetch` + `merge-base` 判定，FF only，禁 `git add -A`。
- **`node_modules` 误提交**：几万个小文件，必须 `.gitignore` 先落地再 `npm install`（§6 顺序已锁）。
- **TS 7 未知兼容**：见 §2，设了硬关卡，不静默吞错。
- **既有红灯仍在**：`test_quality_numbers_sync.py::业务模块` 202/203 漂移（上一轮已挂账），本波不顺手修，避免与另一会话冲突。

**回「1」我按 §6 开工；要改哪个决策直接说编号。**

---

## 9. 执行记录（2026-11-06 W0 落地）

> 老板回「1」后执行 §6。结论：**口径回写单提交（`bd78d7c`），骨架与登录链路已落地待提交。**

### 9.1 三处清单预测被实测修正（诚实回写）

| 预测 | 实测 | 处理 |
|---|---|---|
| TS 7.0.2 设 `tsc` 硬关卡，不兼容就降 5.9.x | **TS 7.0.2 通过**（`tsc --noEmit` exit 0） | 不降级；但需改 2 处：① `baseUrl` 在 TS7 被移除→删除该键（`paths` 相对 tsconfig 解析）；② `manualChunks` 对象式被 Vite 类型拒→**推迟到 W2 图表库接入**（W0 无图表依赖，不值得为类型摩擦留代码） |
| 首屏 JS gzip ≤200 KiB | **126.5 KiB**（407 KB raw） | 达标 ✓；react+router+query+zustand+登录页，未含图表库 |
| /api/health 经 proxy 返 200 | **5050 返回 502**（上游未服务） | proxy 配置正确（5173→5050 转发验证过）；**真实登录 E2E 因 5050 未就绪未完成**，列为待补 |

### 9.2 验证结果（§5 九项）

| # | 检查 | 结果 |
|---|---|---|
| 1 | `npm install` | ✅ 72 包，无 peer 冲突 |
| 2 | `tsc --noEmit` | ✅ exit 0（TS 7.0.2 兼容，修 baseUrl/manualChunks 后通过） |
| 3 | `npm run build` | ✅ dist 产出，gzip 126.5 KiB ≤200 |
| 4 | `npm run dev` + proxy | ⚠️ 5173 正常服务（`id="root"` 200），`/api` 已转发 5050；**5050 返 502 故 health 未达 200** |
| 5 | 登录链路 | ⚠️ 代码完整（Zod 严格校验 + 401 单飞刷新 + 来源路由保留），**真实后端 E2E 因 5050 未就绪未完成** |
| 6 | Vitest | ✅ 8/8 通过（envelope 缺字段即抛错、LoginData 校验） |
| 7 | 守卫回归 | ✅ docs/数字三套守卫 31 项全过（排除已挂账的 `业务模块` 202/203 漂移） |
| 8 | 污染检查 | ✅ `node_modules` 被 gitignore；app.py/pages/modules/backend 零改动 |
| 9 | 后端安全 | ✅ 全程未连运行中的 5050 / `backend/data/app.db`；OpenAPI 实跑仍用独立库 |

### 9.3 待补（不阻塞提交，需老板点头）

- **#4/#5 真实 E2E**：待 5050 后端确认就绪后，用 demo 账号走通 `/api/auth/login` → token → 过期刷新 → 来源路由。
- **openapi TAGS 补 7 项**（W0 清单 §7 决策 3 已定：单开一轮，不混进本波）。
- **`业务模块` 202/203 漂移**（上一轮已挂账，非本波）。

### 9.4 提交边界

- 本波 **只 add** `frontend-v2/`（源码+配置+lockfile，node_modules/dist 被 gitignore）+ `docs/frontend-v2/W0-CHECKLIST.md`。
- **不碰** `backups/shepherd_history_restored.csv`（他会话）、`.trae/`、`artifacts/`、`thesis/*.docx`（均非本波）。
- FF only，禁 `git add -A`。
