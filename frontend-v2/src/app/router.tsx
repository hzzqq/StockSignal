import { lazy, Suspense } from 'react'
import {
  createRootRoute, createRoute, createRouter, Outlet, redirect, lazyRouteComponent,
} from '@tanstack/react-router'
import { LoginPage } from '@/features/auth/LoginPage'
import { requireAuth } from './guards'
import { AppShell } from './AppShell'
import { resolveResearchSearch, resolveLegacySearch, resolveCompareSearch } from '@/lib/deeplink'
import type { ResearchRouteSearch, CompareRouteSearch } from '@/lib/deeplink'

/**
 * 路由级懒加载（2026-11-09）：页面组件不再静态进 index 主包。
 *
 * 历史：26 个页面组件全部静态 import，首屏必须下载整站代码（index 493 kB）。
 * 现用 TanStack 官方 lazyRouteComponent（支持 preload / 模块缺失重载），
 * 只有命中该路由才拉取对应 chunk；LoginPage 与 AppShell 是首屏/外壳，保持静态。
 * 5 个需要 route.useSearch() 传参的 wrapper 不能整块懒加载，改为内部 React.lazy。
 * ⚠️ 新增页面必须走 lazyRouteComponent，别把静态 import 加回来（守卫见
 * tests/unit/route-lazy.test.ts）。
 */
const LazyDashboard = lazyRouteComponent(() => import('@/features/dashboard/Dashboard'), 'Dashboard')
const LazyDecisionPanel = lazyRouteComponent(() => import('@/features/decision/DecisionPanel'), 'DecisionPanel')
const LazyDecisionReplay = lazyRouteComponent(() => import('@/features/decision/DecisionReplay'), 'DecisionReplay')
const LazyMorningReport = lazyRouteComponent(() => import('@/features/morning/MorningReport'), 'MorningReport')
const LazyP1Signals = lazyRouteComponent(() => import('@/features/p1/P1Signals'), 'P1Signals')
const LazyRecommendation = lazyRouteComponent(() => import('@/features/recommend/Recommendation'), 'Recommendation')
const LazyPaperTrades = lazyRouteComponent(() => import('@/features/paper/PaperTrades'), 'PaperTrades')
const LazyAlerts = lazyRouteComponent(() => import('@/features/alerts/Alerts'), 'Alerts')
const LazyWebApps = lazyRouteComponent(() => import('@/features/webapps/WebApps'), 'WebApps')
const LazyBreadthOverview = lazyRouteComponent(() => import('@/features/breadth/BreadthOverview'), 'BreadthOverview')
const LazyLadderResonance = lazyRouteComponent(() => import('@/features/breadth/LadderResonance'), 'LadderResonance')
const LazyEventPoolView = lazyRouteComponent(() => import('@/features/ops/EventPoolView'), 'EventPoolView')
const LazyPredictionLogView = lazyRouteComponent(() => import('@/features/ops/PredictionLogView'), 'PredictionLogView')
const LazySystemStatusView = lazyRouteComponent(() => import('@/features/ops/SystemStatusView'), 'SystemStatusView')
const LazyDiagnosticsView = lazyRouteComponent(() => import('@/features/ops/DiagnosticsView'), 'DiagnosticsView')
const LazySixDimView = lazyRouteComponent(() => import('@/features/stock/SixDimView'), 'SixDimView')
const LazySettingsView = lazyRouteComponent(() => import('@/features/settings/SettingsView'), 'SettingsView')
const LazyCatalogView = lazyRouteComponent(() => import('@/features/catalog/CatalogView'), 'CatalogView')
const LazyLeadLagMatrixView = lazyRouteComponent(() => import('@/features/matrix/LeadLagMatrixView'), 'LeadLagMatrixView')
const LazyGuideView = lazyRouteComponent(() => import('@/features/guide/GuideView'), 'GuideView')
const LazyFactorAnalysis = lazyRouteComponent(() => import('@/features/factor/FactorAnalysis'), 'FactorAnalysis')
const LazyBacktest = lazyRouteComponent(() => import('@/features/backtest/Backtest'), 'Backtest')
const LazyMarketPanorama = lazyRouteComponent(() => import('@/features/market/MarketPanorama'), 'MarketPanorama')
const LazyMarketRegime = lazyRouteComponent(() => import('@/features/market/MarketRegime'), 'MarketRegime')
const LazyPortfolio = lazyRouteComponent(() => import('@/features/portfolio/Portfolio'), 'Portfolio')
const LazyFundFlow = lazyRouteComponent(() => import('@/features/fundflow/FundFlow'), 'FundFlow')
const LazyTradingAccount = lazyRouteComponent(() => import('@/features/trading/TradingAccount'), 'TradingAccount')
const LazyMacroData = lazyRouteComponent(() => import('@/features/macro/MacroData'), 'MacroData')
const LazyDragonTiger = lazyRouteComponent(() => import('@/features/dragontiger/DragonTiger'), 'DragonTiger')
const LazyTheme = lazyRouteComponent(() => import('@/features/theme/Theme'), 'Theme')
const LazyStrong = lazyRouteComponent(() => import('@/features/strong/Strong'), 'Strong')
const LazySectorRotation = lazyRouteComponent(() => import('@/features/sector-rotation/SectorRotation'), 'SectorRotation')
const LazyWatch = lazyRouteComponent(() => import('@/features/watch/Watch'), 'Watch')
const LazyQuoteBoard = lazyRouteComponent(() => import('@/features/quote-board/QuoteBoard'), 'QuoteBoard')
const LazyUserManagement = lazyRouteComponent(() => import('@/features/admin/UserManagement'), 'UserManagement')
const LazyDashboardCustom = lazyRouteComponent(() => import('@/features/dashboard/DashboardCustom'), 'DashboardCustom')
const LazyDataExport = lazyRouteComponent(() => import('@/features/export/DataExport'), 'DataExport')
const LazyMe = lazyRouteComponent(() => import('@/features/me/Me'), 'Me')
const LazyEarningsCalendar = lazyRouteComponent(() => import('@/features/calendar/EarningsCalendar'), 'EarningsCalendar')
const LazyReviewNotes = lazyRouteComponent(() => import('@/features/review/ReviewNotes'), 'ReviewNotes')
const LazySentimentClock = lazyRouteComponent(() => import('@/features/analytics/SentimentClock'), 'SentimentClock')
const LazySimilarDays = lazyRouteComponent(() => import('@/features/analytics/SimilarDays'), 'SimilarDays')
const LazyInflectionScan = lazyRouteComponent(() => import('@/features/analytics/InflectionScan'), 'InflectionScan')
const LazyRegimeDuration = lazyRouteComponent(() => import('@/features/analytics/RegimeDuration'), 'RegimeDuration')
const LazyMomentumResonance = lazyRouteComponent(() => import('@/features/breadth/MomentumResonance'), 'MomentumResonance')
const LazyLimitUpReview = lazyRouteComponent(() => import('@/features/breadth/LimitUpReview'), 'LimitUpReview')
const LazyMarketSentiment = lazyRouteComponent(() => import('@/features/market/MarketSentiment'), 'MarketSentiment')

// wrapper 内部按需加载纯组件（它们依赖 route.useSearch()，wrapper 本身必须静态）
const LazyDataSourceView = lazy(() => import('@/features/catalog/DataSourceView').then((m) => ({ default: m.DataSourceView })))
const LazyResearchView = lazy(() => import('@/features/stock/ResearchView').then((m) => ({ default: m.ResearchView })))
const LazyFundamentalsView = lazy(() => import('@/features/stock/FundamentalsView').then((m) => ({ default: m.FundamentalsView })))
const LazyCompareView = lazy(() => import('@/features/stock/CompareView').then((m) => ({ default: m.CompareView })))
const LazyFinancialHunter = lazy(() => import('@/features/stock/FinancialHunter').then((m) => ({ default: m.FinancialHunter })))

/** 懒加载期间的诚实占位：不编造数据、不显示旧页面。 */
function RouteLoading() {
  return <div role="status" className="flow">页面加载中…</div>
}

// 根布局：仅渲染子路由出口（登录页、/legacy 兼容层与鉴权外壳并列挂在根下）
const rootRoute = createRootRoute({
  component: () => <Outlet />,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>) => ({
    from: typeof search.from === 'string' ? search.from : '/',
  }),
  component: LoginPage,
})

// W4-B · /legacy 旧链接兼容层：与 loginRoute 并列挂在 rootRoute（不能放 appRoute 下，
// 否则 requireAuth 会先把未登录用户跳去 /login，且 loginRoute 的 validateSearch 只留 from 会吞掉 query）。
// ⚠️ 这是客户端 history.replace，非 HTTP 302；纯 SPA + Vite dev proxy 产生不了 3xx。
const legacyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/legacy',
  validateSearch: (raw: Record<string, unknown>): Record<string, unknown> => ({
    hub_gyj_view: typeof raw.hub_gyj_view === 'string' ? raw.hub_gyj_view : undefined,
    pick_stock: typeof raw.pick_stock === 'string' ? raw.pick_stock : undefined,
  }),
  beforeLoad: ({ search }) => {
    const resolved = resolveLegacySearch(search)
    throw redirect({ to: '/stock/research', search: resolved, replace: true })
  },
  component: () => null,
})

// 鉴权外壳：所有子路由统一走 requireAuth，未登录跳 /login 并保留来源
const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'app',
  beforeLoad: () => {
    requireAuth('/')
  },
  component: AppShell,
})

const dashboardRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/',
  component: LazyDashboard,
})

const decisionRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/decision',
  component: LazyDecisionPanel,
})

const replayRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/replay',
  component: LazyDecisionReplay,
})

const morningRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/morning',
  component: LazyMorningReport,
})

const p1Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/p1',
  component: LazyP1Signals,
})

const recommendRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/recommend',
  component: LazyRecommendation,
})

const paperRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/paper',
  component: LazyPaperTrades,
})

const alertsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/alerts',
  component: LazyAlerts,
})

const webappsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/webapps',
  component: LazyWebApps,
})

const breadthRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/breadth',
  component: LazyBreadthOverview,
})

const ladderRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/ladder',
  component: LazyLadderResonance,
})

const eventsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/events',
  component: LazyEventPoolView,
})

const predictionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/predictions',
  component: LazyPredictionLogView,
})

const opsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/ops',
  component: LazySystemStatusView,
})

// W4-D · 数据源与接口检测（两块检测同页，主动探测、默认零网络）
const diagnosticsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/diagnostics',
  component: LazyDiagnosticsView,
})

// W4-E · 设置 / v1 功能全景 / 只读端点数据浏览器（侧边栏底部固定入口）
const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/settings',
  component: LazySettingsView,
})

const catalogRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/catalog',
  component: LazyCatalogView,
})

// W4-F · v1-only 迁移：66 维度领先滞后矩阵 / 96 新手教程（底部固定入口，不进 NAV）
const matrixRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/matrix',
  component: LazyLeadLagMatrixView,
})

const guideRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/guide',
  component: LazyGuideView,
})

const factorRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/factor',
  component: LazyFactorAnalysis,
})

const backtestRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/backtest',
  component: LazyBacktest,
})

const panoramaRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/panorama',
  component: LazyMarketPanorama,
})

const regimeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/regime',
  component: LazyMarketRegime,
})

const portfolioRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/portfolio',
  component: LazyPortfolio,
})

const fundFlowRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/fund-flow',
  component: LazyFundFlow,
})

const tradingAccountRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/trading-account',
  component: LazyTradingAccount,
})

const macroDataRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/macro-data',
  component: LazyMacroData,
})

const dragonTigerRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/dragon-tiger',
  component: LazyDragonTiger,
})

const themeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/theme',
  component: LazyTheme,
})

const strongRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/strong',
  component: LazyStrong,
})

const sectorRotationRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/sector-rotation',
  component: LazySectorRotation,
})

const watchRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/watch',
  component: LazyWatch,
})

const quoteBoardRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/quote-board',
  component: LazyQuoteBoard,
})

// 管理端（92 用户管理 V2 化）：底部固定入口，不进 NAV（保持导航分组/图标唯一守卫）
const usersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/users',
  component: LazyUserManagement,
})

// 77 财报猎手（v2 native，旧 77 财报猎手页）：?code= 入边（与 fundamentals 同款写法）。
const financialHunterRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/financial-hunter',
  validateSearch: (raw: Record<string, unknown>): { code?: string } => {
    const code = raw.code
    return typeof code === 'string' && /^\d{6}$/.test(code) ? { code } : {}
  },
  component: FinancialHunterRouteView,
})

// 73 自定义看板（v2 native，旧 73 自定义看板页）：?widgets= 可选深链覆盖（逗号分隔 id）。
const dashboardCustomRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/dashboard-custom',
  validateSearch: (raw: Record<string, unknown>): { widgets?: string } => ({
    widgets: typeof raw.widgets === 'string' ? raw.widgets : undefined,
  }),
  component: LazyDashboardCustom,
})

// 95 数据导出（v2 native，旧 95 数据导出页）：浏览归档快照并导出原始 JSON（纯前端，无写能力）。
const dataExportRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/export',
  component: LazyDataExport,
})

// 91 我的（v2 native，旧 91 我的页）：展示登录身份 + 自定义看板偏好种子。
const meRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/me',
  component: LazyMe,
})

// 16 财报日历（v2 native，旧 16 财报日历页）：财报披露日历（真实 akshare 数据源）。
const earningsCalendarRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/earnings-calendar',
  component: LazyEarningsCalendar,
})

// 99 决策问答（v2 native，旧 99 决策问答页）：逐日复盘笔记（只读，缺失即诚实空态）。
const reviewNotesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/review-notes',
  component: LazyReviewNotes,
})

// 65 投机情绪周期时钟（v2 native /sentiment-clock）：离线可靠广度统计真页面。
const sentimentClockRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/sentiment-clock',
  component: LazySentimentClock,
})

// 67 历史相似日聚类（v2 native /similar-days）：离线可靠广度统计真页面。
const similarDaysRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/similar-days',
  component: LazySimilarDays,
})

// 68 情绪拐点扫描器（v2 native /inflection-scan）：离线可靠广度统计真页面。
const inflectionScanRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/inflection-scan',
  component: LazyInflectionScan,
})

// 69 温度持续期与回归时长（v2 native /regime-duration）：离线可靠广度统计真页面。
const regimeDurationRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/regime-duration',
  component: LazyRegimeDuration,
})

// 62 动量×广度共振（v2 native /momentum-resonance）：离线广度统计真页面。
const momentumResonanceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/momentum-resonance',
  component: LazyMomentumResonance,
})

// 70 涨停复盘 × 龙头识别（v2 native /limit-up-review）：实时涨停池（东财，10 分钟缓存）。
const limitUpReviewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/limit-up-review',
  component: LazyLimitUpReview,
})

// 50 市场情绪·广度与情绪温度计（v2 native /market-sentiment）：实时市场驱动力（21 指标）。
const marketSentimentRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/market-sentiment',
  component: LazyMarketSentiment,
})

function FinancialHunterRouteView() {
  const search = financialHunterRoute.useSearch()
  return (
    <Suspense fallback={<RouteLoading />}>
      <LazyFinancialHunter search={search} />
    </Suspense>
  )
}

const dataRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/data',
  validateSearch: (raw: Record<string, unknown>): { path?: string } => ({
    path: typeof raw.path === 'string' ? raw.path : undefined,
  }),
  component: DataRouteView,
})

/** 薄 wrapper：把 query 里的端点路径传给纯组件（E2E 无需 RouterProvider）。 */
function DataRouteView() {
  const search = dataRoute.useSearch()
  return (
    <Suspense fallback={<RouteLoading />}>
      <LazyDataSourceView initialPath={search.path ?? ''} />
    </Suspense>
  )
}

const sixDimRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/stock/six-dim',
  component: LazySixDimView,
})

// W4-B · /stock/research（旧 24 页）：validateSearch 输出全字段 optional（ResearchRouteSearch），
// 避免 AppShell.tsx 泛化 <Link to={it.to}> 因 search 必填而 tsc 失败；1.170.46 中 validateSearch
// 同步早于渲染，无需 beforeLoad/useEffect 即可首帧预选。
const researchRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/stock/research',
  validateSearch: (raw: Record<string, unknown>): ResearchRouteSearch => {
    const r = resolveResearchSearch(raw)
    return r.code === undefined ? { view: r.view } : { view: r.view, code: r.code }
  },
  component: ResearchRouteView,
})

// W4-B · /stock/fundamentals（旧 22 页）：?code= 入边（旧 24:114-118 反向深链）。
// validateSearch 校验 6 位，缺/非法不写 code 键；页面纯组件统一回落到默认 '600519'
// （与 W4-A SixDimView / 旧 search_ui.py:235 一致）。默认值由组件而非路由注入，
// 这样输出全字段 optional，AppShell 泛化 <Link> 不受影响。
const fundamentalsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/stock/fundamentals',
  validateSearch: (raw: Record<string, unknown>): { code?: string } => {
    const code = raw.code
    return typeof code === 'string' && /^\d{6}$/.test(code) ? { code } : {}
  },
  component: FundamentalsRouteView,
})

/** 薄 wrapper：只读取已由 validateSearch 预选的 search，传给纯组件（E2E 无需 RouterProvider）。 */
function ResearchRouteView() {
  const search = researchRoute.useSearch()
  return (
    <Suspense fallback={<RouteLoading />}>
      <LazyResearchView search={search} />
    </Suspense>
  )
}

function FundamentalsRouteView() {
  const search = fundamentalsRoute.useSearch()
  return (
    <Suspense fallback={<RouteLoading />}>
      <LazyFundamentalsView search={search} />
    </Suspense>
  )
}

// W4-C · /stock/compare（多股对比）：?codes=逗号分隔&period=... 入边。
// validateSearch 输出全字段 optional（codes/period 均为字符串，解析在组件内做），
// 沿用 researchRoute 同款写法，避免 AppShell 泛化 <Link> 因 search 必填而 tsc 失败。
const compareRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/stock/compare',
  validateSearch: (raw: Record<string, unknown>): { codes?: string; period?: string } => ({
    codes: typeof raw.codes === 'string' ? raw.codes : undefined,
    period: typeof raw.period === 'string' ? raw.period : undefined,
  }),
  component: CompareRouteView,
})

/** 薄 wrapper：把字符串态 search 经 resolveCompareSearch 归一后传给纯组件。 */
function CompareRouteView() {
  const search = compareRoute.useSearch()
  const resolved = resolveCompareSearch(search) as CompareRouteSearch
  return (
    <Suspense fallback={<RouteLoading />}>
      <LazyCompareView search={resolved} />
    </Suspense>
  )
}

const routeTree = rootRoute.addChildren([
  loginRoute,
  legacyRoute,
  appRoute.addChildren([
    dashboardRoute,
    decisionRoute,
    replayRoute,
    morningRoute,
    p1Route,
    recommendRoute,
    paperRoute,
    alertsRoute,
    webappsRoute,
    breadthRoute,
    ladderRoute,
    eventsRoute,
    predictionsRoute,
    opsRoute,
    diagnosticsRoute,
    settingsRoute,
    catalogRoute,
    matrixRoute,
    guideRoute,
    factorRoute,
    backtestRoute,
    panoramaRoute,
    regimeRoute,
    portfolioRoute,
    fundFlowRoute,
    tradingAccountRoute,
    macroDataRoute,
    dragonTigerRoute,
    themeRoute,
    strongRoute,
    sectorRotationRoute,
    watchRoute,
    quoteBoardRoute,
    usersRoute,
    financialHunterRoute,
    dashboardCustomRoute,
    dataExportRoute,
    meRoute,
    earningsCalendarRoute,
    reviewNotesRoute,
    sentimentClockRoute,
    similarDaysRoute,
    inflectionScanRoute,
    regimeDurationRoute,
    momentumResonanceRoute,
    limitUpReviewRoute,
    marketSentimentRoute,
    dataRoute,
    sixDimRoute,
    researchRoute,
    fundamentalsRoute,
    compareRoute,
  ]),
])

/**
 * W4-B 根因修复 · URL query 一律按「字符串」序列化。
 *
 * 缺陷：TanStack Router 1.170.46 默认 parseSearch = parseSearchWith(JSON.parse)
 * (@tanstack/router-core/dist/esm/searchParams.js:5)，内部先 qss.decode (:22)，
 * 再对数字开头的值调 JSON.parse（:3 的 jsonStart 含 \d、:26-29）。于是 6 位纯数字
 * 股票代码 '600519' 被解析成 number 600519；而 legacyRoute.validateSearch 的
 * `typeof raw.pick_stock === 'string'` 与 deeplink.ts pickCode 的 `typeof === 'string'`
 * 都会拒收 number，导致 /legacy redirect 后的 URL 丢失合法 code。
 * （'000001' 因前导零令 JSON.parse 抛错而保持字符串，恰好绕过该缺陷；
 *   直达 /stock/research?code=600519 因浏览器地址栏不被 rewrite 而看似正常。）
 *
 * 股票代码是字符串契约：这里用 URLSearchParams 把 query 值一律当字符串，
 * 并让 stringify 不给纯数字串加 JSON 引号（默认 stringifySearchWith
 * (JSON.stringify, JSON.parse) 会把 '600519' 写成 '"600519"'，令 URL 出现 %22
 * 而破坏 `code=600519` 字面量）。同时保住中文 hub_gyj_view 的解码。
 * 序列化配置也导出给运行时集成测试复用，避免测试与生产配置漂移。
 */
function parseSearchAsStrings(searchStr: string): Record<string, string> {
  const out: Record<string, string> = {}
  const s = searchStr.startsWith('?') ? searchStr.slice(1) : searchStr
  for (const [k, v] of new URLSearchParams(s)) out[k] = v
  return out
}

function stringifySearchAsStrings(search: Record<string, unknown>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(search)) {
    if (v !== undefined && v !== null) p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const searchSerialization = {
  parseSearch: parseSearchAsStrings,
  stringifySearch: stringifySearchAsStrings,
}

export const router = createRouter({ routeTree, ...searchSerialization })

// 类型安全路由注册（TanStack Router v1 标准）
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
