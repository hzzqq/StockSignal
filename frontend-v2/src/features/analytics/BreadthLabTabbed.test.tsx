import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { BreadthLabTabbed } from './BreadthLabTabbed'

vi.mock('@/api/read', () => ({
  getBreadthAnalytics: vi.fn(() => new Promise<never>(() => {})),
  getBreadthZSeries: vi.fn(() => new Promise<never>(() => {})),
  getMomentumBreadth: vi.fn(() => new Promise<never>(() => {})),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => <div data-testid="echart" /> }))

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => sessionStorage.clear())

describe('BreadthLabTabbed · 情绪五页重组（2026-11-23）', () => {
  it('五个 tab 齐全，默认情绪时钟', () => {
    renderWithClient(<BreadthLabTabbed />)
    for (const label of ['情绪时钟', '温度持续期', '历史相似日', '拐点扫描', '动量共振']) {
      expect(screen.getByRole('tab', { name: label })).toBeTruthy()
    }
    expect(screen.getByRole('tab', { name: '情绪时钟' }).getAttribute('aria-selected')).toBe('true')
  })

  it('切到动量共振 tab 并写入会话记忆', () => {
    renderWithClient(<BreadthLabTabbed />)
    fireEvent.click(screen.getByRole('tab', { name: '动量共振' }))
    expect(screen.getByRole('tab', { name: '动量共振' }).getAttribute('aria-selected')).toBe('true')
    expect(sessionStorage.getItem('ss_breadth_lab_tab')).toBe('momentum')
  })

  it('会话记忆：刷新后仍在上次 tab', () => {
    sessionStorage.setItem('ss_breadth_lab_tab', 'duration')
    renderWithClient(<BreadthLabTabbed />)
    expect(screen.getByRole('tab', { name: '温度持续期' }).getAttribute('aria-selected')).toBe('true')
  })
})
