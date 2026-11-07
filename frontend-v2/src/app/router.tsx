import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
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

// 根布局：仅渲染子路由出口（登录页与鉴权外壳并列挂在根下）
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

const routeTree = rootRoute.addChildren([
  loginRoute,
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
  ]),
])

export const router = createRouter({ routeTree })

// 类型安全路由注册（TanStack Router v1 标准）
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
