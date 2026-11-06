import type { EChartsOption } from 'echarts'
import { EChart } from './EChart'
import { CHART } from './palette'

interface PositionGaugeProps {
  pct: number | null
  color?: string | null
}

/** 仓位建议仪表盘（0–100%）。颜色取决策闭环下发的 pos.color，缺失回退涨色。 */
export function PositionGauge({ pct, color }: PositionGaugeProps) {
  const value = pct ?? 0
  const accent = color ?? CHART.up
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        radius: '92%',
        center: ['50%', '58%'],
        progress: { show: true, width: 10, itemStyle: { color: accent } },
        axisLine: { lineStyle: { width: 10, color: [[1, CHART.border]] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { length: '58%', width: 4, itemStyle: { color: accent } },
        anchor: { show: true, size: 8, itemStyle: { color: accent } },
        detail: {
          valueAnimation: true,
          formatter: (v: number) => `${v.toFixed(0)}%`,
          color: CHART.txt,
          fontSize: 22,
          offsetCenter: [0, '42%'],
        },
        title: { show: false },
        data: [{ value }],
      },
    ],
  }
  return <EChart option={option} height={180} />
}
