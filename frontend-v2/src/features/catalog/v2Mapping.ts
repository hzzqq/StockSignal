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
 */

export type V2Status = 'native' | 'data' | 'v1-only' | 'v1-pinned'

export interface V2Mapping {
  status: V2Status
  to?: AppPath
  dataPath?: string
  dataLabel?: string
  note?: string
}

/** ① v2 已实现的等价页面（与 router.tsx / nav.ts 的真实路由一一对应）。
 *  含「漂移收口」：原来被错标成 data / v1-only 的页，因 v2 实际已有完整页面，
 *  在此统一升级为 native（如行情看板→/quote-board、资金流向→/fund-flow、龙虎榜→
 *  /dragon-tiger 等），使功能全景不再低估 v2 覆盖。 */
const NATIVE: Record<string, { to: AppPath; note?: string }> = {
  // 个股研究簇
  '20_个股分析.py': { to: '/stock/research', note: 'v1 已内嵌进 24 页，v2 统一由个股研究承接' },
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
  '42_模拟交易.py': { to: '/paper' },
  '40_仓位管理.py': { to: '/portfolio' },
  '41_组合收益.py': { to: '/portfolio' },
  '45_持仓中心.py': { to: '/portfolio' },
  // 行情 / 板块 / 盯盘
  '10_行情看板.py': { to: '/quote-board' },
  '11_股票选取.py': { to: '/quote-board', note: '选股入口由行情看板承接' },
  '12_板块轮动.py': { to: '/sector-rotation' },
  '14_智能盯盘.py': { to: '/watch' },
  '46_自选股监控.py': { to: '/watch' },
  '35_资金流向.py': { to: '/fund-flow' },
  // 广度·温度簇
  '56_市场状态机.py': { to: '/regime' },
  '57_市场全景.py': { to: '/panorama' },
  '59_市场温度计.py': { to: '/breadth' },
  '61_广度分化.py': { to: '/breadth', note: '以广度总览视图承载' },
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
}

/** ② 无等价页面，但有真实只读端点可查看的关联数据（不是等价功能，页面会明示）。
 *  注：本档仅保留 v2 确无完整页面的页；已有等价 v2 页面的（如 10/35/84/85 等）
 *  已升级到 NATIVE，不再列入此处。 */
const DATA: Record<string, { path: string; label: string }> = {
  '16_财报日历.py': { path: '/api/v2/read/financials', label: '财务数据' },
  '31_形态选股.py': { path: '/api/v2/read/daily-recommendation', label: '每日荐股结果' },
  '32_智能选股.py': { path: '/api/v2/read/daily-recommendation', label: '每日荐股结果' },
  '34_体检扫描.py': { path: '/api/v2/read/six-dim', label: '六维评分数据' },
  '44_智能条件单.py': { path: '/api/v2/read/alert-rules', label: '告警规则' },
  '47_价格预警.py': { path: '/api/v2/read/alert-rules', label: '告警规则' },
  '50_市场情绪.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '60_事件对比分析.py': { path: '/api/v2/read/event-pool', label: '事件因子池' },
  '62_动量广度共振.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '63_温度回测.py': { path: '/api/v2/read/backtest-runs', label: '回测运行记录' },
  '65_投机情绪周期时钟.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '67_历史相似日聚类前向分布.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '68_情绪拐点扫描器.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '69_温度持续期与回归时长.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '70_涨停复盘.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '73_自定义看板.py': { path: '/api/v2/read/user-dashboard', label: '用户看板数据' },
  '91_我的.py': { path: '/api/v2/read/user-dashboard', label: '用户看板数据' },
  '94_消息中心.py': { path: '/api/v2/read/alert-log', label: '告警日志' },
  '95_数据导出.py': { path: '/api/v2/read/snapshot-dates', label: '快照日期清单' },
  '98_仓位落地.py': { path: '/api/v2/read/daily-snapshot', label: '今日决策快照' },
  '99_决策问答.py': { path: '/api/v2/read/review-notes', label: '复盘笔记' },
}

/** ③ v1 保留（永久不迁 v2）：真实交易 / 低频遗留 / 实验性页面，v2 明确不做等价实现。
 *  其中 43 实盘交易：真实券商下单(QMT/同花顺)仅 v1；v2 仅有只读账户概览（交易账户入口），
 *  不提供任何交易能力，符合「实盘交易最好不要放在 v2」的红线。 */
const PINNED: Record<string, { note: string }> = {
  '13_市场强弱.py': { note: '与广度·温度簇高度重叠且依赖 v1 实时行情单例，留 v1' },
  '15_市场驱动力.py': { note: '实验性视图，v2 暂无等价计划' },
  '17_市场魔方.py': { note: '展示性视图，v2 不做等价实现' },
  '25_QuantAgent投研.py': { note: '实验性 Agent 流程，留 v1 观察' },
  '33_ETF筛选.py': { note: '小众筛选器，v2 暂无等价计划' },
  '43_实盘交易.py': { note: '真实券商下单(QMT/同花顺)仅 v1；v2 仅有只读账户概览（交易账户入口），不提供交易能力' },
  '52_股吧.py': { note: '社区抓取，低频遗留，留 v1' },
  '53_星辰AI.py': { note: '独立 AI 对话，留 v1' },
  '81_自然语言选股.py': { note: '实验性 NL 选股，v2 暂无等价计划' },
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
