import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LoginPage } from './LoginPage'
import { login, register } from '@/api/endpoints'
import { clearAuth } from '@/app/guards'
import { getPublicOverview, getPublicIndexIntraday, getPublicPicks } from '@/api/read'

const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: unknown }) => <span>{String(children)}</span>,
  useNavigate: () => mockNavigate,
  useSearch: vi.fn(() => ({ from: '/' })),
}))
vi.mock('@/api/endpoints', () => ({ login: vi.fn(), register: vi.fn() }))
vi.mock('@/app/guards', () => ({ clearAuth: vi.fn() }))
// EChart 是 canvas 图表（echarts 动态分包），测试环境替换为空壳，只断言渲染分支
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
vi.mock('@/api/read', () => ({
  getPublicOverview: vi.fn(),
  getPublicIndexIntraday: vi.fn(),
  getPublicPicks: vi.fn(),
}))

const mLogin = vi.mocked(login)
const mRegister = vi.mocked(register)
const mClear = vi.mocked(clearAuth)
const mPub = vi.mocked(getPublicOverview)
const mIntraday = vi.mocked(getPublicIndexIntraday)
const mPicks = vi.mocked(getPublicPicks)

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

const PUB_OK = {
  date: '2026-11-17', as_of: '2026-11-17T16:31:19', cycle: '冰点', temperature: 29,
  indicators: {
    up_count: 1216, down_count: 3882, limit_up: 37, limit_down: 84,
    red_ratio: 23.85, median_chg: -1.27,
  },
  event_factor: { long_count: 20, adj: 2, as_of: '2026-11-09' },
} as never

const INTRADAY_OK = {
  code: 'sh000001', name: '上证指数', date: '2026-11-20', prev_close: 3401,
  rows: [
    { time: '2026-11-20 09:35:00', close: 3403 },
    { time: '2026-11-20 09:40:00', close: 3404.5 },
  ],
} as never

const PICKS_OK = {
  stocks: [
    { code: '688519', name: '演示半导体', pred: 0.1 },
    { code: '688766', name: null, pred: null },
  ],
  stocks_as_of: '2026-11-17',
  sectors: [{ industry: '电池', chg_pct: -1.2, net: '-12.50亿' }],
  disclaimer: '量化信号与资金流均为灰度参考，不构成投资建议',
} as never

beforeEach(() => {
  mLogin.mockReset(); mRegister.mockReset(); mClear.mockReset()
  mPub.mockReset(); mIntraday.mockReset(); mPicks.mockReset()
  mockNavigate.mockReset()
  localStorage.clear()
  // 默认给齐三端点（个别用例覆写失败分支）
  mPub.mockResolvedValue(PUB_OK)
  mIntraday.mockResolvedValue(INTRADAY_OK)
  mPicks.mockResolvedValue(PICKS_OK)
})

describe('LoginPage · 登录页 · 双态 + 端到端登录 + 行情台', () => {
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
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    expect(mLogin).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText('29')).toBeTruthy())
    expect(screen.getByText('1216')).toBeTruthy()
    expect(screen.getByText('3882')).toBeTruthy()
    expect(screen.getByText('37')).toBeTruthy()
    expect(screen.getByText('84')).toBeTruthy()
    expect(screen.getByText(/红盘占比 23\.9%/)).toBeTruthy()
    expect(screen.getByText(/快照数据日：2026-11-17/)).toBeTruthy()
  })

  it('公开摘要失败 → 三面板诚实降级全「—」，绝不编造数字', async () => {
    mPub.mockRejectedValue(new Error('net down'))
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    // 温度进度条 aria-label（文本不在 DOM text，用 role 查）
    expect(screen.getByRole('img', { name: '资金温度暂无数据' })).toBeTruthy()
    expect(await screen.findByText('快照数据日：—')).toBeTruthy()
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

describe('LoginPage · 上证分时 + 今日推荐（2026-11-21 老板需求）', () => {
  it('分时卡渲染数据日与昨收基准；推荐卡渲染股票/板块真实条目', async () => {
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    expect(await screen.findByText('上证分时')).toBeTruthy()
    // 等数据落地：分时头 数据日 + 当日涨跌（(3404.5-3401)/3401*100=+0.10%）
    await waitFor(() => expect(screen.getByText(/\+0\.10%/)).toBeTruthy())
    expect(screen.getByText(/2026-11-20/)).toBeTruthy()
    expect(screen.getByText(/昨收基准 3401\.00/)).toBeTruthy()
    // 今日推荐：股票名 + 代码 + 预测分；未命中名称显「—」；板块 + 净额
    expect(screen.getByText('今日推荐')).toBeTruthy()
    expect(screen.getByText(/信号数据日 2026-11-17/)).toBeTruthy()
    expect(screen.getByText('演示半导体')).toBeTruthy()
    expect(screen.getByText('+10.0%')).toBeTruthy()
    expect(screen.getByText('电池')).toBeTruthy()
    expect(screen.getByText('净额 -12.50亿')).toBeTruthy()
    expect(screen.getByText('量化信号与资金流均为灰度参考，不构成投资建议')).toBeTruthy()
  })

  it('分时与推荐取数失败 → 诚实空态，绝不编造行情/推荐', async () => {
    mIntraday.mockRejectedValue(new Error('sina down'))
    mPicks.mockRejectedValue(new Error('picks down'))
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    expect(await screen.findByText(/暂无分时数据（非交易时段或数据源不可用）/)).toBeTruthy()
    expect(screen.getByText('— 暂无信号标的')).toBeTruthy()
    expect(screen.getByText('— 暂无板块资金流数据')).toBeTruthy()
  })

  it('AI 信号卡已由「今日推荐」承接：不再出现旧「看多标的」孤值卡', async () => {
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    await waitFor(() => expect(screen.getByText('今日推荐')).toBeTruthy())
    expect(screen.queryByText('AI 信号')).toBeNull()
  })
})

describe('LoginPage · 开放注册（2026-11-21 接入）', () => {
  it('切到注册模式 → 出现确认密码框，提交调 register（密码不一致本地拦）', async () => {
    mRegister.mockResolvedValue({
      id: 9, username: 'newbie', role: 'user', created_at: '2026-01-01', is_active: true,
    } as never)
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    fireEvent.click(screen.getByRole('tab', { name: '注册' }))
    expect(screen.getByLabelText('确认密码')).toBeTruthy()
    await waitFor(() => expect(screen.getByLabelText('用户名')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'newbie' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Pass@123' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'Pass@999' } })
    fireEvent.click(screen.getByText('立即注册'))
    expect(screen.getByText('两次输入的密码不一致')).toBeTruthy()
    expect(mRegister).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'Pass@123' } })
    fireEvent.click(screen.getByText('立即注册'))
    await waitFor(() => expect(mRegister).toHaveBeenCalledWith('newbie', 'Pass@123', 'Pass@123'))
    // 注册成功 → 回到登录模式 + 提示请登录（绝不自动登录假装发 token）
    expect(await screen.findByText(/注册成功（newbie），请登录/)).toBeTruthy()
    expect(screen.getByRole('tab', { name: '登录' }).getAttribute('aria-selected')).toBe('true')
    expect((screen.getByLabelText('用户名') as HTMLInputElement).value).toBe('newbie')
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('注册失败（后端 409/422 message）→ 原样披露错误，不伪装成功', async () => {
    renderLP()
    fireEvent.click(screen.getByText(/去登录/))
    fireEvent.click(screen.getByRole('tab', { name: '注册' }))
    mRegister.mockRejectedValue(new Error('用户名已存在'))
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'Pass@123' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'Pass@123' } })
    fireEvent.click(screen.getByText('立即注册'))
    await waitFor(() => expect(screen.getByText('用户名已存在')).toBeTruthy())
  })
})
