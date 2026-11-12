import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MorningReport } from './MorningReport'
import type { ReviewNotes } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getReviewNotes: vi.fn(),
}))
import { getReviewNotes } from '@/api/read'
const mocked = vi.mocked(getReviewNotes)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = { date: '2026-03-01', content: '今日复盘：市场震荡。' }

beforeEach(() => {
  mocked.mockReset()
})

describe('MorningReport 四态 + 诚实红线', () => {
  it('默认未选日期 → 不发起查询（不把查不到伪装成今天数据）', () => {
    renderWithClient(<MorningReport />)
    expect(screen.getByText(/未选择日期，不发起查询/)).toBeTruthy()
  })

  it('ok 渲染复盘笔记原文', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MorningReport />)
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-03-01' } })
    expect(await screen.findByText('复盘笔记 2026-03-01')).toBeTruthy()
    expect(screen.getByText('今日复盘：市场震荡。')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('笔记加载失败'))
    renderWithClient(<MorningReport />)
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-03-01' } })
    await expect(screen.findByText('笔记加载失败')).resolves.toBeTruthy()
  })

  it('空结果 → 诚实空态（暂无数据）', async () => {
    mocked.mockResolvedValue(null as unknown as ReviewNotes)
    renderWithClient(<MorningReport />)
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-03-01' } })
    await expect(screen.findByText('暂无数据')).resolves.toBeTruthy()
  })
})
