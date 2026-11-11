import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MomentumResonance } from './MomentumResonance'

vi.mock('@/api/read', () => ({
  getMomentumBreadth: vi.fn(),
}))
import { getMomentumBreadth } from '@/api/read'
const mocked = vi.mocked(getMomentumBreadth)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  available: true,
  reason: null,
  rr_labels: ['冰点', '偏冷', '中性', '活跃', '狂热'],
  mom_labels: ['强杀跌', '弱', '温和', '强', '极强'],
  matrix: [
    [1, 0, 0, 0, 0],
    [0, 0, 1, 2, 0],
    [0, 1, 1, 1, 1],
    [1, 0, 0, 1, 4],
    [0, 0, 0, 0, 1],
  ],
  totals_row: [1, 3, 4, 6, 1],
  totals_col: [2, 1, 2, 4, 6],
  n_days: 15,
  current: { available: true, date: '2026-08-21', rr_band: 2, mom_band: 1, rr_label: '中性', mom_label: '温和', red_ratio: 46.67, zt_prev_ret: -0.62 },
  stats: { available: true, reason: null, co_hot: 40.0, co_cold: 13.3, dominant_cell: ['活跃', '极强', 4], n_days: 15 },
  trajectory: { available: true, dates: ['2026-08-03', '2026-08-04'], rr_band: [3, 3], mom_band: [3, 4] },
  note: '共振矩阵…',
}

const unavailableData = {
  available: false,
  reason: '广度历史读取失败',
  rr_labels: ['冰点', '偏冷', '中性', '活跃', '狂热'],
  mom_labels: ['强杀跌', '弱', '温和', '强', '极强'],
  matrix: [],
  totals_row: [],
  totals_col: [],
  n_days: 0,
  current: { available: false },
  stats: { available: false },
  trajectory: { available: false, dates: [], rr_band: [], mom_band: [] },
  note: '离线广度历史读取失败，无法生成共振矩阵。',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('MomentumResonance 三态 + 矩阵渲染', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<MomentumResonance />)
    expect(screen.getByText(/加载共振矩阵/)).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('共振矩阵加载失败')))
    renderWithClient(<MomentumResonance />)
    await expect(screen.findByText(/共振矩阵加载失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染样本天数 + 共振矩阵 + 轨迹', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MomentumResonance />)
    expect(await screen.findByText('样本天数')).toBeTruthy()
    expect(screen.getByText('15')).toBeTruthy()
    expect(screen.getByText('共振矩阵（共现天数）')).toBeTruthy()
    expect(screen.getByText('共振轨迹（近期）')).toBeTruthy()
    // 当前红盘率数值如实展示，不补零
    expect(screen.getByText('46.67%')).toBeTruthy()
  })

  it('available=false → 诚实空态', async () => {
    mocked.mockResolvedValue(unavailableData)
    renderWithClient(<MomentumResonance />)
    await expect(screen.findByText(/暂无可用的广度历史/)).resolves.toBeTruthy()
  })
})
