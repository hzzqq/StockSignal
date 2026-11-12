import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { buildKlineModel, buildKlineOption, KLineChart } from './KLineChart'
import { CHART } from '@/shared/charts/palette'
import { DIRECTION_HEX } from './common'

vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))

type VolItem = { value: number | null; itemStyle: { color: string } } | null

/** 4 根：前 3 根完整，第 4 根 OHLC 全缺失但 volume 有效（真实取数失败场景）。 */
function rows() {
  return [
    { date: '2026-01-01', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
    { date: '2026-01-02', open: 10.5, high: 11, low: 10, close: 11, volume: 120 },
    { date: '2026-01-03', open: 11, high: 12, low: 10.5, close: 11.5, volume: 130 },
    { date: '2026-01-04', open: null, high: null, low: null, close: null, volume: 90 },
  ]
}

function volumeData(option: ReturnType<typeof buildKlineOption>): VolItem[] {
  const series = option.series as unknown as Array<{ name?: string; data?: unknown[] }>
  const vol = series.find((s) => s.name === '成交量')
  return (vol?.data ?? []) as VolItem[]
}

describe('KLineChart · 缺失数据不得臆断涨跌方向（诚实红线）', () => {
  it('⚠️ OHLC 缺失但成交量有效 → 成交量柱应使用中性色，绝不染涨色', () => {
    const model = buildKlineModel(rows())!
    const data = volumeData(buildKlineOption(model, 'market'))
    expect(data).toHaveLength(4)
    expect(data[3]).not.toBeNull()
    expect(data[3]!.itemStyle.color).toBe(CHART.ink3)
  })

  it('⚠️ 最新一根收盘价缺失 → 「最新收盘」Stat 显「--」且不得染跌色', () => {
    render(<KLineChart rows={rows()} priceDomain="market" />)
    expect(screen.getByText('最新收盘')).toBeTruthy()
    const stat = screen.getByText('最新收盘').parentElement
    const valueEl = stat?.querySelector('.text-kpi')
    expect(valueEl?.textContent).toBe('--')
    // 修复前 lastUp=false → style 带跌色；缺失应为无色（中性）
    expect(valueEl?.getAttribute('style')).toBeFalsy()
  })

  it('OHLC 缺失行蜡烛不画（null），MA/MACD 未就绪段一律 null，不补 0', () => {
    const model = buildKlineModel(rows())!
    const series = buildKlineOption(model, 'market').series as unknown as Array<{ name?: string; data?: unknown[] }>
    const candle = series.find((s) => s.name === 'K线')!.data!
    expect(candle[3]).toBeNull()
    expect(candle.slice(0, 3).every((v) => Array.isArray(v))).toBe(true)
    expect(model.ma.ma5.slice(0, 4).every((v) => v === null)).toBe(true)
    expect(model.macd.dif.every((v) => v === null)).toBe(true)
    expect(model.macd.hist.every((v) => v === null)).toBe(true)
  })

  it('正常 K 线的成交量柱按涨跌着色：收>=开 → 涨色，收<开 → 跌色', () => {
    const model = buildKlineModel([
      { date: '2026-01-01', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
      { date: '2026-01-02', open: 11, high: 11.2, low: 10, close: 10.2, volume: 120 },
    ])!
    const data = volumeData(buildKlineOption(model, 'market'))
    expect(data[0]!.itemStyle.color).toBe(DIRECTION_HEX.market.up)
    expect(data[1]!.itemStyle.color).toBe(DIRECTION_HEX.market.down)
  })

  it('双套价格域语义：market 红涨绿跌 / report 绿涨红跌（不设默认值）', () => {
    const model = buildKlineModel(rows())!
    const market = buildKlineOption(model, 'market')
    const report = buildKlineOption(model, 'report')
    const candleOf = (o: ReturnType<typeof buildKlineOption>) => {
      const series = o.series as unknown as Array<{ name?: string; itemStyle?: { color?: string } }>
      return series.find((s) => s.name === 'K线')!.itemStyle!
    }
    expect(candleOf(market).color).toBe(CHART.up)
    expect(candleOf(report).color).toBe(CHART.docUp)
    expect(CHART.docUp).not.toBe(CHART.up)
  })

  it('rows 为空 → 诚实空态，不画空图表', () => {
    render(<KLineChart rows={[]} priceDomain="market" />)
    expect(screen.getByText('K 线图暂无数据可绘制')).toBeTruthy()
    expect(screen.getByText('rows 为空数组，未做补零或日期兜底')).toBeTruthy()
  })
})
