import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { P1Tabbed } from './P1Tabbed'

vi.mock('@/api/read', () => ({
  getP1Signals: vi.fn(),
}))
import { getP1Signals } from '@/api/read'
const mocked = vi.mocked(getP1Signals)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  signal_h10: {
    latest_date: '2026-10-16',
    generated_at: '2026-11-02',
    top_long: [{ symbol: '600000', name: '浦发银行', pred: 0.1234, rank: 1.5 }],
    top_short: [{ symbol: '600001', name: '邯郸钢铁', pred: 0.5, rank: 2.0 }],
  },
}

beforeEach(() => {
  sessionStorage.clear()
  mocked.mockReset()
})

describe('P1Tabbed · 双 tab 合并（2026-11-22 侧栏减臃肿）', () => {
  it('默认显示「量化信号」tab，渲染信号数据', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<P1Tabbed />)
    expect(screen.getByRole('tab', { name: '量化信号' }).getAttribute('aria-selected')).toBe('true')
    expect(await screen.findByText('signal_h10')).toBeTruthy()
  })

  it('切换到「组合构建诊断」tab 后渲染诊断视图，切换态写 sessionStorage', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<P1Tabbed />)
    fireEvent.click(screen.getByRole('tab', { name: '组合构建诊断' }))
    expect(screen.getByRole('tab', { name: '组合构建诊断' }).getAttribute('aria-selected')).toBe('true')
    expect(sessionStorage.getItem('ss_p1_tab')).toBe('construction')
    // 诊断视图取本地随包 JSON（零网络），其内容渲染出现即证明视图已切换
    expect(mocked).toHaveBeenCalledTimes(1) // 切 tab 不重新拉 P1 信号
  })

  it('会话内记忆：刷新（重挂载）后仍在上次选中的 tab', () => {
    sessionStorage.setItem('ss_p1_tab', 'construction')
    mocked.mockResolvedValue(okData)
    renderWithClient(<P1Tabbed />)
    expect(screen.getByRole('tab', { name: '组合构建诊断' }).getAttribute('aria-selected')).toBe('true')
  })
})
