import { describe, it, expect } from 'vitest'
import { ConstructionDiagSchema } from '@/features/p1/constructionDiag'
import {
  buildEquityOption,
  buildDecayOption,
  buildRfSweepOption,
} from '@/features/p1/ConstructionDiagnostics'
import raw from '@/features/p1/data/constructionDiag.json'
import { CHART } from '@/shared/charts/palette'

/** 极简 option 形状（只断言本页关心字段，避免耦合 ECharts 完整类型）。 */
interface SeriesLike {
  type?: string
  data?: unknown[]
  lineStyle?: { color?: string }
  markArea?: { data?: unknown[] }
}
interface OptionLike {
  series?: SeriesLike[]
}

describe('P1 组合构建诊断 · 载荷与图表', () => {
  const data = ConstructionDiagSchema.parse(raw as unknown)

  it('随包 JSON 通过 schema 校验，且曲线等长', () => {
    expect(data.headline.rf).toBe(10)
    expect(data.headline.buffer).toBe(0)
    expect(data.curves.long_only_net).toHaveLength(data.curves.dates.length)
    expect(data.curves.long_short_net).toHaveLength(data.curves.dates.length)
    expect(data.curves.benchmark_gross).toHaveLength(data.curves.dates.length)
    expect(data.alpha_decay).toHaveLength(4)
    expect(data.rf_sweep).toHaveLength(3)
  })

  it('净值曲线 option：三轮 line + 2026 markArea，首轮用交易屏涨色', () => {
    const opt = buildEquityOption(data) as unknown as OptionLike
    expect(opt.series).toHaveLength(3)
    expect(opt.series![0].type).toBe('line')
    const markData = opt.series![0].markArea?.data as unknown[]
    expect(markData).toBeDefined()
    expect((markData[0] as unknown[])).toHaveLength(2) // 单条 2026 区带：[起点, 终点]
    expect(opt.series![0].lineStyle?.color).toBe(CHART.up) // 纯多头 net 涨=红
    expect(opt.series![2].lineStyle?.color).toBe(CHART.ink3) // 基准 gross 中性灰虚线
  })

  it('alpha 衰减 option：4 根 bar', () => {
    const opt = buildDecayOption(data) as unknown as OptionLike
    expect(opt.series![0].type).toBe('bar')
    expect(opt.series![0].data).toHaveLength(4)
  })

  it('rf 扫描 option：3 根 bar，按正负着色（rf=20 为负→跌色绿）', () => {
    const opt = buildRfSweepOption(data) as unknown as OptionLike
    const bars = opt.series![0].data as Array<{ itemStyle: { color: string } }>
    expect(bars).toHaveLength(3)
    expect(bars[1].itemStyle.color).toBe(CHART.down) // rf=20 净收益为负 → 跌色
    expect(bars[0].itemStyle.color).toBe(CHART.up) // rf=10 净收益为正 → 涨色
  })
})
