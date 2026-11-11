import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MarketSentiment } from './MarketSentiment'

vi.mock('@/api/read', () => ({
  getMarketSentiment: vi.fn(),
}))
import { getMarketSentiment } from '@/api/read'
const mocked = vi.mocked(getMarketSentiment)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  available: true,
  reason: null,
  data_as_of: '2026-03-01',
  temperature: 57.3,
  level: { label: '中性', emoji: '⚖️', color: '#2b8aef' },
  dims: {
    资金: [
      { key: 'margin_net', name: '融资净买入额', unit: '亿元', value: 46.8, spark: [40.2, 58.5, 44.8], heat: 60.1, available: true },
      { key: 'north_net', name: '北向净买额', unit: '亿元', value: null, spark: [null, null, null], heat: null, available: true },
    ],
  },
  unavailable: [{ dim: '情绪', key: 'vix', reason: 'akshare 限流' }],
  note: '综合市场温度由可用指标…',
}

const unavailableData = {
  available: false,
  reason: '市场驱动力数据加载失败（网络与缓存均不可用）',
  data_as_of: null,
  temperature: null,
  level: null,
  dims: {},
  unavailable: [],
  note: '市场驱动力数据加载失败…',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('MarketSentiment 三态 + 维度渲染 + 诚实降级', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<MarketSentiment />)
    expect(screen.getByText(/加载市场情绪/)).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('市场情绪加载失败')))
    renderWithClient(<MarketSentiment />)
    await expect(screen.findByText(/市场情绪加载失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染温度计 + 维度指标 + 缺值显「—」', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketSentiment />)
    expect(await screen.findByText('综合市场温度')).toBeTruthy()
    expect(screen.getByText('57.3')).toBeTruthy()
    // 维度分组卡片标题
    expect(screen.getByText('资金')).toBeTruthy()
    // 指标行
    expect(screen.getByText('融资净买入额')).toBeTruthy()
    // 取不到的指标（value=null）显「—」，不补零
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    // 不可用清单
    expect(screen.getByText(/不可用指标（诚实降级）/)).toBeTruthy()
  })

  it('available=false → 诚实空态', async () => {
    mocked.mockResolvedValue(unavailableData)
    renderWithClient(<MarketSentiment />)
    await expect(screen.findByText(/市场情绪数据暂时取不到/)).resolves.toBeTruthy()
    expect(screen.getByText(/网络与缓存均不可用/)).toBeTruthy()
  })
})
