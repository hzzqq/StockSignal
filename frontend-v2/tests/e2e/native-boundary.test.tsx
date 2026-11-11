// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { Me } from '@/features/me/Me'
import { EarningsCalendar } from '@/features/calendar/EarningsCalendar'
import { ReviewNotes } from '@/features/review/ReviewNotes'

/**
 * 收口页真实回归（16 财报日历 / 91 我的 / 99 决策问答）。
 *
 * 三页均为 v2 native（/earnings-calendar / /me / /review-notes），复用只读端点。
 * 守诚实红线：取不到即显「无数据」/「暂无」，不补零、不编造；错误态显 role=alert。
 * 网络一律走 MSW node，零真实请求。
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

const server = setupServer(
  ...handlers,
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  localStorage.clear()
})
afterAll(() => server.close())

function mount(node: ReactNode) {
  return render(<Providers>{node}</Providers>)
}

describe('91 我的（/me）', () => {
  it('渲染账户与看板偏好；无登录态如实显「请重新登录」，看板 chips 来自真实偏好', async () => {
    mount(<Me />)
    expect(screen.getByRole('heading', { name: '我的' })).toBeTruthy()
    // 无 ss_user → 诚实空态
    expect(screen.getByText(/请重新登录/)).toBeTruthy()
    // 看板偏好（MSW 返回 userDashboard 夹具）→ 默认组件 chips 落地
    await waitFor(() => expect(screen.getByText('今日决策快照')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText('回测运行记录')).toBeTruthy()
  })

  it('看板偏好加载失败显错误态（role=alert），不吞成空数据', async () => {
    server.use(
      http.get('/api/v2/read/user-dashboard', () =>
        HttpResponse.json({ status: 'error', code: 'x', message: '看板偏好加载失败' }, { status: 200 }),
      ),
    )
    mount(<Me />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/看板偏好加载失败/)).toBeTruthy()
  })
})

describe('16 财报日历（/earnings-calendar）', () => {
  it('市场/报告期下拉与披露表格真实渲染（来自真实披露日历夹具）', async () => {
    mount(<EarningsCalendar />)
    expect(screen.getByRole('heading', { name: '财报日历' })).toBeTruthy()
    // 两个下拉
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBe(2)
    expect(screen.getByText('沪深京')).toBeTruthy()
    expect(screen.getByText('2025年报')).toBeTruthy()
    // 默认 MSW 返回 6 行 → 表格与数据来源注记落地
    await waitFor(() => expect(screen.getByText('贵州茅台')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText('数据来源：东方财富 财报预约披露日历（年报）')).toBeTruthy()
  })

  it('真实 akshare 列名（首次预约/实际披露）也能渲染披露时间与状态，不全显「—」', async () => {
    // 守卫：真缺陷曾因列名漂移让这三列全变「—」，而夹具用旧列名使 MSW 全绿。
    // 这里绕过规整层直接喂 akshare 原始形态，锁死前端 pickDisclosure/pickStatus 容错。
    server.use(
      http.get('/api/v2/read/earnings-calendar', () =>
        HttpResponse.json({
          status: 'ok', code: 'ok', message: 'earnings-calendar',
          data: {
            market: '沪深京', period: '2025年报', date: '2026-03-21', unavailable: false,
            note: '数据来源：东方财富 财报预约披露日历（年报）',
            rows: [{ 股票代码: '000001', 股票简称: '平安银行', 首次预约: '2026-03-21T00:00:00.000', 实际披露: '2026-03-21T00:00:00.000' }],
          },
        }),
      ),
    )
    mount(<EarningsCalendar />)
    await waitFor(() => expect(screen.getByRole('table')).toBeTruthy(), { timeout: 5000 })
    // 只在表格内断言（下拉里也有「2025年报」，须排除歧义）：三列都有真实值，不是「—」
    const table = screen.getByRole('table')
    expect(within(table).getByText('平安银行')).toBeTruthy()
    expect(within(table).getByText('2026-03-21')).toBeTruthy()  // 披露时间：实际披露截前 10 位
    expect(within(table).getByText('2025年报')).toBeTruthy()    // 报告期：回落到请求参数
    // 原始形态没有「披露状态」列 → 状态列如实显「—」（仅此 1 处），不编造状态；
    // 真端点会规整出「已披露/预约待披露」，见后端 test_earnings_calendar_contract.py。
    expect(within(table).getAllByText('—')).toHaveLength(1)
    expect(screen.queryByText('该市场/报告期暂无披露日历数据')).toBeNull()
  })

  it('数据源不可得（unavailable）显诚实空态，不编造行', async () => {
    server.use(
      http.get('/api/v2/read/earnings-calendar', () =>
        HttpResponse.json({
          status: 'ok', code: 'ok', message: 'earnings-calendar',
          data: { market: '沪深京', period: '2025年报', rows: [], date: null, unavailable: true, note: '暂取不到' },
        }),
      ),
    )
    mount(<EarningsCalendar />)
    await waitFor(() => expect(screen.getByText('财报披露日历暂时取不到')).toBeTruthy(), { timeout: 5000 })
    expect(screen.queryByText('贵州茅台')).toBeNull()
  })

  it('有可达端点但本市场/报告期无数据显空态，不谎报有数据', async () => {
    server.use(
      http.get('/api/v2/read/earnings-calendar', () =>
        HttpResponse.json({
          status: 'ok', code: 'ok', message: 'earnings-calendar',
          data: { market: '深市', period: '2023年报', rows: [], date: null, unavailable: false, note: '该期暂无' },
        }),
      ),
    )
    mount(<EarningsCalendar />)
    await waitFor(() => expect(screen.getByText('该市场/报告期暂无披露日历数据')).toBeTruthy(), { timeout: 5000 })
  })

  it('加载失败显错误态（role=alert）', async () => {
    server.use(
      http.get('/api/v2/read/earnings-calendar', () => HttpResponse.json({ status: 'error', code: 'x', message: '披露日历加载失败' }, { status: 200 })),
    )
    mount(<EarningsCalendar />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/披露日历加载失败/)).toBeTruthy()
  })
})

describe('99 决策问答（/review-notes）', () => {
  it('默认日期无复盘笔记（后端 not_found）→ 诚实空态，不编造内容', async () => {
    mount(<ReviewNotes />)
    expect(screen.getByRole('heading', { name: '决策问答' })).toBeTruthy()
    const dateInput = screen.getByDisplayValue('2026-09-21') as HTMLInputElement
    expect(dateInput).toBeTruthy()
    await waitFor(() => expect(screen.getByText('该日期暂无复盘笔记')).toBeTruthy(), { timeout: 5000 })
  })

  it('切换日期仍无笔记 → 仍诚实空态（不依赖写死文件）', async () => {
    mount(<ReviewNotes />)
    const dateInput = screen.getByDisplayValue('2026-09-21') as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2024-01-01' } })
    // 夹具对所有 date 均返回 not_found → 空态持续
    await waitFor(() => expect(screen.getByText('该日期暂无复盘笔记')).toBeTruthy(), { timeout: 5000 })
  })

  it('端点异常仍诚实空态，且把真实错误原因作为 hint 带出（不静默吞错）', async () => {
    // 设计契约：本页无独立 ErrorState，任何取数失败一律按「该日期暂无复盘笔记」呈现，
    // 但必须把后端返回的真实错误文案作为 hint 显出，避免把 500 谎报成「今天没写笔记」。
    server.use(
      http.get('/api/v2/read/review-notes', () =>
        HttpResponse.json({ status: 'error', code: 'server_error', message: '复盘笔记加载失败', data: null }),
      ),
    )
    mount(<ReviewNotes />)
    await waitFor(() => expect(screen.getByText('该日期暂无复盘笔记')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/复盘笔记加载失败/)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })
})
