import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import { useBreadthAnalytics } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { Loading, ErrorState, EmptyState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { AnalyticsHeader, DataBoundary, SectionState, show, showNum, showPct } from './shared'

/** 与 v1 65 页侧栏及后端 _ANALYTICS_WINDOWS 一致；非法值后端直接 400，不静默兜底。 */
const WINDOWS = [60, 120, 250, 750, 2000] as const
const LINE_COLORS = [CHART.accent, CHART.warn, '#a855f7', CHART.ok, '#eab308']

/** 各序列按自身 min–max 归一化以便叠加；缺失送 null（ECharts 不画），绝不补 0。 */
function normalize(vals: (number | null)[]): (number | null)[] {
  const nums = vals.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (nums.length === 0) return vals.map(() => null)
  const lo = Math.min(...nums)
  const hi = Math.max(...nums)
  return vals.map((v) => {
    if (v === null || !Number.isFinite(v)) return null
    return lo === hi ? 0 : (v - lo) / (hi - lo)
  })
}

const SELECT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/**
 * 65 投机情绪周期时钟（v2 native /sentiment-clock）。
 * 数据源：GET /api/v2/read/breadth-analytics 的 phase 段（speculative_clock 纯模块）。
 * 与 v1 对齐：时间窗口可切、当前相位五档、5 维归一化时序、离线数据边界。
 */
export function SentimentClock() {
  const [window, setWindow] = useState<number>(250)
  const q = useBreadthAnalytics(window)
  const d = q.data
  const phase = d?.sections.phase
  const cur = phase?.current
  const ser = phase?.series

  const cols = Object.keys(ser?.series ?? {})
  const lineOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: cols.map((c) => ser?.labels?.[c] ?? c),
      textStyle: { color: CHART.ink2 },
      top: 0,
    },
    grid: { left: 48, right: 16, top: 32, bottom: 28 },
    xAxis: {
      type: 'category',
      data: ser?.dates ?? [],
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: cols.map((c, i) => ({
      name: ser?.labels?.[c] ?? c,
      type: 'line',
      showSymbol: false,
      data: normalize(ser?.series?.[c] ?? []),
      lineStyle: { color: LINE_COLORS[i % LINE_COLORS.length], width: 1.6 },
      itemStyle: { color: LINE_COLORS[i % LINE_COLORS.length] },
      connectNulls: false,
    })),
  }

  return (
    <div className="space-y-4">
      <AnalyticsHeader
        title="投机情绪周期时钟"
        caption="用涨停家数 + 红盘占比的历史分位识别投机情绪相位（亢奋 / 活跃 / 偏冷 / 冰点 / 中性）。纯离线、描述性框架。"
        data={d}
      />

      <Card>
        <label className="block text-xs text-sf-ink-2">
          时间窗口
          <select
            className={SELECT_CLS}
            value={window}
            onChange={(e) => setWindow(Number(e.target.value))}
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>
                近 {w} 日
              </option>
            ))}
          </select>
        </label>
        <p className="mt-2 text-xs text-sf-ink-3">
          本次响应窗口 {show(d?.window)} 交易日；时序实际返回 {show(ser?.dates?.length)} 个点。
        </p>
      </Card>

      {q.isLoading && <Loading label="加载离线广度统计…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '离线广度统计加载失败'} />
      )}
      {!q.isLoading && !q.isError && !d && <EmptyState label="暂无离线广度统计" />}

      {d && (
        <>
          <SectionState section={cur} label="当前相位">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="当前投机情绪相位" value={show(cur?.phase)} sub={`广度快照 ${show(cur?.date)}`} />
              <Stat label="红盘占比" value={showNum(cur?.red_ratio, 2, '%')} sub="离线可靠字段" />
              <Stat
                label="涨停家数"
                value={show(cur?.limit_up)}
                sub={`历史分位 ${showPct(cur?.limit_up_pct)}`}
              />
              <Stat label="跌停家数" value={show(cur?.limit_down)} sub="离线可靠字段" />
            </div>
            <Card title={`当前（${show(cur?.date)}）· ${show(cur?.phase)}`} className="mt-3">
              <p className="text-sm text-sf-ink-2">
                红盘占比 {showNum(cur?.red_ratio, 2, '%')} ｜ 涨停家数 {show(cur?.limit_up)}（历史分位{' '}
                {showPct(cur?.limit_up_pct)}）｜ 跌停家数 {show(cur?.limit_down)}
              </p>
              <p className="mt-1 text-xs text-sf-ink-3">{show(cur?.reason)}</p>
            </Card>
          </SectionState>

          <Card title="广度情绪时序（归一化叠加）">
            <SectionState section={ser} label="情绪时序">
              {ser?.dates?.length ? (
                <>
                  <EChart
                    option={lineOption}
                    height={380}
                    ariaLabel="广度情绪时序折线图：五个可靠维度各自归一化后叠加"
                  />
                  <p className="mt-1 text-xs text-sf-ink-3">
                    各线按自身区间归一化以便叠加对比走势；缺失点不绘制、不补零。仅描述历史周期，不构成方向预测。
                  </p>
                </>
              ) : (
                <EmptyState label="暂无足够广度历史生成时序图" />
              )}
            </SectionState>
          </Card>

          <DataBoundary
            data={d}
            method="相位判定基于红盘占比 + 涨停家数的历史分位（亢奋 ≥60% 且涨停家数前 20% / 活跃 ≥60% / 冰点 <30% 且涨停家数后 20% / 偏冷 <40% / 否则中性），用于描述投机情绪所处阶段。"
          />
        </>
      )}
    </div>
  )
}
