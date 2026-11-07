// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { EventPoolView } from '@/features/ops/EventPoolView'
import { PredictionLogView } from '@/features/ops/PredictionLogView'
import { SystemStatusView } from '@/features/ops/SystemStatusView'

/**
 * W3 后续簇 · 5 个真实数据源的前端契约 E2E（MSW）。
 * 独立成文件，不改动 flow.test.tsx（后者由并行工作流负责 E2E 转正）。
 * 验证「client → Zod → query → 组件」链路，以及两条诚实红线：
 *  ① 事件池必须原样带出「非买卖指令」口径；
 *  ② 命中率分母只算已兑现样本、回测负收益/负 Sharpe 不取绝对值。
 */
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ height }: { height?: number }) => <div data-testid="echart" style={{ height }} />,
}))

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
})
afterAll(() => server.close())

describe('W3 后续簇 · 真实数据源契约', () => {
  it('事件因子池页经 /event-pool 渲染，并原样带出免责口径', async () => {
    render(
      <Providers>
        <EventPoolView />
      </Providers>,
    )
    expect(await screen.findByText('事件因子池', {}, { timeout: 5000 })).toBeTruthy()
    expect(await screen.findByText('口径与免责', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('统计意义上的超额收益概率排序，非买卖指令')).toBeTruthy()
    expect(screen.getByText('sh600707')).toBeTruthy()
    expect(screen.getByText('池内标的明细')).toBeTruthy()
  })

  it('预测校准日志页经 /prediction-log 渲染，未兑现样本不计入命中率分母', async () => {
    render(
      <Providers>
        <PredictionLogView />
      </Providers>,
    )
    expect(await screen.findByText('预测校准日志', {}, { timeout: 5000 })).toBeTruthy()
    expect(await screen.findByText('口径说明', {}, { timeout: 5000 })).toBeTruthy()
    // fixture 共 5 条：3 条已兑现（2 命中 / 1 未命中）、2 条 hit=null 未兑现。
    // 命中率 = 2/3 = 66.7%，分母必须为 3 而不是 5。
    expect(screen.getByText('66.7%')).toBeTruthy()
    expect(screen.getByText('分母 3 条')).toBeTruthy()
    expect(screen.getAllByText('未兑现').length).toBeGreaterThanOrEqual(2)
  })

  it('数据与运维状态页经 3 个端点分块渲染，负收益如实带符号', async () => {
    render(
      <Providers>
        <SystemStatusView />
      </Providers>,
    )
    expect(await screen.findByText('数据与运维状态', {}, { timeout: 5000 })).toBeTruthy()
    expect(await screen.findByText('P1 信号同步', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('4 个副本超出新鲜度 SLA')).toBeTruthy()
    expect(screen.getByText('回测运行记录')).toBeTruthy()
    // 负收益与负 Sharpe 原样带符号，绝不取绝对值或包装成「领先」。
    expect(screen.getByText('-1.88')).toBeTruthy()
    expect(screen.getByText('-0.31')).toBeTruthy()
    expect(screen.getByText('数据刷新状态')).toBeTruthy()
  })
})
