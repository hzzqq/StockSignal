import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LeadLagMatrixView } from './LeadLagMatrixView'

vi.mock('@/api/read', () => ({
  getBreadthHistory: vi.fn(),
}))
import { getBreadthHistory } from '@/api/read'
const mocked = vi.mocked(getBreadthHistory)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  mocked.mockReset()
})

describe('LeadLagMatrixView 三态 + 诚实空态', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<LeadLagMatrixView />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('广度历史加载失败'))
    renderWithClient(<LeadLagMatrixView />)
    await expect(screen.findByText('广度历史加载失败')).resolves.toBeTruthy()
  })

  it('空数据 → 诚实空态「有效样本不足，未计算矩阵」（不补零/不编造）', async () => {
    mocked.mockResolvedValue([])
    renderWithClient(<LeadLagMatrixView />)
    await expect(screen.findByText('有效样本不足，未计算矩阵')).resolves.toBeTruthy()
  })
})
