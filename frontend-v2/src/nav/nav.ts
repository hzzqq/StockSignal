/** 前端 V2 导航单一真理源（PLAN.md §3.3）。路径与 router.tsx 中的路由严格对应。 */
export type AppPath =
  | '/'
  | '/decision'
  | '/replay'
  | '/morning'
  | '/p1'
  | '/p1-construction'
  | '/recommend'
  | '/paper'
  | '/alerts'
  | '/webapps'
  | '/breadth'
  // 61 广度结构分化 / 63 温度档历史回测（parity B 批次）
  | '/breadth-divergence'
  | '/temperature-backtest'
  | '/pattern-scan'
  | '/ladder'
  | '/events'
  | '/event-backtest'
  | '/policy-transmission'
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
  | '/stock/screener'
  | '/factor'
  | '/backtest'
  | '/panorama'
  | '/regime'
  | '/portfolio'
  | '/fund-flow'
  | '/trading-account'
  | '/macro-data'
  | '/dragon-tiger'
  | '/theme'
  | '/strong'
  | '/sector-rotation'
  | '/watch'
  | '/quote-board'
  | '/login'
  | '/matrix'
  | '/guide'
  | '/users'
  | '/financial-hunter'
  | '/dashboard-custom'
  | '/export'
  | '/earnings-calendar'
  | '/me'
  | '/review-notes'
  | '/sentiment-clock'
  | '/similar-days'
  | '/inflection-scan'
  | '/regime-duration'
  | '/momentum-resonance'
  | '/limit-up-review'
  | '/market-sentiment'
  // 15 市场驱动力（2026-11-19 由 v1-pinned 升 native）：复用 /market-sentiment 数据的五维派生页
  | '/market-drivers'
  | '/xingchen'
  // 股吧社区（52 页 V2 化）：后端 /api/forum 完整 CRUD，非 v1「社区抓取」遗留
  | '/forum'

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
    group: '决策与晨报',
    items: [
      { to: '/', label: '概览', icon: '◎' },
      { to: '/decision', label: '今日决策面板', icon: '◆' },
      { to: '/replay', label: '决策回放', icon: '↺' },
      { to: '/morning', label: '每日晨报', icon: '☀' },
      { to: '/p1', label: 'P1 量化信号', icon: '∑' },
      { to: '/p1-construction', label: 'P1 组合构建诊断', icon: '📐' },
      // 事件因子与校准属决策支持，从广度组迁入以腾出位置给新的分化/回测页
      { to: '/event-backtest', label: '事件因子回测', icon: '⌖' },
      { to: '/policy-transmission', label: '政策传导', icon: '📜' },
      { to: '/predictions', label: '预测校准日志', icon: '◴' },
    ],
  },
  {
    group: '智能助手与社区',
    items: [
      { to: '/xingchen', label: '星辰 AI 助手', icon: '🌟' },
      { to: '/review-notes', label: '决策问答', icon: '❓' },
      // 52 页：v1 就走 /api/forum（纯后端 CRUD），旧映射标「社区抓取，留 v1」是失实描述
      { to: '/forum', label: '股吧社区', icon: '💬' },
    ],
  },
  {
    group: '个股研究',
    items: [
      { to: '/stock/six-dim', label: '六维评分', icon: '⬡' },
      { to: '/stock/research', label: '个股研究', icon: '✦' },
      { to: '/stock/fundamentals', label: '基本面分析', icon: '▤' },
      { to: '/stock/compare', label: '个股对比', icon: '⇄' },
      { to: '/stock/screener', label: '选股框架', icon: '⌕' },
      { to: '/factor', label: '因子分析', icon: '◫' },
      { to: '/financial-hunter', label: '财报猎手', icon: '📒' },
      { to: '/earnings-calendar', label: '财报日历', icon: '🗓' },
    ],
  },
  {
    group: '策略与持仓',
    items: [
      { to: '/recommend', label: '每日荐股', icon: '★' },
      { to: '/backtest', label: '策略回测', icon: '⊟' },
      { to: '/pattern-scan', label: '技术形态扫描', icon: '⌗' },
      { to: '/paper', label: '模拟交易', icon: '⊞' },
      { to: '/portfolio', label: '持仓中心', icon: '💼' },
      { to: '/trading-account', label: '交易账户（只读）', icon: '💰' },
      { to: '/alerts', label: '告警引擎', icon: '!' },
    ],
  },
  {
    group: '行情与市场',
    items: [
      { to: '/quote-board', label: '行情看板', icon: '📊' },
      { to: '/panorama', label: '市场全景', icon: '◉' },
      { to: '/regime', label: '市场状态机', icon: '❖' },
      { to: '/fund-flow', label: '资金流向', icon: '🌊' },
      { to: '/macro-data', label: '宏观数据', icon: '🌐' },
      { to: '/dragon-tiger', label: '龙虎榜', icon: '🐯' },
      { to: '/theme', label: '题材热点', icon: '🧱' },
      { to: '/strong', label: '实时强势榜', icon: '🏅' },
      { to: '/sector-rotation', label: '板块轮动', icon: '🔥' },
      { to: '/watch', label: '智能盯盘', icon: '👁️' },
      { to: '/market-drivers', label: '市场驱动力', icon: '🧮' },
    ],
  },
  {
    group: '广度·温度与情绪',
    items: [
      { to: '/breadth', label: '广度总览', icon: '🌡' },
      { to: '/breadth-divergence', label: '广度结构分化', icon: '▥' },
      { to: '/temperature-backtest', label: '温度档回测', icon: '⌁' },
      { to: '/ladder', label: '连板梯队共振', icon: '🪜' },
      { to: '/sentiment-clock', label: '投机情绪时钟', icon: '◷' },
      { to: '/market-sentiment', label: '市场情绪温度计', icon: '⚖️' },
      { to: '/regime-duration', label: '温度持续期', icon: '⧗' },
      { to: '/similar-days', label: '历史相似日', icon: '≋' },
      { to: '/inflection-scan', label: '情绪拐点扫描', icon: '⤴' },
      { to: '/momentum-resonance', label: '动量×广度共振', icon: '🌀' },
      { to: '/limit-up-review', label: '涨停复盘', icon: '🏆' },
      { to: '/events', label: '事件因子池', icon: '◈' },
    ],
  },
  {
    group: '数据·运维·系统',
    items: [
      { to: '/ops', label: '数据与运维状态', icon: '⚙' },
      { to: '/diagnostics', label: '数据源与接口检测', icon: '⛭' },
      { to: '/export', label: '数据导出', icon: '📤' },
      { to: '/catalog', label: 'v1 功能全景', icon: '▣' },
      { to: '/matrix', label: '维度领先滞后矩阵', icon: '⊹' },
      { to: '/webapps', label: '网页作品集', icon: '▦' },
      { to: '/dashboard-custom', label: '自定义看板', icon: '🧩' },
      { to: '/guide', label: '新手教程', icon: '◇' },
      { to: '/settings', label: '设置', icon: '⚒' },
      { to: '/users', label: '用户管理', icon: '👥' },
      { to: '/me', label: '我的', icon: '👤' },
    ],
  },
]

/**
 * 登录回流白名单补集（不在侧栏 NAV 中的合法路径）。
 *
 * 历史：这里曾有 20 条「底部固定入口」——它们既不进 NAV，又在 AppShell 里
 * 手抄一份 `to="..."` 平铺，造成左侧 40+ 链接无分类、真源分裂。
 * 现已全部按语义并入 NAV 七个分组，AppShell 只从 NAV 派生，不再硬编码。
 * 仅保留 /data：它由「v1 功能全景」深链进入，不做侧栏入口，但登录后
 * 从该页回流时仍必须是合法目标（否则会被静默甩回首页）。
 * /login 不在其中 —— 它是未鉴权入口，不能作为登录后的回流目标。
 */
export const UTILITY_PATHS: readonly AppPath[] = ['/data']
