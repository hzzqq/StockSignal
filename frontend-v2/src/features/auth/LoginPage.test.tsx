import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LoginPage } from './LoginPage'
import { login } from '@/api/endpoints'
import { clearAuth } from '@/app/guards'
import { getDailySnapshot } from '@/api/read'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: unknown }) => <span>{String(children)}</span>,
  useNavigate: () => mockNavigate,
  useSearch: vi.fn(() => ({ from: '/' })),
}))
vi.mock('@/api/endpoints', () => ({ login: vi.fn() }))
vi.mock('@/app/guards', () => ({ clearAuth: vi.fn() }))
vi.mock('@/api/read', () => ({ getDailySnapshot: vi.fn() }))

const mLogin = vi.mocked(login)
const mClear = vi.mocked(clearAuth)
const mSnap = vi.mocked(getDailySnapshot)

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
}
function renderLP() {
  return render(
    <QueryClientProvider client={client()}>
      <LoginPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mLogin.mockReset(); mClear.mockReset(); mSnap.mockReset(); mockNavigate.mockReset()
  localStorage.clear()
})

describe('LoginPage · 登录页 · 双态 + 端到端登录 + 行情台诚实缺失', () => {
  it('欢迎态渲染品牌门禁；点「去登录」切到表单态', () => {
    renderLP()
    expect(screen.getByText(/放心交给 StockSignal/)).toBeTruthy()
    fireEvent.click(screen.getByText(/去登录/))
    expect(screen.getByText('🔑 登录 StockSignal')).toBeTruthy()
  })

  it('表单态：一键填演示账号 → 用户名/密码预填', () => {
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    fireEvent.click(screen.getByText('🧪 一键填演示账号'))
    expect((screen.getByLabelText('用户名') as HTMLInputElement).value).toBe('demo')
    expect((screen.getByLabelText('密码') as HTMLInputElement).value).toBe('Demo@123')
  })

  it('空用户名/密码提交 → 本地校验报错且未调 login', () => {
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    fireEvent.click(screen.getByText('立即登录'))
    expect(screen.getByText('请输入用户名和密码')).toBeTruthy()
    expect(mLogin).not.toHaveBeenCalled()
  })

  it('登录成功 → 写 token/localStorage + navigate + 行情台显示真实温度', async () => {
    mLogin.mockResolvedValue({
      access_token: 'tok', refresh_token: undefined,
      user: { id: 1, username: 'demo', role: 'user', created_at: '2026-01-01', is_active: true },
    } as never)
    mSnap.mockResolvedValue({
      date: '2026-03-01', temperature: 55, cycle: '震荡', indicators: {}, event_factor: undefined,
    } as never)
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    await waitFor(() => expect(screen.getByLabelText('用户名')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'demo' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Demo@123' } })
    fireEvent.click(screen.getByText('立即登录'))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalled())
    expect(localStorage.getItem('ss_token')).toBe('tok')
    expect(screen.getByText('资金温度')).toBeTruthy()
    expect(screen.getByText('55')).toBeTruthy()
    expect(screen.getByText('事件因子信号暂无数据')).toBeTruthy()
  })

  it('登录失败 → clearAuth + 错误态披露（不伪装成功）', async () => {
    mLogin.mockRejectedValue(new Error('bad creds'))
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    await waitFor(() => expect(screen.getByLabelText('用户名')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'y' } })
    fireEvent.click(screen.getByText('立即登录'))
    await waitFor(() => expect(screen.getByText('bad creds')).toBeTruthy())
    expect(mClear).toHaveBeenCalled()
  })
})
