/** 前端 V2 导航单一真理源（PLAN.md §3.3）。路径与 router.tsx 中的路由严格对应。 */
export type AppPath =
  | '/'
  | '/decision'
  | '/replay'
  | '/morning'
  | '/p1'
  | '/recommend'
  | '/paper'
  | '/alerts'
  | '/webapps'
  | '/breadth'
  | '/ladder'
  | '/events'
  | '/predictions'
  | '/ops'
  | '/diagnostics'
  | '/settings'
  | '/catalog'
  | '/data'
  | '/stock/six-dim'
  | '/stock/research'
  | '/stock/fundamentals'
  | '/stock/compare'
  | '/factor'
  | '/backtest'
  | '/panorama'
  | '/regime'
  | '/portfolio'
  | '/fund-flow'
  | '/trading-account'
  | '/macro-data'
  | '/login'
  | '/matrix'
  | '/guide'

export interface NavItem {
  to: AppPath
  label: string
  icon: string
}

export interface NavGroup {
  group: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    group: '首页',
    items: [{ to: '/', label: '概览', icon: '◎' }],
  },
  {
    group: '决策中枢',
    items: [
      { to: '/decision', label: '今日决策面板', icon: '◆' },
      { to: '/replay', label: '决策回放', icon: '↺' },
      { to: '/morning', label: '每日晨报', icon: '☀' },
      { to: '/p1', label: 'P1 量化信号', icon: '∑' },
    ],
  },
  {
    group: '量化与工具',
    items: [
      { to: '/recommend', label: '每日荐股', icon: '★' },
      { to: '/paper', label: '模拟交易', icon: '⊞' },
      { to: '/alerts', label: '告警引擎', icon: '!' },
      { to: '/webapps', label: '网页作品集', icon: '▦' },
      { to: '/stock/six-dim', label: '六维评分', icon: '⬡' },
      { to: '/stock/research', label: '个股研究', icon: '✦' },
      { to: '/stock/fundamentals', label: '基本面分析', icon: '▤' },
      { to: '/stock/compare', label: '个股对比', icon: '⇄' },
      { to: '/factor', label: '因子分析', icon: '◫' },
      { to: '/backtest', label: '策略回测', icon: '⊟' },
      { to: '/portfolio', label: '持仓中心', icon: '💼' },
      { to: '/trading-account', label: '实盘交易', icon: '💰' },
    ],
  },
  {
    group: '市场广度·温度',
    items: [
        { to: '/breadth', label: '广度总览', icon: '🌡' },
        { to: '/ladder', label: '连板梯队共振', icon: '🪜' },
        { to: '/events', label: '事件因子池', icon: '◈' },
        { to: '/predictions', label: '预测校准日志', icon: '◴' },
        { to: '/ops', label: '数据与运维状态', icon: '⚙' },
        { to: '/diagnostics', label: '数据源与接口检测', icon: '⛭' },
        { to: '/panorama', label: '市场全景', icon: '◉' },
        { to: '/regime', label: '市场状态机', icon: '❖' },
        { to: '/fund-flow', label: '资金流向', icon: '🌊' },
        { to: '/macro-data', label: '宏观数据', icon: '🌐' },
    ],
  },
]

/**
 * 底部固定入口 / 登录回流白名单的单一真理源。
 * 这些路径不进 NAV（导航守卫锁死 4 组、第 3 组 11 项（含 ◫ 因子分析 / ⊟ 策略回测 / 💼 持仓中心）、图标全局唯一），
 * 但同样是真实路由：LoginPage 的 knownPaths 必须认它们，否则从这些页被踢去
 * 登录后会静默回首页（历史缺陷：手抄 KNOWN_PATHS 漏掉新增路径）。
 * /login 不在其中 —— 它是未鉴权入口，不能作为登录后的回流目标。
 */
export const UTILITY_PATHS: readonly AppPath[] = [
  '/settings', '/catalog', '/data', '/matrix', '/guide',
]
