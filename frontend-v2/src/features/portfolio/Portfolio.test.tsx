import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Portfolio } from './Portfolio'
import type { Portfolio as PortfolioData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getPortfolio: vi.fn(),
  getPositionAllocation: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getPortfolio, getPositionAllocation } from '@/api/read'
const mocked = vi.mocked(getPortfolio)
const mockedAlloc = vi.mocked(getPositionAllocation)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: PortfolioData = {
  summary: { total_cost: 176000, total_market_value: 185500, total_pnl: 9500, total_pnl_pct: 5.4, position_count: 2 },
  positions: [
    { ticker: '600519', name: '贵州茅台', buy_date: '2026-01-02', buy_price: 1700, shares: 100, remaining_shares: 100, cost: 170000, current_price: 1800, market_value: 180000, realized_pnl: 0, pnl: 10000, pnl_pct: 5.88 },
    { ticker: '000001', name: '平安银行', buy_date: '2026-01-03', buy_price: 12, shares: 1000, remaining_shares: 500, cost: 6000, current_price: 11, market_value: 5500, realized_pnl: 0, pnl: -500, pnl_pct: -8.33 },
  ],
  attribution: [
    { ticker: '600519', name: '贵州茅台', pnl: 10000, pnl_pct: 5.88, contribution: 104.17 },
    { ticker: '000001', name: '平安银行', pnl: -500, pnl_pct: -8.33, contribution: -4.17 },
  ],
  weights: [
    { ticker: '600519', name: '贵州茅台', weight_pct: 96.77 },
    { ticker: '000001', name: '平安银行', weight_pct: 3.23 },
  ],
  curve: [
    { date: '2026-01-01', portfolio: 100, benchmark: 100 },
    { date: '2026-01-02', portfolio: 101.2, benchmark: 99.8 },
  ],
  curve_available: true,
  date: null,
  note: '持仓为本地模拟/历史数据',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('Portfolio 三态 + 字段渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Portfolio />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('数据不足（insufficient_data）')))
    renderWithClient(<Portfolio />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染持仓汇总 + 持仓明细', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<Portfolio />)
    expect(await screen.findByText(/持仓明细/)).toBeTruthy()
    expect(screen.getByText('贵州茅台')).toBeTruthy()
    expect(screen.getByText('平安银行')).toBeTruthy()
  })

  it('empty（无持仓）显示暂无持仓数据', async () => {
    mocked.mockResolvedValue({ ...okData, positions: [] })
    renderWithClient(<Portfolio />)
    expect(await screen.findByText('暂无持仓数据')).toBeTruthy()
  })

  it('收益归因分段：贡献 + 占比 + 净值曲线', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<Portfolio />)
    // 切到收益归因
    const btn = await screen.findByText('收益归因')
    btn.click()
    expect(await screen.findByText('盈亏贡献（按个股，红涨绿跌）')).toBeTruthy()
    expect(screen.getByText('持仓市值占比')).toBeTruthy()
    expect(screen.getByText('组合净值曲线（基准沪深300，尽力而为）')).toBeTruthy()
  })

  it('决策落地 tab：渲染目标权重分配表 + 诚实免责', async () => {
    mocked.mockResolvedValue(okData)
    mockedAlloc.mockResolvedValue({
      status: 'ok',
      source: 'recommend',
      meta: {
        mode: 'score',
        degraded: false,
        cap_pct: 20,
        target_pct: 60,
        sum_pct: 60,
        n_alloc: 3,
        n_excluded: 0,
        capped: ['600519'],
        overflow_pct: 0,
        market: { snapshot_date: '2026-11-09', temperature: 12.5, band: '中性偏暖' },
        source: { key: 'recommend', label: '荐股引擎综合分', generated_at: '2026-11-09T15:30:00', data_as_of: '2026-11-08' },
      },
      allocations: [
        { code: '600519', name: '贵州茅台', score: 82, weight: 0.2, pct: 20 },
        { code: '000001', name: '平安银行', score: 55, weight: 0.1333, pct: 13.33 },
        { code: '300750', name: '宁德时代', score: 63, weight: 0.2667, pct: 26.67 },
      ],
      excluded: [],
      note: '仓位落地为纯建议层',
      unavailable: [],
    })
    renderWithClient(<Portfolio />)
    const landingBtn = await screen.findByText('决策落地')
    landingBtn.click()
    expect(await screen.findByText('目标权重分配（3 只）')).toBeTruthy()
    expect(screen.getByText('贵州茅台')).toBeTruthy()
    // 诚实免责：建议≠交易（横幅 + 页脚各一处）+ 只读不碰
    expect(screen.getAllByText(/建议 ≠ 交易/).length).toBeGreaterThan(0)
    expect(screen.getByText(/只读不碰/)).toBeTruthy()
  })

  it('决策落地 tab：后端 unavailable → 诚实错误态，展示后端 reason 且不编造分配', async () => {
    mocked.mockResolvedValue(okData)
    mockedAlloc.mockRejectedValue(new Error('分配不可用（市场仓位不可得，不实时臆算）'))
    renderWithClient(<Portfolio />)
    const landingBtn = await screen.findByText('决策落地')
    landingBtn.click()
    // 后端 fail 信封 → client 抛错 → error 态，原样带出后端 reason（诚实，不兜底）
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText(/分配不可用/)).toBeTruthy()
    // 绝不编造：无分配表、无目标权重数字
    expect(screen.queryByText(/目标权重分配/)).toBeNull()
    expect(screen.queryByText('60.00%')).toBeNull()
  })
})
