# StockSignal 功能版块 × Skill × 专家 细分映射表

> 用途：拿着这份表，按版块逐个去跑对应的 Skill / 专家（智能体）。
> 依据：功能版块取自 `modules/widgets._NAV_GROUPS`（6 个一级类目两级结构 + Hero + Admin），为代码权威结构。
> 命名说明：`cb_teams_marketplace` 的金融类条目**同名即既是 Skill 也是 Expert 智能体** —— Skill 用 Skill 工具 / 斜杠命令加载，Expert 走左侧专家面板或 Agent 类型调用。

---

## 总览（6 个一级类目两级结构 + Hero + Admin）

| # | 分组 | 核心版块 | 首选去跑的 Skill / Expert |
|---|------|---------|--------------------------|
| 1 | 📈 行情盯盘 | 行情看板 / 智能盯盘 / 资金流向 / 每日晨报 | `a-share-daily-review` · `market-overview` · `northbound-flow` |
| 2 | 🧩 板块结构 | 板块轮动 / 市场魔方 | `sector-comparison` · `industry-chain` · `market-mainline` |
| 3 | 🌐 市场宽度 | 市场强弱/驱动力/情绪/事件/财报日历/连板龙头/温度系/状态机/全景（19 页） | `market-mainline` · `market-overview` · `bubble-detection` · StockPartnerTeam 6 专家 |
| 4 | 🔎 个股研究 | 个股研究 / 股票选取 / 个股分析 / 多股对比 / 基本面分析 | `stock-deep-dive` · `stock-logic-research` · `valuation-framework` · `company-quality` |
| 5 | 🧪 量化选股 | 智能选股 / 形态选股 / ETF筛选 / QuantAgent / 策略回测 / P1量化信号 | `onequant-backtest` · `quant-signal-landing-sop` · `westock-skill` |
| 6 | 💼 持仓交易 | 持仓中心 / 仓位管理 / 组合收益 / 自选监控 / 实盘 / 模拟 | `position-management` · `risk-checkup` · `westock-skill` |
| 7 | 🛠 工具 | 体检扫描 / 价格预警 / 数据导出 / 智能条件单 | `risk-checkup` · `offline-realdata-cache` · `xlsx` |
| 8 | 💬 社区与 AI | 星辰 AI / 股吧 / 消息中心 / 投研圆桌 | `stocksignal-xc-theming` · StockPartnerTeam（经 `stock-partner-lead` 编排） |
| ★ | 🎯 今日决策面板（Hero） | 综合决策首页 | `a-share-advisor` · `portfolio-manager` · `signal-chief` |
| ⚙ | 账户 / 系统（Admin） | 用户管理 / 系统配置 | `flask-secure-json-api` · `dual-machine-git-safety` |

---

## 1. 📈 行情盯盘
**页面**：`10_行情看板` · `14_智能盯盘` · `35_资金流向` · `51_每日晨报`

**🎯 相关 Skill（技能）**
- `a-share-daily-review` — A股收盘后全维度复盘（技术面/情绪面/短线博弈/板块拆解 + 热点速览），自动生成自包含 HTML。
- `market-overview` — 市场整体行情分析（全球联动/盘前/盘后/龙虎榜/北向/情绪解读 11 类主题）。
- `a-stock-data` — A股全栈数据（行情/研报/信号/资金/财务），底层多源。
- `westock-data` — 经 westock-mcp 查实时行情/K线/资金/宏观。
- `invest-calendar` — 财经事件日历（财报/解禁/FOMC/LPR），喂给每日晨报。
- `daily-financial-news` — 多源财经资讯聚合，生成晨报素材。
- `ashare-short-term-trading` — 日内/短线节点评估（盘后诊断、盘中评估）。

**🧠 相关 Expert（专家/智能体）**
- `market-overview`（专家）—— 盘前/盘后综述、龙虎榜、北向、情绪。
- `northbound-flow`（专家）—— 北向资金行为（对应资金流向页）。
- `signal-chief`（角色）—— 四层信号（政策/行业/新闻/资金）择时。
- `shortterm-surfer`（角色）—— 周度题材 + 开盘竞价确认的短线视角。
- `a-share-advisor`（统一入口）—— 一句话路由到上述专家。

---

## 2. 🧩 板块结构
**页面**：`12_板块轮动` · `17_市场魔方`

**🎯 相关 Skill（技能）**
- `sector-comparison` — 板块比较（行业比较/轮动/投资选择）。
- `industry-chain` — 产业链映射（主题投资/行业挖掘）。
- `market-mainline` — A股市场主线识别（结构/题材周期/资金行为）。
- `a-stock-data` — 板块成份/概念/资金数据。

**🧠 相关 Expert（专家/智能体）**
- `sector-comparison`（专家）
- `industry-chain`（专家）
- `market-mainline`（专家）
- `industry-strategist`（角色）—— 行业趋势 + 估值约束找低估受益。

---

## 3. 🌐 市场宽度（广度 · 温度 · 结构，19 页）
**页面**：`13_市场强弱` · `15_市场驱动力` · `50_市场情绪` · `23_事件追踪` · `16_财报日历` · `58_连板龙头共振` · `59_市场温度计` · `60_事件对比分析` · `61_广度分化` · `62_动量广度共振` · `63_温度回测` · `65_投机情绪周期时钟` · `66_维度领先-滞后矩阵` · `67_历史相似日聚类` · `68_情绪拐点扫描器` · `69_温度持续期与回归时长` · `56_市场状态机` · `57_市场全景`

**🎯 相关 Skill（技能）**
- `market-mainline` — 主线/广度结构识别。
- `market-overview` — 市场整体温度与广度。
- `a-share-daily-review` — 广度 + 情绪 + 涨停梯队复盘。
- `a-stock-data` / `westock-data` — 广度/情绪底层数据。
- `invest-calendar` — 财报日历/事件追踪的数据源。
- `bubble-detection` — 反身性与预期泡沫（极端广度过热识别）。

**🧠 相关 Expert（专家/智能体）**
- **StockPartnerTeam 6 专家**（经 `stock-partner-lead` 编排，对应「投研圆桌」页）：
  - 广度温度官 — 广度/温度/情绪极值
  - 指数结构师 — 指数结构与分层
  - 主线猎手 — 主线与题材周期
  - 资金行为师 — 资金流向与博弈
  - 仓位司令 — 由广度温度推导仓位
  - `contrarian-investor`（逆向视角）—— 极端恐慌→反弹等逆向信号
- `market-mainline`（专家）· `market-overview`（专家）· `bubble-detection`（专家）· `sentiment-analyst`（专家）

---

## 4. 🔎 个股研究
**页面**：`24_个股研究` · `11_股票选取` · `20_个股分析` · `21_多股对比` · `22_基本面分析`

**🎯 相关 Skill（技能）**
- `stock-deep-dive` — 个股精准分析（投资逻辑/基本面/财报/技术/资金/同业比较）。
- `stock-logic-research` — 个股核心投资逻辑深度研究。
- `valuation-framework` — 估值与定价框架。
- `company-quality` — 公司质地打分（基本面/质量）。
- `financial-report` — 财报质量与公告影响力。
- `a-stock-data` / `westock-data` / `westock-skill` — 行情/财务/选股数据。

**🧠 相关 Expert（专家/智能体）**
- `stock-deep-dive`（专家）· `stock-logic-research`（专家）· `valuation-framework`（专家）· `company-quality`（专家）· `financial-report`（专家）
- 分析师角色：`fundamentals-analyst` · `technicals-analyst` · `valuation-analyst` · `growth-analyst` · `news-sentiment-analyst`
- **投资者人格视角**（对同一只票多视角）：`warren-buffett` · `charlie-munger` · `peter-lynch` · `michael-burry` · `ben-graham` · `mohnish-pabrai` · `phil-fisher` · `aswath-damodaran` · `cathie-wood` · `bill-ackman` · `stanley-druckenmiller` · `nassim-taleb` · `rakesh-jhunjhunwala`

---

## 5. 🧪 量化选股
**页面**：`32_智能选股` · `31_形态选股` · `33_ETF筛选` · `25_QuantAgent投研` · `30_策略回测` · `55_P1量化信号`

**🎯 相关 Skill（技能）**
- `onequant-backtest` — OneQuant 4.0 量化回测（Web/API/CLI/批量）。
- `quant-signal-landing-sop` — 量化信号重训→落地生产 SOP（训练被墙钟杀/替换/集成不赢陷阱）。
- `westock-skill` — 条件选股/标签选股/策略选股。
- `ashare-short-term-trading` — 短线信号与初筛。
- `a-stock-data` — 因子/行情数据。

**🧠 相关 Expert（专家/智能体）**
- `signal-chief`（角色）—— 四层信号体系择时。
- `industry-strategist`（角色）· `fundamental-researcher`（角色）
- 分析师角色：`technicals-analyst` · `fundamentals-analyst` · `portfolio-manager`

---

## 6. 💼 持仓交易
**页面**：`45_持仓中心` · `40_仓位管理` · `41_组合收益` · `46_自选股监控` · `43_实盘交易` · `42_模拟交易`

**🎯 相关 Skill（技能）**
- `position-management` — 仓位决策（仓位管理/风险控制）。
- `risk-checkup` — 持仓体检与组合风险管理。
- `westock-skill` — 经 westock-mcp 模拟/实盘交易、条件单。
- `ashare-short-term-trading` — 买卖质量回溯、盘中评估。
- `flask-secure-json-api` — 实盘交易后端安全信封（工程侧）。

**🧠 相关 Expert（专家/智能体）**
- `position-management`（专家）· `risk-checkup`（专家）
- 角色：`portfolio-manager` · `risk-manager` · `contrarian-investor`

---

## 7. 🛠 工具
**页面**：`34_体检扫描` · `47_价格预警` · `95_数据导出` · `44_智能条件单`

**🎯 相关 Skill（技能）**
- `risk-checkup` — 体检扫描（持仓/组合风险）。
- `offline-realdata-cache` — 数据导出离线真实缓存模式（避免导出假数据）。
- `xlsx` — Excel 数据分析与导出。
- `markitdown` — 文档/报表转 Markdown 导出。
- `westock-skill` — 价格预警 / 智能条件单。

**🧠 相关 Expert（专家/智能体）**
- `risk-checkup`（专家）· `risk-manager`（角色）

---

## 8. 💬 社区与 AI
**页面**：`53_星辰AI` · `52_股吧` · `94_消息中心` · `64_投研圆桌`

**🎯 相关 Skill（技能）**
- `stocksignal-xc-theming` — StockSignal 全站统一视觉主题（星辰 AI 深色主题落地）。
- `a-share-advisor` — AI 统一分析入口（路由到各专家）。
- `daily-financial-news` — 资讯流喂给股吧/消息中心。
- `handoff-doc` — 圆桌/讨论精华沉淀为交接文档。

**🧠 相关 Expert（专家/智能体）**
- **StockPartnerTeam 6 专家**（广度温度官/指数结构师/主线猎手/资金行为师/仓位司令 + 逆向 `contrarian-investor`），经 `stock-partner-lead` 编排生成多视角圆桌。
- `a-share-advisor`（统一入口路由）

---

## ★ 🎯 今日决策面板（Hero 页 `54`）
**🎯 相关 Skill**：`a-share-daily-review` · `position-management` · `market-overview`
**🧠 相关 Expert**：`portfolio-manager`（最终决策）· `signal-chief`（择时信号）· `a-share-advisor`（入口）

---

## ⚙ 账户 / 系统（Admin：`92_用户管理` · `93_系统配置`）
**🎯 相关 Skill（工程侧）**：`flask-secure-json-api` · `dual-machine-git-safety` · `github` · `session-archiver`
**🧠 相关 Expert**：无业务专家；归工程/运维类 Skill 处理。

---

## 跨版块通用 · 工程 / 质量 / 数据基础设施 Skill
（任何版块要改代码、补测试、做 UI、导出数据都可调用）

- `ast-invariant-guard` — AST 源码级防回退护栏（配色/响应信封/分页等不变量）。
- `ast-safe-edit` — AST 安全批量改写（含中文 .py 机械化编辑）。
- `silent-failure-defect-hunt` — 静默失败缺陷狩猎（不崩但语义错）。
- `self-driving-dev` — 自主开发循环（自找活/自验收/自推送）。
- `sdd-tdd` — 规范驱动 + 测试驱动（先写失败测试再实现）。
- `stocksignal-xc-theming` / `frontend-design` / `ui-ux-pro-max` / `frontend-spec` — UI/主题/前端规范。
- `flask-secure-json-api` — Flask 后端统一 JSON 信封、禁泄漏。
- `dual-machine-git-safety` / `github` — 双机/多 agent 的 git 安全红线与推送。
- `progress-doc` / `handoff-doc` / `planning-with-files` / `mermaid-diagram` — 进度/交接/规划文档。
- `offline-realdata-cache` / `microapp-data-hub` / `xlsx` / `markitdown` — 离线真实数据、微应用后端、表格/文档导出。
- `delivery-no-pseudoblock` — 交付前伪阻断闸门（每份交付前自检）。
- `futures-combo` — 商品期货组合（老板 6 品种：玻璃/纸浆/纯碱/鸡蛋/白糖/乙二醇；**跨资产，非 A股**，按需调用）。
- `force-hy3-model` — 自动化任务强制用 hy3 模型（省成本）。

---

## 全量 Expert 名册（按视角归类）

**A. 市场 / 广度 / 结构**
market-mainline · market-overview · sector-comparison · industry-chain · style-rotation · northbound-flow · bubble-detection · sentiment-analyst

**B. 个股 / 估值 / 基本面**
stock-deep-dive · stock-logic-research · valuation-framework · company-quality · financial-report · dividend-returns · going-global · fund-crowding · institutional-holdings · macro-research · macro-to-stock

**C. 分析师角色**
fundamentals-analyst · technicals-analyst · valuation-analyst · growth-analyst · news-sentiment-analyst

**D. 组合 / 风险 / 信号**
portfolio-manager · risk-manager · position-management · risk-checkup · signal-chief · industry-strategist

**E. 投资者人格视角（同一标的多视角）**
warren-buffett · charlie-munger · peter-lynch · michael-burry · nassim-taleb · cathie-wood · ben-graham · bill-ackman · stanley-druckenmiller · mohnish-pabrai · phil-fisher · aswath-damodaran · rakesh-jhunjhunwala

**F. 逆向 / 短线 / 研究**
contrarian-investor · shortterm-surfer · fundamental-researcher

**G. 编排 / 统一入口**
stock-partner-lead（投研圆桌编排）· a-share-advisor（A股统一入口路由）· StockPartnerTeam 6 专家（广度温度官/指数结构师/主线猎手/资金行为师/仓位司令 + 逆向）

---

## 使用建议（怎么「拿去跑」）
1. **按版块取表**：先定位你要跑的版块 → 看该版块的 Skill + Expert 清单。
2. **Skill**：对我说「跑 `<skill名>` 分析 `<具体标的/版块>`」即可（如「跑 a-share-daily-review 复盘今天」）。
3. **Expert**：走左侧专家面板选对应专家，或让我用 Agent 拉起（如「用 stock-deep-dive 专家分析 000021.SZ」）。
4. **圆桌多视角**：对复杂问题用 `stock-partner-lead` 编排 6 专家 + 逆向，输出整合报告。
5. **同名即双通道**：market-mainline / stock-deep-dive 等既可作为 Skill 也可作为 Expert，按需选其一即可。
