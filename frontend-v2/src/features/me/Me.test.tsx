import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Me } from './Me'
import type { PublicUser } from '@/api/schemas/admin'
import { getCurrentUser } from '@/lib/auth'
import { useUserDashboard } from '@/lib/queries'

vi.mock('@/lib/auth', () => ({
  getCurrentUser: vi.fn(),
}))
vi.mock('@/lib/queries', () => ({
  useUserDashboard: vi.fn(),
}))

const mUser = vi.mocked(getCurrentUser)
const mDash = vi.mocked(useUserDashboard)

function mkClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
}
function renderMe() {
  return render(
    <QueryClientProvider client={mkClient()}>
      <Me />
    </QueryClientProvider>,
  )
}

const adminUser = {
  id: 1,
  username: 'admin',
  role: 'admin',
  created_at: '2026-01-01',
  is_active: true,
} as unknown as PublicUser

const normalUser = {
  id: 2,
  username: 'u2',
  role: 'user',
  created_at: '2026-02-02',
  is_active: true,
} as unknown as PublicUser

beforeEach(() => {
  mUser.mockReset()
  mDash.mockReset()
})

describe('Me · 我的 · 账户 + 自定义看板偏好（只读）', () => {
  it('未登录（getCurrentUser=null）→ 诚实空态「请重新登录」', () => {
    mUser.mockReturnValue(null)
    mDash.mockReturnValue({ data: { default_widgets: [] } } as never)
    renderMe()
    expect(screen.getByText('未读取到登录信息（请重新登录）。')).toBeTruthy()
  })

  it('管理员账户 → 用户名 + 「管理员」徽章', () => {
    mUser.mockReturnValue(adminUser)
    mDash.mockReturnValue({ data: { default_widgets: [] } } as never)
    renderMe()
    expect(screen.getByText('admin')).toBeTruthy()
    expect(screen.getByText('管理员')).toBeTruthy()
    expect(screen.getByText(/创建于 2026-01-01/)).toBeTruthy()
  })

  it('普通用户 → 「普通用户」徽章', () => {
    mUser.mockReturnValue(normalUser)
    mDash.mockReturnValue({ data: { default_widgets: [] } } as never)
    renderMe()
    expect(screen.getByText('u2')).toBeTruthy()
    expect(screen.getByText('普通用户')).toBeTruthy()
  })

  it('created_at 缺失 → 如实显「—」', () => {
    mUser.mockReturnValue({
      id: 3,
      username: 'u3',
      role: 'user',
      created_at: null,
      is_active: true,
    } as unknown as PublicUser)
    mDash.mockReturnValue({ data: { default_widgets: [] } } as never)
    renderMe()
    expect(screen.getByText(/创建于 —/)).toBeTruthy()
  })

  it('看板偏好：default_widgets 为空 → 「暂无默认组件」', () => {
    mUser.mockReturnValue(normalUser)
    mDash.mockReturnValue({ data: { default_widgets: [] } } as never)
    renderMe()
    expect(screen.getByText('暂无默认组件')).toBeTruthy()
  })

  it('看板偏好：已知 + 未知 widget 标签（未知显原始 id）', () => {
    mUser.mockReturnValue(normalUser)
    mDash.mockReturnValue({
      data: { default_widgets: ['snapshot', 'zzz'], note: 'n', updated_at: '2026-03-03' },
    } as never)
    renderMe()
    expect(screen.getByText('今日决策快照')).toBeTruthy()
    expect(screen.getByText('zzz')).toBeTruthy()
    expect(screen.getByText('n')).toBeTruthy()
    expect(screen.getByText(/更新于 2026-03-03/)).toBeTruthy()
  })

  it('看板偏好加载中 → Loading 态', () => {
    mUser.mockReturnValue(normalUser)
    mDash.mockReturnValue({ isLoading: true } as never)
    renderMe()
    expect(screen.getByText('加载看板偏好…')).toBeTruthy()
  })

  it('看板偏好加载失败 → ErrorState（不伪装成无数据）', () => {
    mUser.mockReturnValue(normalUser)
    mDash.mockReturnValue({ isError: true, error: new Error('boom') } as never)
    renderMe()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByText('boom')).toBeTruthy()
  })
})
