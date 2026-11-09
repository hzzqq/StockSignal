import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FactorAnalysis } from './FactorAnalysis'
import type { FactorAnalysis as FactorAnalysisData } from '@/api/schemas/read'

// 隔离真实 API：只替换 getFactorAnalysis；图表组件在 jsdom 不可用，mock 为 null。
vi.mock('@/api/read', () => ({
  getFactorAnalysis: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getFactorAnalysis } from '@/api/read'
const mocked = vi.mocked(getFactorAnalysis)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: FactorAnalysisData = {
  codes: ['600519', '000001', '300750'],
  days: 250,
  factor: 'momentum',
  forward: 1,
  n_layers: 5,
  ic_series: [
    { date: '2026-10-01', ic: 0.03 },
    { date: '2026-10-02', ic: -0.02 },
  ],
  ic_summary: {
    n: 2,
    ic_mean: 0.005,
    ic_std: 0.03,
    ir: 0.16,
    positive_ratio: 0.5,
    t_stat: 0.4,
  },
  layered_cum: [
    { date: '2026-10-01', '0': 0.01, '1': 0.005, '2': 0, '3': -0.005, '4': -0.01 },
  ],
  long_short_cum: [{ date: '2026-10-01', ic: 0.02 }],
  errs: [],
  date: '2026-10-02',
  note: '逐标的独立取数、独立降级；缺失为 null 且不补 0',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('FactorAnalysis 三态 + 字段渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<FactorAnalysis />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态（诚实不谎报为数据）', async () => {
    mocked.mockImplementation(() =>
      Promise.reject(new Error('数据不足（insufficient_data）')),
    )
    renderWithClient(<FactorAnalysis />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染 IC 汇总与三图卡片标题', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<FactorAnalysis />)
    expect(await screen.findByText('样本期数 n')).toBeTruthy()
    expect(screen.getByText('IC 均值')).toBeTruthy()
    expect(screen.getByText('逐期 IC 序列')).toBeTruthy()
    expect(
      screen.getByText('分层累计收益（因子由大到小分层的净值曲线）'),
    ).toBeTruthy()
    expect(screen.getByText('多空组合累计净值')).toBeTruthy()
  })

  it('empty（ic_series 为空）显示暂无因子数据', async () => {
    mocked.mockResolvedValue({ ...okData, ic_series: [] })
    renderWithClient(<FactorAnalysis />)
    expect(await screen.findByText('暂无因子数据')).toBeTruthy()
  })
})
