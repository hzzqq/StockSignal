import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UserManagement } from './UserManagement'
import { getCurrentUser } from '@/lib/auth'
import { listUsers, createUser, updateUser, deleteUser, listLogs } from '@/api/admin'
import type { PublicUser } from '@/api/schemas/admin'

vi.mock('@/lib/auth', () => ({ getCurrentUser: vi.fn() }))
vi.mock('@/api/admin', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  deleteUser: vi.fn(),
  listLogs: vi.fn(),
}))

const mUser = vi.mocked(getCurrentUser)
const mList = vi.mocked(listUsers)
const mCreate = vi.mocked(createUser)
const mUpdate = vi.mocked(updateUser)
const mDelete = vi.mocked(deleteUser)
const mLogs = vi.mocked(listLogs)

const admin = {
  id: 1, username: 'admin', role: 'admin', created_at: '2026-01-01', is_active: true,
} as unknown as PublicUser
const normal = {
  id: 2, username: 'u2', role: 'user', created_at: '2026-02-02', is_active: true,
} as unknown as PublicUser

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
}
function renderUM() {
  return render(
    <QueryClientProvider client={client()}>
      <UserManagement />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mUser.mockReset(); mList.mockReset(); mCreate.mockReset()
  mUpdate.mockReset(); mDelete.mockReset(); mLogs.mockReset()
})

describe('UserManagement · 用户管理 · 管理员门控 + 列表/创建/日志/删除保护', () => {
  it('非管理员 → 无权限空态（不显示任何用户数据）', () => {
    mUser.mockReturnValue(normal)
    renderUM()
    expect(screen.getByText('无访问权限')).toBeTruthy()
  })

  it('登录信息失效（getCurrentUser=null）→ 无权限空态', () => {
    mUser.mockReturnValue(null)
    renderUM()
    expect(screen.getByText('无访问权限')).toBeTruthy()
  })

  it('管理员 → 渲染三标签 tablist', () => {
    mUser.mockReturnValue(admin)
    renderUM()
    expect(screen.getByRole('tablist', { name: '用户管理' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '用户列表' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '创建用户' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '操作日志' })).toBeTruthy()
  })

  it('用户列表：成功 → 渲染用户名与计数', async () => {
    mUser.mockReturnValue(admin)
    mList.mockResolvedValue({
      items: [
        { id: 1, username: 'admin', role: 'admin', created_at: '2026-01-01', is_active: true },
        { id: 2, username: 'u2', role: 'user', created_at: '2026-02-02', is_active: true },
      ],
      total: 2, pages: 1,
    } as never)
    renderUM()
    await waitFor(() => expect(screen.getAllByText('admin').length).toBeGreaterThan(0))
    expect(screen.getByText('u2')).toBeTruthy()
    expect(screen.getByText(/共 2 个用户/)).toBeTruthy()
  })

  it('用户列表：取数失败 → ErrorState（不编造用户）', async () => {
    mUser.mockReturnValue(admin)
    mList.mockRejectedValue(new Error('boom'))
    renderUM()
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.getByText('boom')).toBeTruthy()
  })

  it('用户列表：空数据 → 「暂无用户」', async () => {
    mUser.mockReturnValue(admin)
    mList.mockResolvedValue({ items: [], total: 0, pages: 0 } as never)
    renderUM()
    await waitFor(() => expect(screen.getByText('暂无用户')).toBeTruthy())
  })

  it('删除保护：自己与初始管理员按钮禁用，其他用户可删', async () => {
    mUser.mockReturnValue(admin)
    mList.mockResolvedValue({
      items: [
        { id: 1, username: 'admin', role: 'admin', created_at: '2026-01-01', is_active: true },
        { id: 2, username: 'u2', role: 'user', created_at: '2026-02-02', is_active: true },
      ],
      total: 2, pages: 1,
    } as never)
    renderUM()
    await waitFor(() => expect(screen.getAllByText('admin').length).toBeGreaterThan(0))
    const selfDel = screen.getByLabelText('删除用户 admin') as HTMLButtonElement
    expect(selfDel.disabled).toBe(true)
    const otherDel = screen.getByLabelText('删除用户 u2') as HTMLButtonElement
    expect(otherDel.disabled).toBe(false)
  })

  it('创建用户：空表单按钮禁用；填后提交成功 → 「创建成功」', async () => {
    mUser.mockReturnValue(admin)
    mCreate.mockResolvedValue(undefined as never)
    renderUM()
    fireEvent.click(screen.getByRole('tab', { name: '创建用户' }))
    const submit = screen.getByLabelText('创建用户') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'newu' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Pass@123' } })
    expect(submit.disabled).toBe(false)
    fireEvent.click(submit)
    await waitFor(() => expect(screen.getByText(/创建成功/)).toBeTruthy())
    expect(mCreate).toHaveBeenCalledTimes(1)
  })

  it('操作日志：成功 → 渲染日志条目', async () => {
    mUser.mockReturnValue(admin)
    mLogs.mockResolvedValue({
      items: [
        { id: 1, action: 'create_user', username: 'u2', target: 'newu', created_at: '2026-01-01T00:00:00', detail: '' },
      ],
      total: 1, pages: 1,
    } as never)
    renderUM()
    fireEvent.click(screen.getByRole('tab', { name: '操作日志' }))
    await waitFor(() => expect(screen.getByText('u2')).toBeTruthy())
    expect(screen.getByText('create_user', { exact: false })).toBeTruthy()
  })
})
