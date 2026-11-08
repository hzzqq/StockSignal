import { createRootRoute, createRoute, createRouter, Outlet, redirect } from '@tanstack/react-router'
import { LoginPage } from '@/features/auth/LoginPage'
import { requireAuth } from './guards'
import { AppShell } from './AppShell'
import { Dashboard } from '@/features/dashboard/Dashboard'
import { DecisionPanel } from '@/features/decision/DecisionPanel'
import { DecisionReplay } from '@/features/decision/DecisionReplay'
import { MorningReport } from '@/features/morning/MorningReport'
import { P1Signals } from '@/features/p1/P1Signals'
import { Recommendation } from '@/features/recommend/Recommendation'
import { PaperTrades } from '@/features/paper/PaperTrades'
import { Alerts } from '@/features/alerts/Alerts'
import { WebApps } from '@/features/webapps/WebApps'
import { BreadthOverview } from '@/features/breadth/BreadthOverview'
import { LadderResonance } from '@/features/breadth/LadderResonance'
import { EventPoolView } from '@/features/ops/EventPoolView'
import { PredictionLogView } from '@/features/ops/PredictionLogView'
import { SystemStatusView } from '@/features/ops/SystemStatusView'
import { DiagnosticsView } from '@/features/ops/DiagnosticsView'
import { SixDimView } from '@/features/stock/SixDimView'
import { FundamentalsView } from '@/features/stock/FundamentalsView'
import { ResearchView } from '@/features/stock/ResearchView'
import { CompareView } from '@/features/stock/CompareView'
import { resolveResearchSearch, resolveLegacySearch, resolveCompareSearch } from '@/lib/deeplink'
import type { ResearchRouteSearch, CompareRouteSearch } from '@/lib/deeplink'

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
  component: Dashboard,
})

const decisionRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/decision',
  component: DecisionPanel,
})

const replayRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/replay',
  component: DecisionReplay,
})

const morningRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/morning',
  component: MorningReport,
})

const p1Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/p1',
  component: P1Signals,
})

const recommendRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/recommend',
  component: Recommendation,
})

const paperRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/paper',
  component: PaperTrades,
})

const alertsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/alerts',
  component: Alerts,
})

const webappsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/webapps',
  component: WebApps,
})

const breadthRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/breadth',
  component: BreadthOverview,
})

const ladderRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/ladder',
  component: LadderResonance,
})

const eventsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/events',
  component: EventPoolView,
})

const predictionsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/predictions',
  component: PredictionLogView,
})

const opsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/ops',
  component: SystemStatusView,
})

// W4-D · 数据源与接口检测（两块检测同页，主动探测、默认零网络）
const diagnosticsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/diagnostics',
  component: DiagnosticsView,
})

const sixDimRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/stock/six-dim',
  component: SixDimView,
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
  return <ResearchView search={search} />
}

function FundamentalsRouteView() {
  const search = fundamentalsRoute.useSearch()
  return <FundamentalsView search={search} />
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
  return <CompareView search={resolved} />
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
