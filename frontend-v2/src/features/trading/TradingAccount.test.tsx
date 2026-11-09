import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TradingAccount } from './TradingAccount'
import type { TradingAccount as TradingAccountData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getTradingAccount: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getTradingAccount } from '@/api/read'
const mocked = vi.mocked(getTradingAccount)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: TradingAccountData = {
  account: {
    broker_type: 'sim', mode: '模拟', init_cash: 1000000, cash: 870944,
    position_cost: 129056, total_assets: 1000000, available: true,
  },
  positions: [
    { code: '600519', name: '贵州茅台', qty: 100, avg_cost: 1290.56, cost_basis: 129056 },
  ],
  orders: [
    { time: '2026-09-09 12:10', code: '600519', name: '贵州茅台', side: '买', price: 1290.56, qty: 100, amount: 129056 },
  ],
  note: '本页为 V2 只读概览，读取本地模拟账本',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('TradingAccount 三态 + 三块渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<TradingAccount />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('数据不足（insufficient_data）')))
    renderWithClient(<TradingAccount />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染账户/持仓/订单三块关键数据', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<TradingAccount />)
    expect(await screen.findByText('账户概览')).toBeTruthy()
    expect(screen.getByText('当前持仓（1）')).toBeTruthy()
    expect(screen.getByText('订单流水（1）')).toBeTruthy()
    // 账户 KPI
    expect(screen.getByText('模拟账本')).toBeTruthy()
    // 持仓表（贵州茅台同时出现在持仓与订单，故用 getAllByText）
    expect(screen.getAllByText('贵州茅台').length).toBeGreaterThan(0)
    // 订单方向（A 股：买入红）
    expect(screen.getByText('买入 ▲')).toBeTruthy()
  })

  it('无账本时显示整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      account: { broker_type: 'sim', mode: '模拟', available: false },
      positions: [],
      orders: [],
      note: '本页为 V2 只读概览',
    })
    renderWithClient(<TradingAccount />)
    expect(await screen.findByText('暂无本地模拟账本')).toBeTruthy()
  })

  it('有账户但无持仓/订单时仍渲染账户概览，不显示持仓/订单空块报错', async () => {
    mocked.mockResolvedValue({
      account: { broker_type: 'sim', mode: '模拟', cash: 1000000, position_cost: null, total_assets: 1000000, available: true },
      positions: [],
      orders: [],
      note: '本页为 V2 只读概览',
    })
    renderWithClient(<TradingAccount />)
    expect(await screen.findByText('账户概览')).toBeTruthy()
    expect(screen.getByText('暂无持仓（本地模拟账本无持仓记录）。')).toBeTruthy()
    expect(screen.getByText('暂无订单（本地模拟账本无交易记录）。')).toBeTruthy()
  })
})
