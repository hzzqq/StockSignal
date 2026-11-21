// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { EarningsCalendar } from '@/features/calendar/EarningsCalendar'

/**
 * 财报日历折叠 + 行点击财报弹窗（earnings-modal）守卫：
 *  ① 大表折叠：默认不渲染 table + summary 精确（N 条 · 最近披露日 X，取披露时间列最小值）；
 *  ② 行点击（6 位码）打开 role=dialog 财报弹窗，fundamentals/financials 请求发生；
 *  ③ open=false（未点击）零个股域请求（MSW 请求计数反证「查询不挂载不发请求」）；
 *  ④ 「—」兜底码行点击不弹窗、不发请求；
 *  ⑤ 三 tab 受控切换：balance/cash 各自触发对应 report 请求；
 *  ⑥ Esc / 遮罩点击关闭弹窗。
 *
 * MSW 复用现有 handlers：/earnings-calendar 夹具含 600519 贵州茅台行（披露时间最小值 2026-03-20）；
 * /fundamentals、/financials 已按 code 分派（600519 → fundamentalsFull / financialsFull），零新夹具。
 */

const server = setupServer(...handlers)

/** MSW 请求计数（仅个股域端点），用于「不发请求」与 report 参数反证。 */
const calls = { fundamentals: 0, financials: 0, lastFinReport: '' }

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'bypass' })
  server.events.on('request:start', ({ request }) => {
    const u = new URL(request.url)
    if (u.pathname === '/api/v2/read/fundamentals') calls.fundamentals++
    if (u.pathname === '/api/v2/read/financials') {
      calls.financials++
      calls.lastFinReport = u.searchParams.get('report') ?? ''
    }
  })
})
afterEach(() => {
  server.resetHandlers()
  calls.fundamentals = 0
  calls.financials = 0
  calls.lastFinReport = ''
  cleanup()
})
afterAll(() => server.close())

function renderCalendar() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <EarningsCalendar />
    </QueryClientProvider>,
  )
}

/** 等数据到位 → 展开折叠卡 → 等表格出现。 */
async function expandTable() {
  await screen.findByText(/沪深京 · 2025年报/)
  fireEvent.click(screen.getByRole('button', { name: '展开 ▾' }))
  await screen.findByRole('table')
}

/** 展开并点击 600519 贵州茅台行，返回弹窗 dialog 元素。 */
async function openModalByRowClick() {
  await expandTable()
  fireEvent.click(screen.getByText('贵州茅台'))
  return screen.findByRole('dialog')
}

describe('① 大表折叠（CollapsibleCard）', () => {
  it('折叠态不渲染 table，summary 精确为「6 条 · 最近披露日 2026-03-20」（披露时间最小值）', async () => {
    renderCalendar()
    await screen.findByText(/沪深京 · 2025年报/)
    // 折叠态：连日历表一起不渲染（CollapsibleCard 不渲染 children）
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText('6 条 · 最近披露日 2026-03-20')).toBeTruthy()
  })

  it('展开后表格行可见（真实性断言保留：600519 贵州茅台行）', async () => {
    renderCalendar()
    await expandTable()
    expect(screen.getByText('贵州茅台')).toBeTruthy()
    expect(screen.getByText('600519')).toBeTruthy()
  })
})

describe('② 行点击财报弹窗', () => {
  it('点击 600519 行打开 role=dialog，头部信息卡 + perf 9 项 + 默认利润表 tab 渲染', async () => {
    renderCalendar()
    const dialog = await openModalByRowClick()
    expect(within(dialog).getByText(/贵州茅台/)).toBeTruthy()
    // 头部信息卡：fundamentals 夹具字段
    expect(await within(dialog).findByText('PE(TTM)')).toBeTruthy()
    expect(within(dialog).getAllByText('营收(亿元)').length).toBeGreaterThan(0)
    // 财报三表：income 默认激活 + 表格渲染
    const incomeTab = within(dialog).getByRole('radio', { name: '利润表' })
    expect(incomeTab.getAttribute('aria-checked')).toBe('true')
    expect(within(dialog).getByRole('table')).toBeTruthy()
    // 底部「查看 K 线」按钮存在
    expect(within(dialog).getByText('查看 K 线')).toBeTruthy()
  })

  it('弹窗打开后 fundamentals / financials(income) 请求确实发生', async () => {
    renderCalendar()
    await openModalByRowClick()
    await screen.findByRole('dialog')
    await waitFor(() => expect(calls.fundamentals).toBeGreaterThan(0))
    await waitFor(() => expect(calls.financials).toBeGreaterThan(0))
    expect(calls.lastFinReport).toBe('income')
  })
})

describe('③ 弹窗关闭时不发请求（查询不挂载不发请求）', () => {
  it('未点击任何行（open=false）：个股域 fundamentals/financials 零请求', async () => {
    renderCalendar()
    // 等日历数据到位（说明日历查询已完成，给足个股查询若误挂载的触发窗口）
    await screen.findByText(/沪深京 · 2025年报/)
    await waitFor(() => expect(calls.fundamentals).toBe(0))
    expect(calls.financials).toBe(0)
  })
})

describe('④ 「—」兜底码不触发弹窗', () => {
  it('code=— 的行点击：无 dialog、无个股域请求', async () => {
    server.use(
      http.get('/api/v2/read/earnings-calendar', () =>
        HttpResponse.json({
          status: 'ok',
          code: 'ok',
          message: 'ok',
          data: {
            market: '沪深京',
            period: '2025年报',
            date: null,
            unavailable: false,
            note: '',
            rows: [
              {
                股票代码: '—',
                股票简称: '未知主体',
                报告期: '2025年报',
                披露时间: '2026-03-20',
                披露状态: '已披露',
              },
            ],
          },
        }),
      ),
    )
    renderCalendar()
    await expandTable()
    fireEvent.click(screen.getByText('未知主体'))
    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(calls.fundamentals).toBe(0))
    expect(calls.financials).toBe(0)
  })
})

describe('⑤ 财报三表 tab 切换', () => {
  it('balance / cash 切换各自触发对应 report 请求（income+balance+cash 共 3 次）', async () => {
    renderCalendar()
    const dialog = await openModalByRowClick()
    await within(dialog).findByText('PE(TTM)')
    fireEvent.click(within(dialog).getByRole('radio', { name: '资产负债表' }))
    await waitFor(() => expect(calls.lastFinReport).toBe('balance'))
    fireEvent.click(within(dialog).getByRole('radio', { name: '现金流量表' }))
    await waitFor(() => expect(calls.lastFinReport).toBe('cash'))
    expect(calls.financials).toBe(3)
    // aria-checked 受控状态跟随
    expect(
      within(dialog).getByRole('radio', { name: '现金流量表' }).getAttribute('aria-checked'),
    ).toBe('true')
    expect(
      within(dialog).getByRole('radio', { name: '利润表' }).getAttribute('aria-checked'),
    ).toBe('false')
  })
})

describe('⑥ Esc / 遮罩关闭', () => {
  it('Esc 关闭弹窗（dialog 从 DOM 移除）', async () => {
    renderCalendar()
    await openModalByRowClick()
    expect(await screen.findByRole('dialog')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('点击遮罩（role=presentation）关闭弹窗', async () => {
    renderCalendar()
    await openModalByRowClick()
    expect(await screen.findByRole('dialog')).toBeTruthy()
    fireEvent.click(screen.getByRole('presentation'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})
