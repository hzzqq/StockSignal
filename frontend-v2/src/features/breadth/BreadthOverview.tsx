import type { DailySnapshot, BreadthPoint, LadderDay } from '@/api/schemas/read'
import type { EChartsOption } from 'echarts'
import { useDailySnapshot, useBreadthTimeseries, useLadderDetail } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { FreshnessBadge } from '@/shared/ui/FreshnessBadge'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { ScenarioChart } from '@/shared/charts/ScenarioChart'
import { CHART } from '@/shared/charts/palette'
import {
  freshnessLevelFromAge,
  freshnessFromStatus,
  type FreshnessLevel,
} from '@/lib/freshness'
import { fmtNum } from '@/lib/format'

/**
 * W3 广度·温度首簇落地页（对应 IA-MIGRATION.md §4 W3）。
 * 数据来源：
 *  - getDailySnapshot（12 只读端点之一）：温度/红盘比/连板摘要/情景/事件因子
 *  - getBreadthTimeseries（新增）：snapshots 聚合的广度时序
 *  - getLadderDetail（新增）：shepherd_ladder_history 连板梯队明细
 * 缺失字段诚实留空，不编造。
 */

function num(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export function BreadthOverview() {
  const daily = useDailySnapshot()
  const breadth = useBreadthTimeseries()
  const ladder = useLadderDetail()

  return (
    <div className="space-y-4">
      <QueryState
        isLoading={daily.isLoading}
        isError={daily.isError}
        error={daily.error}
      >
        {daily.data ? <BreadthBody snapshot={daily.data} /> : null}
      </QueryState>

      <Card title="广度时序（涨跌家数 · 近期）">
        <QueryState
          isLoading={breadth.isLoading}
          isError={breadth.isError}
          error={breadth.error}
          isEmpty={!!breadth.data && breadth.data.length === 0}
        >
          {breadth.data ? <BreadthTrend series={breadth.data} /> : null}
        </QueryState>
      </Card>

      <Card title="连板梯队明细">
        <QueryState
          isLoading={ladder.isLoading}
          isError={ladder.isError}
          error={ladder.error}
          isEmpty={!!ladder.data && ladder.data.length === 0}
        >
          {ladder.data ? <LadderDetailView history={ladder.data} /> : null}
        </QueryState>
      </Card>
    </div>
  )
}

function BreadthBody({ snapshot }: { snapshot: DailySnapshot }) {
  const ind = snapshot.indicators ?? {}
  const level: FreshnessLevel =
    typeof snapshot.data_age_days === 'number'
      ? freshnessLevelFromAge(snapshot.data_age_days)
      : freshnessFromStatus(snapshot.data_freshness?.status)

  const breadthOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: ['上涨', '下跌', '涨停', '跌停'],
      axisLabel: { color: CHART.txt },
      axisLine: { lineStyle: { color: CHART.border } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.txt },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        type: 'bar',
        barWidth: '52%',
        data: [
          { value: Number(ind.up_count ?? 0), itemStyle: { color: CHART.up } },
          { value: Number(ind.down_count ?? 0), itemStyle: { color: CHART.down } },
          { value: Number(ind.limit_up ?? 0), itemStyle: { color: CHART.up } },
          { value: Number(ind.limit_down ?? 0), itemStyle: { color: CHART.down } },
        ],
      },
    ],
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">市场广度·温度总览</h2>
        <FreshnessBadge level={level} />
        <span className="text-xs text-sf-txt/50">权威数据日 {snapshot.date}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="市场温度" value={fmtNum(snapshot.temperature)} sub={snapshot.cycle} />
        <Stat label="红盘比" value={fmtNum(ind.red_ratio)} />
        <Stat label="中位涨跌幅" value={fmtNum(ind.median_chg)} />
        <Stat label="成交额(亿)" value={fmtNum(ind.turnover_amt)} />
      </div>

      <Card title="涨跌家数分布">
        <EChart option={breadthOption} height={240} />
      </Card>

      {snapshot.scenario && snapshot.scenario.length > 0 && (
        <Card title="情景概率">
          <ScenarioChart items={snapshot.scenario} />
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card title="连板梯队（今日摘要）">
          <div className="text-sm text-sf-txt/70">
            最高板{' '}
            <span className="text-sf-txt font-semibold">
              {snapshot.ladder?.max_boards ?? '—'}
            </span>
            {' · '}连板总数{' '}
            <span className="text-sf-txt font-semibold">
              {snapshot.ladder?.total_connect ?? '—'}
            </span>
          </div>
          <div className="text-xs text-sf-txt/40 mt-1">
            下方「连板梯队明细」为历史逐日分布（含板位家数）
          </div>
        </Card>
        <Card title="事件因子">
          {snapshot.event_factor?.available ? (
            <div className="text-sm text-sf-txt/70">
              多头 {snapshot.event_factor.long_count ?? '—'} 只
              {snapshot.event_factor.adj != null && (
                <span className="ml-2">调节 {snapshot.event_factor.adj}</span>
              )}
            </div>
          ) : (
            <div className="text-sm text-sf-txt/40">事件因子不可用</div>
          )}
        </Card>
        <Card title="综合评分">
          <Stat
            label="评分"
            value={fmtNum(snapshot.score)}
            sub={`偏向 ${snapshot.bias ?? '—'}`}
          />
        </Card>
      </div>
    </>
  )
}

function BreadthTrend({ series }: { series: BreadthPoint[] }) {
  // 取最近 60 个交易日，保证可读；老数据仍可下拉/翻页（后续波）。
  const recent = series.slice(-60)
  const dates = recent.map((p) => p.date)
  const up = recent.map((p) => num(p.up_count))
  const down = recent.map((p) => num(p.down_count))

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['上涨家数', '下跌家数'],
      textStyle: { color: CHART.txt },
      top: 0,
    },
    grid: { left: 48, right: 16, top: 28, bottom: 28 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: CHART.txt, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.border } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.txt },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        name: '上涨家数',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: up,
        itemStyle: { color: CHART.up },
        lineStyle: { color: CHART.up, width: 1.5 },
      },
      {
        name: '下跌家数',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: down,
        itemStyle: { color: CHART.down },
        lineStyle: { color: CHART.down, width: 1.5 },
      },
    ],
  }

  return (
    <div>
      <EChart option={option} height={260} />
      <div className="text-xs text-sf-txt/40 mt-1">
        数据来自 data/snapshots/*.json 聚合（共 {series.length} 个交易日，近期展示 60 个）
      </div>
    </div>
  )
}

function LadderDetailView({ history }: { history: LadderDay[] }) {
  const latest = history[history.length - 1]
  const dist = latest?.distribution ?? {}

  // 板位降序（高板在上），家数作为横向条形；高板用红、低板用绿，直观看梯队强弱。
  const boards = Object.keys(dist)
    .map((k) => Number(k))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => b - a)
  const maxBoard = boards[0] ?? 0

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    grid: { left: 40, right: 16, top: 10, bottom: 24 },
    xAxis: {
      type: 'value',
      axisLabel: { color: CHART.txt },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    yAxis: {
      type: 'category',
      data: boards.map((b) => `${b} 板`),
      axisLabel: { color: CHART.txt },
      axisLine: { lineStyle: { color: CHART.border } },
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
                : CHART.border,
          },
        })),
        label: { show: true, position: 'right', color: CHART.txt },
      },
    ],
  }

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat label="最新数据日" value={latest?.date ?? '—'} />
        <Stat label="最高板" value={fmtNum(latest?.max_boards)} />
        <Stat label="连板总数" value={fmtNum(latest?.total_connect)} />
        <Stat label="历史样本" value={fmtNum(history.length)} sub="交易日" />
      </div>
      <EChart option={option} height={Math.max(160, boards.length * 26)} />
      <div className="text-xs text-sf-txt/40 mt-1">
        数据来自 data/shepherd_ladder_history.json（逐日连板分布；红色=高板位）
      </div>
    </div>
  )
}
