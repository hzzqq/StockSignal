import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReviewNotes } from './ReviewNotes'
import type { ReviewNotes as ReviewNotesData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({ getReviewNotes: vi.fn() }))
// 保留真实 reviewImagePrecheckError（前置校验用例走真逻辑），只 mock 网络函数 uploadReviewImage
vi.mock('@/api/batchB', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/batchB')>()
  return { ...actual, uploadReviewImage: vi.fn() }
})
import { getReviewNotes } from '@/api/read'
import { uploadReviewImage } from '@/api/batchB'
const mocked = vi.mocked(getReviewNotes)
const mockedUpload = vi.mocked(uploadReviewImage)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeAll(() => {
  // jsdom 未实现 objectURL（本次会话内预览依赖它），测试里打桩
  URL.createObjectURL = vi.fn(() => 'blob:mock-preview')
  URL.revokeObjectURL = vi.fn()
})

beforeEach(() => {
  mocked.mockReset()
  mockedUpload.mockReset()
})

function pickFile(file: File) {
  const input = screen.getByLabelText('选择复盘图片') as HTMLInputElement
  fireEvent.change(input, { target: { files: [file] } })
}

/**
 * 已知设计性局限（见 V2-STATUS-PLAN §30）：后端 /review-notes 对「文件缺失」走
 * _not_found() error 信封，与 validation_error / invalid_data / 网络失败共用同一通道，
 * 前端无法区分，故统一显示「该日期暂无复盘笔记」+ hint 原样带出 error.message。
 * 本测试锁住当前真实行为（尤其「hint 不吞异常」），不把设计局限包装成已修复。
 *
 * 图片上传（51 晨报 parity）用例：前置校验不发请求 / 成功追加 markdown 链接 /
 * objectURL 本次会话预览 / 服务端失败原样展示。
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

describe('ReviewNotes · 复盘图片上传（51 晨报 parity）', () => {
  it('上传成功 → draft 前加空行追加 markdown 链接，objectURL 本次会话预览', async () => {
    mockedUpload.mockResolvedValue({
      filename: 'shot.png',
      url: '/api/v2/read/review-images/2026-09-21/shot.png',
      date: '2026-09-21',
    })
    renderWithClient(<ReviewNotes />)
    pickFile(new File([new Uint8Array([1, 2, 3])], 'shot.png', { type: 'image/png' }))
    // 空 draft 首次上传：直接追加链接（无前置空行）；有正文时才加空行分隔（见下方二次上传断言）
    const textarea = (await waitFor(() => {
      const el = screen.getByLabelText('复盘笔记正文') as HTMLTextAreaElement
      expect(el.value).toBe('![shot.png](/api/v2/read/review-images/2026-09-21/shot.png)')
      return el
    })) as HTMLTextAreaElement
    expect(mockedUpload).toHaveBeenCalledTimes(1)
    const [calledFile, calledDate] = mockedUpload.mock.calls[0]
    expect(calledFile.name).toBe('shot.png')
    expect(calledDate).toBe('2026-09-21')
    // 本次会话内 objectURL 预览（服务端 URL 受 JWT 保护，不直连渲染）
    expect(screen.getByAltText('shot.png')).toBeTruthy()
    expect(screen.getByAltText('shot.png').getAttribute('src')).toBe('blob:mock-preview')
    expect(screen.getByText(/历史图片预览需登录态/)).toBeTruthy()
    // 再输入正文，再传一张：链接继续追加且前加空行
    fireEvent.change(textarea, { target: { value: '今日缩量。' } })
    mockedUpload.mockResolvedValue({
      filename: 'b.gif',
      url: '/api/v2/read/review-images/2026-09-21/b.gif',
      date: '2026-09-21',
    })
    pickFile(new File([new Uint8Array([1])], 'b.gif', { type: 'image/gif' }))
    await waitFor(() => {
      const el = screen.getByLabelText('复盘笔记正文') as HTMLTextAreaElement
      expect(el.value).toBe(
        '今日缩量。\n\n![b.gif](/api/v2/read/review-images/2026-09-21/b.gif)',
      )
    })
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2)
  })

  it('超过 5MB → 前置拦截显「图片不合规」，不发上传请求', () => {
    renderWithClient(<ReviewNotes />)
    pickFile(new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'big.png', { type: 'image/png' }))
    expect(screen.getByText('图片不合规：图片超过 5MB 上限')).toBeTruthy()
    expect(mockedUpload).not.toHaveBeenCalled()
  })

  it('非白名单扩展名（.txt）→ 前置拦截显「图片不合规」，不发上传请求', () => {
    renderWithClient(<ReviewNotes />)
    pickFile(new File([new Uint8Array([1])], 'note.txt', { type: 'text/plain' }))
    expect(screen.getByText(/图片不合规：不支持的图片格式/)).toBeTruthy()
    expect(mockedUpload).not.toHaveBeenCalled()
  })

  it('上传失败 → 原样显示服务端中文错误，不吞异常', async () => {
    mockedUpload.mockRejectedValue(new Error('图片超过 5MB 上限'))
    renderWithClient(<ReviewNotes />)
    pickFile(new File([new Uint8Array([1])], 'ok.webp', { type: 'image/webp' }))
    expect(await screen.findByText('上传失败：图片超过 5MB 上限')).toBeTruthy()
  })
})
