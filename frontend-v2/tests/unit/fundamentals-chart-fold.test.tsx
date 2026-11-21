// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { financialsFull } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { CHART } from '@/shared/charts/palette'
import { buildFinancialTrendOption } from '@/features/stock/FinancialTrendChart'
import { FundamentalsView } from '@/features/stock/FundamentalsView'

/**
 * 基本面分析页 · 历史业绩趋势图 + 多期财报折叠。
 * - buildFinancialTrendOption 纯函数：倒序正序化、缺失期不进 series、柱/同比映射、
 *   同比正负双色（行情屏语义）、无同比时不虚构副轴。
 * - 页面级：metric 三选一切换、「无同比序列」诚实提示、折叠态表格不渲染（mutation
 *   反证：若 children 折叠时仍渲染则本文件红）、summary 摘要可见。
 * - 既有测试回归：src/features/stock/FundamentalsView.test.tsx 原断言不变跑通过。
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

// jsdom 无 canvas：与全仓兄弟测试一致，用轻量替身替换真实 EChart，
// 只验证 option 构造与页面契约，不验证绘图本身；ariaLabel 透出便于断言切换。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({
    height,
    ariaLabel,
  }: {
    height?: number
    ariaLabel?: string
  }) => <div data-testid="echart" data-aria={ariaLabel} style={{ height }} />,
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }

function renderView(search?: { code?: string }) {
  return render(
    <Providers>
      <FundamentalsView search={search} />
    </Providers>,
  )
}

// ───────── buildFinancialTrendOption 纯函数 ─────────

describe('buildFinancialTrendOption · option 构造', () => {
  // 后端倒序（新→旧）原样传入；含：缺柱期（null / NaN）、缺同比期（null）。
  const rows = [
    { 报告期: '2025-09-30', 营业总收入: 1231.23, 营业总收入_同比: 15.3 },
    { 报告期: '2025-06-30', 营业总收入: null, 营业总收入_同比: 9.2 },
    { 报告期: '2025-03-31', 营业总收入: NaN, 营业总收入_同比: -1.1 },
    { 报告期: '2024-12-31', 营业总收入: 980.3, 营业总收入_同比: -2.5 },
    { 报告期: '2024-09-30', 营业总收入: 889.2, 营业总收入_同比: null },
    { 报告期: '2024-06-30', 营业总收入: 810.5 },
  ]

  it('倒序输入 → X 轴按报告期正序；null/NaN 缺柱期整期不进 series（不补 0）', () => {
    const opt = buildFinancialTrendOption(rows, '营业总收入')
    const xAxis = (opt as { xAxis: { data: string[] } }).xAxis
    expect(xAxis.data).toEqual(['2024-06-30', '2024-09-30', '2024-12-31', '2025-09-30'])

    const series = (opt as { series: Array<{ name: string; type: string; data: unknown[] }> }).series
    const bar = series.find((s) => s.type === 'bar')
    expect(bar?.name).toBe('营业总收入')
    expect(bar?.data).toEqual([810.5, 889.2, 980.3, 1231.23])
    expect(bar?.data).not.toContain(null)
    expect(bar?.data).not.toContain(0)
  })

  it('同比映射：正值 series 只含正数（红 CHART.up），负值 series 只含负数（绿 CHART.down），缺失断线', () => {
    const opt = buildFinancialTrendOption(rows, '营业总收入')
    const series = (opt as { series: Array<{ name: string; type: string; yAxisIndex?: number; data: Array<number | null>; itemStyle: { color: string } }> }).series
    const yoyLines = series.filter((s) => s.type === 'line' && s.name === '同比%')
    expect(yoyLines.length).toBe(2)
    expect(yoyLines.every((s) => s.yAxisIndex === 1)).toBe(true)

    const pos = yoyLines.find((s) => s.itemStyle.color === CHART.up)
    const neg = yoyLines.find((s) => s.itemStyle.color === CHART.down)
    expect(pos?.data).toEqual([null, null, null, 15.3])
    expect(neg?.data).toEqual([null, null, -2.5, null])
    // 缺同比期（2024-09-30）与缺柱期（2025-06-30 / 2025-03-31）都不出现任何数值
    expect(pos?.data.concat(neg?.data ?? [])).not.toContain(9.2)
    expect(pos?.data.concat(neg?.data ?? [])).not.toContain(-1.1)
    // 双轴：主轴亿元 + 副轴同比%
    const yAxis = (opt as { yAxis: Array<{ name: string; position?: string }> }).yAxis
    expect(yAxis.length).toBe(2)
    expect(yAxis[0].name).toBe('营业总收入(亿元)')
    expect(yAxis[1].name).toBe('同比%')
    expect(yAxis[1].position).toBe('right')
  })

  it('全程无同比列 → 只输出柱，不虚构副轴与同比线', () => {
    const noYoy = [
      { 报告期: '2025-09-30', 净资产收益率: 24.6 },
      { 报告期: '2025-06-30', 净资产收益率: 18.2 },
    ]
    const opt = buildFinancialTrendOption(noYoy, '净资产收益率')
    const raw = opt as {
      series: Array<{ type: string; name: string }>
      yAxis: unknown[]
      dataZoom: Array<{ type: string }>
    }
    expect(raw.series.length).toBe(1)
    expect(raw.series[0]).toMatchObject({ type: 'bar', name: '净资产收益率' })
    expect(raw.yAxis.length).toBe(1)
    // dataZoom（inside + slider）始终内置，便于长期拖拽
    expect(raw.dataZoom.map((d) => d.type).sort()).toEqual(['inside', 'slider'])
  })
})

// ───────── 页面级：趋势卡 / metric 切换 / 折叠 ─────────

describe('FundamentalsView · 历史业绩趋势卡与财报表折叠', () => {
  it('默认画营业总收入；切换归母净利润后图随受控 state 更新', async () => {
    renderView()
    expect(await screen.findByText('历史业绩趋势', {}, FIND)).toBeTruthy()
    expect(screen.getByTestId('echart').getAttribute('data-aria')).toContain('营业总收入')
    expect(screen.getByRole('radio', { name: '营业总收入' }).getAttribute('aria-checked')).toBe('true')

    fireEvent.click(screen.getByRole('radio', { name: '归母净利润' }))
    expect(screen.getByRole('radio', { name: '归母净利润' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('radio', { name: '营业总收入' }).getAttribute('aria-checked')).toBe('false')
    expect(screen.getByTestId('echart').getAttribute('data-aria')).toContain('归母净利润')
  })

  it('指标无 _同比 列 → 如实提示「无同比序列」，不虚构折线（净资产收益率）', async () => {
    renderView()
    await screen.findByText('历史业绩趋势', {}, FIND)
    fireEvent.click(screen.getByTestId('metric-净资产收益率'))
    expect(
      await screen.findByText(
        '该指标无同比序列（当前财报未提供「净资产收益率_同比」），仅绘制柱体，不补零',
        {},
        FIND,
      ),
    ).toBeTruthy()
    expect(screen.getByTestId('echart').getAttribute('data-aria')).toContain('净资产收益率')
  })

  it('metric 在 rows 中全缺失 → 空态诚实提示，不渲染图', async () => {
    server.use(
      http.get('/api/v2/read/financials', () =>
        HttpResponse.json({
          status: 'ok',
          code: 'ok',
          message: 'ok',
          data: {
            code: '600519',
            report: 'income',
            rows: [{ 报告期: '2025-09-30', 营业总收入: 1231.23 }],
            date: '2025-09-30',
            note: null,
          },
        }),
      ),
    )
    renderView()
    await screen.findByText('历史业绩趋势', {}, FIND)
    fireEvent.click(screen.getByTestId('metric-净资产收益率'))
    expect(
      await screen.findByText('「净资产收益率」在当前财报 rows 中无有效数值', {}, FIND),
    ).toBeTruthy()
    expect(screen.queryByTestId('echart')).toBeNull()
  })

  it('折叠态：summary 可见、表格（含表头）不渲染（mutation 反证：children 折叠时渲染则本用例红）；展开后表格可见', async () => {
    renderView()
    // 折叠态 summary（N 期 · 最新报告期 X · 营业总收入 Y 亿）
    expect(
      await screen.findByText('2 期 · 最新报告期 2025-09-30 · 营业总收入 1231.23 亿', {}, FIND),
    ).toBeTruthy()
    // 折叠态反证：FinancialTable 的 children 不渲染
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('报告期')).toBeNull()

    const btn = screen.getByRole('button', { name: '展开 ▾' })
    fireEvent.click(btn)
    expect(screen.getByRole('button', { name: /收起/ }).getAttribute('aria-expanded')).toBe('true')
    const table = screen.getByRole('table')
    expect(table).toBeTruthy()
    expect(screen.getByText('报告期')).toBeTruthy()
    expect(screen.getByText('2025-09-30')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '收起 ▴' }))
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('折叠摘要取 rows[0]（后端倒序 = 最新期）；fixture 覆盖 mock 数据一致性', async () => {
    // financialsFull rows[0] 即 2025-09-30（倒序），与上方折叠用例的 summary 断言互相锁死
    expect(financialsFull.rows[0]['报告期']).toBe('2025-09-30')
  })
})
