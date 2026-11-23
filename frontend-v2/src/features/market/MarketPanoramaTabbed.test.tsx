import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { MarketPanoramaTabbed } from './MarketPanoramaTabbed'

vi.mock('@/api/read', () => ({
  getMarketPanorama: vi.fn(() => new Promise<never>(() => {})),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => <div data-testid="echart" /> }))

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => sessionStorage.clear())

describe('MarketPanoramaTabbed · 全景/状态机合并（2026-11-23）', () => {
  it('默认显示市场全景，可切到市场状态机', () => {
    renderWithClient(<MarketPanoramaTabbed />)
    expect(screen.getByRole('tab', { name: '市场全景' }).getAttribute('aria-selected')).toBe('true')
    fireEvent.click(screen.getByRole('tab', { name: '市场状态机' }))
    expect(screen.getByRole('tab', { name: '市场状态机' }).getAttribute('aria-selected')).toBe('true')
    expect(sessionStorage.getItem('ss_panorama_tab')).toBe('regime')
  })

  it('会话记忆：刷新后仍在上次 tab', () => {
    sessionStorage.setItem('ss_panorama_tab', 'regime')
    renderWithClient(<MarketPanoramaTabbed />)
    expect(screen.getByRole('tab', { name: '市场状态机' }).getAttribute('aria-selected')).toBe('true')
  })
})
