import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { Stat } from '@/shared/ui/Stat'
import { EmptyState } from '@/shared/ui/States'
import { DIRECTION_HEX, DIRECTION_INK, type PriceDomain } from './common'
import { intradayAvg, parseIntradayRows } from './klineMath'

/**
 * 个股分时图：价格线 + 均价线 + 昨收基准虚线 + 成交量副图。
 *
 * 视觉口径对齐 v1 modules/visualizer_kline.py::intraday（价格线按相对昨收的涨跌着色、
 * 均价线琥珀虚线、基准虚线中性灰、成交量柱按涨跌着色）。
 *
 * 诚实红线：
 *  - **昨收基准取不到就不画基准线**，并如实标注「暂无昨收基准」；此时价格线/成交量柱
 *    用中性色（不臆断涨跌方向），绝不拿当日首笔开盘或现价冒充昨收；
 *  - 均价 = 累计成交额 / 累计成交量；累计成交量为 0 → null（断线），不拿收盘价冒充；
 *  - rows 为空 → 空态，不画空图表；
 *  - 图下方同卡片给出 Stat（最新价 / 均价 / 昨收 / 较昨收），图形不是关键数值的唯一载体。
 */
export interface IntradayChartProps {
  /** /api/v2/read/stock-intraday 的 rows（通用透传，列名英文）。 */
  rows: Record<string, unknown>[]
  /** 昨收基准价：null/undefined/非有限 → 不画基准线并如实标注。 */
  prevClose?: number | null
  /** 页面级价格域：market=交易屏（红涨绿跌），report=报告体/个股页（绿涨红跌）。 */
  priceDomain: PriceDomain
  height?: number
}

export function IntradayChart({ rows, prevClose, priceDomain, height = 340 }: IntradayChartProps) {
  const model = useMemo(() => buildIntradayModel(rows), [rows])
  const base = typeof prevClose === 'number' && Number.isFinite(prevClose) ? prevClose : null

  if (model === null) {
    return (
      <EmptyState label="分时图暂无数据可绘制" hint="rows 为空数组，未做补零或日期兜底" />
    )
  }

  const option = buildIntradayOption(model, base, priceDomain)
  const last = model.points.length - 1
  const lastPoint = model.points[last]
  const ink = DIRECTION_INK[priceDomain]
  const dir = DIRECTION_HEX[priceDomain]
  const lastClose = lastPoint.close
  const chg = base !== null && lastClose !== null ? lastClose - base : null
  const chgPct = chg !== null && base !== null && base !== 0 ? (chg / base) * 100 : null
  const upTone = chg === null ? undefined : chg >= 0 ? ink.up : ink.down

  return (
    <div>
      {base === null && (
        <p role="status" className="text-body text-sf-warn mb-2">
          暂无昨收基准
          <span className="text-sf-ink-3">
            （昨收价未取到，未绘制基准线，涨跌方向不作推断）
          </span>
        </p>
      )}
      <EChart
        option={option}
        height={height}
        ariaLabel="个股分时图：价格线与均价线，叠加昨收基准虚线与成交量副图；关键数值见下方指标卡与分时数据表"
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        <Stat label="最新价" value={fmt(lastClose)} color={upTone} sub={lastPoint.label} />
        <Stat label="均价" value={fmt(model.avg[last])} />
        <Stat label="昨收基准" value={base === null ? '暂无' : fmt(base)} />
        <Stat
          label="较昨收"
          value={chg === null ? '暂无' : `${chg.toFixed(2)}（${chgPct === null ? '--' : `${chgPct.toFixed(2)}%`}）`}
          color={upTone}
        />
      </div>
      {/* 涨跌方向的等价数据表：图形不是关键数值的唯一载体（无障碍）。 */}
      <div className="overflow-x-auto mt-3">
        <table className="w-full text-body border-collapse">
          <caption className="sr-only">分时等价数据表：时间、价格、均价、成交量</caption>
          <thead>
            <tr className="text-label text-sf-ink-3 border-b border-sf-line">
              <th scope="col" className="text-left py-2 pr-3 font-normal">时间</th>
              <th scope="col" className="text-left py-2 pr-3 font-normal">价格</th>
              <th scope="col" className="text-left py-2 pr-3 font-normal">均价</th>
              <th scope="col" className="text-left py-2 pr-3 font-normal">成交量</th>
            </tr>
          </thead>
          <tbody className="text-sf-ink-2">
            {model.points.map((p, i) => (
              <tr key={`${p.time}-${i}`} className="border-b border-sf-line last:border-0">
                <td className="py-1.5 pr-3 tabular-nums">{p.label}</td>
                <td className="py-1.5 pr-3 tabular-nums">{fmt(p.close)}</td>
                <td className="py-1.5 pr-3 tabular-nums">{fmt(model.avg[i])}</td>
                <td className="py-1.5 pr-3 tabular-nums">
                  {p.volume === null ? '—' : p.volume.toLocaleString('zh-CN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* 图表用色与页面语义一致：报告体口径下涨=绿（doc-up）、跌=红（doc-down）。 */}
      <span className="sr-only">
        {`涨跌方向配色：涨 ${dir.up}、跌 ${dir.down}`}
      </span>
    </div>
  )
}

/** 分时计算结果（供 option 构造与 Stat/数据表复用）。 */
export interface IntradayModel {
  points: ReturnType<typeof parseIntradayRows>
  avg: (number | null)[]
}

/** 解析 rows 并算出均价；无可绘制数据时返回 null。 */
export function buildIntradayModel(rows: Record<string, unknown>[]): IntradayModel | null {
  const points = parseIntradayRows(rows)
  if (points.length === 0) return null
  return { points, avg: intradayAvg(points) }
}

/**
 * 构造分时 option。prevClose 为 null → 不画昨收基准线（诚实降级）。
 * 导出以便单测直接断言「有/无基准线」与 series 结构。
 */
export function buildIntradayOption(
  model: IntradayModel,
  prevClose: number | null,
  priceDomain: PriceDomain,
): EChartsOption {
  const { points, avg } = model
  const dir = DIRECTION_HEX[priceDomain]
  const hasBase = prevClose !== null && Number.isFinite(prevClose)
  // 无昨收基准 → 方向不可判定，价格线/成交量柱用中性色（不臆断涨跌）。
  const lineColor = hasBase ? dir.up : CHART.accent
  const volumeColor = (close: number | null) => {
    if (!hasBase || close === null) return CHART.ink3
    return close >= (prevClose as number) ? dir.up : dir.down
  }

  const labels = points.map((p) => p.label)
  const closes = points.map((p) => p.close)

  // 价格轴围绕昨收上下留白（基准线始终在可视区内）；无基准时按当日区间。
  const known = closes.filter((c): c is number => c !== null)
  const baseList = hasBase ? [...known, prevClose as number] : known
  const lo = baseList.length ? Math.min(...baseList) : 0
  const hi = baseList.length ? Math.max(...baseList) : 0
  const pad = (hi - lo) * 0.08 || hi * 0.01 || 1

  return {
    backgroundColor: 'transparent',
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const idx = typeof list[0]?.dataIndex === 'number' ? list[0].dataIndex : -1
        if (idx < 0 || idx >= points.length) return ''
        const p = points[idx]
        const chg = hasBase && p.close !== null ? p.close - (prevClose as number) : null
        const chgPct = chg !== null && (prevClose as number) !== 0 ? (chg / (prevClose as number)) * 100 : null
        return [
          `<b>${p.label}</b>`,
          `价格 ${fmt(p.close)}`,
          `均价 ${fmt(avg[idx])}`,
          hasBase
            ? `较昨收 ${chg === null ? '--' : chg.toFixed(2)}（${chgPct === null ? '--' : `${chgPct.toFixed(2)}%`}）`
            : '较昨收 --（暂无昨收基准）',
          `成交量 ${p.volume === null ? '--' : p.volume.toLocaleString('zh-CN')}`,
        ].join('<br/>')
      },
    },
    legend: {
      data: ['价格', '均价', '成交量'],
      top: 0,
      itemGap: 12,
      textStyle: { color: CHART.ink2 },
    },
    grid: [
      { left: 56, right: 24, top: 36, height: '54%' },
      { left: 56, right: 24, top: '70%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: labels, gridIndex: 0, axisLabel: { color: CHART.ink3, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
      { type: 'category', data: labels, gridIndex: 1, axisLabel: { show: false }, axisLine: { lineStyle: { color: CHART.line } } },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        scale: true,
        min: lo - pad,
        max: hi + pad,
        axisLabel: { color: CHART.ink3 },
        splitLine: { lineStyle: { color: CHART.grid } },
      },
      { type: 'value', gridIndex: 1, scale: true, axisLabel: { color: CHART.ink3 }, splitLine: { show: false } },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }],
    series: [
      {
        name: '价格',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: closes,
        showSymbol: false,
        lineStyle: { width: 1.6, color: lineColor },
        areaStyle: { color: lineColor, opacity: 0.12 },
        markLine: hasBase
          ? {
              silent: true,
              symbol: 'none',
              data: [{ yAxis: prevClose }],
              lineStyle: { color: CHART.ink3, type: 'dashed', width: 1 },
              label: { show: true, formatter: '昨收', color: CHART.ink3, position: 'insideEndTop' },
            }
          : undefined,
      },
      {
        name: '均价',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: avg,
        showSymbol: false,
        lineStyle: { width: 1.2, color: CHART.warn, type: 'dashed' },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: points.map((p) => ({
          value: p.volume,
          itemStyle: { color: volumeColor(p.close) },
        })),
      },
    ],
  }
}

/** 数值格式化：null/undefined/NaN → '--'（绝不补 0）。 */
function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}
