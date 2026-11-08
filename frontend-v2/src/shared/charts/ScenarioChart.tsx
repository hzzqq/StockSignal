import type { EChartsOption } from 'echarts'
import { EChart } from './EChart'
import { CHART } from './palette'

export interface ScenarioItem {
  name?: string | null
  prob?: number | null
  color?: string | null
}

/** 情景概率横向条形图。颜色取各情景下发的 color，缺失回退边框色。 */
export function buildScenarioOption(items: ScenarioItem[]): EChartsOption {
  // 诚实红线：prob 缺失 → null（ECharts 不画柱、不显示 0%），绝不补 0。
  const data = items.filter((i) => i.name != null)
  return {
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
          value: typeof d.prob === 'number' && Number.isFinite(d.prob) ? d.prob : null,
          itemStyle: { color: d.color ?? CHART.border, borderRadius: [0, 7, 7, 0] },
        })),
        label: { show: true, position: 'right', color: CHART.txt, formatter: '{c}%' },
      },
    ],
  }
}

export function ScenarioChart({ items }: { items: ScenarioItem[] }) {
  const option = buildScenarioOption(items)
  const missing = items.filter((i) => i.name != null && !(typeof i.prob === 'number' && Number.isFinite(i.prob))).length
  return (
    <>
      <EChart
        option={option}
        height={Math.max(120, items.filter((i) => i.name != null).length * 30)}
        ariaLabel={`情景概率条形图${missing > 0 ? `，其中 ${missing} 个情景概率缺失（不画柱、不显示 0%）` : ''}`}
      />
      {missing > 0 && (
        <p className="text-label text-sf-ink-3">
          {missing} 个情景未提供概率值，已留空（显示「—」语义），不按 0% 计算。
        </p>
      )}
    </>
  )
}
