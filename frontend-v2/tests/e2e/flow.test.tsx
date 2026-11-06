// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { RouterProvider } from '@tanstack/react-router'
import { Providers } from '@/app/providers'
import { router } from '@/app/router'
import { BreadthOverview } from '@/features/breadth/BreadthOverview'
import { LadderResonance } from '@/features/breadth/LadderResonance'

// jsdom 无 canvas / ResizeObserver，图表组件在 E2E 里以占位替身渲染，
// 把验证焦点放在「登录 → 守卫 → 数据端到端」链路上（图表已由单测/构建覆盖）。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ height }: { height?: number }) => <div data-testid="echart" style={{ height }} />,
}))
vi.mock('@/shared/charts/ScenarioChart', () => ({
  ScenarioChart: () => <div data-testid="scenario-chart" />,
}))

// 兜底：万一真实图表组件被渲染，提供空 ResizeObserver 避免崩溃。
if (!('ResizeObserver' in globalThis)) {
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  localStorage.clear()
  try {
    ;(router as unknown as { reset?: () => void }).reset?.()
  } catch {
    /* 单例路由无 reset 时忽略，状态保持确定性 */
  }
})
afterAll(() => server.close())

describe('前端 E2E（MSW 契约）', () => {
  it('未登录访问 / 被守卫重定向到登录页', async () => {
    render(
      <Providers>
        <RouterProvider router={router} />
      </Providers>,
    )
    expect(await screen.findByText('StockSignal 登录')).toBeTruthy()
  })

  it('登录 → 仪表盘渲染决策快照（端到端数据流）', async () => {
    render(
      <Providers>
        <RouterProvider router={router} />
      </Providers>,
    )
    // 守卫先把我们带到 /login
    const userField = await screen.findByPlaceholderText('用户名')
    fireEvent.change(userField, { target: { value: 'demo' } })
    fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: 'Demo@123' } })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))

    // 登录成功后跳回 dashboard，daily-snapshot 经 MSW→client→query→组件渲染
    expect(await screen.findByText('市场温度', {}, { timeout: 5000 })).toBeTruthy()
    // 登录链路确实写入了 token（guards / 后续鉴权依赖）
    expect(localStorage.getItem('ss_token')).toBe('mock-access-token')
  })

  it('广度页经新增只读端点渲染 W3 时序/连板明细（MSW 数据流）', async () => {
    // 直接渲染广度页组件，验证 /breadth-timeseries 与 /ladder-detail 两条新增端点
    // 经 client→Zod→query→组件真实驱动（绕过登录流程，登录链路已由上一条用例覆盖）。
    // 注：图表在 E2E 下以占位替身渲染，故断言落在真实 DOM 文本（仅查询成功才渲染）。
    render(
      <Providers>
        <BreadthOverview />
      </Providers>,
    )
    // 今日摘要（daily-snapshot）
    expect(await screen.findByText('市场广度·温度总览', {}, { timeout: 5000 })).toBeTruthy()
    // 广度时序（/breadth-timeseries）——卡片标题仅在查询成功(非 error)时渲染
    expect(await screen.findByText('广度时序（涨跌家数 · 近期）', {}, { timeout: 5000 })).toBeTruthy()
    // 连板明细（/ladder-detail）—— Stat 标签仅在数据加载后渲染
    expect(await screen.findByText('连板梯队明细', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('最新数据日')).toBeTruthy()
  })

  it('连板梯队共振页经 /ladder-detail 渲染（MSW 数据流）', async () => {
    // 验证 W3 新增的 /ladder 连板梯队共振页经新增只读端点 /ladder-detail 真实驱动。
    render(
      <Providers>
        <LadderResonance />
      </Providers>,
    )
    expect(await screen.findByText('连板梯队共振', {}, { timeout: 5000 })).toBeTruthy()
    expect(await screen.findByText('最新数据日', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('连板强度趋势（最高板 / 连板总数）')).toBeTruthy()
    expect(screen.getByText('最新板位分布')).toBeTruthy()
  })
})

// 真实后端冒烟：仅当显式开启 VITE_E2E_LIVE=1 时运行。
// 当前 5050 服务返 502（未起），故默认跳过——诚实标注「未实测」，不伪造成功。
const LIVE = import.meta.env.VITE_E2E_LIVE === '1'
describe.skipIf(!LIVE)('真实后端冒烟（需 VITE_E2E_LIVE=1；当前 5050 返 502 故默认跳过）', () => {
  it('GET /api/health 不返 502', async () => {
    const res = await fetch('http://127.0.0.1:5050/api/health')
    expect(res.status).not.toBe(502)
  })
})
