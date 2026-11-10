// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { FactorAnalysis } from '@/features/factor/FactorAnalysis'

/**
 * 71 因子分析（/factor）真人交互级 E2E（MSW）。
 * 重点：表单（标的/因子/回看天数/分层数/持有期）→ 运行分析 → 回显请求参数；
 * 诚实红线——有效标的<3 时渲染「暂无因子数据」，不补零、不编造因子结论。
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

describe('71 · 因子分析', () => {
  it('默认参数即触发分析，加载后展示 IC 汇总与分层累计收益', async () => {
    render(
      <Providers>
        <FactorAnalysis />
      </Providers>,
    )
    expect(await screen.findByText('因子分析')).toBeTruthy()
    expect((screen.getByLabelText(/标的代码/) as HTMLInputElement).value).toBe(
      '600519,000001,300750',
    )
    // 加载完成：IC 汇总卡 + 分层累计收益曲线卡
    expect(await screen.findByText('IC 均值', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText(/分层累计收益/)).toBeTruthy()
  })

  it('切换因子 + 运行分析 → 回显所选因子（动量 → 5 日反转）', async () => {
    render(
      <Providers>
        <FactorAnalysis />
      </Providers>,
    )
    expect(await screen.findByText('因子分析')).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/因子/), { target: { value: 'reversal' } })
    fireEvent.click(screen.getByRole('button', { name: '运行分析' }))
    expect(await screen.findByText(/因子 5 日反转/, {}, { timeout: 5000 })).toBeTruthy()
  })

  it('标的输入为受控字段（清空后键入单一标的）', async () => {
    render(
      <Providers>
        <FactorAnalysis />
      </Providers>,
    )
    expect(await screen.findByText('因子分析')).toBeTruthy()
    const codes = screen.getByLabelText(/标的代码/) as HTMLInputElement
    fireEvent.change(codes, { target: { value: '600519' } })
    expect(codes.value).toBe('600519')
  })

  it('有效标的<3 → 诚实空态（暂无因子数据），不补零曲线', async () => {
    render(
      <Providers>
        <FactorAnalysis />
      </Providers>,
    )
    expect(await screen.findByText('因子分析')).toBeTruthy()
    const codes = screen.getByLabelText(/标的代码/) as HTMLInputElement
    fireEvent.change(codes, { target: { value: '600519' } })
    fireEvent.click(screen.getByRole('button', { name: '运行分析' }))
    expect(await screen.findByText('暂无因子数据', {}, { timeout: 5000 })).toBeTruthy()
    expect(
      screen.getByText('有效标的不足 3 只或取数全部失败，无法得出因子结论（后端 honest 降级）'),
    ).toBeTruthy()
    expect(screen.queryByText('分层累计收益')).toBeNull()
  })
})
