import type { LadderDay } from '@/api/schemas/read'
import type { EChartsOption } from 'echarts'
import { useLadderDetail } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'

/**
 * W3 连板梯队共振页（对应 IA-MIGRATION.md §4 W3，页面号约 58）。
 * 数据来源：getLadderDetail（/api/v2/read/ladder-detail，读 data/shepherd_ladder_history.json）。
 * 渲染：① 最高板 / 连板总数随时间趋势；② 最新一日板位分布条形（高板红/低板绿）。
 * 缺失字段诚实留空，不编造。
 */

export function LadderResonance() {
  const ladder = useLadderDetail()
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">连板梯队共振</h2>
        <span className="text-label text-sf-ink-3">数据源 shepherd_ladder_history</span>
        <a
          href="/breadth"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          ← 返回广度总览
        </a>
      </div>

      <QueryState
        isLoading={ladder.isLoading}
        isError={ladder.isError}
        error={ladder.error}
        isEmpty={!!ladder.data && ladder.data.length === 0}
      >
        {ladder.data ? <LadderBody history={ladder.data} /> : null}
      </QueryState>
    </div>
  )
}

function LadderBody({ history }: { history: LadderDay[] }) {
  const latest = history[history.length - 1]
  const dates = history.map((d) => d.date)
  const maxBoards = history.map((d) => (typeof d.max_boards === 'number' ? d.max_boards : null))
  const totalConnect = history.map((d) => (typeof d.total_connect === 'number' ? d.total_connect : null))

  const trendOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['最高板', '连板总数'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 40, right: 16, top: 28, bottom: 48 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        name: '最高板',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: maxBoards,
        itemStyle: { color: CHART.up },
        lineStyle: { color: CHART.up, width: 1.5 },
      },
      {
        name: '连板总数',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: totalConnect,
        itemStyle: { color: CHART.down },
        lineStyle: { color: CHART.down, width: 1.5 },
      },
    ],
  }

  const dist = latest?.distribution ?? {}
  const boards = Object.keys(dist)
    .map((k) => Number(k))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => b - a)
  const maxBoard = boards[0] ?? 0

  const distOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    grid: { left: 40, right: 16, top: 10, bottom: 24 },
    xAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'category',
      data: boards.map((b) => `${b} 板`),
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        data: boards.map((b) => ({
          value: dist[String(b)] ?? 0,
          itemStyle: {
            color:
              maxBoard > 0
                ? b >= Math.ceil(maxBoard * 0.6)
                  ? CHART.up
                  : CHART.down
                : CHART.line,
          },
        })),
        label: { show: true, position: 'right', color: CHART.ink2 },
      },
    ],
  }

  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="最新数据日" value={latest?.date ?? '—'} />
        <Stat label="最高板" value={fmtNum(latest?.max_boards)} />
        <Stat label="连板总数" value={fmtNum(latest?.total_connect)} />
        <Stat label="历史样本" value={fmtNum(history.length)} sub="交易日" />
      </div>

      <Card title="连板强度趋势（最高板 / 连板总数）">
        <EChart option={trendOption} height={260} ariaLabel="连板强度趋势折线图：逐日最高板与连板总数" />
      </Card>

      <Card title="最新板位分布">
        <EChart option={distOption} height={Math.max(160, boards.length * 26)} ariaLabel="最新交易日板位分布条形图，高板位红色、低板位绿色" />
        <div className="text-xs text-sf-ink-3 mt-1">
          红色=高板位（≥最高板的 60%），绿色=低板位；数据来自 data/shepherd_ladder_history.json
        </div>
      </Card>
    </div>
  )
}
