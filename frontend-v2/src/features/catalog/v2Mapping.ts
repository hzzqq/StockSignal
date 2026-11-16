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
 *    63 温度回测与 /backtest 模块错配，撤下 native 回落 v1-only；
 *    并为 42/11/14/20/40/41/45/46/61/95 等只读缩水页补齐诚实 note，杜绝「标 native 却零说明」。
 */

export type V2Status = 'native' | 'data' | 'v1-only' | 'v1-pinned'

export interface V2Mapping {
  status: V2Status
  to?: AppPath
  dataPath?: string
  dataLabel?: string
  note?: string
}

/** 已知能力缩水的诚实说明（集中定义，避免多页重复文案漂移）：
 *  - 只读聚合页：主力资金流只读、写能力由本批 /watch 面板承接、实时现价未聚合；
 *  - 只读快照页：组合编辑 / 权重调整等 v1 写操作 v2 未承接。 */
const WATCH_READONLY_NOTE =
  '逐只主力资金流为只读聚合；自选股增删/垃圾股标记/自定义打分由本批 /watch 页写面板承接；实时现价与涨跌幅未在只读端点聚合'
const SNAPSHOT_READONLY_NOTE = '只读快照视图，v1 的组合编辑/权重调整等写操作 v2 未承接'

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
  '51_每日晨报.py': { to: '/morning' },
  '54_今日决策面板.py': { to: '/decision' },
  '55_P1量化信号.py': { to: '/p1' },
  '97_决策回放.py': { to: '/replay' },
  // 量化工具
  '30_策略回测.py': { to: '/backtest' },
  '71_因子分析.py': { to: '/factor' },
  '72_六维评分.py': { to: '/stock/six-dim' },
  // 交易 / 持仓
  '42_模拟交易.py': { to: '/paper', note: '仅展示 /api/v2/read/paper-trades 只读账本；v1 的模拟下单/平仓写入本地 JSON 账本，后端无对应写端点，v2 暂未承接' },
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
  '56_市场状态机.py': { to: '/regime' },
  '57_市场全景.py': { to: '/panorama' },
  '59_市场温度计.py': { to: '/breadth' },
  '61_广度分化.py': { to: '/breadth', note: 'v2 仅广度总览，v1 的 modules/breadth_divergence.py 分化维度算法未承接' },
  '58_连板龙头共振.py': { to: '/ladder' },
  // 市场数据
  '75_题材热点.py': { to: '/theme' },
  '76_实时强势榜.py': { to: '/strong' },
  '84_宏观数据.py': { to: '/macro-data' },
  '85_龙虎榜.py': { to: '/dragon-tiger' },
  '64_投研圆桌.py': { to: '/predictions' },
  // 告警 / 系统 / 教学
  '74_告警引擎.py': { to: '/alerts' },
  '82_数据时效性看板.py': { to: '/ops', note: '以数据与运维状态视图承载' },
  '86_网页作品集.py': { to: '/webapps' },
  '93_系统配置.py': { to: '/settings' },
  '90_登录.py': { to: '/login', note: '账号密码登录与行情台已实现；验证码登录/注册未接入，v2 不做假功能' },
  '96_新手教程.py': { to: '/guide', note: '四步上手/模块导览/术语表/FAQ/主线/误区已移植；教学视频与 Streamlit 快捷键不适用未移植' },
  // W4-F · v1-only 收口（路径均已在 router.tsx 真实注册）
  '66_维度领先滞后矩阵.py': { to: '/matrix', note: '以有序对明细表承载（带符号 lag），样本下限比 v1 更严格' },
  // 92 用户管理（管理员专属）：v2 等价实现 /users，三 Tab（列表/创建/日志）+ 角色门控；
  // 与 v1 同源「不能删自己/初始 admin」规则；与交易无关，实盘交易红线不受影响。
  '92_用户管理.py': { to: '/users' },
  // 77 财报猎手：v2 等价实现 /financial-hunter，逐股票三表（income/balance/cash）切换深挖；
  // 非跨股筛选器（v2 暂无跨股财报筛选端点），页面如实说明。
  '77_财报猎手.py': { to: '/financial-hunter' },
  // 73 自定义看板：v2 等价实现 /dashboard-custom，勾选组件 + localStorage 持久化，聚合现有只读端点。
  '73_自定义看板.py': { to: '/dashboard-custom' },
  // 95 数据导出：v2 等价实现 /export，仅浏览归档快照并导出原始 JSON（纯前端，无写能力）；
  // v1 的 CSV/Excel/PDF/ZIP/研报多格式导出尚未承接，note 如实声明。
  '95_数据导出.py': { to: '/export', note: '当前仅导出原始 JSON 归档；v1 的 CSV/Excel/PDF/ZIP/研报多格式导出 v2 尚未承接' },
  // —— 以下为「已被现有 native 真实覆盖、此前误报为 data」的页，集中收口为 native（不新建页）——
  // 31/32 形态选股/智能选股：v2 等价实现 /recommend（每日荐股结果，只读展示）。
  '31_形态选股.py': { to: '/recommend', note: 'v2 由每日荐股承接荐股结果；技术形态扫描器本身未迁移，已在 /stock/screener 如实登记' },
  '32_智能选股.py': { to: '/recommend' },
  // 34 体检扫描：v2 等价实现 /stock/six-dim（六维评分），非新建页。
  '34_体检扫描.py': { to: '/stock/six-dim' },
  // 47 价格预警：v2 等价实现 /alerts，四类价格预警 CRUD 已承接。
  // 44 智能条件单涉及自动触发真实下单，属实盘红线，已移入 PINNED，绝不映射到 /alerts 冒充等价。
  '47_价格预警.py': { to: '/alerts', note: '四类价格预警（price/pattern/volume/announcement）创建/启停/删除已承接' },
  // 60 事件对比分析：v2 等价实现 /events（事件因子池只读展示）。
  '60_事件对比分析.py': { to: '/events' },
  // 63 温度回测：/backtest 是策略回测而非温度回测（模块错配），不在此登记 native，
  // 回落 v1-only；v1 的 modules/temperature_backtest.py 算法 v2 未承接，详见 V1-V2-PARITY.md B 类。
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
  '67_历史相似日聚类前向分布.py': { to: '/similar-days' },
  '68_情绪拐点扫描器.py': { to: '/inflection-scan' },
  '69_温度持续期与回归时长.py': { to: '/regime-duration' },
  // 62 动量×广度共振：v2 等价实现 /momentum-resonance（离线广度统计真页面）。
  '62_动量广度共振.py': { to: '/momentum-resonance' },
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
  '15_市场驱动力.py': { note: '实验性视图，v2 暂无等价计划' },
  '17_市场魔方.py': { note: '展示性视图，v2 不做等价实现' },
  '25_QuantAgent投研.py': { note: '实验性 Agent 流程，留 v1 观察' },
  '33_ETF筛选.py': { note: '小众筛选器，v2 不做等价实现；已在 /stock/screener 如实登记并给出 v1 直达' },
  '43_实盘交易.py': { note: '真实券商下单(QMT/同花顺)仅 v1；v2 仅有只读账户概览（交易账户入口），不提供交易能力' },
  // 44 智能条件单：原被错标 native→/alerts，实为真实券商条件单 / 自动扫描触发下单，属实盘红线，纠正归入 PINNED。
  '44_智能条件单.py': { note: '真实券商条件单 / 自动扫描触发下单仅 v1；后端 /api/cond-orders、action=buy|sell、调度器真实下单属实盘红线，v2 不提供' },
  '81_自然语言选股.py': { note: '实验性 NL 选股；v2 仅承接语义解析层（/stock/screener 透明展示「听懂了什么」，不触网、不返回候选标的），联网筛选执行仍仅 v1，v2 不做等价实现' },
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
