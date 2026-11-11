import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LimitUpReview } from './LimitUpReview'

vi.mock('@/api/read', () => ({
  getLimitUpReview: vi.fn(),
}))
import { getLimitUpReview } from '@/api/read'
const mocked = vi.mocked(getLimitUpReview)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  available: true,
  date: '20261106',
  note: '数据源东财涨停池…',
  pool: {
    available: true,
    reason: null,
    date: '20261106',
    count: 4,
    first_boards: 2,
    connect_boards: 2,
    max_boards: 3,
    broken_count: 1,
    bands: { 早板: 1, 尾板: 1, 上午板: 1, 其他: 1 },
    rows: [
      { code: '600519', name: '贵州茅台', industry: '白酒', boards: 1, seal: 120000, amount: 500000, first_seal_band: '早板', broken: 0 },
      { code: '300750', name: '宁德时代', industry: '电池', boards: 3, seal: 200000, amount: 900000, first_seal_band: '上午板', broken: 0 },
    ],
    leaderboard: [
      { name: '宁德时代', code: '300750', industry: '电池', boards: 3, score: 100, s_height: 100, s_seal: 100, s_ind: 100, s_amt: 100, ind_n: 1, seal: 200000, amount: 900000 },
    ],
    themes: [{ industry: '白酒', count: 1 }, { industry: '电池', count: 1 }],
    broken_list: [],
  },
  ladder: { available: true, reason: null, distribution: [[3, 1] as [number, number], [2, 1] as [number, number], [1, 2] as [number, number]], max_boards: 3, total_connect: 1, gaps: [] },
  context: { available: true, reason: null, fail_ratio: 18.27, limit_up_cnt: 85, cycle: '主升高潮', temperature: 87, state: '震荡', confidence: 0.6 },
}

const poolDownData = {
  available: false,
  date: '20261106',
  note: '数据源东财涨停池…',
  pool: { available: false, reason: 'ConnectionError: 东财涨停池数据源不可达', date: '20261106', count: 0, first_boards: 0, connect_boards: 0, max_boards: 0, broken_count: 0, bands: {}, rows: [], leaderboard: [], themes: [], broken_list: [] },
  ladder: { available: false, reason: null, distribution: [], max_boards: 0, total_connect: 0, gaps: [] },
  context: { available: false },
}

beforeEach(() => {
  mocked.mockReset()
})

describe('LimitUpReview 三态 + 诚实降级', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<LimitUpReview />)
    expect(screen.getByText(/加载涨停复盘/)).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('涨停复盘加载失败')))
    renderWithClient(<LimitUpReview />)
    await expect(screen.findByText(/涨停复盘加载失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染涨停池 + 龙头榜 + 上下文', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<LimitUpReview />)
    expect(await screen.findByText('龙头评分榜')).toBeTruthy()
    expect(screen.getAllByText('宁德时代').length).toBeGreaterThan(0)
    expect(screen.getByText('市场上下文')).toBeTruthy()
    // 数值如实展示
    expect(screen.getAllByText('100.0').length).toBeGreaterThan(0)
  })

  it('pool 不可用 → 诚实降级空态', async () => {
    mocked.mockResolvedValue(poolDownData)
    renderWithClient(<LimitUpReview />)
    await expect(screen.findByText(/涨停池暂时取不到/)).resolves.toBeTruthy()
    expect(screen.getByText(/东财涨停池数据源不可达/)).toBeTruthy()
  })
})
