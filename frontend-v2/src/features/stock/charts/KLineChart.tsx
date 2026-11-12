import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { Stat } from '@/shared/ui/Stat'
import { EmptyState } from '@/shared/ui/States'
import { DIRECTION_HEX, DIRECTION_INK, type PriceDomain } from './common'
import { macdSeries, parseKlineRows, rollingMean } from './klineMath'

/**
 * 个股 K 线图：蜡烛 + MA5/10/20 + 成交量副图 + MACD 副图 + dataZoom。
 *
 * 视觉口径（v1 modules/visualizer_kline.py 同源三格布局）：
 *   主图 / 成交量副图 / MACD 副图，dataZoom = inside + slider。
 *
 * 诚实红线：
 *  - MA / MACD 前若干根样本不足 → null，ECharts 断线（不补 0、不跨缺口连值）；
 *  - rows 里缺 open/high/low/close 的行不画蜡烛（置 null），绝不补 0；
 *  - 缺 OHLC 时方向未知：成交量柱走中性色、「最新收盘」不着涨跌色，绝不臆断涨/跌；
 *  - 数据为空 → 空态，不画空图表；
 *  - 图下方同卡片给出 Stat（最新收盘 / MA / MACD），图形不是关键数值的唯一载体。
 *
 * 涨跌色：按 priceDomain 注入（DESIGN.md §3/§6.2「K线阴阳线：按 priceDomain 注入，
 * 报告体页面不得沿用交易屏红涨绿跌」）；调用点必须显式传 priceDomain，不设默认值。
 */
export interface KLineChartProps {
  /** /api/v2/read/stock-kline 的 rows（通用透传，列名英文）。 */
  rows: Record<string, unknown>[]
  /** 页面级价格域：market=交易屏（红涨绿跌），report=报告体/个股页（绿涨红跌）。 */
  priceDomain: PriceDomain
  height?: number
}

export function KLineChart({ rows, priceDomain, height = 520 }: KLineChartProps) {
  const model = useMemo(() => buildKlineModel(rows), [rows])

  if (model === null) {
    return <EmptyState label="K 线图暂无数据可绘制" hint="rows 为空数组，未做补零或日期兜底" />
  }

  const option = buildKlineOption(model, priceDomain)
  const last = model.bars.length - 1
  const ink = DIRECTION_INK[priceDomain]
  const lastBar = model.bars[last]
  // OHLC 缺失时无法确定涨跌；lastUp=null 表示「方向未知」，不得按 false 落到跌色。
  const { close: lastClose, open: lastOpen } = lastBar
  const lastUp = lastClose !== null && lastOpen !== null ? lastClose >= lastOpen : null

  return (
    <div>
      <EChart
        option={option}
        height={height}
        ariaLabel="个股 K 线图：蜡烛与 MA5/MA10/MA20 均线、成交量副图与 MACD 副图，可拖拽缩放；关键数值见下方指标卡与 K 线数据表"
      />
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
        <Stat
          label="最新收盘"
          value={fmt(lastBar.close)}
          color={lastUp === null ? undefined : lastUp ? ink.up : ink.down}
          sub={lastBar.date}
        />
        <Stat label="MA5" value={fmt(model.ma.ma5[last])} />
        <Stat label="MA10" value={fmt(model.ma.ma10[last])} />
        <Stat label="MA20" value={fmt(model.ma.ma20[last])} />
        <Stat label="MACD" value={fmt(model.macd.hist[last], 4)} />
      </div>
    </div>
  )
}

/** K 线计算结果（供 option 构造与 Stat 复用）。 */
export interface KlineModel {
  bars: ReturnType<typeof parseKlineRows>
  ma: { ma5: (number | null)[]; ma10: (number | null)[]; ma20: (number | null)[] }
  macd: ReturnType<typeof macdSeries>
}

/** 解析 rows 并算出 MA / MACD；无可绘制数据时返回 null。 */
export function buildKlineModel(rows: Record<string, unknown>[]): KlineModel | null {
  const bars = parseKlineRows(rows)
  if (bars.length === 0) return null
  const closes = bars.map((b) => b.close)
  return {
    bars,
    ma: {
      ma5: rollingMean(closes, 5),
      ma10: rollingMean(closes, 10),
      ma20: rollingMean(closes, 20),
    },
    macd: macdSeries(closes),
  }
}

/**
 * 构造 K 线 option。导出以便单测直接断言 series / grid / dataZoom 结构。
 */
export function buildKlineOption(model: KlineModel, priceDomain: PriceDomain): EChartsOption {
  const { bars, ma, macd } = model
  const dir = DIRECTION_HEX[priceDomain]
  const dates = bars.map((b) => b.date)

  const candleData = bars.map((b) =>
    b.open === null || b.close === null || b.low === null || b.high === null
      ? null
      : [b.open, b.close, b.low, b.high],
  )
  // 成交量柱按当根阴阳染色；但 OHLC 缺失时「方向未知」，用中性色而非默认涨色
  // （与 IntradayChart.volumeColor 同口径：无基准/无收盘 → CHART.ink3）。
  const volumeData = bars.map((b) => {
    if (b.volume === null) return null
    const { open, close } = b
    return {
      value: b.volume,
      itemStyle: {
        color:
          open !== null && close !== null
            ? close < open
              ? dir.down
              : dir.up
            : CHART.ink3,
      },
    }
  })
  const macdData = macd.hist.map((v) =>
    v === null ? null : { value: v, itemStyle: { color: v >= 0 ? dir.up : dir.down } },
  )

  // 数据量大时初始聚焦最近 120 根（其余靠滑块/滚轮查看；全量已加载）。
  const zoomStart = bars.length > 120 ? Math.round((1 - 120 / bars.length) * 100) : 0

  return {
    backgroundColor: 'transparent',
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const idx = typeof list[0]?.dataIndex === 'number' ? list[0].dataIndex : -1
        if (idx < 0 || idx >= bars.length) return ''
        const b = bars[idx]
        const chg = b.close !== null && b.open !== null ? b.close - b.open : null
        const chgPct = chg !== null && b.open ? (chg / b.open) * 100 : null
        return [
          `<b>${b.date}</b>`,
          `开 ${fmt(b.open)}　高 ${fmt(b.high)}`,
          `低 ${fmt(b.low)}　收 ${fmt(b.close)}`,
          `涨跌 ${chg === null ? '--' : chg.toFixed(2)}（${chgPct === null ? '--' : `${chgPct.toFixed(2)}%`}）`,
          `成交量 ${b.volume === null ? '--' : b.volume.toLocaleString('zh-CN')}`,
          `MA5 ${fmt(ma.ma5[idx])}　MA10 ${fmt(ma.ma10[idx])}　MA20 ${fmt(ma.ma20[idx])}`,
          `DIF ${fmt(macd.dif[idx], 4)}　DEA ${fmt(macd.dea[idx], 4)}　MACD ${fmt(macd.hist[idx], 4)}`,
        ].join('<br/>')
      },
    },
    legend: {
      data: ['K线', 'MA5', 'MA10', 'MA20', '成交量', 'DIF', 'DEA', 'MACD'],
      top: 0,
      itemGap: 12,
      textStyle: { color: CHART.ink2 },
    },
    grid: [
      { left: 56, right: 24, top: 40, height: '30%' },
      { left: 56, right: 24, top: '44%', height: '11%' },
      { left: 56, right: 24, top: '60%', height: '13%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: CHART.line } } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false }, axisLine: { lineStyle: { color: CHART.line } } },
      { type: 'category', data: dates, gridIndex: 2, axisLabel: { color: CHART.ink3, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, scale: true, axisLabel: { color: CHART.ink3 }, splitLine: { lineStyle: { color: CHART.grid } } },
      { type: 'value', gridIndex: 1, scale: true, axisLabel: { color: CHART.ink3 }, splitLine: { show: false } },
      { type: 'value', gridIndex: 2, scale: true, axisLabel: { color: CHART.ink3 }, splitLine: { lineStyle: { color: CHART.grid } } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], start: zoomStart, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2], start: zoomStart, end: 100, bottom: 6, height: 18 },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: candleData,
        itemStyle: {
          color: dir.up,
          color0: dir.down,
          borderColor: dir.up,
          borderColor0: dir.down,
        },
      },
      { name: 'MA5', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: ma.ma5, showSymbol: false, lineStyle: { width: 1.4, color: CHART.warn } },
      { name: 'MA10', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: ma.ma10, showSymbol: false, lineStyle: { width: 1.3, color: CHART.accent } },
      { name: 'MA20', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: ma.ma20, showSymbol: false, lineStyle: { width: 1.2, color: CHART.ok } },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumeData },
      { name: 'DIF', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: macd.dif, showSymbol: false, lineStyle: { width: 1.4, color: CHART.ink2 } },
      { name: 'DEA', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: macd.dea, showSymbol: false, lineStyle: { width: 1.2, color: CHART.ink2, type: 'dashed' } },
      { name: 'MACD', type: 'bar', xAxisIndex: 2, yAxisIndex: 2, data: macdData },
    ],
  } as EChartsOption
}

/** 数值格式化：null/undefined/NaN → '--'（绝不补 0）。 */
function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}
