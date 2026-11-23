import type { AppPath } from '@/nav/nav'
import { V1_PAGES, type V1Page } from './v1Pages.generated'

/**
 * v1 功能页 → v2 落地状态（单一真理源，供功能全景页与守卫共用）。
 *
 * 四档**诚实口径**，绝不把未实现的功能标成已完成，也不把 v2 已落地页贬成未迁移：
 *  - native     : v2 有等价页面，直接跳路由；
 *  - data       : v2 无等价页面，但有可查看的关联只读端点（真实数据，非等价功能）；
 *  - v1-only    : v2 尚未迁移、但计划迁移，明确标注并给出 v1 直达链接；
 *  - v1-pinned  : v1 保留（永久不迁 v2）—— 真实交易 / 低频遗留 / 实验性页面，
 *                 v2 明确不做等价实现。
 *
 * 映射按 v1 文件名精确匹配；未登记的页一律回落 v1-only（不臆造对应关系）。
 * 优先级：NATIVE > DATA > PINNED > v1-only 回落。
 *
 * 2026-11-16 双向失真纠正（权威对照见 docs/frontend-v2/V1-V2-PARITY.md，回归网见 v2Mapping.test.ts）：
 *  - 纠正「低估」：53 星辰 AI / 52 股吧 v2 已完整实现，由 pinned 升级 native；
 *  - 纠正「高估」：44 智能条件单涉真实下单，由 native 降 pinned（实盘红线）；
 *    63 温度回测与 /backtest 模块错配，先撤下假 native；2026-11-16 parity B 批次
 *    已由 /temperature-backtest 真承接 modules/temperature_backtest.py，升回 native；
 *    61 广度分化亦由 /breadth-divergence 承接分化维度算法，不再只是广度总览。
 *    并为 42/11/14/20/40/41/45/46/95 等只读缩水页补齐诚实 note，杜绝「标 native 却零说明」。
 *
 * 2026-11-19 迁移与诚实校正：
 *  - 59 市场温度计 / 64 投研圆桌此前「标 native 无 note」属台账失真：59 仅部分迁移（8 指标分解/
 *    极端区信号/历史类比/基准窗口未迁），64 的 /predictions 是 prediction_log 而非静态报告，
 *    两者均补 note 明示能力边界；
 *  - 15 市场驱动力由 v1-pinned 升 native → /market-sentiment「市场驱动力」tab（2026-11-22 并入，原 /market-drivers redirect），复用 /api/v2/read/market-sentiment，
 *    归一化/相关/CSV 为派生并如实标注（无上证参考线）。
 */

export type V2Status = 'native' | 'data' | 'v1-only' | 'v1-pinned'

export interface V2Mapping {
  status: V2Status
  to?: AppPath
  dataPath?: string
  dataLabel?: string
  note?: string
}

/** 只读快照页：v1 的组合编辑写操作已于 parity 补批承接（POST/DELETE /api/v2/portfolio），
 *  但 /portfolio 的只读快照视图本身不提供组合编辑 UI——写操作在页面「模拟账本写操作」面板。 */
const SNAPSHOT_READONLY_NOTE = '只读快照视图；v1 的组合编辑写操作已在 /portfolio 的模拟账本写面板承接（添加/删除/卖出，本地 CSV 全站共享、非实盘）'

/** 逐只主力资金流为只读聚合：自选股增删/垃圾股标记/自定义打分由 /watch 写面板承接；
 *  实时现价与涨跌幅未在只读端点聚合（v1 由实时行情单例提供，v2 有意不引入实时单例）。 */
const WATCH_READONLY_NOTE =
  '逐只主力资金流为只读聚合；自选股增删/垃圾股标记/自定义打分由本批 /watch 页写面板承接；实时现价与涨跌幅未在只读端点聚合'

/** ① v2 已实现的等价页面（与 router.tsx / nav.ts 的真实路由一一对应）。
 *  含「漂移收口」：原来被错标成 data / v1-only 的页，因 v2 实际已有完整页面，
 *  在此统一升级为 native（如行情看板→/quote-board、资金流向→/fund-flow、龙虎榜→
 *  /dragon-tiger 等），使功能全景不再低估 v2 覆盖。 */
const NATIVE: Record<string, { to: AppPath; note?: string }> = {
  // 个股研究簇
  '20_个股分析.py': { to: '/stock/research', note: 'v1 已内嵌进 24 页，v2 统一由个股研究承接；' + SNAPSHOT_READONLY_NOTE },
  '21_多股对比.py': { to: '/stock/compare' },
  '22_基本面分析.py': { to: '/stock/fundamentals' },
  '23_事件追踪.py': { to: '/events', note: '以事件因子池视图承载' },
  '24_个股研究.py': { to: '/stock/research' },
  // 决策 / 复盘 / 晨报 / 信号
  '36_每日荐股.py': { to: '/recommend' },
  // parity B：GET /review-notes 已有读；PUT /review-notes 承接按日期保存 Markdown 全文。
  // 2026-11-20：图片上传已承接（POST /review-images 上传 + markdown 链接写入笔记文本，与 v1 同语义）。
  '51_每日晨报.py': { to: '/morning', note: '晨报主体已承接；复盘笔记段由 /review-notes 的 PUT 承接按日期保存，图片上传已承接（POST /review-images，上传后以 markdown 图片链接写入笔记文本，与 v1 同语义；历史图片为登录态链接呈现，不做匿名渲染）' },
  '54_今日决策面板.py': { to: '/decision' },
  '55_P1量化信号.py': { to: '/p1' },
  '97_决策回放.py': { to: '/replay' },
  // 量化工具
  '30_策略回测.py': { to: '/backtest' },
  '71_因子分析.py': { to: '/factor' },
  '72_六维评分.py': { to: '/stock/six-dim' },
  // 交易 / 持仓
  // parity C：本地模拟账本写已接回（POST/DELETE paper-trades + reset），JWT 用户隔离，绝不触实盘
  '42_模拟交易.py': { to: '/paper', note: 'v2 /paper 已承接 v1 的模拟账本写（本地 JSON 原子写、JWT 用户隔离、删除仅删记录不回滚现金/持仓）；与 43 实盘交易红线无关' },
  '40_仓位管理.py': { to: '/portfolio', note: SNAPSHOT_READONLY_NOTE },
  '41_组合收益.py': { to: '/portfolio', note: SNAPSHOT_READONLY_NOTE },
  '45_持仓中心.py': { to: '/portfolio', note: SNAPSHOT_READONLY_NOTE },
  // 行情 / 板块 / 盯盘
  '10_行情看板.py': { to: '/quote-board' },
  '11_股票选取.py': { to: '/quote-board', note: '选股入口由行情看板承接；' + WATCH_READONLY_NOTE },
  '12_板块轮动.py': { to: '/sector-rotation' },
  '14_智能盯盘.py': { to: '/watch', note: WATCH_READONLY_NOTE },
  '46_自选股监控.py': { to: '/watch', note: WATCH_READONLY_NOTE },
  '35_资金流向.py': { to: '/fund-flow' },
  // 广度·温度簇
  '56_市场状态机.py': { to: '/panorama', note: '2026-11-23 相似页合并：与 57 市场全景同源（同 /market-panorama 端点），并入 /panorama「市场状态机」tab；旧 /regime 路由 redirect' },
  '57_市场全景.py': { to: '/panorama' },
  // 2026-11-20 迁移：59 四块能力已承接。/breadth 现含牧羊人 8 指标热度贡献分解、
  // 极端区信号（sentiment_edge）、历史情境类比与基准窗口切换（近一季/近一年/全历史 2007 起），
  // 实时取数走后端聚合端点 /market-temperature；缺失指标诚实显「—」不补 0。
  '59_市场温度计.py': {
    to: '/breadth',
    note: '已迁移：/breadth 承接 v1 的牧羊人 8 指标热度贡献分解、极端区信号（sentiment_edge）、历史情境类比与基准窗口切换（近一季/近一年/全历史 2007 起），实时取数走后端聚合端点 /market-temperature，缺失指标诚实显「—」不补 0；/market-sentiment 是 50 的等价页，不是 59',
  },
  // 2026-11-19：15 市场驱动力由 v1-pinned 跨档为 native；2026-11-22 侧栏减臃肿并入
  // /market-sentiment 的 tab 视图（MarketSentimentTabbed），旧 /market-drivers 路由 redirect。
  // 复用 /api/v2/read/market-sentiment 的 21 指标五维 dims；归一化子图/相关热力/CSV 均由端点 spark 派生，
  // 端点未提供上证参考线与全 180 天原始面板，页面如实标注「派生、口径不同」。
  '15_市场驱动力.py': {
    to: '/market-sentiment',
    note: '已迁移：/market-sentiment「市场驱动力」tab（原 /market-drivers 已并入）复用同端点 21 指标五维数据，五维归一化叠加、相关性热力与 CSV 导出均由端点近 40 点 spark 派生并显式标注；v1 的上证参考线与全 180 天原始归一化面板端点未提供，未编造',
  },
  // parity B：/breadth-divergence 已承接分化维度算法（日历热力 + 分化检测 + 双轴趋势）。
  '61_广度分化.py': { to: '/breadth-divergence', note: 'v2 由 /breadth-divergence 承接 modules/breadth_divergence.py 的日历热力、分化检测与趋势（真实离线广度序列）' },
  '58_连板龙头共振.py': { to: '/ladder' },
  // 市场数据
  '75_题材热点.py': { to: '/theme' },
  '76_实时强势榜.py': { to: '/strong' },
  '84_宏观数据.py': { to: '/macro-data' },
  '85_龙虎榜.py': { to: '/dragon-tiger' },
  // 2026-11-19 诚实标注：/predictions 是 prediction_log 校准日志 + 温度时序，
  // 与 v1 的静态投研圆桌交付物（本地 MD 报告 + 内嵌 HTML 仪表盘片段 + MD/HTML 双下载 + KPI 带）
  // 数据源不同。2026-11-21 parity 补批：/predictions 顶部新增「投研圆桌 · 静态报告」卡片，
  // 承接 v1 的 MD 正文 + 内嵌 HTML 仪表盘 + MD/HTML 双预览双下载（GET /api/v2/read/stock-report，
  // 白名单目录固定为 deliverables/stock-partner/2026-09-11/，KPI 带同款正则提取）。
  '64_投研圆桌.py': {
    to: '/predictions',
    note: '已承接（2026-11-21 parity 补批）：/predictions 是 prediction_log 校准日志 + 温度时序；v1 静态投研圆桌报告（deliverables/stock-partner/2026-09-11/ 的 MD 正文 + 内嵌 HTML 仪表盘 + MD/HTML 双下载 + KPI 带）由页面顶部静态报告卡承接（GET /api/v2/read/stock-report）',
  },
  // 告警 / 系统 / 教学
  '74_告警引擎.py': { to: '/alerts' },
  '82_数据时效性看板.py': { to: '/ops', note: '以数据与运维状态视图承载' },
  '86_网页作品集.py': { to: '/webapps' },
  '93_系统配置.py': { to: '/settings' },
  '90_登录.py': { to: '/login', note: '账号密码登录 + 行情台（上证分时/今日推荐合并组件）+ 开放注册已实现（2026-11-21，POST /api/auth/register，注册成功不自动登录）；验证码登录依赖短信网关，v2 不做假功能' },
  '96_新手教程.py': { to: '/guide', note: '四步上手/模块导览/术语表/FAQ/主线/误区已移植；教学视频与 Streamlit 快捷键不适用未移植' },
  // W4-F · v1-only 收口（路径均已在 router.tsx 真实注册）
  '66_维度领先滞后矩阵.py': { to: '/matrix', note: '以有序对明细表承载（带符号 lag），样本下限比 v1 更严格' },
  // 92 用户管理（管理员专属）：v2 等价实现 /users，三 Tab（列表/创建/日志）+ 角色门控；
  // 与 v1 同源「不能删自己/初始 admin」规则；与交易无关，实盘交易红线不受影响。
  '92_用户管理.py': { to: '/users' },
  // 77 财报猎手：v2 等价实现 /financial-hunter，逐股票三表（income/balance/cash）切换深挖；
  // 非跨股筛选器（v2 暂无跨股财报筛选端点），页面如实说明。
  '77_财报猎手.py': { to: '/financial-hunter', note: 'v2 已承接业绩预告信号扫描（GET /api/v2/read/earnings-hunter，封装 modules.financial_hunter.scan，best-effort）与个股一键研报（/stock-report）；逐股财报深挖走 financials 三表。仍非任意财务字段组合查询' },
  '81_自然语言选股.py': { to: '/stock/screener', note: 'v2 已承接语义解析层 + 执行链路（POST /api/v2/nl-screen/execute：候选池三级降级取数 → 条件过滤 → 二道闸排雷，available=false 原文透出）；执行依赖联网取数，离线环境仍只展示解析（能力边界非故障）' },
  // 73 自定义看板：parity B 新增服务端持久化 PUT /api/v2/read/user-dashboard（v2 组件 id，保序），
  // localStorage 仍作即时本地态；深链 ?widgets= 只读覆盖不回写。
  '73_自定义看板.py': { to: '/dashboard-custom', note: '服务端偏好写已承接（PUT user-dashboard，v2 组件 id）；注意 v2 的 5 个组件与 v1 的 6 个 Streamlit widget 并非一一对应' },
  // 95 数据导出：v2 等价实现 /export，仅浏览归档快照并导出原始 JSON（纯前端，无写能力）；
  // v1 的 CSV/Excel/PDF/ZIP/研报多格式导出尚未承接，note 如实声明。
  '95_数据导出.py': { to: '/export', note: 'v2 已承接多格式导出（GET /api/v2/read/export-bundle：7 数据集 best-effort → ZIP(全 CSV)/Excel 多 Sheet/PDF 中文摘要/JSON 预览）与一键研报（GET /api/v2/read/stock-report HTML/MD）；单数据集失败进 skipped 全清单，绝不补零' },
  // —— 以下为「已被现有 native 真实覆盖、此前误报为 data」的页，集中收口为 native（不新建页）——
  // 31/32 形态选股/智能选股：v2 等价实现 /recommend（每日荐股结果，只读展示）。
  // parity C：v1 31 的高级形态识别纯函数已后端化，/pattern-scan 真承接（不是荐股结果代偿）
  '31_形态选股.py': { to: '/pattern-scan', note: 'v2 由 /pattern-scan 承接 v1 的 MACD/均线/KDJ 金叉死叉与顶底背离纯函数算法（POST pattern-scan，单股失败 available=false 原样透出）' },
  '32_智能选股.py': { to: '/recommend' },
  // 34 体检扫描：v2 等价实现 /stock/six-dim（六维评分），非新建页。
  '34_体检扫描.py': { to: '/stock/six-dim' },
  // 47 价格预警：v2 等价实现 /alerts，四类价格预警 CRUD 已承接。
  // 44 智能条件单涉及自动触发真实下单，属实盘红线，已移入 PINNED，绝不映射到 /alerts 冒充等价。
  '47_价格预警.py': { to: '/alerts', note: '四类价格预警（price/pattern/volume/announcement）创建/启停/删除已承接' },
  // 60 事件对比分析：v2 等价实现 /events（事件因子池只读展示）。
  '60_事件对比分析.py': { to: '/events' },
  // parity B：/temperature-backtest 承接 modules/temperature_backtest.py 五档回测
  // （GET /api/v2/read/temperature-backtest，n<50 标低置信，available=false 透出 reason）。
  '63_温度回测.py': { to: '/temperature-backtest', note: 'v2 由 /temperature-backtest 承接五档温度历史回测（1/5 日红盘率回归）；与 /backtest 策略回测是不同能力' },
  // 94 消息中心：v2 等价实现 /alerts（告警日志只读展示）。
  '94_消息中心.py': { to: '/alerts' },
  // 98 仓位落地：v2 等价实现 /decision（今日决策快照），非新建页。
  '98_仓位落地.py': { to: '/decision' },
  // 16 财报日历：v2 等价实现 /earnings-calendar（新增只读端点，真实 akshare 披露日历）。
  '16_财报日历.py': { to: '/earnings-calendar' },
  // 91 我的 / 99 决策问答：v2 等价实现 /me（账户+看板偏好）/review-notes（复盘笔记），非新建页；
  // 91 的 token 信息 / 登录历史 / 偏好持久化 / 头像 / 登出已承接，note 如实声明。
  '91_我的.py': { to: '/me', note: 'token 信息 / 登录历史 / 偏好设置持久化 / 头像 / 登出已承接' },
  '99_决策问答.py': { to: '/review-notes' },
  // 65/67/68/69 离线可靠广度统计：v2 真页面（共用 /breadth-analytics，68 另按需取 /breadth-zseries）。
  '65_投机情绪周期时钟.py': { to: '/sentiment-clock' },
  '67_历史相似日聚类前向分布.py': { to: '/sentiment-clock', note: '2026-11-23 相似页重组：与 65/68/69 同走 /breadth-analytics，并入 /sentiment-clock「历史相似日」tab；旧路径 redirect' },
  '68_情绪拐点扫描器.py': { to: '/sentiment-clock', note: '2026-11-23 相似页重组：并入 /sentiment-clock「拐点扫描」tab；旧路径 redirect' },
  '69_温度持续期与回归时长.py': { to: '/sentiment-clock', note: '2026-11-23 相似页重组：并入 /sentiment-clock「温度持续期」tab；旧路径 redirect' },
  // 62 动量×广度共振：v2 等价实现 /momentum-resonance（离线广度统计真页面）。
  '62_动量广度共振.py': { to: '/sentiment-clock', note: '2026-11-23 相似页重组：并入 /sentiment-clock「动量共振」tab；旧路径 redirect' },
  // 70 涨停复盘×龙头识别：v2 等价实现 /limit-up-review（实时涨停池，联网不可用诚实降级）。
  '70_涨停复盘.py': { to: '/limit-up-review' },
  // 50 市场情绪·温度计：v2 等价实现 /market-sentiment（实时市场驱动力，单源失败优雅降级）。
  '50_市场情绪.py': { to: '/market-sentiment' },
  // —— 本批双向失真纠正：以下两页 v2 已完整实现，此前被低估为 pinned，纠正为 native ——
  // 53 星辰 AI：多会话 CRUD / 四种回应风格 / 问题分析卡 / 追问 chips / 模型徽标 /
  // Markdown+JSON 导出 / 取消生成已承接；模型分层路由选择器与 1.5s 任务轮询由 React Query 轮询等价替代。
  '53_星辰AI.py': { to: '/xingchen', note: 'v2 多会话 CRUD / 四种回应风格 / 问题分析卡 / 追问 chips / 模型徽标 / Markdown+JSON 导出 / 取消生成已承接；v1 的模型分层路由选择器与 1.5s 任务轮询在 v2 由 React Query 轮询等价替代' },
  // 52 股吧：列表/详情/发帖/评论/点赞/删除/按股票筛选已承接，后端同为 /api/forum；
  // 旧 pinned 注记「社区抓取，低频遗留」失实 —— 52 页明写纯前端聚合走后端 /api/forum，后端为完整 CRUD。
  '52_股吧.py': { to: '/forum', note: 'v2 列表/详情/发帖/评论/点赞/删除/按股票筛选已承接，后端同为 /api/forum；失实更正：旧 PINNED 注记「社区抓取，低频遗留，留 v1」有误，pages/52_股吧.py:6 明写纯前端聚合走后端 /api/forum，backend/api/forum_routes.py 为完整 CRUD，非抓取遗留' },
}

/** ② 无等价页面，但有真实只读端点可查看的关联数据（不是等价功能，页面会明示）。
 *  注：本档仅保留 v2 确无完整页面的页；已有等价 v2 页面的（如 10/35/84/85 等）
 *  已升级到 NATIVE，不再列入此处。 */
const DATA: Record<string, { path: string; label: string }> = {}

/** ③ v1 保留（永久不迁 v2）：真实交易 / 低频遗留 / 实验性页面，v2 明确不做等价实现。
 *  其中 43 实盘交易：真实券商下单(QMT/同花顺)仅 v1；v2 仅有只读账户概览（交易账户入口），
 *  不提供任何交易能力，符合「实盘交易最好不要放在 v2」的红线。 */
const PINNED: Record<string, { note: string }> = {
  '13_市场强弱.py': { note: '与广度·温度簇高度重叠且依赖 v1 实时行情单例，留 v1' },
  // 15 市场驱动力已于 2026-11-19 迁移至 native（2026-11-22 并入 /market-sentiment tab，见 NATIVE 段），不再 pinned。
  '17_市场魔方.py': { note: '展示性视图，v2 不做等价实现' },
  '25_QuantAgent投研.py': { note: '实验性 Agent 流程，留 v1 观察' },
  '33_ETF筛选.py': { note: '小众筛选器，v2 不做等价实现；已在 /stock/screener 如实登记并给出 v1 直达' },
  '43_实盘交易.py': { note: '真实券商下单(QMT/同花顺)仅 v1；v2 仅有只读账户概览（交易账户入口），不提供交易能力' },
  // 44 智能条件单：原被错标 native→/alerts，实为真实券商条件单 / 自动扫描触发下单，属实盘红线，纠正归入 PINNED。
  '44_智能条件单.py': { note: '真实券商条件单 / 自动扫描触发下单仅 v1；后端 /api/cond-orders、action=buy|sell、调度器真实下单属实盘红线，v2 不提供' },
  '83_分析规则库.py': { note: '规则维护工具，留 v1' },
  '87_语音事件.py': { note: '语音采集低频功能，留 v1' },
}

export function mappingOf(page: V1Page): V2Mapping {
  const n = NATIVE[page.file]
  if (n) return { status: 'native', to: n.to, note: n.note }
  const d = DATA[page.file]
  if (d) {
    return {
      status: 'data',
      dataPath: d.path,
      dataLabel: d.label,
      note: 'v2 暂无等价页面；此处仅查看关联的只读数据，不等同于该功能',
    }
  }
  const p = PINNED[page.file]
  if (p) return { status: 'v1-pinned', note: p.note }
  return { status: 'v1-only', note: 'v2 尚未迁移，请从 v1 打开' }
}

/** 四档数量由真实清单实时统计（不写死数字，防止清单增删后 UI 说谎）。 */
export function statusCounts(): Record<V2Status, number> {
  const out: Record<V2Status, number> = { native: 0, data: 0, 'v1-only': 0, 'v1-pinned': 0 }
  for (const p of V1_PAGES) out[mappingOf(p).status] += 1
  return out
}

/** 守卫用：所有 native 目标必须是 NAV/路由里真实存在的路径（由调用方校验）。 */
export const NATIVE_TARGETS: readonly AppPath[] = Array.from(
  new Set(Object.values(NATIVE).map((v) => v.to)),
)

/** 守卫用：登记在 NATIVE / PINNED 的文件名（校验 key 合法性、无跨档重复，防改表漏项/多项）。 */
export const NATIVE_FILES: readonly string[] = Object.keys(NATIVE)
export const PINNED_FILES: readonly string[] = Object.keys(PINNED)
