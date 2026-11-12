import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReviewNotes } from './ReviewNotes'
import type { ReviewNotes as ReviewNotesData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({ getReviewNotes: vi.fn() }))
import { getReviewNotes } from '@/api/read'
const mocked = vi.mocked(getReviewNotes)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  mocked.mockReset()
})

/**
 * 已知设计性局限（见 V2-STATUS-PLAN §30）：后端 /review-notes 对「文件缺失」走
 * _not_found() error 信封，与 validation_error / invalid_data / 网络失败共用同一通道，
 * 前端无法区分，故统一显示「该日期暂无复盘笔记」+ hint 原样带出 error.message。
 * 本测试锁住当前真实行为（尤其「hint 不吞异常」），不把设计局限包装成已修复。
 */
describe('ReviewNotes · 99 决策问答 · 复盘笔记只读视图', () => {
  it('ok → 渲染「复盘笔记 · 日期」+ 内容原文（纯文本，不引入 markdown）', async () => {
    mocked.mockResolvedValue({ date: '2026-09-21', content: '# 复盘\n今日缩量。' })
    renderWithClient(<ReviewNotes />)
    expect(await screen.findByText('复盘笔记 · 2026-09-21')).toBeTruthy()
    expect(screen.getByText(/# 复盘/)).toBeTruthy()
    expect(mocked).toHaveBeenCalledWith('2026-09-21') // 默认日期发起查询
  })

  it('error（not_found）→ 「该日期暂无复盘笔记」+ hint 原样带出原因，不吞异常', async () => {
    mocked.mockRejectedValue(new Error('review_notes_2026-09-21.md 不存在'))
    renderWithClient(<ReviewNotes />)
    await expect(screen.findByText('该日期暂无复盘笔记')).resolves.toBeTruthy()
    expect(screen.getByText('review_notes_2026-09-21.md 不存在')).toBeTruthy()
    expect(screen.queryByText(/复盘笔记 ·/)).toBeNull()
  })

  it('改选日期 → 以新日期重新发起查询', async () => {
    // 按请求日期返回对应笔记，否则默认首查就会拿到 08-31 的内容
    mocked.mockImplementation((date) =>
      Promise.resolve({ date, content: date === '2026-08-31' ? '八月收官。' : '默认笔记。' }),
    )
    renderWithClient(<ReviewNotes />)
    await screen.findByText('复盘笔记 · 2026-09-21') // 默认日期首查完成
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-08-31' } })
    expect(await screen.findByText('复盘笔记 · 2026-08-31')).toBeTruthy()
    expect(screen.getByText('八月收官。')).toBeTruthy()
    expect(mocked).toHaveBeenCalledWith('2026-08-31')
  })

  it('加载中 → 显「加载中…」，不提前显示空态或笔记', () => {
    mocked.mockReturnValue(new Promise<ReviewNotesData>(() => {}))
    renderWithClient(<ReviewNotes />)
    expect(screen.getByText('加载中…')).toBeTruthy()
    expect(screen.queryByText('该日期暂无复盘笔记')).toBeNull()
    expect(screen.queryByText(/复盘笔记 ·/)).toBeNull()
  })
})
