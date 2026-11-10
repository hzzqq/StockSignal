// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers, resetAdminMock } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { UserManagement } from '@/features/admin/UserManagement'
import type { PublicUser } from '@/api/schemas/admin'

/**
 * 用户管理（/users，92 页 V2 化）真人交互级 E2E。
 *
 * 不引入 Playwright（项目硬规则）：本文件用 Testing Library 在 jsdom 真实渲染纯组件，
 * 覆盖键盘输入 / 表单禁用态 / 点击 / 模态确认 / 搜索回车 / 错误态。
 * 多浏览器真交互由既有 headless 目检脚本（probe_frontend_v2_realbackend.py）覆盖。
 */
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
    useNavigate: () => vi.fn(),
  }
})

const server = setupServer(...handlers)

function seedAuth(role: 'admin' | 'user', username = 'admin', id = 1) {
  const me: PublicUser = {
    id,
    username,
    role,
    created_at: '2026-01-01T08:00:00Z',
    is_active: true,
    avatar: null,
    settings: {},
  }
  localStorage.setItem('ss_token', 'mock-access-token')
  localStorage.setItem('ss_user', JSON.stringify(me))
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  resetAdminMock()
  cleanup()
  localStorage.clear()
})
afterAll(() => server.close())

function mount(node: ReactNode) {
  return render(<Providers>{node}</Providers>)
}

describe('用户管理 · 权限门控', () => {
  it('非管理员显示无权限空态，不暴露任何用户数据', () => {
    seedAuth('user', 'demo', 2)
    mount(<UserManagement />)
    expect(screen.getByText('无访问权限')).toBeTruthy()
    // 非管理员不应出现「用户列表」Tab
    expect(screen.queryByRole('tab', { name: '用户列表' })).toBeNull()
  })

  it('管理员可见三 Tab 并加载出种子用户', async () => {
    seedAuth('admin')
    mount(<UserManagement />)
    expect(screen.getByRole('tab', { name: '用户列表' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '创建用户' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '操作日志' })).toBeTruthy()
    // 用户名单元格（span.font-medium）与角色单元格（td）同时含 'admin'，须定向匹配避免多节点歧义
    await waitFor(
      () => expect(screen.getAllByText('admin').length).toBeGreaterThan(0),
      { timeout: 5000 },
    )
    expect(screen.getByText('demo')).toBeTruthy()
    expect(screen.getByText('guest')).toBeTruthy()
  })
})

describe('用户管理 · 创建用户（表单交互）', () => {
  it('用户名或密码为空时创建按钮禁用；填写后启用并提交创建', async () => {
    seedAuth('admin')
    mount(<UserManagement />)
    fireEvent.click(screen.getByRole('tab', { name: '创建用户' }))

    const submit = screen.getByRole('button', { name: '创建用户' })
    expect((submit as HTMLButtonElement).disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'alice' } })
    expect((submit as HTMLButtonElement).disabled).toBe(true) // 密码仍空
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret123' } })
    expect((submit as HTMLButtonElement).disabled).toBe(false)

    fireEvent.click(submit)
    await waitFor(() => expect(screen.getByText('用户 alice 创建成功')).toBeTruthy(), { timeout: 5000 })

    // 切回列表，新用户已落库（MSW 内存态）
    fireEvent.click(screen.getByRole('tab', { name: '用户列表' }))
    await waitFor(() => expect(screen.getByText('alice')).toBeTruthy(), { timeout: 5000 })
  })

  it('后端报错（用户名已存在）时真实报错，不编造成功', async () => {
    seedAuth('admin')
    mount(<UserManagement />)
    fireEvent.click(screen.getByRole('tab', { name: '创建用户' }))
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByRole('button', { name: '创建用户' }))
    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert.textContent).toContain('用户名已存在')
    }, { timeout: 5000 })
  })
})

describe('用户管理 · 删除确认（模态交互）', () => {
  it('删除非保护用户：弹出确认框 → 确认 → 用户从列表移除', async () => {
    seedAuth('admin')
    mount(<UserManagement />)
    // 默认停在第一 Tab（用户列表），等待列表加载
    await waitFor(() => expect(screen.getByText('guest')).toBeTruthy(), { timeout: 5000 })

    // guest 可被删除（非自己、非初始 admin）
    fireEvent.click(screen.getByRole('button', { name: '删除用户 guest' }))
    expect(screen.getByRole('dialog', { name: '确认删除' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(screen.queryByText('guest')).toBeNull(), { timeout: 5000 })
  })

  it('初始管理员删除按钮禁用（不能删除初始 admin）', async () => {
    seedAuth('admin')
    mount(<UserManagement />)
    await waitFor(
      () => expect(screen.getAllByText('admin').length).toBeGreaterThan(0),
      { timeout: 5000 },
    )
    const delAdmin = screen.getByRole('button', { name: '删除用户 admin' }) as HTMLButtonElement
    expect(delAdmin.disabled).toBe(true)
  })
})

describe('用户管理 · 搜索（键盘交互）', () => {
  it('搜索框回车按用户名过滤列表', async () => {
    seedAuth('admin')
    mount(<UserManagement />)
    await waitFor(() => expect(screen.getByText('demo')).toBeTruthy(), { timeout: 5000 })

    const search = screen.getByLabelText('搜索用户名') as HTMLInputElement
    fireEvent.change(search, { target: { value: 'demo' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    await waitFor(() => {
      expect(screen.getByText('demo')).toBeTruthy()
      expect(screen.queryByText('guest')).toBeNull()
    }, { timeout: 5000 })
  })
})

describe('用户管理 · 错误态诚实渲染', () => {
  it('后端返回 status=error → 真实错误态（role=alert），不降级成空表', async () => {
    server.use(
      http.get('/api/admin/users', () =>
        HttpResponse.json(
          { status: 'error', code: 'not_found', message: '数据文件缺失', data: null },
          { status: 200 },
        ),
      ),
    )
    seedAuth('admin')
    mount(<UserManagement />)
    await waitFor(() => {
      const alert = screen.getByRole('alert')
      expect(alert.textContent).toContain('数据文件缺失')
    }, { timeout: 5000 })
  })
})
