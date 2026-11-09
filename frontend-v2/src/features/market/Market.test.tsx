import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MarketRegime } from './MarketRegime'
import { MarketPanorama } from './MarketPanorama'
import type { MarketPanorama as MarketPanoramaData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getMarketPanorama: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getMarketPanorama } from '@/api/read'
const mocked = vi.mocked(getMarketPanorama)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: MarketPanoramaData = {
  k: 8,
  regime: {
    available: true,
    data: { rows: 4771, start: '2007-01-04', end: '2026-08-21' },
    latest: { date: '2026-08-21', state: '震荡', confidence: 0.42, metrics: { red_ratio: 51.3, limit_up: 40, limit_down: 8 } },
    state_distribution: { 普涨: 612, 结构牛: 488, 震荡: 2210, 恐慌: 905, 暴跌: 556 },
    transition_matrix: { 震荡: { 震荡: 0.3, 普涨: 0.2 } },
    analogs: [
      { date: '2023-05-04', distance: 1.2, state: '普涨', metrics: { red_ratio: 62.0, limit_up: 55, limit_down: 3 }, forward: { d5: { avg_red: 55.0, up_frac: 0.6, median_delta: 1.1 } } },
    ],
  },
  shepherd_latest: { date: '2026-08-21', red_ratio: 51.3, limit_up: 40, limit_down: 8, connect_hl: 6, zt_fail_ratio: 0.19 },
  shepherd_series: [{ date: '2026-08-21', red_ratio: 51.3 }],
  shepherd_unavailable: [['zt_fail_ratio', '该日数据源缺失']],
  date: '2026-08-21',
  note: '市场状态五档=规则可解释分类',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('MarketRegime 三态 + 字段渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<MarketRegime />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('数据不足（insufficient_data）')))
    renderWithClient(<MarketRegime />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染状态卡 + 状态分布 + 相似日', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketRegime />)
    expect(await screen.findByText('当前市场状态')).toBeTruthy()
    expect(screen.getByText('状态分布（全样本各状态天数）')).toBeTruthy()
    expect(screen.getByText('震荡')).toBeTruthy()
    expect(screen.getByText('2023-05-04')).toBeTruthy()
  })

  it('empty（regime.latest 缺失）显示暂无状态机数据', async () => {
    mocked.mockResolvedValue({ ...okData, regime: { available: false, reason: 'x' } })
    renderWithClient(<MarketRegime />)
    expect(await screen.findByText('暂无状态机数据')).toBeTruthy()
  })
})

describe('MarketPanorama 三态 + 字段渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<MarketPanorama />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('数据不足（insufficient_data）')))
    renderWithClient(<MarketPanorama />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染广度快照 + 红盘率 + 缺失字段', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketPanorama />)
    expect(await screen.findByText('市场状态')).toBeTruthy()
    expect(screen.getByText('红盘率(%)')).toBeTruthy()
    expect(screen.getByText('涨停家数')).toBeTruthy()
    expect(screen.getByText('数据源缺失字段（诚实带出）')).toBeTruthy()
    expect(screen.getByText(/zt_fail_ratio/)).toBeTruthy()
  })

  it('empty（regime.latest 缺失）显示暂无市场全景数据', async () => {
    mocked.mockResolvedValue({ ...okData, regime: { available: false, reason: 'x' } })
    renderWithClient(<MarketPanorama />)
    expect(await screen.findByText('暂无市场全景数据')).toBeTruthy()
  })
})
