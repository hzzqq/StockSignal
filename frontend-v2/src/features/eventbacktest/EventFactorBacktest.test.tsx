import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { EventBacktest } from '@/api/schemas/read'

// 隔离真实 API：只替换 useEventBacktest；图表组件在 jsdom 不可用，mock 为 null。
let resultOverride: unknown = { isLoading: true, isError: false, error: null, data: undefined }
vi.mock('@/lib/queries', () => ({
  useEventBacktest: vi.fn(() => resultOverride),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { EventFactorBacktest } from './EventFactorBacktest'

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: EventBacktest = {
  available: true,
  metric: 'limit_down_ratio',
  tail: 0.1,
  direction: 'high',
  horizon: 1,
  n_event: 296,
  n_base: 3800,
  base_rate: 0.498,
  event_rate: 0.625,
  edge_pp: 12.7,
  z: 4.36,
  distribution: Array.from({ length: 10 }, (_, i) => ({
    bucket: `${i / 10}-${(i + 1) / 10}`,
    event_count: i,
    base_count: 100 + i * 10,
  })),
  example_dates: [
    { date: '2015-07-08', metric_value: 9.41, forward_red_day_frac: 1.0 },
    { date: '2020-02-03', metric_value: 8.1, forward_red_day_frac: 1.0 },
  ],
  method: 'two-proportion z-test（pooled）',
  honesty_notes: [
    '方法：walk-forward（第 i 天阈值只用 [0,i) 历史分位，无未来函数）。',
    '结果度量：前向 N 日「红盘日占比」，非指数收益率。',
    '指标均为尺度无关的占比类（跨年代采样规模可比）。',
  ],
}

beforeEach(() => {
  resultOverride = { isLoading: true, isError: false, error: null, data: undefined }
})

describe('EventFactorBacktest 三态 + 诚实红线', () => {
  it('loading 显示加载中占位', () => {
    renderWithClient(<EventFactorBacktest />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('ok 渲染统计卡、分布图与诚实脚注', async () => {
    resultOverride = { isLoading: false, isError: false, error: null, data: okData }
    renderWithClient(<EventFactorBacktest />)
    expect(await screen.findByText('触发样本')).toBeTruthy()
    expect(screen.getByText('基准红盘率')).toBeTruthy()
    expect(screen.getByText('事件红盘率')).toBeTruthy()
    expect(screen.getByText('边缘')).toBeTruthy()
    expect(screen.getByText('z 值')).toBeTruthy()
    expect(screen.getByText('前向红盘日占比分布：事件 vs 基准')).toBeTruthy()
    // 诚实脚注原样带出（非指数收益率）
    expect(screen.getByText(/非指数收益率/)).toBeTruthy()
  })

  it('available=false 显示 reason 而非补零', async () => {
    resultOverride = {
      isLoading: false,
      isError: false,
      error: null,
      data: { available: false, reason: '历史样本中未触发' },
    }
    renderWithClient(<EventFactorBacktest />)
    expect(await screen.findByText('历史样本中未触发')).toBeTruthy()
  })

  it('z=null 小样本显示「样本不足未检验」而非伪造成显著性', async () => {
    resultOverride = {
      isLoading: false,
      isError: false,
      error: null,
      data: { ...okData, n_event: 12, z: null, honesty_notes: [...(okData.honesty_notes ?? []), '触发观测 12 < 30，显著性（z）未计算，仅作描述性参考。'] },
    }
    renderWithClient(<EventFactorBacktest />)
    expect(await screen.findByText('样本不足未检验')).toBeTruthy()
  })

  it('点击预设「广度冰点」改写指标与方向控件', () => {
    renderWithClient(<EventFactorBacktest />)
    fireEvent.click(screen.getByText('广度冰点'))
    const selects = screen.getAllByRole('combobox')
    expect((selects[0] as HTMLSelectElement).value).toBe('red_ratio')
    expect((selects[1] as HTMLSelectElement).value).toBe('low')
  })
})
