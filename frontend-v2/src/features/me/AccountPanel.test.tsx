// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { communityHandlers, resetCommunityMock } from '@/mocks/handlersCommunity'
import { ToastProvider } from '@/shared/ui/Toast'
import { AccountPanel } from './AccountPanel'

/**
 * AccountPanel 真测：setupServer(...communityHandlers) 启动演示态账户后端。
 * 覆盖 token 信息 / 登录历史 / 设置保存成功 / 非法 JSON 被拒 / 登出清 token /
 * 接口失败显示真实错误，并验证登出失败绝不伪造成功（不清 token、不跳 /login）。
 */
const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }))

// 保留真实模块其余导出（guards.tsx 会 import redirect），只替换 useNavigate。
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

const server = setupServer(...communityHandlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  resetCommunityMock()
  localStorage.clear()
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
      <ToastProvider>
        <AccountPanel />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

/** 等 /me 回填偏好编辑框完成，避免异步回填覆盖手动输入的测试值。 */
async function waitMeReady() {
  await screen.findByText(/账号 ID 1/, {}, FIND)
}

describe('AccountPanel · 账户面板（演示态 MSW 真测）', () => {
  it('token 信息 → sub/role/iat/exp 如实展示，iat/exp 标注「Unix 秒」', async () => {
    renderView()
    expect(await screen.findByText('1767225600', {}, FIND)).toBeTruthy()
    expect(screen.getByText('1767229200')).toBeTruthy()
    expect(screen.getByText('demo')).toBeTruthy()
    expect(screen.getByText('user')).toBeTruthy()
    expect(screen.getAllByText(/Unix 秒/)).toHaveLength(2)
  })

  it('登录历史 → 展示 action=login 的记录', async () => {
    renderView()
    expect(await screen.findByText(/127\.0\.0\.1/, {}, FIND)).toBeTruthy()
    expect(screen.getAllByText(/login/).length).toBeGreaterThanOrEqual(2)
  })

  it('偏好设置：合法 JSON 对象 → 保存成功', async () => {
    renderView()
    await waitMeReady()
    fireEvent.change(screen.getByLabelText('偏好设置 JSON'), {
      target: { value: '{"theme_mode":"light"}' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    expect(await screen.findByText('设置已保存', {}, FIND)).toBeTruthy()
  })

  it('偏好设置：非法 JSON → 显示「设置内容不是合法 JSON」，不保存', async () => {
    renderView()
    await waitMeReady()
    fireEvent.change(screen.getByLabelText('偏好设置 JSON'), {
      target: { value: 'not-json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    expect(await screen.findByText('设置内容不是合法 JSON', {}, FIND)).toBeTruthy()
    expect(screen.queryByText('设置已保存')).toBeNull()
  })

  it('偏好设置：JSON 数组非对象 → 显示「settings 必须是对象」', async () => {
    renderView()
    await waitMeReady()
    fireEvent.change(screen.getByLabelText('偏好设置 JSON'), { target: { value: '[1,2]' } })
    fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
    expect(await screen.findByText('settings 必须是对象', {}, FIND)).toBeTruthy()
  })

  it('登出成功 → 清 token（ss_token/refresh/user）并跳 /login', async () => {
    localStorage.setItem('ss_token', 'demo-token')
    localStorage.setItem('ss_refresh', 'demo-refresh')
    localStorage.setItem('ss_user', JSON.stringify({ id: 1, username: 'demo', role: 'user' }))
    renderView()
    await screen.findByRole('button', { name: '退出登录' }, FIND)
    fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
    await waitFor(
      () =>
        expect(mockNavigate).toHaveBeenCalledWith({
          to: '/login',
          search: { from: '/' },
        }),
      FIND,
    )
    expect(localStorage.getItem('ss_token')).toBeNull()
    expect(localStorage.getItem('ss_refresh')).toBeNull()
    expect(localStorage.getItem('ss_user')).toBeNull()
  })

  it('登出失败 → 不清 token、不跳 /login（不伪造成功）', async () => {
    localStorage.setItem('ss_token', 'demo-token')
    server.use(http.post('/api/auth/logout', () => failure('登出服务异常')))
    renderView()
    await screen.findByRole('button', { name: '退出登录' }, FIND)
    fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
    expect(await screen.findByText('登出服务异常', {}, FIND)).toBeTruthy()
    expect(localStorage.getItem('ss_token')).toBe('demo-token')
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('token-info 接口失败 → 显示真实错误文案', async () => {
    server.use(http.get('/api/auth/token-info', () => failure('Token 服务不可用')))
    renderView()
    expect(await screen.findByText('Token 服务不可用', {}, FIND)).toBeTruthy()
  })
})
