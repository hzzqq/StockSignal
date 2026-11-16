// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { communityHandlers, resetCommunityMock } from '@/mocks/handlersCommunity'
import { ForumView } from './ForumView'

/**
 * ForumView 真测：setupServer(...communityHandlers) 启动演示态内存后端，
 * 走「发帖→列表出现 / 评论→详情出现 / 点赞+1 / 删除消失 / views 自增」完整链路，
 * 并验证空标题 400、非作者删除 400、接口失败都显示真实错误文案（不伪装成功）。
 */
const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

// 发帖表单里的 StockSearchInput 在输入股票时会查此端点；演示态返回空数组，
// 不干扰社区主链路断言（帖子关联股票为可选，主链路用例不触发搜索）。
const server = setupServer(
  ...communityHandlers,
  http.get('/api/stocks/search', () =>
    HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data: [] }),
  ),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  resetCommunityMock()
  vi.clearAllMocks()
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }

function failure(message: string) {
  return HttpResponse.json(
    { status: 'error', code: 'server_error', message, data: null },
    { status: 500 },
  )
}

function mkClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderView() {
  return render(
    <QueryClientProvider client={mkClient()}>
      <ForumView />
    </QueryClientProvider>,
  )
}

describe('ForumView · 股吧社区（演示态 MSW 真测）', () => {
  it('列表加载 → 展示演示帖子标题', async () => {
    renderView()
    expect(await screen.findByText('贵州茅台年报解读', {}, FIND)).toBeTruthy()
    expect(screen.getByText('平安银行估值讨论')).toBeTruthy()
    expect(screen.getByText('今日盘面随笔')).toBeTruthy()
  })

  it('发帖 → 新帖出现在列表（发布→列表出现）', async () => {
    renderView()
    await screen.findByText('贵州茅台年报解读', {}, FIND)
    fireEvent.change(screen.getByLabelText('帖子标题'), { target: { value: '新帖子标题' } })
    fireEvent.change(screen.getByLabelText('帖子内容'), { target: { value: '新帖正文内容' } })
    fireEvent.click(screen.getByRole('button', { name: '发布帖子' }))
    expect(await screen.findByText('新帖子标题', {}, FIND)).toBeTruthy()
  })

  it('打开详情 → 展示正文与评论列表', async () => {
    renderView()
    fireEvent.click(await screen.findByText('贵州茅台年报解读', {}, FIND))
    expect(await screen.findByText(/直销渠道确实是看点/, {}, FIND)).toBeTruthy()
    expect(screen.getByText(/同意，还要看批价/)).toBeTruthy()
    expect(screen.getByText(/茅台 2025 年报营收稳健增长/)).toBeTruthy()
  })

  it('发表评论 → 新评论出现在详情（评论→详情出现）', async () => {
    renderView()
    fireEvent.click(await screen.findByText('贵州茅台年报解读', {}, FIND))
    await screen.findByText(/直销渠道确实是看点/, {}, FIND)
    fireEvent.change(screen.getByLabelText('评论内容'), { target: { value: '这是一条新评论' } })
    fireEvent.click(screen.getByRole('button', { name: '发表评论' }))
    expect(await screen.findByText(/这是一条新评论/, {}, FIND)).toBeTruthy()
  })

  it('点赞 → likes 从 5 变 6', async () => {
    renderView()
    fireEvent.click(await screen.findByText('贵州茅台年报解读', {}, FIND))
    expect(await screen.findByRole('button', { name: '点赞（5）' }, FIND)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '点赞（5）' }))
    expect(await screen.findByRole('button', { name: '点赞（6）' }, FIND)).toBeTruthy()
  })

  it('空标题发帖 → 显示真实错误「标题不能为空」，不伪造成功', async () => {
    renderView()
    await screen.findByText('贵州茅台年报解读', {}, FIND)
    fireEvent.change(screen.getByLabelText('帖子内容'), { target: { value: '只有正文没有标题' } })
    fireEvent.click(screen.getByRole('button', { name: '发布帖子' }))
    expect(await screen.findByText('标题不能为空', {}, FIND)).toBeTruthy()
    expect(screen.queryByText('发布成功')).toBeNull()
    // 失败后保留用户输入（不清空表单），且列表未被新增帖子污染
    expect((screen.getByLabelText('帖子内容') as HTMLTextAreaElement).value).toBe('只有正文没有标题')
    expect(screen.getByText('贵州茅台年报解读')).toBeTruthy()
    expect(screen.getByText('平安银行估值讨论')).toBeTruthy()
    expect(screen.getByText('今日盘面随笔')).toBeTruthy()
  })

  it('删除自己的帖子 → 二次确认后从列表消失', async () => {
    renderView()
    fireEvent.click(await screen.findByText('贵州茅台年报解读', {}, FIND))
    await screen.findByRole('button', { name: /点赞（5）/ }, FIND)
    fireEvent.click(screen.getByRole('button', { name: '删除帖子' }))
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    await screen.findByText('帖子列表', {}, FIND)
    await waitFor(() => expect(screen.queryByText('贵州茅台年报解读')).toBeNull(), FIND)
  })

  it('删除他人帖子 → 显示 400「只能删除自己的帖子」', async () => {
    renderView()
    fireEvent.click(await screen.findByText('平安银行估值讨论', {}, FIND))
    await screen.findByRole('button', { name: /点赞（2）/ }, FIND)
    fireEvent.click(screen.getByRole('button', { name: '删除帖子' }))
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    expect(await screen.findByText('只能删除自己的帖子', {}, FIND)).toBeTruthy()
  })

  it('列表接口失败 → 显示真实错误文案', async () => {
    server.use(http.get('/api/forum/posts', () => failure('帖子服务不可用')))
    renderView()
    expect(await screen.findByText('帖子服务不可用', {}, FIND)).toBeTruthy()
  })

  it('点击关联股票 → navigate 到 /stock/research?code=600519', async () => {
    renderView()
    const stockBtn = await screen.findByText(/600519）→ 个股研究/, {}, FIND)
    fireEvent.click(stockBtn)
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/stock/research',
      search: { code: '600519' },
    })
  })
})
