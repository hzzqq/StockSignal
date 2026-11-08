import type { AppPath } from '@/nav/nav'
import { V1_PAGES, type V1Page } from './v1Pages.generated'

/**
 * v1 功能页 → v2 落地状态（单一真理源，供功能全景页与守卫共用）。
 *
 * 三档**诚实口径**，绝不把未实现的功能标成已完成：
 *  - native   : v2 有等价页面，直接跳路由；
 *  - data     : v2 无等价页面，但有可查看的关联只读端点（真实数据，非等价功能）；
 *  - v1-only  : v2 尚未迁移，明确标注并给出 v1 直达链接。
 *
 * 映射按 v1 文件名精确匹配；未登记的页一律回落 v1-only（不臆造对应关系）。
 */

export type V2Status = 'native' | 'data' | 'v1-only'

export interface V2Mapping {
  status: V2Status
  to?: AppPath
  dataPath?: string
  dataLabel?: string
  note?: string
}

/** ① v2 已实现的等价页面（与 router.tsx 的真实路由一一对应）。 */
const NATIVE: Record<string, { to: AppPath; note?: string }> = {
  '21_多股对比.py': { to: '/stock/compare' },
  '22_基本面分析.py': { to: '/stock/fundamentals' },
  '23_事件追踪.py': { to: '/events', note: '以事件因子池视图承载' },
  '24_个股研究.py': { to: '/stock/research' },
  '36_每日荐股.py': { to: '/recommend' },
  '42_模拟交易.py': { to: '/paper' },
  '51_每日晨报.py': { to: '/morning' },
  '54_今日决策面板.py': { to: '/decision' },
  '55_P1量化信号.py': { to: '/p1' },
  '58_连板龙头共振.py': { to: '/ladder' },
  '61_广度分化.py': { to: '/breadth', note: '以广度总览视图承载' },
  '72_六维评分.py': { to: '/stock/six-dim' },
  '74_告警引擎.py': { to: '/alerts' },
  '82_数据时效性看板.py': { to: '/ops', note: '以数据与运维状态视图承载' },
  '86_网页作品集.py': { to: '/webapps' },
  '97_决策回放.py': { to: '/replay' },
  '20_个股分析.py': { to: '/stock/research', note: 'v1 已内嵌进 24 页，v2 统一由个股研究承接' },
}

/** ② 无等价页面，但有真实只读端点可查看的关联数据（不是等价功能，页面会明示）。 */
const DATA: Record<string, { path: string; label: string }> = {
  '10_行情看板.py': { path: '/api/v2/read/index-quotes', label: '主要指数行情' },
  '14_智能盯盘.py': { path: '/api/v2/read/index-quotes', label: '主要指数行情' },
  '16_财报日历.py': { path: '/api/v2/read/financials', label: '财务数据' },
  '30_策略回测.py': { path: '/api/v2/read/backtest-runs', label: '回测运行记录' },
  '31_形态选股.py': { path: '/api/v2/read/daily-recommendation', label: '每日荐股结果' },
  '32_智能选股.py': { path: '/api/v2/read/daily-recommendation', label: '每日荐股结果' },
  '34_体检扫描.py': { path: '/api/v2/read/six-dim', label: '六维评分数据' },
  '40_仓位管理.py': { path: '/api/v2/read/daily-snapshot', label: '今日决策快照' },
  '41_组合收益.py': { path: '/api/v2/read/paper-trades', label: '模拟交易记录' },
  '44_智能条件单.py': { path: '/api/v2/read/alert-rules', label: '告警规则' },
  '46_自选股监控.py': { path: '/api/v2/read/alert-rules', label: '告警规则' },
  '47_价格预警.py': { path: '/api/v2/read/alert-rules', label: '告警规则' },
  '50_市场情绪.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '56_市场状态机.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '57_市场全景.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '59_市场温度计.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '60_事件对比分析.py': { path: '/api/v2/read/event-pool', label: '事件因子池' },
  '62_动量广度共振.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '63_温度回测.py': { path: '/api/v2/read/backtest-runs', label: '回测运行记录' },
  '65_投机情绪周期时钟.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '67_历史相似日聚类前向分布.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '68_情绪拐点扫描器.py': { path: '/api/v2/read/breadth-timeseries', label: '广度时序' },
  '69_温度持续期与回归时长.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '70_涨停复盘.py': { path: '/api/v2/read/breadth-history', label: '广度历史' },
  '71_因子分析.py': { path: '/api/v2/read/event-pool', label: '事件因子池' },
  '73_自定义看板.py': { path: '/api/v2/read/user-dashboard', label: '用户看板数据' },
  '75_题材热点.py': { path: '/api/v2/read/event-pool', label: '事件因子池' },
  '77_财报猎手.py': { path: '/api/v2/read/financials', label: '财务数据' },
  '91_我的.py': { path: '/api/v2/read/user-dashboard', label: '用户看板数据' },
  '93_系统配置.py': { path: '/api/v2/read/diagnostics', label: '系统检测总览' },
  '94_消息中心.py': { path: '/api/v2/read/alert-log', label: '告警日志' },
  '95_数据导出.py': { path: '/api/v2/read/snapshot-dates', label: '快照日期清单' },
  '98_仓位落地.py': { path: '/api/v2/read/daily-snapshot', label: '今日决策快照' },
  '99_决策问答.py': { path: '/api/v2/read/review-notes', label: '复盘笔记' },
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
  return { status: 'v1-only', note: 'v2 尚未迁移，请从 v1 打开' }
}

/** 三档数量由真实清单实时统计（不写死数字，防止清单增删后 UI 说谎）。 */
export function statusCounts(): Record<V2Status, number> {
  const out: Record<V2Status, number> = { native: 0, data: 0, 'v1-only': 0 }
  for (const p of V1_PAGES) out[mappingOf(p).status] += 1
  return out
}

/** 守卫用：所有 native 目标必须是 NAV/路由里真实存在的路径（由调用方校验）。 */
export const NATIVE_TARGETS: readonly AppPath[] = Array.from(
  new Set(Object.values(NATIVE).map((v) => v.to)),
)
