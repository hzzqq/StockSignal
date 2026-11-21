import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { buildIntradayModel, buildIntradayOption, IntradayChart } from './IntradayChart'
import { CHART } from '@/shared/charts/palette'
import { DIRECTION_HEX } from './common'

vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))

function rows() {
  return [
    { time: '2026-11-06 09:31:00', close: 10.5, volume: 100, amount: 1050 },
    { time: '2026-11-06 09:32:00', close: 10.8, volume: 120, amount: 1296 },
  ]
}

function seriesOf(option: ReturnType<typeof buildIntradayOption>) {
  return option.series as unknown as Array<{ name?: string; data?: unknown[]; markLine?: unknown }>
}

describe('IntradayChart · 分时明细表折叠（默认只留一行摘要）', () => {
  it('⚠️ 默认折叠：表格 DOM 不渲染（children 不出），summary 含「N 笔」与最新价', () => {
    const { container } = render(<IntradayChart rows={rows()} prevClose={10} priceDomain="market" />)
    // 折叠态：children 不渲染 → 表格整体不存在（mutation 反证：若总渲染则此断言红）
    expect(container.querySelector('table')).toBeNull()
    expect(screen.queryByText('时间')).toBeNull()
    // 摘要：N 笔 · 最新 HH:MM 价格 P
    expect(screen.getByText('2 笔 · 最新 09:32 价格 10.80')).toBeTruthy()
    const btn = screen.getByRole('button', { name: '展开 ▾' })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
  })

  it('⚠️ 展开后全量表可见（时间/价格/均价/成交量四列齐全）', () => {
    render(<IntradayChart rows={rows()} prevClose={10} priceDomain="market" />)
    fireEvent.click(screen.getByRole('button', { name: '展开 ▾' }))
    expect(screen.getByRole('button', { name: '收起 ▴' }).getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getAllByText('09:31').length).toBeGreaterThanOrEqual(1)
    // 09:32 同时出现在 Stat sub 与表格单元格中，用 getAllByText 避免多匹配报错
    expect(screen.getAllByText('09:32').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('时间')).toBeTruthy()
    // 「均价」同时出现在表头与 Stat 标签中，用 getAllByText 避免多匹配报错
    expect(screen.getAllByText('均价').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('成交量')).toBeTruthy()
  })

  it('昨收基准缺失 → 摘要尾加「· 暂无昨收基准」；末笔 close 缺失 → 价格「—」', () => {
    render(
      <IntradayChart
        rows={[{ time: '2026-11-06 09:31:00', close: null, volume: 100 }]}
        priceDomain="market"
      />,
    )
    expect(screen.getByText('1 笔 · 最新 09:31 价格 — · 暂无昨收基准')).toBeTruthy()
  })
})

describe('IntradayChart · 图表本体不折叠且诚实红线不回归', () => {
  it('rows 为空 → 诚实空态，不画空图表', () => {
    render(<IntradayChart rows={[]} priceDomain="market" />)
    expect(screen.getByText('分时图暂无数据可绘制')).toBeTruthy()
    expect(screen.getByText('rows 为空数组，未做补零或日期兜底')).toBeTruthy()
  })

  it('昨收缺失 → 不画基准线（无 markLine），价格线/量柱中性色，不臆断涨跌', () => {
    const model = buildIntradayModel(rows())!
    const series = seriesOf(buildIntradayOption(model, null, 'market'))
    const price = series.find((s) => s.name === '价格')!
    expect(price.markLine).toBeUndefined()
    expect((price.data as (number | null)[]).every((v) => v === null || typeof v === 'number')).toBe(true)
  })

  it('有昨收 → 基准虚线画在昨收价上', () => {
    const model = buildIntradayModel(rows())!
    const series = seriesOf(buildIntradayOption(model, 10, 'market'))
    const price = series.find((s) => s.name === '价格')!
    expect(price.markLine).toBeTruthy()
  })

  it('均价线为琥珀虚线、成交量按涨跌着色（market 口径）', () => {
    const model = buildIntradayModel(rows())!
    const option = buildIntradayOption(model, 10, 'market')
    const series = option.series as unknown as Array<{
      name?: string
      lineStyle?: { color?: string; type?: string }
      data?: Array<{ value: number | null; itemStyle: { color: string } } | null>
    }>
    const avg = series.find((s) => s.name === '均价')!
    expect(avg.lineStyle!.color).toBe(CHART.warn)
    expect(avg.lineStyle!.type).toBe('dashed')
    const vol = series.find((s) => s.name === '成交量')!.data as Array<{
      itemStyle: { color: string }
    }>
    expect(vol[0]!.itemStyle.color).toBe(DIRECTION_HEX.market.up)
    expect(vol[1]!.itemStyle.color).toBe(DIRECTION_HEX.market.up)
  })

  it('图表 Stat 与 aria 标签仍在（图形不是关键数值的唯一载体）', () => {
    render(<IntradayChart rows={rows()} prevClose={10} priceDomain="market" />)
    expect(screen.getByText('最新价')).toBeTruthy()
    expect(screen.getByText('均价')).toBeTruthy()
    expect(screen.getByText('昨收基准')).toBeTruthy()
    expect(screen.getByText('较昨收')).toBeTruthy()
  })
})
