import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { EarningsCalendar as EarningsCalendarData } from '@/api/schemas/read'
import { EarningsCalendar } from './EarningsCalendar'

vi.mock('@/api/read', () => ({
  getEarningsCalendar: vi.fn(),
}))
import { getEarningsCalendar } from '@/api/read'
const mocked = vi.mocked(getEarningsCalendar)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: EarningsCalendarData = {
  market: '沪深京',
  period: '2025年报',
  rows: [
    { 股票代码: '600000', 股票简称: '浦发银行', 报告期: '2025年报', 披露状态: '已披露' },
  ],
  date: null,
  unavailable: false,
  note: '',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('EarningsCalendar 四态 + 诚实降级', () => {
  it('loading 显示披露日历加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<EarningsCalendar />)
    expect(screen.getByText('加载披露日历…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('披露日历加载失败'))
    renderWithClient(<EarningsCalendar />)
    await expect(screen.findByText('披露日历加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染披露日历表（候选列缺失由 pick 函数显「—」）', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<EarningsCalendar />)
    // 标题常驻；改用数据态 Card 标题（含条数）作为加载完成信号
    expect(await screen.findByText(/沪深京 · 2025年报（1 条）/)).toBeTruthy()
    expect(screen.getByText('浦发银行')).toBeTruthy()
    expect(screen.getByText('600000')).toBeTruthy()
  })

  it('unavailable → 诚实空态「财报披露日历暂时取不到」+ reason', async () => {
    mocked.mockResolvedValue({
      market: '沪深京',
      period: '2025年报',
      rows: [],
      date: null,
      unavailable: true,
      note: '数据源限流',
    } as EarningsCalendarData)
    renderWithClient(<EarningsCalendar />)
    await expect(screen.findByText('财报披露日历暂时取不到')).resolves.toBeTruthy()
    expect(screen.getByText(/数据源限流/)).toBeTruthy()
  })

  it('空 rows → 诚实空态「该市场/报告期暂无披露日历数据」', async () => {
    mocked.mockResolvedValue({
      market: '沪深京',
      period: '2025年报',
      rows: [],
      date: null,
      unavailable: false,
      note: '',
    } as EarningsCalendarData)
    renderWithClient(<EarningsCalendar />)
    await expect(screen.findByText('该市场/报告期暂无披露日历数据')).resolves.toBeTruthy()
  })
})
