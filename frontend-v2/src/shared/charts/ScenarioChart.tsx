import type { EChartsOption } from 'echarts'
import { EChart } from './EChart'
import { CHART } from './palette'

export interface ScenarioItem {
  name?: string | null
  prob?: number | null
  color?: string | null
}

/** 情景概率横向条形图。颜色取各情景下发的 color，缺失回退边框色。 */
export function ScenarioChart({ items }: { items: ScenarioItem[] }) {
  const data = items.filter((i) => i.name != null)
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    grid: { left: 76, right: 36, top: 8, bottom: 8 },
    tooltip: { show: false },
    xAxis: { type: 'value', max: 100, show: false },
    yAxis: {
      type: 'category',
      data: data.map((d) => d.name ?? ''),
      axisLine: { lineStyle: { color: CHART.border } },
      axisTick: { show: false },
      axisLabel: { color: CHART.txt, fontSize: 12 },
    },
    series: [
      {
        type: 'bar',
        barWidth: 14,
        showBackground: true,
        backgroundStyle: { color: CHART.bg, borderRadius: 7 },
        data: data.map((d) => ({
          value: d.prob ?? 0,
          itemStyle: { color: d.color ?? CHART.border, borderRadius: [0, 7, 7, 0] },
        })),
        label: { show: true, position: 'right', color: CHART.txt, formatter: '{c}%' },
      },
    ],
  }
  return <EChart option={option} height={Math.max(120, data.length * 30)} />
}
