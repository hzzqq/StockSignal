import type { EChartsOption } from 'echarts'
import { EChart } from './EChart'
import { CHART } from './palette'

interface PositionGaugeProps {
  pct: number | null
  color?: string | null
}

/**
 * 仓位建议仪表盘（0–100%）。颜色取决策闭环下发的 pos.color，缺失回退涨色。
 *
 * 诚实红线：pct 缺失或非有限数时**不画指针、不显示 0%**，只给「—」空态。
 * 旧实现 `const value = pct ?? 0` 会在快照不含 position 时伪造出
 * 「系统建议空仓 0%」的确定性结论，属把「无数据」当成「数值为 0」。
 */
export function PositionGauge({ pct, color }: PositionGaugeProps) {
  if (typeof pct !== 'number' || !Number.isFinite(pct)) {
    return (
      <div
        role="status"
        aria-label="暂无仓位建议数据"
        className="flex items-center justify-center text-kpi font-semibold text-sf-ink-3"
        style={{ height: 180 }}
      >
        —
      </div>
    )
  }

  const value = Math.max(0, Math.min(100, pct))
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
