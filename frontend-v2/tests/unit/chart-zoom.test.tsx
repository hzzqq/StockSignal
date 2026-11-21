import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { buildIntradayOption, buildIntradayModel } from '@/features/stock/charts/IntradayChart'
import { FundFlow } from '@/features/fundflow/FundFlow'
import { BreadthOverview, histRangeValid, filterBreadthHistoryByRange } from '@/features/breadth/BreadthOverview'
import { Portfolio } from '@/features/portfolio/Portfolio'
import type { FundFlow as FundFlowData } from '@/api/schemas/read'
import type { BreadthHistoryPoint } from '@/api/schemas/read'

/**
 * chart-zoom 守卫（2026-11-21）：时间 x 轴图统一带 dataZoom（inside + slider）。
 *
 * 真实缺陷背景：长周期时序图（融资融券、长周期广度、IC 序列等）点数动辄数百，
 * 只能整段展示无法细看，与 KLineChart.tsx:177 / FinancialTrendChart.tsx:128
 * 既有范式（dataZoom inside+slider 内置 option）不一致。
 *
 * 守卫策略：
 *  - 纯函数直测：buildIntradayOption（已有 inside，必须补 slider）；
 *  - 渲染捕获：mock EChart 抓真实 option，断言时间轴图含 inside+slider、
 *    分类轴图（行业条形）不带 dataZoom（口径不外溢）；
 *  - BreadthOverview 长周期历史的日期区间过滤：纯函数测非法区间不生效、
 *    起>止禁用；UI 测按钮 disabled 与标题如实书写（全历史 ≠ 近 250 日）。
 */

// EChart 替身：把传入 option 捕获到 hoisted 数组，供断言（jsdom 无 canvas，与全仓同款做法）。
const { captured } = vi.hoisted(() => ({ captured: [] as Array<Record<string, unknown>> }))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ option }: { option: Record<string, unknown> }) => {
    captured.push(option)
    return <div data-testid="echart" />
  },
}))

// BreadthOverview / FundFlow / Portfolio 全部经 '@/lib/queries' 取数，统一 mock。
vi.mock('@/lib/queries', () => ({
  useFundFlow: vi.fn(),
  useDailySnapshot: vi.fn(),
  useBreadthTimeseries: vi.fn(),
  useLadderDetail: vi.fn(),
  useBreadthHistory: vi.fn(),
  useMarketTemperature: vi.fn(),
  usePortfolio: vi.fn(),
  usePositionAllocation: vi.fn(),
}))

import {
  useFundFlow,
  useDailySnapshot,
  useBreadthTimeseries,
  useLadderDetail,
  useBreadthHistory,
  useMarketTemperature,
  usePortfolio,
  usePositionAllocation,
} from '@/lib/queries'

function ok(data: unknown) {
  return { isLoading: false, isError: false, error: null, data }
}

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/** option 的 dataZoom type 列表（无 dataZoom → []）。 */
function zoomTypes(option: unknown): string[] {
  const dz = (option as { dataZoom?: Array<{ type?: string }> }).dataZoom
  return Array.isArray(dz) ? dz.map((d) => d.type ?? '') : []
}

/** 按 legend 名找捕获到的 option（取最后一次渲染的，重渲染后旧 option 仍在数组前部）。 */
function findOption(legendName: string): Record<string, unknown> | undefined {
  for (let i = captured.length - 1; i >= 0; i--) {
    const data = (captured[i] as { legend?: { data?: string[] } }).legend?.data
    if (Array.isArray(data) && data.includes(legendName)) return captured[i]
  }
  return undefined
}

beforeEach(() => {
  captured.length = 0
  vi.mocked(useFundFlow).mockReset()
  vi.mocked(useDailySnapshot).mockReset()
  vi.mocked(useBreadthTimeseries).mockReset()
  vi.mocked(useLadderDetail).mockReset()
  vi.mocked(useBreadthHistory).mockReset()
  vi.mocked(useMarketTemperature).mockReset()
  vi.mocked(usePortfolio).mockReset()
  vi.mocked(usePositionAllocation).mockReset()
  cleanup()
})

// ───────── ① IntradayChart：已有 inside，必须补 slider ─────────

describe('chart-zoom · IntradayChart 分时图', () => {
  it('dataZoom 含 inside + slider，且双 grid（价格+成交量）联动', () => {
    const rows = [
      { time: '2026-11-06 09:31:00', close: 10.5, volume: 100, amount: 1050 },
      { time: '2026-11-06 09:32:00', close: 10.8, volume: 120, amount: 1296 },
    ]
    const model = buildIntradayModel(rows)!
    const option = buildIntradayOption(model, 10, 'market') as {
      dataZoom: Array<{ type: string; xAxisIndex?: number[] }>
    }
    expect(option.dataZoom.map((d) => d.type)).toEqual(['inside', 'slider'])
    // 两个 grid 的 x 轴（价格 0 / 成交量 1）都必须被联动缩放
    for (const d of option.dataZoom) {
      expect(d.xAxisIndex).toEqual([0, 1])
    }
  })
})

// ───────── ② FundFlow：大盘主力 + 融资融券两图，行业条形（分类轴）不带 ─────────

const fundflowData: FundFlowData = {
  northbound: { available: true, northbound_net_available: true, boards: [] },
  industry: {
    available: true,
    rows: [
      { industry: '半导体', chg_pct: 2.5, inflow: 500.0, outflow: 400.0, net: 100.0 },
      { industry: '银行', chg_pct: -1.1, inflow: 200.0, outflow: 250.0, net: -50.0 },
    ],
  },
  market: {
    available: true,
    rows: [
      { date: '2026-11-06', index_chg_pct: 0.5, main_net: 120.0 },
      { date: '2026-11-07', index_chg_pct: -0.3, main_net: -80.0 },
    ],
  },
  margin: {
    available: true,
    rows: [{ date: '2026-11-06', total_rzmr_yi: 500.0 }],
    latest: { date: '2026-11-06', total_rzmr_yi: 500.0, total_rzye_yi: 13000.0 },
  },
}

describe('chart-zoom · FundFlow 大盘主力 / 融资融券时序图', () => {
  it('两张时间轴图均含 inside + slider；行业条形图（分类轴）不带 dataZoom', () => {
    vi.mocked(useFundFlow).mockReturnValue(ok(fundflowData) as never)
    renderWithClient(<FundFlow />)

    // 渲染顺序：行业条形（无 legend）→ 大盘主力 → 融资融券
    expect(captured).toHaveLength(3)
    const industry = captured.find((o) => !('legend' in o))
    expect(industry).toBeTruthy()
    expect(zoomTypes(industry)).toEqual([]) // 分类轴不外溢

    const market = findOption('主力净流入')!
    expect(market).toBeTruthy()
    expect(zoomTypes(market)).toEqual(['inside', 'slider'])

    const margin = findOption('融资买入额(合计)')!
    expect(margin).toBeTruthy()
    expect(zoomTypes(margin)).toEqual(['inside', 'slider'])
  })
})

// ───────── ③ BreadthOverview 长周期历史：dataZoom + 日期区间过滤 ─────────

/** 300 个连续日（2007-01-02 起），可精确预测 slice(-250) 与区间命中数。 */
function histFixture(n: number): BreadthHistoryPoint[] {
  const out: BreadthHistoryPoint[] = []
  const base = Date.UTC(2007, 0, 2)
  for (let i = 0; i < n; i++) {
    out.push({
      date: new Date(base + i * 86_400_000).toISOString().slice(0, 10),
      up_count: 1000 + i,
      down_count: 900 + i,
      red_ratio: 50,
    })
  }
  return out
}

function mountOverview(hist: BreadthHistoryPoint[]) {
  vi.mocked(useDailySnapshot).mockReturnValue(ok({ indicators: {}, date: '2026-11-20' }) as never)
  vi.mocked(useBreadthTimeseries).mockReturnValue(
    ok([{ date: '2026-11-19', up_count: 1, down_count: 2 }]) as never,
  )
  vi.mocked(useLadderDetail).mockReturnValue(ok([]) as never)
  vi.mocked(useBreadthHistory).mockReturnValue(ok(hist) as never)
  vi.mocked(useMarketTemperature).mockReturnValue(ok(undefined) as never)
  return renderWithClient(<BreadthOverview />)
}

describe('chart-zoom · BreadthOverview 长周期广度历史', () => {
  it('长周期历史图含 inside + slider（x 轴为时间序列）', () => {
    mountOverview(histFixture(300))
    const hist = findOption('红盘比%')!
    expect(hist).toBeTruthy()
    expect(zoomTypes(hist)).toEqual(['inside', 'slider'])
  })

  it('日期区间过滤（纯函数）：闭区间含两端；ISO 字符串直接比较，不经日期兜底', () => {
    const hist = histFixture(30)
    expect(filterBreadthHistoryByRange(hist, '2007-01-10', '2007-01-14')).toHaveLength(5)
    expect(filterBreadthHistoryByRange(hist, '2007-01-10', '2007-01-10')).toHaveLength(1)
    expect(filterBreadthHistoryByRange(hist, '2099-01-01', '2099-12-31')).toHaveLength(0)
  })

  it('日期区间校验（纯函数）：空区间 / 单侧为空 / 起>止 均非法（非法区间不生效）', () => {
    expect(histRangeValid('', '')).toBe(false) // 空区间
    expect(histRangeValid('2020-01-01', '')).toBe(false) // 单侧为空
    expect(histRangeValid('', '2020-01-01')).toBe(false)
    expect(histRangeValid('2020-01-02', '2020-01-01')).toBe(false) // 起>止
    expect(histRangeValid('2020-01-01', '2020-01-01')).toBe(true) // 起=止 合法
  })

  it('UI：空区间与起>止时「查区间」禁用；合法区间点击后标题如实书写命中数', () => {
    mountOverview(histFixture(300))
    const start = screen.getByLabelText('历史区间起始日期') as HTMLInputElement
    const end = screen.getByLabelText('历史区间结束日期') as HTMLInputElement
    const apply = screen.getByRole('button', { name: '查区间' }) as HTMLButtonElement

    // 空区间 → 禁用
    expect(apply.disabled).toBe(true)
    // 起>止 → 仍禁用（非法区间不生效，按钮不可点）
    fireEvent.change(start, { target: { value: '2007-01-20' } })
    fireEvent.change(end, { target: { value: '2007-01-10' } })
    expect(apply.disabled).toBe(true)
    // 合法区间 → 可点；点击后过滤生效，标题写命中数
    fireEvent.change(start, { target: { value: '2007-01-10' } })
    fireEvent.change(end, { target: { value: '2007-01-14' } })
    expect(apply.disabled).toBe(false)
    fireEvent.click(apply)
    expect(screen.getByText(/区间筛选 2007-01-10 ~ 2007-01-14（命中 5 个交易日）/)).toBeTruthy()
  })

  it('UI：全历史模式标题如实写「全历史（共 300 个交易日）」而非「近 250 日」', () => {
    mountOverview(histFixture(300))
    fireEvent.click(screen.getByRole('button', { name: '全历史' }))
    expect(screen.getByText(/全历史（共 300 个交易日）/)).toBeTruthy()
    expect(screen.queryByText(/展示最近 250 个/)).toBeNull()
    // 放开全历史后，图上确实画了全部 300 个日期
    const hist = findOption('红盘比%')!
    const xAxis = (hist as { xAxis?: { data?: string[] } }).xAxis
    expect(xAxis?.data).toHaveLength(300)
  })

  it('UI：默认近 250 日口径保持（300 条样本 → 图上 250 个日期）', () => {
    mountOverview(histFixture(300))
    expect(screen.getByText(/展示最近 250 个（共 300 个交易日）/)).toBeTruthy()
    const hist = findOption('红盘比%')!
    const xAxis = (hist as { xAxis?: { data?: string[] } }).xAxis
    expect(xAxis?.data).toHaveLength(250)
  })
})

// ───────── ④ Portfolio 净值曲线 vs 沪深300 ─────────

describe('chart-zoom · Portfolio 净值曲线', () => {
  it('收益归因视图下净值曲线 option 含 inside + slider', () => {
    vi.mocked(usePortfolio).mockReturnValue(
      ok({
        positions: [{ ticker: '600519', name: '贵州茅台', buy_price: 100, current_price: 110, remaining_shares: 100, cost: 10000, market_value: 11000, pnl: 1000, pnl_pct: 10 }],
        attribution: [{ ticker: '600519', name: '贵州茅台', contribution: 10 }],
        weights: [{ ticker: '600519', name: '贵州茅台', weight_pct: 100 }],
        curve_available: true,
        curve: [
          { date: '2026-01-05', portfolio: 1.0, benchmark: 1.0 },
          { date: '2026-01-06', portfolio: 1.01, benchmark: 1.005 },
          { date: '2026-01-07', portfolio: 1.02, benchmark: 1.004 },
        ],
      }) as never,
    )
    vi.mocked(usePositionAllocation).mockReturnValue(ok(undefined) as never)
    renderWithClient(<Portfolio />)

    fireEvent.click(screen.getByRole('button', { name: '收益归因' }))
    const curve = findOption('组合净值')!
    expect(curve).toBeTruthy()
    expect(zoomTypes(curve)).toEqual(['inside', 'slider'])
  })
})
