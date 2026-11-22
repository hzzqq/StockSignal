import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MarketSentimentTabbed } from './MarketSentimentTabbed'

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
    ],
  },
  unavailable: [],
  note: '综合市场温度由可用指标…',
}

beforeEach(() => {
  sessionStorage.clear()
  mocked.mockReset()
})

describe('MarketSentimentTabbed · 双 tab 合并（2026-11-22 侧栏减臃肿）', () => {
  it('默认显示「情绪温度计」tab，渲染温度数据', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketSentimentTabbed />)
    expect(screen.getByRole('tab', { name: '情绪温度计' }).getAttribute('aria-selected')).toBe('true')
    expect(await screen.findByText('综合市场温度')).toBeTruthy()
    expect(screen.getByText('57.3')).toBeTruthy()
  })

  it('切换到「市场驱动力」tab 后渲染五维视图，切换态写 sessionStorage', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketSentimentTabbed />)
    fireEvent.click(screen.getByRole('tab', { name: '市场驱动力' }))
    expect(screen.getByRole('tab', { name: '市场驱动力' }).getAttribute('aria-selected')).toBe('true')
    expect(sessionStorage.getItem('ss_market_tab')).toBe('drivers')
    // 两个视图复用同一端点：切换 tab 后数据仍在（不下架数据）
    expect(mocked).toHaveBeenCalled()
  })

  it('会话内记忆：刷新（重挂载）后仍在上次选中的 tab', () => {
    sessionStorage.setItem('ss_market_tab', 'drivers')
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketSentimentTabbed />)
    expect(screen.getByRole('tab', { name: '市场驱动力' }).getAttribute('aria-selected')).toBe('true')
  })
})
