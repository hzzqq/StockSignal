import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LoginPage } from './LoginPage'
import { login } from '@/api/endpoints'
import { clearAuth } from '@/app/guards'
import { getPublicOverview } from '@/api/read'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: unknown }) => <span>{String(children)}</span>,
  useNavigate: () => mockNavigate,
  useSearch: vi.fn(() => ({ from: '/' })),
}))
vi.mock('@/api/endpoints', () => ({ login: vi.fn() }))
vi.mock('@/app/guards', () => ({ clearAuth: vi.fn() }))
vi.mock('@/api/read', () => ({ getPublicOverview: vi.fn() }))

const mLogin = vi.mocked(login)
const mClear = vi.mocked(clearAuth)
const mPub = vi.mocked(getPublicOverview)

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
  mLogin.mockReset(); mClear.mockReset(); mPub.mockReset(); mockNavigate.mockReset()
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

  it('未登录即调公开摘要端点并渲染三面板真实数据（2026-11-17 修复：不再等登录）', async () => {
    mPub.mockResolvedValue({
      date: '2026-11-17', as_of: '2026-11-17T16:31:19', cycle: '冰点', temperature: 29,
      indicators: {
        up_count: 1216, down_count: 3882, limit_up: 37, limit_down: 84,
        red_ratio: 23.85, median_chg: -1.27,
      },
      event_factor: { long_count: 20, adj: 2, as_of: '2026-11-09' },
    } as never)
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    // 关键行为：未登录（不发 login）行情台就有数据
    expect(mLogin).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText('29')).toBeTruthy())
    expect(screen.getByText('1216')).toBeTruthy()
    expect(screen.getByText('3882')).toBeTruthy()
    expect(screen.getByText('37')).toBeTruthy()
    expect(screen.getByText('84')).toBeTruthy()
    expect(screen.getByText('20')).toBeTruthy()
    expect(screen.getByText('信号数据日 2026-11-09')).toBeTruthy()
    expect(screen.getByText(/红盘占比 23\.9%/)).toBeTruthy()
    expect(screen.getByText(/快照数据日：2026-11-17/)).toBeTruthy()
  })

  it('公开摘要失败 → 三面板诚实降级全「—」，绝不编造数字', async () => {
    mPub.mockRejectedValue(new Error('net down'))
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    // 温度进度条 aria-label（文本不在 DOM text，用 role 查）
    expect(screen.getByRole('img', { name: '资金温度暂无数据' })).toBeTruthy()
    expect(screen.getByText('事件因子信号暂无数据')).toBeTruthy()
    expect(screen.getByText('快照数据日：—')).toBeTruthy()
    // 上涨家数等指标位 = 破折号占位（DeskMetric dash）
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(6)
  })

  it('登录成功 → 写 token/localStorage + navigate + 行情台保持真实温度', async () => {
    mLogin.mockResolvedValue({
      access_token: 'tok', refresh_token: undefined,
      user: { id: 1, username: 'demo', role: 'user', created_at: '2026-01-01', is_active: true },
    } as never)
    mPub.mockResolvedValue({
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
