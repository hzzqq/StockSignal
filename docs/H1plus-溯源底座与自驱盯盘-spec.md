# Spec：H1+ 两个增强方向（全站引用溯源底座 · 研究智能体定时自驱盯盘）

> 状态：**待老板拍板**（本文冻结前不写实现代码）｜制定：2026-10-04｜任务：team/TASKS.md T-211
> 方法：SDD+TDD（拍板后先冻结本 spec 的 AC，再写失败测试 → 实现 → mutation 验证非假绿）
> 前置勘测（**先勘测后设计，勿重复造轮子**）：
> - H1 AI 研究智能体**已交付**：`modules/research_agent.py`（契约 `.workbuddy/specs/ai_research_agent_contract.md` AC1–AC8）
>   已具备 **`[S#]` 引用 + 逐步 `data_as_of`/`citations`** 的溯源能力 —— 方向 A 的地基已在。
> - 定时基建**已存在**：`backend/market_alert_engine.py`（15 分钟扫描 + 6h 冷却 + 交易时段 + pytest 自动跳过）、
>   `backend/conditional_engine.py` 调度器、`backend/desktop_notify.py` 推送、`backend/tasks/worker.py`（AI 任务异步通道）
>   —— 方向 B 只需把「触发」接到 `research_agent`，**不新建调度框架**。
> - 全源新鲜度**已存在**：`modules/decision.assess_freshness`（源→as_of/lag/status）+ `data_health`
>   （含 `test_data_health.py` / `test_decision_data_freshness.py` 守卫）—— 方向 A 的取数真理源已在。

---

## 方向 A：全站引用溯源底座（"结论怎么来的、可不可信"）

### A.1 目标与边界
把 H1 已具备的「引用溯源」从**研究智能体回答内**下沉为**全站可点的数据来源底账**：任何指标卡 / 关键结论，
都能点开查看 **数据源 / 数据日(as_of) / 抓取时间 / 是否回退 / 是否陈旧**，一句话定位从产品承诺变成页面事实。

**非目标（明确划界，防摊大饼）**：
- 不改任何取值/决策逻辑（additive-only）；不新增数据源；不做「结论级因果解释」。
- 不迁 `ui_kit._KIT_CSS` 调用点（守 §四：统一＝改 primitive 不迁调用点）。

### A.2 架构（单一真理源 + 薄 UI）
1. **`modules/data_provenance.py`（新，单一真理源）**
   - `build_provenance(source_name) -> dict`：返回 `{source, as_of, fetched_at, source_chain, is_fallback, freshness}`
     —— **复用** `decision.assess_freshness` 与 `data_health` 的既有源表，**不自造第二套新鲜度口径**。
   - `slug_to_sources(page_or_card)`：声明式映射「页面/卡片 → 依赖源」（集中登记，防散落）。
2. **`ui_kit` 新增基元 `prov_badge(sources)`（additive）**
   - 渲染一个「ⓘ 数据来源」徽标（CSS 变量驱动，六风格自动适配）；点击展开来源明细（原生 `<details>` 或既有 popover，
     **不引入整页 rerun**，守 §一-3）。
   - 复用 `page_utils` 三件套与 `ui_kit` 既有 CSS 基元。
3. **接线（additive，逐页小步）**：优先 5 个高价值页（行情看板 / 今日决策面板 / 市场情绪 / 个股研究 / 实时强势榜），
   在关键卡片挂 `prov_badge`；老页面不改不报错（缺映射→徽标不渲染）。

### A.3 验收标准（AC，可测）
- **AC-A1 单一真理源**：`build_provenance` 的 `as_of/freshness` 必须来自 `assess_freshness`/`data_health`，
  AST/行为测试断言**不存在第二套阈值常量**（防口径漂移）。
- **AC-A2 诚实语义**：源取不到→徽标显示"未知"并注明**不臆造**（守 §五）；`is_fallback=True` 必须显示回退标记；
  `freshness ∈ {warn,stale}` 必须显式警示（不得静默为正常）。
- **AC-A3 无 rerun**：徽标交互为纯前端（`<details>`/CSS），AST 守卫断言未引入 `st.rerun()` 于基元内。
- **AC-A4 风格自适应**：颜色全走 CSS 变量；六风格下徽标可读（守卫钉选择器使用变量）。
- **AC-A5 页面零破坏**：未登记的页面/卡片调用即 no-op，不抛错；全量 pytest 绿。

### A.4 复用 vs 新增
| 复用（不重写） | 新增 |
|---|---|
| `decision.assess_freshness` / `data_health`（源表+阈值） | `modules/data_provenance.py`（注册表+映射） |
| `ui_kit` CSS 基元 / `page_utils` 三件套 | `ui_kit.prov_badge` 徽标基元 |
| H1 `research_agent` 的 `[S#]`/`as_of`（回答内已溯源） | 页面级 `slug_to_sources` 登记表 |

---

## 方向 B：研究智能体定时自驱盯盘（手动问答 → 自驱盯梢）

### B.1 目标与边界
让研究智能体从「用户提问才跑」升级为「**定时/事件自驱**：盯到异常（异动告警/持仓异动/条件单触发）→
自动发起一次针对性 `run_research` → 落研究记录 + 推送给用户」。

**非目标**：不做自动交易（守 H1 只读红线：`conditional_orders` 仅 `action="list"`）；不引入新的 LLM 费用失控路径。

### B.2 架构（复用既有调度与推送，不新建框架）
1. **触发源（复用）**：`market_alert_engine` 产出的 `market_alerts`（已有 15min 扫描+6h 冷却）；
   可选扩展：持仓异动（复用既有 monitor/alert 数据）。
2. **`backend/research_watch.py`（新，编排薄层）**
   - 监听新告警 → 组装问题（如"XX 板块异动，请分析原因与影响"）→ 调 `modules/research_agent.run_research`（**经
     `mcp_server.gateway` 工具护栏**）→ 结果落库（新表 `research_runs`：question/status/citations/created_at/trigger）。
   - **预算与红线**：单次 `max_steps`/`budget_s` 沿用 H1 clamp（1..8 / 时间预算）；每轮**全局配额**（如每 N 分钟至多 1 次，
     冷却去重，防 LLM 成本失控）；交易时段才跑（复用 alert 引擎的时段判定）；pytest / `STOCKSIGNAL_ENABLE_*` 关闭时自动跳过。
3. **推送（复用）**：复用 `desktop_notify` 与消息中心；前端在「星辰 AI」与「消息中心」展示自驱研究记录（additive）。

### B.3 验收标准（AC，可测）
- **AC-B1 只读红线不回退**：自驱研究**绝不**触发任何写操作（守 H1 AC3；测试断言调度链不含写工具）。
- **AC-B2 有界**：单轮 clamp 沿用 H1；全局配额 + 冷却去重生效（测试注入多告警→断言至多跑 1 次）。
- **AC-B3 诚实降级**：研究失败/工具全挂→`status="unavailable"` 如实记录并推送，**不编造**（守 §五）。
- **AC-B4 测试隔离**：pytest 与禁用环境变量下**不启动**调度线程（复用 alert 引擎既有模式）。
- **AC-B5 可追溯**：每条自驱研究记录含触发原因 + citations（复用 H1 溯源），前端可点开溯源。
- **AC-B6 时段与去重**：非交易时段休眠；同一触发源在冷却期内不重复研究。

### B.4 复用 vs 新增
| 复用（不重写） | 新增 |
|---|---|
| `market_alert_engine`（扫描/冷却/时段/开关） | `backend/research_watch.py`（触发→研究→落库编排） |
| `modules/research_agent.run_research`（含只读红线+有界+溯源） | `research_runs` 表 + 查询端点 |
| `backend/tasks/worker.py`（异步）/ `desktop_notify`（推送） | 前端「自驱研究记录」展示（additive） |

---

## 实施顺序与工作量分级（不含时间估计）
| 顺序 | 项 | 工作量 | 依赖 |
|---|---|---|---|
| 1 | 方向 A 步骤1-2（`data_provenance` + `prov_badge` 基元）+ AC-A1~A4 守卫 | M | 无（纯新增，零风险） |
| 2 | 方向 A 步骤3（5 页接线）+ AC-A5 | S | 步骤1 |
| 3 | 方向 B 步骤1-2（`research_watch` + 表 + 端点）+ AC-B1~B6 守卫 | L | H1（已在） |
| 4 | 方向 B 步骤3（推送 + 前端记录展示） | M | 步骤3 |

> 建议**先 A 后 B**：A 是纯增量、零业务风险、且为 B 的「自驱研究记录」提供溯源展示；B 涉及调度+LLM 成本，需先冻结配额策略。

## 待老板拍板的开放问题
1. **范围**：两个方向都做（A→B 顺序），还是先只做 A？
2. **方向 B 的触发面**：仅「市场异动告警」触发，还是也接「持仓异动 / 条件单触发」？
3. **方向 B 的成本闸**：每轮全局配额（如每 30/60 分钟至多 1 次）与每日上限，取多少？
4. **推送通道**：仅站内（消息中心 + 星辰AI），还是也走 `desktop_notify` 桌面通知？
