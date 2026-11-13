# StockSignal 前端 V2 · 星辰 AI（53_星辰AI）设计草案

> 状态：设计阶段（老板 2026-11-13 拍板"先出设计方案"）。**本文不写业务代码**，只定架构、后端复用契约、数据模型、Dev mock、主题/诚实红线、迁移风险与落地步骤。
> 依据：v1 `pages/53_星辰AI.py`、后端 `modules/background_tasks.py` + `backend/tasks/worker.py(_handle_ai_consult)`、v2 `@/api/client.ts` + `@/api/admin.ts` 现有约定（均已实读，非推测）。

---

## 0. TL;DR

- v2 **当前没有**星辰 AI，它是 11 个 `v1-pinned` 之一（`53_星辰AI.py`，备注"独立 AI 对话，留 v1"）。本草案是从零在 React 栈重建，不是迁移。
- **后端零改动（红线）**：复用现有 `ai_consult` 后台任务 + `/api/chat/*` 对话持久化 + `Bearer` 鉴权。v2 只新增前端。
- **复用 v2 现有能力**：请求走 `@/api/client.ts` 的 `apiFetch<T>`（自动带 token、401 单飞刷新、解包统一信封、Zod 严格校验）；状态走 TanStack Query + Zustand；代理 `/api → 5050` 的 dev 链路不变。
- **设计参考（老板 2026-11-13 指定，优先借鉴）**：`E:/project/ks/FinPilot` 前端——其栈与 v2 近同构（React 19 + Vite 8 + zustand 5 + react-markdown 10 + react-router 7），已有成熟范式：`store/chat.ts`（zustand 多会话 + 消息 `kind/status/process/toolCall/paramPrompt` 判别模型）、`ChatPage`（意图分类→工具/分析/边界拒绝 + 流式 `status` + 参数追问 + 自动滚动 + 空态 hero）、`MessageBubble`/`ProcessCard`/`ChatInput`/`ChatToolbar`。**仅借鉴前端 UX/状态范式与组件拆分；后端仍用 StockSignal 自有 `ai_consult` + 对话持久化，绝不合并 FinPilot 后端（两套后端/任务体系不同）。**
- 还原 v1 关键交互：回应方式选择器（quick/report/debate/teach）、问题分析卡（规则引擎先解析意图、零 LLM 成本）、追问 chips、多会话、导出、模型徽标诚实态。
- 诚实红线：跟随 `data-theme`、A 股双套语义不串、未配置 LLM 显"规则引擎模式"、空/错态不造假。
- 约束：新增路由须显式注册进 `modules/widgets._NAV_GROUPS`（6 类目 / 子簇≤8 / 图标唯一），并同步 `shoot_frontend_v2.py` 的 `ROUTES` 与 `tests/test_frontend_v2_route_coverage.py` 守卫。

---

## 1. 现状：v1 星辰 AI 是什么、为什么 v2 没有

v1 `53_星辰AI.py` 是一个**金融风 AI 对话 + 多市场智能股票分析师**页面，能力相当完整：

- 对话界面：user 右 / assistant 左，带边框气泡区分；时间戳 + 复制回答按钮；跟随全局主题（白天/暗夜）切换。
- 数据来源：接后端 `ai_consult` 后台任务（独立拉取数据、结构化研判），不走页面内同步计算。
- 持久化：按登录用户维度，后端存对话历史（旧单记录 `/api/chat/history` + 新多会话 `/api/chat/conversations*`）。
- 回应方式选择器：`⚡快速问答 / 📋深度研报 / ⚔️多空辩论 / 🎓教学解释`（下发 `style` 给 `ai_engine.STYLE_PRESETS`）。
- 问题分析卡：提交时规则引擎先解析意图（类型/置信度/深度模式），在等待区先行展示——**零 LLM 成本**。
- 追问建议 chips：AI 回答后附 2~3 条按意图分类的可点击追问（静态模板）。
- 模型徽标：顶部如实显示当前 LLM；未配置时显"规则引擎模式"（诚实态）。

**为什么不迁**：它深度依赖 `modules/background_tasks.py`（Streamlit 侧任务客户端）+ `ai_consult` 后台任务 + 对话持久化端点，技术栈与 v2（React SPA）不兼容；且属"独立 AI 对话"非核心分析功能，故按《V1-RETIREMENT-PLAN》留 v1 兜底。**v2 重建时后端契约完全可复用**，只是前端从 Streamlit 换成 React + 现有 `@/api` 客户端。

---

## 2. 目标 / 非目标

**目标（MVP）**
- 在 v2 提供一个等价的星辰 AI 对话页：提交问题 → 后台 `ai_consult` 任务 → 轮询进度 → 渲染结构化研判（markdown + 引用徽标 + 分析卡）。
- 还原：回应方式选择器、问题分析卡、追问 chips、多会话（列表/新建/删除/导出）、模型徽标诚实态、复制回答、滚动到底部。
- 全部走现有 `@/api` 客户端与 `/api` 代理；dev 无后端时 MSW 仿真任务流转。

**非目标（本草案不含）**
- 不碰后端 `ai_consult` / 对话端点 / `ai_engine` 实现（红线）。
- 不做 H1 研究智能体（`_handle_ai_research`，多步工具调用 + 引用溯源）——那是另一个任务类型，可后续独立评估。
- 不引入新的 LLM provider；模型选择仅透传 v1 既有 `model` 字段。

---

## 3. 后端契约（实测，复用不变——红线）

> 所有路径相对 `BASE = import.meta.env.VITE_API_BASE ?? '/api'`，dev 经 Vite proxy 转发到 Flask `5050`。鉴权：`Authorization: Bearer <ss_token>`（由 `apiFetch` 自动注入，401 走单飞刷新）。统一信封：`{status:'ok'|'error', code, message, data}`。

### 3.1 后台任务（ai_consult）
| 动作 | 方法 / 路径 | 请求体 | 成功返回（data） |
|---|---|---|---|
| 提交 | `POST /api/tasks/` | `{"type":"ai_consult","payload":{...}}` | `{"task_id":"<uuid>"}` |
| 轮询 | `GET /api/tasks/<task_id>` | — | 任务对象：`{status:"pending"\|"running"\|"success"\|"error"\|"cancelled", result?, logs?, error?}`（成功时 `result` = `ai_engine.ai_answer` 结构化研判） |
| 取消 | `DELETE /api/tasks/<task_id>` | — | 200 标记 CANCELLED（执行线程不强杀，文案如实"已停止等待"） |

`ai_consult` payload（`_handle_ai_consult` 实测字段）：
```json
{
  "question": "太极实业 600667 怎么样？",
  "context": { "history": [ {"role":"user","content":"..."}, {"role":"assistant","content":"..."} ] },
  "style": "quick | report | debate | teach",   // 非法值由 ai_engine 兜底 quick
  "model": "可选，用户选择模型名；空/非法由 resolve_model 回落 style 分层默认"
}
```
> **实现期需对齐**：`ai_engine.ai_answer` 的实际返回结构（正文 markdown 字段名、引用 `[S#]` 列表、分析卡字段）须在落地时读 `modules/ai_engine.py` 真返回值定 Zod schema，本文不臆造。

### 3.2 对话历史（旧单记录，向后兼容）
| 动作 | 方法 / 路径 | 请求体 | 返回 |
|---|---|---|---|
| 读取 | `GET /api/chat/history` | — | `data: { messages: ChatMessage[] }` |
| 保存 | `POST /api/chat/history` | `{"messages": ChatMessage[]}` | `status:'ok'` |

### 3.3 对话多会话（T-311，新）
| 动作 | 方法 / 路径 | 请求体 | 返回 |
|---|---|---|---|
| 列表 | `GET /api/chat/conversations` | — | `data:{conversations:[{id,title,updated_at,...}]}`；**404 → 前端回退旧单记录模式** |
| 新建 | `POST /api/chat/conversations` | `{"title":"新对话"}` | `data:{id,title}` |
| 读消息 | `GET /api/chat/conversations/<id>` | — | `data:{messages:ChatMessage[]}` |
| 存消息 | `POST /api/chat/conversations/<id>` | `{"messages":ChatMessage[]}` | `status:'ok'` |
| 删除 | `DELETE /api/chat/conversations/<id>` | — | `status:'ok'` |
| 导出 | `GET /api/chat/conversations/<id>/export?format=markdown\|json` | — | markdown=raw bytes(附件) / json=信封 `{data:{...}}` |

### 3.4 ChatMessage 形态（v1 实测字段，v2 收紧为严格 schema）
```ts
// 借鉴 FinPilot store/chat.ts 的判别消息模型（v2 用 Zod 严格收紧）
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string                 // markdown 正文
  kind?: 'text' | 'tool' | 'param-prompt'   // 借鉴 FinPilot：文本 / 任务执行卡 / 参数追问卡
  status?: 'streaming' | 'done' | 'error'    // 流式生命周期（对应 ai_consult 任务轮询）
  process?: ProcessGroup[]        // 中间过程折叠卡（= v1 问题分析卡：先分析问题再作答）
  toolCall?: ToolCallPayload      // kind=tool：ai_consult 任务进度/结果（轮询写入）
  paramPrompt?: ParamPromptPayload // kind=param-prompt：缺参时向用户追问并收集
  ts: string                      // ISO 时间
  chips?: { label: string; prompt: string }[]   // assistant 追问建议（点击直接发送）
  model?: string                  // 该轮所用模型（assistant 才有）
  errors?: string[]               // 部分降级/错误明细（诚实态，照 FinPilot）
}
// 中间过程（= v1 问题分析卡）：提交时先写意图/计划，再作答（零 LLM 成本）
interface ProcessGroup { stage: 'planner'|'analysis'|'debate'; title: string; steps: {node:string;label:string;text:string;degraded?:boolean}[] }
interface ToolCallPayload { toolKey: string; label: string; status: 'running'|'done'|'error'; params: Record<string,unknown>; progress?: {taskType:string|null;status:string;total:number;done:number;failed:number;message:string|null}; result?: unknown; error?: string }
interface ParamPromptPayload { toolKey: string; label: string; fields: string[]; known?: Record<string,unknown>; answered?: boolean; submitted?: Record<string,unknown> }
```
> v1 历史里消息字段较随意（含 `chips` 等），v2 用 Zod 严格校验、缺字段按"诚实空态"而非补默认。

---

## 4. v2 前端架构

### 4.1 新增文件清单
```
frontend-v2/src/
  api/
    chat.ts                 # 复用 apiFetch：submitAiConsult / getTask / cancelTask / 会话 CRUD / 导出
    schemas/chat.ts         # Zod：ChatMessage / TaskStatus / AiConsultResult / Conversation(List) / ProcessGroup / ToolCall / ParamPrompt
  features/xingchen/
    XingchenPage.tsx        # 页面容器（注册 nav + router）；借鉴 FinPilot ChatPage：意图分类→提交/边界拒绝、流式 status、自动滚动、空态 hero
    ChatPanel.tsx           # 消息流 + 自动滚到底部 + 回到底部按钮（借鉴 FinPilot scrollRef）
    MessageBubble.tsx       # 借鉴 FinPilot：按 kind 判别渲染（user 右 / assistant 左）；markdown + ProcessCard + TaskCard + ParamPromptCard + 降级/错误 tag
    Markdown.tsx            # react-markdown + remark-gfm（与 FinPilot 同选型）+ [S#] 引用徽标 + 表格/行内码
    ProcessCard.tsx         # 借鉴 FinPilot：中间过程折叠卡（= v1 问题分析卡，planner→analysis→debate）
    TaskCard.tsx            # 借鉴 FinPilot ToolCard：ai_consult 任务进度/结果卡（轮询写入）
    ParamPromptCard.tsx     # 借鉴 FinPilot：缺参时向用户追问并收集（= v1 追问 chips 升级）
    StyleSelector.tsx       # 回应方式 radio（quick/report/debate/teach）→ 下发 style
    ModelBadge.tsx          # 模型徽标诚实态（未配置显"规则引擎模式"）
    Composer.tsx            # 借鉴 FinPilot ChatInput：液态玻璃输入框 + 快捷指令面板 + Enter 发送 + 停止生成
    ConversationSidebar.tsx # 多会话列表/新建/删除/导出
    useXingchen.ts          # 借鉴 FinPilot store/chat.ts：zustand 多会话 + 判别消息 + addMessage/updateMessage/updateToolCall/appendProcessStep
    intent.ts               # 客户端意图分类（镜像 v1 _xc_suggestion_kind + FinPilot classifyIntent，零成本）
  mocks/
    handlers.ts             # 追加 MSW：/api/tasks, /api/chat/* 仿真任务流转
    fixtures.ts             # 追加：样例研判 / 历史消息 / 会话列表
```
> 路由注册：`src/nav/nav.ts` 增 `AppPath.xingchen = '/xingchen'`，并在 `modules/widgets._NAV_GROUPS`（v1 侧静态导航）同步显式注册（受 `tests/test_sidebar_nav.py` 锁：6 类目 / 子簇≤8 / 图标全局唯一）。
> **样式约束**：FinPilot 用 antd 6 + 自有 CSS 变量（`--fp-text`/`--fp-glass-border`/`--fp-gold`）；v2 用 Tailwind 4 + 既有 `--color-sf-*` 令牌，**不引入 antd**，仅借鉴组件拆分与交互范式。

### 4.2 组件树（按 msg.kind 判别渲染，借鉴 FinPilot MessageBubble）
```
XingchenPage
├─ ConversationSidebar      (多会话：列表 / 新建 / 删除 / 导出 markdown|json)
└─ ChatPanel
   ├─ 顶部条：ModelBadge（诚实态）
   ├─ 消息流（scrollRef 自动滚到底部）
   │   └─ MessageBubble×N  ── 按 msg.kind 判别：
   │       ├─ user          → 右对齐气泡
   │       ├─ assistant(text)→ 左对齐气泡 + ProcessCard(分析卡) + Markdown + 降级/错误 tag + 复制/时间戳
   │       ├─ tool          → TaskCard（ai_consult 任务进度/结果）
   │       └─ param-prompt  → ParamPromptCard（缺参追问）
   │       └─ SuggestionChips（assistant 轮，点击直接发送）
   ├─ 回到底部按钮（滚动偏离浮现）
   └─ Composer
       ├─ StyleSelector     (⚡快速问答/📋深度研报/⚔️多空辩论/🎓教学解释)
       ├─ 快捷指令面板（聚焦弹出，点击填充并发送，借鉴 FinPilot ChatInput）
       └─ 输入框 + 发送 / 停止生成
```

### 4.3 状态管理（借鉴 FinPilot store/chat.ts，适配 StockSignal 后端）
- **Zustand（主，借鉴 FinPilot `store/chat.ts`）**：`useXingchenStore` 管理 `sessions: ChatSession[]`（多会话）+ `activeId`，动作 `createSession/deleteSession/setActive/renameSession/addMessage/updateMessage/updateToolCall/appendProcessStep`（与 FinPilot 一一对应）。
  - 消息模型为 FinPilot 式判别消息（`kind/status/process/toolCall/paramPrompt`，见 §3.4）；提交时建 `status:'streaming'` 助手消息，轮询回填 `done`/`error` + `toolCall` 进度 + `appendProcessStep` 写分析卡。
  - **持久化适配（关键差异）**：不照搬 FinPilot 的 `persist(localStorage)`，改「内存态 + 后端同步」——消息变更 debounce 写 `POST /api/chat/conversations/<id>`；进入会话 `GET` 拉取；404 回退旧 `/api/chat/history`。既保留 FinPilot 多会话 UX，又接 StockSignal 既有按用户后端持久化（刷新不丢、跨设备可见）。
- **TanStack Query（辅助）**：会话列表 `useChatConversations()`、当前会话消息 `useChatMessages(convId)`（对齐 v2 既有 `lib/queries.ts` 惯例，用 `apiFetch` 取数）。
- **ai_consult 提交+轮询**：`useMutation` 提交 `POST /api/tasks/` → `onSuccess` 轮询 `GET /api/tasks/<id>`（间隔 ~1.5s，对齐 v1 `run_every=1.5`，超时 ~30s 兜底报错）→ 回填消息 `status/result/errors` 与 `toolCall` 进度。

### 4.4 数据模型（Zod，落 `schemas/chat.ts`）
- `ChatMessageSchema`（含 `kind/status/process/toolCall/paramPrompt`，对齐 §3.4）、`TaskStatusSchema`、`AiConsultResultSchema`（**实现期按 `ai_engine` 真返回值补全字段**）、`ConversationSchema`、`ConversationListSchema`、`ProcessGroupSchema`、`ToolCallSchema`、`ParamPromptSchema`。
- 每个 `api/chat.ts` 函数模式对齐 `admin.ts`：`apiFetch<unknown>(path,init)` → `Schema.parse(data)`，缺字段/类型不符即抛 `ApiError`（不兜底，对齐 PLAN §4.3 红线）。

---

## 5. 关键交互还原清单（对应 v1 功能点）

| v1 / FinPilot 能力 | v2 落点（借鉴 FinPilot 组件） | 备注 |
|---|---|---|
| 对话气泡 user 右 / assistant 左 | `MessageBubble` 按 `kind` 判别渲染 | 跟随 `data-theme`；Tailwind 令牌替代 FinPilot 的 `--fp-text` 等 CSS 变量 |
| 回应方式选择器 | `StyleSelector` → 下发 `style` | 透传 `ai_consult` payload |
| 问题分析卡（零 LLM 成本） | `ProcessCard`（= FinPilot 中间过程折叠卡） | 提交时先 `appendProcessStep` 写意图/计划，再作答 |
| 追问 chips / 参数追问 | `SuggestionChips` + `ParamPromptCard`（= FinPilot param-prompt） | 点击直接发送；缺参时显卡片收集 |
| 流式生成态 | 消息 `status:'streaming'→'done'/'error'` + `TaskCard` 进度 | 对应 `ai_consult` 轮询 |
| 多会话 CRUD | `ConversationSidebar` + `useXingchenStore` | 后端持久化；404 回退旧单记录 |
| 导出 | `ConversationSidebar` | markdown / json 两格式，复用 `/export` |
| 模型徽标诚实态 | `ModelBadge` | 后端未配置 LLM → 显"规则引擎模式" |
| 复制 / 回到底部 / 停止生成 | `MessageBubble` 复制 + `ChatPanel` 滚动 + `Composer` 停止 | 对齐 FinPilot 交互 |
| 空态 hero 视觉 | `XingchenPage` 无消息时 hero | 借鉴 FinPilot 空态，视觉改 v2 设计系统 |
| 快捷指令面板 | `Composer` 聚焦弹出内嵌快捷指令面板 | 借鉴 FinPilot `ChatInput` 焦点弹面板（不单建文件，内置于 `Composer.tsx`） |
| 欢迎语 + 快捷 chips | `XingchenPage` 首屏 | 镜像 v1 `WELCOME` |

---

## 6. Dev / MSW mock 方案（无真后端也能跑验收）

在 `src/mocks/handlers.ts` 追加（与现有 `http.get('/api/v2/read/...')` 同机制）：
- `POST /api/tasks/` → 返回 `{data:{task_id:'mock-<n>'}}`，并把请求 question 记到内存。
- `GET /api/tasks/<id>` → 首个轮询返回 `running`，第二个返回 `success` + 由 `fixtures.ts` 提供样例 `AiConsultResult`（含 markdown 正文 + `[S#]` 引用 + 分析卡字段）。
- `GET/POST /api/chat/history`、`GET/POST/DELETE /api/chat/conversations*` → 返回样例消息/会话列表，导出返回样例 markdown。
- 这样 `shoot_frontend_v2.py` 在 dev（MSW 接管）下即可对 `/xingchen` 跑真实浏览器目检，无需起 Flask 5050。

---

## 7. 主题与诚实红线（对齐 v1 修正 + V2 设计系统）

- **主题**：星辰 AI 页跟随全局 `data-theme`（dark/light），用 v2 既有 CSS 令牌（`--color-sf-bg` 等），不强制暗色；气泡/输入/发送键沿用品牌渐变令牌。
- **A 股双套语义**：页面内若展示涨跌，遵循 v2 全站红线——交易屏 `ss-up` 红涨 / `ss-down` 绿跌；报告体 `doc-up` 绿涨 / `doc-down` 红跌；两主题恒等（不串）。
- **诚实态**：模型徽标未配置显"规则引擎模式"；缺数据/任务失败显真实错误文案（如"后台服务连接失败"），**绝不补默认、不伪装成功、不画 0**。
- **可访问性**：气泡对比度、引用徽标 `cursor:help` 提示，沿用 v2 设计系统。

---

## 8. 迁移风险与约束（落地前必读）

1. **导航锁**：新增 `/xingchen` 须显式注册进 v1 侧 `modules/widgets._NAV_GROUPS`（静态导航），受 `tests/test_sidebar_nav.py` 守卫——一级类目恒 6、顺序固定、图标全局唯一、子簇≤8。选哪个类目需在注册时定（建议"市场情绪与广度"或新建"AI 投研"类目，须经守卫放行）。
2. **路由覆盖守卫**：`shoot_frontend_v2.py` 的 `ROUTES` 元组与 `tests/test_frontend_v2_route_coverage.py` 必须同步加入 `/xingchen`，否则 CI 报红。
3. **Markdown 渲染**：v1 用 Streamlit markdown + 自写 CSS（表格/`[S#]` 徽标/行内码/引用块）。v2 需引入 `react-markdown` + `remark-gfm` 并自定义 `S#` 引用徽标组件，需评估包体积（可路由级懒加载，不进首屏）。
4. **后端 LLM 配置依赖**：若后端 `ai_engine` 未配置 LLM，v1 实测走"规则引擎模式"——v2 必须保留该诚实降级路径，且 `ModelBadge` 如实显示。
5. **历史数据兼容**：v1 旧 `/api/chat/history` 消息字段较随意；v2 严格 Zod 解析时，读取旧历史可能触发解析失败 → 须对历史消息做字段归一化（缺字段补 `—`/空数组，不报错不丢消息）。
6. **复刻细节**：v1 的 starfield 背景、引用徽标 hover 提示、复制按钮、回到底部等微交互需在 v2 用等价 CSS/Tailwind 还原，避免体验倒退。
7. **测试守卫**：新增组件须有 colocated `.test.tsx`（沿用 §33–§40 组件测试治理惯例：`QueryClientProvider` 包裹、mock `@tanstack/react-router` 的 `Link/useNavigate`、mock `@/api/chat`）；`shoot_frontend_v2.py` 加 `/xingchen` 真实浏览器目检。
8. **FinPilot 借鉴边界（红线）**：仅借鉴其**前端 UX/状态范式**（zustand 判别消息模型、意图分类→提交/边界拒绝、ProcessCard/TaskCard/ParamPromptCard/Composer 交互、空态 hero）；**绝不引入其 antd 6 依赖**，改用 v2 既有 Tailwind 4 + `--color-sf-*` 令牌还原视觉；**绝不合并 FinPilot 后端**（`terminal/agent/analysisFlow` 的 SSE/工具体系与 StockSignal 的 `ai_consult` 任务 + `ai_engine` 不同），v2 后端契约仍以 §3 实测为准。
9. **Markdown 选型已验证**：FinPilot 同样用 `react-markdown` + `remark-gfm`（v2 草案已规划），落地时复用其 `Markdown` 组件的自定义渲染思路（表格 / `[S#]` 引用徽标 / 行内码），但不搬其 antd 样式。

---

## 9. 验收口径（复用现有工具）

- 单元/组件：`vitest` + colocated `*.test.tsx`（mock `@/api/chat`，断言提交→轮询→渲染链路、意图分类、诚实态、404 回退）。
- 全量闸门：`tsc --noEmit` 0 错 + `vitest run` 全绿。
- 真实浏览器：`shoot_frontend_v2.py` 加 `/xingchen`（含 dark/light 双主题 + 跨主题红线 + 六维类似物若涉及）。验收项沿用既有红线判据（主题生效、A 股双套语义恒等、截图>1KB、缺样式记 null 判失败）。

---

## 10. 落地步骤（分阶段，不一次性大改）

1. **契约对齐**：读 `modules/ai_engine.py` 的 `ai_answer` 真返回结构，定稿 `AiConsultResultSchema`；定 `ChatMessageSchema` 与历史归一化规则。
2. **API 层**：`api/schemas/chat.ts` + `api/chat.ts`（全走 `apiFetch` + Zod，零新封装）。
3. **MSW**：`handlers.ts` + `fixtures.ts` 加 `/api/tasks`、`/api/chat/*` 仿真。
4. **核心组件**：`Markdown` → `MessageBubble`（按 `msg.kind` 判别渲染）→ `ChatPanel` + `useXingchen`（提交+轮询+判别消息）→ `ProcessCard`（问题分析卡= FinPilot 中间过程折叠卡）+ `ParamPromptCard`（缺参追问）+ `SuggestionChips`（assistant 轮追问 chips）+ `Composer`（液态玻璃输入，含样式选择器内嵌）+ `StyleSelector` + `ModelBadge`。
5. **多会话**：`ConversationSidebar` + 404 回退旧模式。
6. **注册与守卫**：`nav.ts` 加路由 + `_NAV_GROUPS` 注册 + `shoot_frontend_v2.py` 与路由覆盖守卫同步。
7. **测试 + 验收**：colocated 测试 + `tsc`/`vitest` + 真实浏览器目检；全绿后 ff-only 提交（仅 `frontend-v2/` + `docs/`）。

> 本草案为设计稿，**未写任何业务代码**。确认后进入第 1 步契约对齐；或老板若要求"直接动手建组件"，再切实现模式。
