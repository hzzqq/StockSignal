// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { SixDimView } from '@/features/stock/SixDimView'
import { NAV } from '@/nav/nav'

/**
 * W4-A · 个股六维评分前端契约 E2E（MSW）。
 * 用 <Providers> 独立渲染（现有 E2E 无 RouterProvider，故页面深链用原生 <a>）。
 * 重点验证三条诚实红线：
 *  ① 缺维显示「缺失」、不补 0 分；
 *  ② date 为 null 显示「暂无权威数据日」，禁止今天日期兜底；
 *  ③ 后端 note 口径原文原样可见，不改写。
 * 另加导航注册断言：/stock/six-dim 并入第 3 组、仍 4 组、图标全局唯一。
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

/** 把默认代码 600519 切到 000001（MSW 返回 partial：capital/growth 缺失、date 为 null）。 */
function switchToPartial() {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '000001' } })
}

describe('W4-A · 个股六维评分', () => {
  it('缺维如实显示「缺失」且不以 0 分呈现', async () => {
    render(
      <Providers>
        <SixDimView />
      </Providers>,
    )
    expect(await screen.findByText('个股六维评分')).toBeTruthy()
    switchToPartial()
    // 等 partial 的降权提示出现，确保新 code 查询已完成
    expect(
      await screen.findByText('仅 4/6 维有效，缺失维未取到数据', {}, { timeout: 5000 }),
    ).toBeTruthy()

    expect(screen.getByTestId('dim-capital').textContent).toBe('缺失')
    expect(screen.getByTestId('dim-growth').textContent).toBe('缺失')
    expect(screen.getAllByText('缺失').length).toBe(2)
    // 缺失维不得被补成 0 / 0.0 / 0.00 之类的分数
    expect(screen.getByTestId('dim-capital').textContent).not.toMatch(/0/)
    expect(screen.getByTestId('dim-growth').textContent).not.toMatch(/0/)
    // 有值维度仍正常显示分数
    expect(screen.getByTestId('dim-technical').textContent).not.toBe('缺失')
  })

  it('date 为 null 时显示「暂无权威数据日」，不显示任何兜底日期', async () => {
    render(
      <Providers>
        <SixDimView />
      </Providers>,
    )
    switchToPartial()
    expect(await screen.findByText('暂无权威数据日', {}, { timeout: 5000 })).toBeTruthy()
    // 不得出现「权威数据日：<某日期>」（含 full 的 2026-11-07 或今天日期）
    expect(screen.queryByText(/权威数据日：/)).toBeNull()
  })

  it('后端 note 口径原文原样可见，不改写', async () => {
    render(
      <Providers>
        <SixDimView />
      </Providers>,
    )
    expect(
      await screen.findByText(
        '逐维独立取数、独立降级；缺失维为 null 且不参与 overall 平均',
        {},
        { timeout: 5000 },
      ),
    ).toBeTruthy()
    // 默认 600519 为 full：数据日有值、6 维齐全、无「缺失」
    expect(await screen.findByText('权威数据日：2026-11-07', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.queryByText('缺失')).toBeNull()
  })

  it('导航注册：/stock/six-dim 并入第 3 组「量化与工具」，仍 4 组、图标全局唯一', () => {
    expect(NAV.length).toBe(4)
    const group3 = NAV[2]
    expect(group3.group).toBe('量化与工具')
    expect(group3.items.some((it) => it.to === '/stock/six-dim')).toBe(true)
    const icons = NAV.flatMap((g) => g.items.map((it) => it.icon))
    expect(new Set(icons).size).toBe(icons.length)
  })
})
