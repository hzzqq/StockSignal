import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 历史业绩趋势图（基本面分析页 /stock/fundamentals）。
 *
 * 数据源：/financials rows（中文动态列名 list[dict]，后端按报告期**倒序**返回）。
 * - 柱 = metric 值（亿元，主轴）；线 = `${metric}_同比`（%，副轴 yAxisIndex:1）。
 *   「_同比」由后端 _compute_yoy 计算的真实同比，tooltip/图例直接写「同比%」。
 * - 诚实红线：metric 缺失（null/undefined/NaN）的报告期**整期剔除**，不画柱不画点、
 *   不补 0；同比缺失的报告期只断线（null，connectNulls=false），同样不补零。
 * - 同比线颜色按正负：正 = CHART.up 红、负/零 = CHART.down 绿（本页为 A 股行情屏语义，
 *   与 KLineChart 的涨跌色一致）；柱体统一 accent 弱色，不抢线。
 * - 报告期数较多时用 dataZoom（inside + slider）拖拽查看长期。
 */

export type FinancialRow = Record<string, unknown>

export interface FinancialTrendChartProps {
  /** /financials rows（后端倒序原样传入，组件内部正序化）。 */
  rows: FinancialRow[]
  /** 图表主指标（柱）的中文列名，默认「营业总收入」。 */
  metric?: string
  height?: number
}

/** 仅认真实数值：null / undefined / NaN / 非数值一律视为缺失。 */
function isFiniteNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/** rows 中是否存在 key 列的至少一个有限数值（用于诚实降级判断）。 */
export function hasFinite(rows: FinancialRow[], key: string): boolean {
  return rows.some((r) => isFiniteNum(r[key]))
}

/**
 * 构建趋势图 option 的纯函数（便于单测）。
 * - 输入 rows 按报告期倒序原样传入，内部按「报告期」字符串升序排列（旧 → 新）。
 * - metric 缺失的报告期整期不进 X 轴 / series（null 期不进 series，绝不补 0）。
 * - 有至少一个同比数值时才输出副轴与同比线（两个同名「同比%」series 按正负分色，
 *   图例按名去重只出现一项）；全程无同比则只输出柱，不虚构副轴。
 */
export function buildFinancialTrendOption(rows: FinancialRow[], metric: string): EChartsOption {
  const sorted = [...rows].sort((a, b) =>
    String(a['报告期'] ?? '').localeCompare(String(b['报告期'] ?? '')),
  )
  // 缺失期整期剔除：不画柱不画点，不补 0。
  const kept = sorted.filter((r) => isFiniteNum(r[metric]))
  const periods = kept.map((r) => String(r['报告期'] ?? ''))
  const values = kept.map((r) => r[metric] as number)
  const yoy = kept.map((r) =>
    isFiniteNum(r[`${metric}_同比`]) ? (r[`${metric}_同比`] as number) : null,
  )
  const hasYoy = yoy.some((v) => v !== null)

  const series: Array<Record<string, unknown>> = [
    {
      name: metric,
      type: 'bar',
      data: values,
      barMaxWidth: 28,
      itemStyle: { color: CHART.accent, opacity: 0.55 },
    },
  ]

  const yAxis: Array<Record<string, unknown>> = [
    {
      type: 'value',
      name: `${metric}(亿元)`,
      scale: true,
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
  ]
  if (hasYoy) {
    yAxis.push({
      type: 'value',
      name: '同比%',
      position: 'right',
      scale: true,
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2, formatter: '{value}%' },
      splitLine: { show: false },
    })
    // 同比按正负拆成两条同名 series（图例按名合并为一项），正红负绿。
    series.push({
      name: '同比%',
      type: 'line',
      yAxisIndex: 1,
      data: yoy.map((v) => (v !== null && v > 0 ? v : null)),
      symbolSize: 6,
      connectNulls: false,
      itemStyle: { color: CHART.up },
      lineStyle: { color: CHART.up, width: 1.6 },
    })
    series.push({
      name: '同比%',
      type: 'line',
      yAxisIndex: 1,
      data: yoy.map((v) => (v !== null && v <= 0 ? v : null)),
      symbolSize: 6,
      connectNulls: false,
      itemStyle: { color: CHART.down },
      lineStyle: { color: CHART.down, width: 1.6 },
    })
  }

  return {
    tooltip: { trigger: 'axis' },
    legend: {
      data: hasYoy ? [metric, '同比%'] : [metric],
      top: 0,
      itemGap: 12,
      textStyle: { color: CHART.ink2 },
    },
    grid: { left: 56, right: 56, top: 32, bottom: 48 },
    xAxis: {
      type: 'category',
      data: periods,
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis,
    dataZoom: [
      { type: 'inside' },
      { type: 'slider', bottom: 6, height: 18 },
    ],
    series,
  } as EChartsOption
}

/** 历史业绩趋势图：柱（指标值，亿元主轴）+ 折线（同比%，副轴），缺失期不绘制。 */
export function FinancialTrendChart({
  rows,
  metric = '营业总收入',
  height = 280,
}: FinancialTrendChartProps) {
  const option = useMemo(() => buildFinancialTrendOption(rows, metric), [rows, metric])
  return (
    <EChart
      option={option}
      height={height}
      className="w-full"
      ariaLabel={`历史${metric}柱状图与同比折线，X 轴为报告期，缺失期不绘制`}
    />
  )
}
