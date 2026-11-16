# StockSignal · v1 / v2 功能对标与能力边界（2026-11-16 parity 批次）

> **「完全做到」≠ 改标签。** 本轮以「v2 逐页、逐端点真实源码」为唯一判据，不采信 `v2Mapping.ts` 里的 `native` 标签，不把只读壳当成等价实现，也不把已完整承接的页面继续钉在 v1。
>
> 单一真理源：
> - 页面映射：`frontend-v2/src/features/catalog/v2Mapping.ts`（74 页精确匹配，四档状态）
> - 路由 / 导航：`src/app/router.tsx`、`src/nav/nav.ts`
> - 后端真实契约：`backend/api/*.py`、`backend/auth/routes.py`（以 Flask `test_client` 实测为准）
> - 跨语言契约守卫：`tests/unit/contract-drift.test.ts`、`tests/unit/backend-write-coverage.test.ts`

---

## 0. 本批结论（TL;DR）

| 结论 | 证据 |
|---|---|
| v2 此前**整批悬空**后端写端点：写操作全站 `useMutation` 零命中，只有 `admin.ts` / `chat.ts` / `endpoints.ts` 三处各自手写 | F1 双向源码审计 + `backend-write-coverage.test.ts` 新守卫 |
| 本批把 **A 类（后端已有 REST 写端点）全量补齐**：自选股、垃圾股、用户打分、四类价格预警、市场告警、股吧社区、账户设置/头像/注册/登出 | 真 Flask 探针 `E:/tmp/ss_parity_api_probe.log`（probe5 独立库）+ 新增 3 组 API/Query/MSW handler |
| 映射表存在**双向失真**：低报 53 星辰 AI / 52 股吧；高报 11/20/40/41/42/44/46 等只读壳 | 逐页源码取证，见 §2 |
| C 类实盘红线明确不做，v2 API 层零路径字面量 | 新守卫硬断言 `/cond-orders`、`/trade/orders`、`action=buy` 绝不出现 |
| 当前四档实时统计：**63 native + 0 data + 1 v1-only + 10 v1-pinned = 74** | `statusCounts()` 实测输出 |

---

## 1. 四分类口径（A / B / C / D）

| 类别 | 定义 | 本批处理 |
|---|---|---|
| **A** | 后端**已有** REST 写端点，v2 只缺 UI + 类型化 API 客户端 | ✅ **本批全量补齐** |
| **B** | 需**新增后端能力 / 算法端点**，v2 无等价实现 | 📋 诚实登记，下一批；页面标注「未承接」，不造假 |
| **C** | 实盘交易红线：真实券商下单与条件单自动执行 | 🔒 **v2 明确不做**，永久留 v1 |
| **D** | Streamlit 特有机制（`fragment` / `components.html` iframe / 桌面通知 / 页面级自动刷新） | ♻️ React / TanStack Query / Notification API 等价替代，不作为「v2 做不到」的理由 |

---

## 2. 映射表双向失真纠偏（以源码为准）

| v1 页 | 旧标注 | 真实状态 | 证据 |
|---|---|---|---|
| `53_星辰AI.py` | `v1-pinned`「独立 AI 对话，留 v1」 | **`native` → `/xingchen`** | v2 已有多会话 CRUD、四种回应风格、意图卡、追问 chips、停止生成、MD/JSON 导出、404 旧单回退、1.5s 轮询 |
| `52_股吧.py` | `v1-pinned`「社区抓取，低频遗留」 | **`native` → `/forum`** | v1 页首行即写「纯前端聚合，走后端 `/api/forum`」；后端 `forum_routes.py` 是完整 CRUD，非抓取遗留 |
| `44_智能条件单.py` | `native → /alerts` | **`v1-pinned`（C 类红线）** | 页内明写真实下单、`action=buy\|sell`、`/api/cond-orders/scan`、调度器自动扫描下单 |
| `43_实盘交易.py` | `v1-pinned` | **保持 `v1-pinned`** | QMT / easytrader 真实券商通道仅 v1 |
| `63_温度回测.py` | `native → /backtest` | **`v1-only`** | `/backtest` 是策略回测运行记录，不是牧羊人温度回测算法；模块错配，撤下假 native |
| `42_模拟交易.py` | `native`（note 空） | **`native` + 诚实 note** | v2 `/paper` 是只读壳，模拟账本写能力未承接 |
| `61_广度分化.py` | 压进 `/breadth` 无 note | **`native` + 诚实 note** | v2 `/breadth` 无 v1 的分化维度 |
| `95_数据导出.py` | 未声明缩水 | **`native` + 诚实 note** | v1 六类产物（CSV / Excel 多 Sheet / PDF / ZIP / 研报 HTML / 研报 MD），v2 `/export` 只有原始 JSON Blob |

防复发守卫：`src/features/catalog/v2Mapping.test.ts` 锁 53/52 为 native、44/43 为 pinned、缩水页 note 非空、native 路径必须是真实 `AppPath`、四档之和 = 74；另扫源码不含 `action=buy` 等红线字面量。

---

## 3. A 类 · 本批补齐清单（后端已有端点 → v2 已接线）

| 能力簇 | 后端端点（真 Flask 实证） | v2 落点 | 关键契约（实测） |
|---|---|---|---|
| 自选股 | `GET/POST/DELETE /api/watchlist`、`POST/DELETE /batch`（5 规则） | `/watch` → `WatchWritePanels` | 重复项 `200 + data:null + message='已在自选股中'`；非法入参 **422** |
| 垃圾股回避池 | `GET/POST/DELETE /api/junk-stocks`、`DELETE /batch`（4 规则） | `/watch` → `WatchWritePanels` | 批量删除 `{deleted: number[]}` |
| 用户打分 | `GET/GET:code/POST/DELETE /api/user-scores`（4 规则） | `/watch` → `WatchWritePanels` | score 0–100 整数；未存在的单条返回 `200 + data:null` |
| 四类价格预警 | `GET/POST/PUT toggle/DELETE /api/price-alerts`（4 规则） | `/alerts` → `AlertWritePanels` | `params` 是 **JSON 字符串**；非 price 类型 `target_price:0.0`、`condition:'above'`；缺参 **422** |
| 市场异动提醒 | `GET/POST read/read-all/scan`、`GET/POST config`（6 规则） | `/alerts` → `AlertWritePanels` | 非管理员 scan **403 `code:'forbidden'`**，管理员 `200 {inserted:n}`；`MarketAlert.created_at` 带 `Z` |
| 股吧社区 | `GET/POST/DELETE /api/forum/posts`、详情/点赞/评论（6 规则） | 新路由 `/forum` → `ForumView` | 详情自增 views；空标题 **422**；仅作者/管理员可删 |
| 账户 | `GET /me`、`/token-info`、`/logins`；`POST /settings`、`/avatar`、`/logout`、`/register` | `/me` → `AccountPanel` | `settings` 已解析为对象；非 data URL 头像 **422**；注册 `201 + code:'created'` |

**统一写层（本批基础设施）**：
- `src/api/write.ts` → `apiMutate<T>(path, method, body?, schema?)`：所有新增写请求统一走 `apiFetch`（Bearer + 401 单飞刷新 + 信封解包）；无响应体端点显式 `schema=null`，不静默成功。
- `src/lib/mutations.ts` → `useWriteMutation({path, method, body, schema, invalidateKeys})`：成功后统一失效查询，禁止乐观更新。
- `src/mocks/writeEnvelope.ts` → `writeOk` / `writeBadRequest`（**422**）/ `writeForbidden`（403）/ `writeNotFound` / 固定 `MOCK_WRITE_TS`。

**防漏接守卫**：`tests/unit/backend-write-coverage.test.ts` 从后端 Python 真扫 `@bp.post|put|delete` 与 `url_prefix`，断言每个非红线写端点要么在 `src/api/*.ts` 接线、要么进入 `HONEST_PENDING` 白名单（写明 B 类原因）；并断言红线端点绝不出现在 v2 API 层。

---

## 4. B 类 · 需后端新增能力（下一批，当前诚实登记）

| 页 | 缺口 | 当前 v2 状态 |
|---|---|---|
| `61_广度分化` | 分化维度算法未承接 | `/breadth` 只有部分聚合 |
| `63_温度回测` | `modules/temperature_backtest.py` 极端区回测 + 基准窗口 | `v1-only`，给 v1 直达链接 |
| `31_形态选股` | 形态识别服务端算法 | `/recommend` 无等价筛选 |
| `77_跨股财报筛选` | 跨股财务条件组合查询 | `/earnings-calendar` 仅日历 |
| `81_自然语言选股执行` | NL 解析有 `/nl-screen`，执行链路无 | 只解析不执行 |
| `95_数据导出` | PDF / Excel 多 Sheet / ZIP / 研报 HTML+MD 六类产物 | `/export` 仅 JSON Blob |
| `42_模拟交易` | 模拟账本写能力 | `/paper` 只读壳 |
| `51_复盘笔记` | 笔记写入 | `/review-notes` 问答式，无写笔记 |
| `73_自定义看板` | 看板布局持久化 | `/dashboard` 无布局写 |

---

## 5. C 类 · 实盘交易红线（v2 明确不做）

以下**整簇**永久留 v1，v2 不提供 UI、不提供 API 客户端、不在 MSW 注册：

- `pages/43_实盘交易.py`、`pages/44_智能条件单.py` 全页
- `/api/cond-orders`、`/api/cond-orders/scan`、`/api/trade/*`
- `action=buy|sell`、`live_mode` 开关
- `RealAccount` / `RealOrder` / `RealPosition` / `ConditionalOrder`
- `backend/broker/execute_order`、QMT / easytrader 券商通道
- 后台条件单调度器自动扫描真实下单

> 若未来要把真实下单带进 v2，属**覆盖长期红线**，必须由老板显式指令 + 单独合规评估；本批默认不触碰。

---

## 6. D 类 · Streamlit 机制的 React 等价替代

| v1 机制 | v2 等价实现 |
|---|---|
| `@st.fragment` 局部刷新 | TanStack Query `refetch` / `invalidateQueries` 精确失效 |
| `components.html` iframe 嵌入 | 原生 React 组件 + ECharts 容器 |
| `st.markdown` 注入桌面通知 script | Web Notification API + 明确用户授权 |
| 页面级定时自动刷新 | `refetchInterval` / 手动「检测」按钮，显式可控 |

不应以「Streamlit 有而 React 没有某控件」为由判定 v2 做不到。

---

## 7. 口径校正记录（以源码实测推翻旧表述）

- `64_投研圆桌.py` **不是**多角色讨论，是读本地 HTML 仪表盘片段 + MD/HTML 双导出；v2 `/predictions` 只有 prediction-log 校准日志。
- `59_市场温度计.py` 是牧羊人 8 指标 0–100 + 五档 + 极端区信号 + 历史情境类比 + 侧栏基准窗口；`50_市场情绪.py` 才是 12–15 个 `_*_sig` 信号函数。v2 `/market-sentiment` 对应 50，不是 59。
- `22↔24` 深链**已闭合**：`/legacy?pick_stock=...` → `lib/deeplink.ts` → `/stock/research?code=...`；出边回 `/stock/fundamentals?code=...`。缺口是 11/20 子页算法能力，不是深链。
- `95` 六类产物、`53` 剩余项（模型选择器 / 归档分组 + TTL=300 导出缓存 / popover、重试、清空二次确认、404 自愈落库）均为真实剩余，不宣称完成。
- `52` 不是「社区抓取遗留」——v1 与 v2 都走同一套后端 `/api/forum` CRUD。

---

## 8. 验证口径

- `npx tsc --noEmit`：0 错。
- `npx vitest run`：全量通过（本批新增 `backend-write-coverage` 5 例、`v2Mapping` 6 例、契约漂移 A 段 23 组夹具配对）。
- 真 Flask `test_client` 探针：独立库 `DATABASE_URL=sqlite:///E:/tmp/ss_probe5/app.db`，测全部非红线写端点；红线端点只查 `url_map` 注册，绝不调用。
- 诚实数据守卫：`honest-data.test.tsx` 扫全 `src`，禁止 `?? 0` / `|| 0` / `new Date()` 冒充数据日。
- 跨语言契约：`contract-drift.test.ts` A 段夹具 ↔ Zod 恒跑；B 段在 `SS_BACKEND_URL` 可用时拉真后端只读端点校验。

> MSW 演示态的时间戳是固定常量 `MOCK_WRITE_TS`，内存态 CRUD 仅为演示交互，不代表真实行情 / 真实账户数据。
