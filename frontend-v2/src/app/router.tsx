import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import { LoginPage } from '@/features/auth/LoginPage'
import { requireAuth } from './guards'

// W0 占位根布局（真实首页在 W1 接数据后替换）
function RootLayout() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-sf-bg text-sf-txt">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">StockSignal V2</h1>
        <p className="text-sf-border">占位首页（W1 接入数据）</p>
      </div>
    </div>
  )
}

const rootRoute = createRootRoute({
  component: RootLayout,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>) => ({
    from: typeof search.from === 'string' ? search.from : '/',
  }),
  component: LoginPage,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    // 未登录 → /login，并保留来源路由
    requireAuth('/')
  },
  component: RootLayout,
})

const routeTree = rootRoute.addChildren([loginRoute, indexRoute])

export const router = createRouter({ routeTree })

// 类型安全路由注册（TanStack Router v1 标准）
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
