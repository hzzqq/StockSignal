// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { ResearchView } from './ResearchView'

/**
 * 个股研究页 · quick 子视图「分时数据独立四态」守卫。
 *
 * 契约取证（backend/api/read_routes.py::stock_intraday）：
 *   底层源存在，故**不走 not_found**；整取数失败/空时诚实返回
 *   status=ok + rows=[] + date=null，绝不 500 / 编造。
 * 因此「暂无分时数据」是正常业务态，必须显式告知；而接口失败必须走错误态，
 * 不能伪装成「无数据」（§30 DataExport 同族红线）。
 *
 * MSW 默认夹具对未知 code 返回 notFound，与后端不一致；本文件对两个端点
 * 均显式注入响应，只测前端契约，不依赖夹具差异。
 */
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
  }
})

// jsdom 无 canvas；桩掉 EChart，用 testid 计数验证「两张图都在」。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => <div data-testid="echart" />,
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

// React Query 重试 + MSW 往返可能超过 findBy* 默认 1s；与既有 W4-B E2E 同用 5s。
const FIND = { timeout: 5000 }

const ok = (data: unknown) =>
  HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })

const KLINE_ROWS = [
  { date: '2026-11-05', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
  { date: '2026-11-06', open: 10.5, high: 11.2, low: 10, close: 11, volume: 120 },
]
const INTRADAY_ROWS = [
  { time: '09:30', close: 10.2, volume: 100, amount: 1020 },
  { time: '09:31', close: 10.5, volume: 120, amount: 1260 },
]

function mockKline(rows: unknown[] = KLINE_ROWS) {
  server.use(
    http.get('/api/v2/read/stock-kline', () =>
      ok({ code: '600519', period: 'daily', rows, date: '2026-11-06', note: 'kline note' }),
    ),
  )
}

function mockIntraday(rows: unknown[], prevClose: number | null = 10) {
  server.use(
    http.get('/api/v2/read/stock-intraday', () =>
      ok({ code: '600519', date: '2026-11-06', rows, prev_close: prevClose, note: 'intraday note' }),
    ),
  )
}

beforeEach(() => {
  mockKline()
})

function renderView() {
  return render(
    <Providers>
      <ResearchView search={{ view: 'quick', code: '600519' }} />
    </Providers>,
  )
}

describe('ResearchView · 分时数据不得静默省略（诚实红线）', () => {
  it('⚠️ 后端真实「无分时数据」= ok + rows=[] → 显式空态，且 K 线表不受连累', async () => {
    mockIntraday([])
    renderView()

    expect(await screen.findByText('暂无分时数据', {}, FIND)).toBeTruthy()
    expect(screen.getByText('分时 rows 为空数组，未做填充或补零')).toBeTruthy()
    // 主数据源独立：K 线表照常渲染
    expect(await screen.findByText('open', {}, FIND)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('⚠️ 分时接口失败 → 错误态 alert，绝不伪装成「暂无分时数据」', async () => {
    server.use(
      http.get('/api/v2/read/stock-intraday', () =>
        HttpResponse.json(
          { status: 'error', code: 'boom', message: '分时接口 500', data: null },
          { status: 200 },
        ),
      ),
    )
    renderView()

    expect(await screen.findByText('分时接口 500', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.queryByText('暂无分时数据')).toBeNull()
  })

  it('分时加载中 → 独立区块显示「加载中…」，不是整块消失', async () => {
    server.use(
      http.get('/api/v2/read/stock-intraday', () => new Promise<never>(() => {})),
    )
    renderView()

    await waitFor(() => expect(screen.getByText('open')).toBeTruthy())
    const section = screen.getByTestId('intraday-section')
    expect(within(section).getByText('加载中…')).toBeTruthy()
  })

  it('分时成功 → K 线 + 分时两张图都在，无空/错态', async () => {
    mockIntraday(INTRADAY_ROWS)
    renderView()

    await waitFor(() => expect(screen.getAllByTestId('echart')).toHaveLength(2))
    expect(screen.queryByText('暂无分时数据')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('K 线 rows 空但分时有数据 → 主数据空态与分时图各自独立，不连带整页空白', async () => {
    mockKline([])
    mockIntraday(INTRADAY_ROWS)
    renderView()

    expect(await screen.findByText('暂无 K 线数据', {}, FIND)).toBeTruthy()
    expect(screen.getAllByTestId('echart').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('暂无分时数据')).toBeNull()
  })

  it('prev_close=null → 分时图仍渲染并如实标注「暂无昨收基准」', async () => {
    mockIntraday(INTRADAY_ROWS, null)
    renderView()

    expect(await screen.findByText(/暂无昨收基准/, {}, FIND)).toBeTruthy()
    expect(screen.getAllByTestId('echart').length).toBeGreaterThanOrEqual(1)
  })
})
