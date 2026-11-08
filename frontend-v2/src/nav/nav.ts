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
  | '/stock/six-dim'
  | '/stock/research'
  | '/stock/fundamentals'
  | '/stock/compare'

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
    ],
  },
]
