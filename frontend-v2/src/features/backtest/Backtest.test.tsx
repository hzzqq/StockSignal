import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Backtest } from './Backtest'
import type { Backtest as BacktestData } from '@/api/schemas/read'

// 隔离真实 API：只替换 getBacktest；图表组件在 jsdom 不可用，mock 为 null。
vi.mock('@/api/read', () => ({
  getBacktest: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getBacktest } from '@/api/read'
const mocked = vi.mocked(getBacktest)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: BacktestData = {
  ticker: '600519',
  strategy: 'multi_factor',
  start: '2024-01-01',
  end: '2024-12-31',
  initial_capital: 100000,
  final_value: 106000,
  total_return_pct: 6.0,
  annualized_return_pct: 6.2,
  max_drawdown_pct: -3.5,
  sharpe_ratio: 1.84,
  win_rate_pct: 58.33,
  profit_factor: 2.15,
  avg_trade_return_pct: 2.41,
  trade_count: 12,
  exposure_pct: 73.5,
  start_date: '2024-01-02',
  end_date: '2024-12-31',
  equity_curve: [
    { date: '2024-01-02', cumulative_return: 0.15, total_asset: 100150, drawdown: 0 },
    { date: '2024-01-03', cumulative_return: 0.31, total_asset: 100310, drawdown: 0 },
    { date: '2024-12-31', cumulative_return: 6.0, total_asset: 106000, drawdown: -3.5 },
  ],
  trades: [
    { entry_date: '2024-01-02', exit_date: '2024-01-08', entry_price: 1685, exit_price: 1712.5, profit_pct: 1.63, exit_reason: '止盈', bars_held: 4 },
    { entry_date: '2024-01-10', exit_date: '2024-01-15', entry_price: 1702, exit_price: 1668.4, profit_pct: -1.98, exit_reason: '止损', bars_held: 3 },
  ],
  date: '2024-12-31',
  note: '单标的独立回测；取数为空时诚实返回 insufficient_data',
}

beforeEach(() => {
  mocked.mockReset()
})


/** 折叠卡默认收起：按 region 名展开后再断言表格行（大表折叠后的正确测试范式）。 */
async function expandCard(name: RegExp | string) {
  const region = await screen.findByRole('region', { name })
  fireEvent.click(within(region).getByRole('button', { name: /展开/ }))
}

describe('Backtest 三态 + 字段渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Backtest />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态（诚实不谎报为数据）', async () => {
    mocked.mockImplementation(() =>
      Promise.reject(new Error('数据不足（insufficient_data）')),
    )
    renderWithClient(<Backtest />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染摘要指标、资金曲线与交易明细', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<Backtest />)
    expect(await screen.findByText('累计收益')).toBeTruthy()
    expect(screen.getByText('年化收益')).toBeTruthy()
    expect(screen.getByText('夏普比率')).toBeTruthy()
    expect(screen.getByText('资金曲线（累计收益 + 回撤）')).toBeTruthy()
    // 大表折叠：title 与 summary 分两处；摘要含真实笔数+累计收益，明细展开后可见着色数值
    expect(screen.getByText('逐笔交易明细')).toBeTruthy()
    expect(screen.getByText(/2 笔 · 累计收益/)).toBeTruthy()
    await expandCard('逐笔交易明细')
    expect(screen.getByText('+1.63%')).toBeTruthy()
    expect(screen.getByText('-1.98%')).toBeTruthy()
  })

  it('empty（equity_curve 为空）显示暂无回测数据', async () => {
    mocked.mockResolvedValue({ ...okData, equity_curve: [] })
    renderWithClient(<Backtest />)
    expect(await screen.findByText('暂无回测数据')).toBeTruthy()
  })

  it('profit_factor 为 null 时显示「全胜/无交易」副文而非补 0', async () => {
    mocked.mockResolvedValue({ ...okData, profit_factor: null })
    renderWithClient(<Backtest />)
    expect(await screen.findByText('盈亏比')).toBeTruthy()
    expect(screen.getByText('（全胜/无交易）')).toBeTruthy()
  })
})
