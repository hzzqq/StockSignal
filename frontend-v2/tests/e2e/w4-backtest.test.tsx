// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { backtest } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { Backtest } from '@/features/backtest/Backtest'

/**
 * 30 策略回测（/backtest）真人交互级 E2E（MSW）。
 * 重点：表单（标的/策略/日期）→ 运行回测 → 回显请求参数（真实后端行为）；
 * 诚实红线——哨兵标的 000000 取数为空时渲染「暂无回测数据」，不补零曲线。
 * 逐笔交易明细已改折叠卡（defaultOpen=false）：先展开再断言表内容，summary 精确断言。
 */
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ height }: { height?: number }) => <div data-testid="echart" style={{ height }} />,
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }

/** 逐笔明细折叠卡：先在折叠卡区域内展开，再断言表内容。 */
async function expandTradesTable() {
  const region = await screen.findByRole('region', { name: '逐笔交易明细' }, FIND)
  fireEvent.click(within(region).getByRole('button', { name: '展开 ▾' }))
}

describe('30 · 策略回测', () => {
  it('默认参数即触发回测，加载后展示摘要与资金曲线', async () => {
    render(
      <Providers>
        <Backtest />
      </Providers>,
    )
    expect(await screen.findByText('策略回测')).toBeTruthy()
    // 表单预填默认标的
    expect((screen.getByLabelText(/标的代码/) as HTMLInputElement).value).toBe('600519')
    // 加载完成后展示摘要指标与曲线卡
    expect(await screen.findByText('累计收益', {}, FIND)).toBeTruthy()
    expect(screen.getByText('资金曲线（累计收益 + 回撤）')).toBeTruthy()
    // 逐笔明细改为折叠卡：summary 精确断言（笔数 + 累计收益，来自 fixture 真实数值），展开后表头可见
    expect(
      screen.getByText(
        `${backtest.trades.length} 笔 · 累计收益 ${Number(backtest.total_return_pct).toFixed(2)}%`,
      ),
    ).toBeTruthy()
    await expandTradesTable()
    expect(screen.getByText('买入日')).toBeTruthy()
    expect(screen.getByText('离场原因')).toBeTruthy()
  })

  it('切换策略 + 运行回测 → 回显所选策略（多因子 → 均线交叉）', async () => {
    render(
      <Providers>
        <Backtest />
      </Providers>,
    )
    expect(await screen.findByText('策略回测')).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/策略/), { target: { value: 'ma_cross' } })
    fireEvent.click(screen.getByRole('button', { name: '运行回测' }))
    // 回显请求参数：后端返回 strategy=ma_cross → 摘要行显示「策略 均线交叉」
    expect(
      await screen.findByText(/策略 均线交叉/, {}, { timeout: 5000 }),
    ).toBeTruthy()
  })

  it('修改标的输入（受控字段）+ 运行回测 → 回显新标的', async () => {
    render(
      <Providers>
        <Backtest />
      </Providers>,
    )
    expect(await screen.findByText('策略回测')).toBeTruthy()
    const ticker = screen.getByLabelText(/标的代码/) as HTMLInputElement
    fireEvent.change(ticker, { target: { value: '000001' } })
    expect(ticker.value).toBe('000001')
    fireEvent.click(screen.getByRole('button', { name: '运行回测' }))
    expect(await screen.findByText(/标的 000001/, {}, { timeout: 5000 })).toBeTruthy()
  })

  it('哨兵标的 000000 取数为空 → 诚实空态，不补零曲线', async () => {
    render(
      <Providers>
        <Backtest />
      </Providers>,
    )
    expect(await screen.findByText('策略回测')).toBeTruthy()
    const ticker = screen.getByLabelText(/标的代码/) as HTMLInputElement
    fireEvent.change(ticker, { target: { value: '000000' } })
    fireEvent.click(screen.getByRole('button', { name: '运行回测' }))
    expect(await screen.findByText('暂无回测数据', {}, { timeout: 5000 })).toBeTruthy()
    expect(
      screen.getByText('该标的在所选区间取数为空，无法回测（后端 honest 降级）'),
    ).toBeTruthy()
    // 空态不应渲染资金曲线卡
    expect(screen.queryByText('资金曲线（累计收益 + 回撤）')).toBeNull()
  })
})
