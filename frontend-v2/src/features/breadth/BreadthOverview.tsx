import type { DailySnapshot, BreadthPoint, LadderDay, BreadthHistoryPoint } from '@/api/schemas/read'
import type { EChartsOption } from 'echarts'
import { useDailySnapshot, useBreadthTimeseries, useLadderDetail, useBreadthHistory } from '@/lib/queries'
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

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export function BreadthOverview() {
  const daily = useDailySnapshot()
  const breadth = useBreadthTimeseries()
  const ladder = useLadderDetail()
  const history = useBreadthHistory()

  return (
    <div className="flow">
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

      <Card title="长周期广度（涨跌家数 · 全历史）">
        <QueryState
          isLoading={history.isLoading}
          isError={history.isError}
          error={history.error}
          isEmpty={!!history.data && history.data.length === 0}
        >
          {history.data ? <BreadthHistoryTrend series={history.data} /> : null}
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
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        barWidth: '52%',
        data: [
          // 缺失送 null：ECharts 不画该柱，绝不把「无数据」渲染成 0 家
          { value: num(ind.up_count), itemStyle: { color: CHART.up } },
          { value: num(ind.down_count), itemStyle: { color: CHART.down } },
          { value: num(ind.limit_up), itemStyle: { color: CHART.up } },
          { value: num(ind.limit_down), itemStyle: { color: CHART.down } },
        ],
      },
    ],
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">市场广度·温度总览</h2>
        <FreshnessBadge level={level} />
        <span className="text-label text-sf-ink-3">权威数据日 {snapshot.date}</span>
        <a
          href="/ladder"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          连板共振页 →
        </a>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="市场温度" value={fmtNum(snapshot.temperature)} sub={snapshot.cycle} />
        <Stat label="红盘比" value={fmtNum(ind.red_ratio)} />
        <Stat label="中位涨跌幅" value={fmtNum(ind.median_chg)} />
        <Stat label="成交额(亿)" value={fmtNum(ind.turnover_amt)} />
      </div>

      <Card title="涨跌家数分布">
        <EChart option={breadthOption} height={240} ariaLabel="当日涨跌家数分布柱状图：上涨、下跌、涨停、跌停四类" />
      </Card>

      {snapshot.scenario && snapshot.scenario.length > 0 && (
        <Card title="情景概率">
          <ScenarioChart items={snapshot.scenario} />
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card title="连板梯队（今日摘要）">
          <div className="text-sm text-sf-ink-2">
            最高板{' '}
            <span className="text-sf-ink font-semibold">
              {snapshot.ladder?.max_boards ?? '—'}
            </span>
            {' · '}连板总数{' '}
            <span className="text-sf-ink font-semibold">
              {snapshot.ladder?.total_connect ?? '—'}
            </span>
          </div>
          <div className="text-xs text-sf-ink-3 mt-1">
            下方「连板梯队明细」为历史逐日分布（含板位家数）
          </div>
        </Card>
        <Card title="事件因子">
          {snapshot.event_factor?.available ? (
            <div className="text-sm text-sf-ink-2">
              多头 {snapshot.event_factor.long_count ?? '—'} 只
              {snapshot.event_factor.adj != null && (
                <span className="ml-2">调节 {snapshot.event_factor.adj}</span>
              )}
            </div>
          ) : (
            <div className="text-sm text-sf-ink-3">事件因子不可用</div>
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
      textStyle: { color: CHART.ink2 },
      top: 0,
    },
    grid: { left: 48, right: 16, top: 28, bottom: 28 },
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
      <EChart option={option} height={260} ariaLabel="近期广度时序折线图：逐日上涨家数与下跌家数" />
      <div className="text-xs text-sf-ink-3 mt-1">
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
  // 无板位时取 0 仅作为配色阈值，不是渲染出来的家数；绝不当作真实数据展示。
  const maxBoard = boards.length ? boards[0] : 0

  const option: EChartsOption = {
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
          value: dist[String(b)] ?? null,
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
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat label="最新数据日" value={latest?.date ?? '—'} />
        <Stat label="最高板" value={fmtNum(latest?.max_boards)} />
        <Stat label="连板总数" value={fmtNum(latest?.total_connect)} />
        <Stat label="历史样本" value={fmtNum(history.length)} sub="交易日" />
      </div>
      <EChart option={option} height={Math.max(160, boards.length * 26)} ariaLabel="最新交易日连板板位分布条形图，按连板数从高到低" />
      <div className="text-xs text-sf-ink-3 mt-1">
        数据来自 data/shepherd_ladder_history.json（逐日连板分布；红色=高板位）
      </div>
    </div>
  )
}

function BreadthHistoryTrend({ series }: { series: BreadthHistoryPoint[] }) {
  // 真实文件跨 2007→2026（数千交易日），展示最近 250 个交易日保证可读。
  const recent = series.slice(-250)
  const dates = recent.map((p) => p.date)
  const up = recent.map((p) => num(p.up_count))
  const down = recent.map((p) => num(p.down_count))
  const red = recent.map((p) => num(p.red_ratio))

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['上涨家数', '下跌家数', '红盘比%'],
      textStyle: { color: CHART.ink2 },
      top: 0,
    },
    grid: { left: 48, right: 48, top: 28, bottom: 28 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: [
      {
        type: 'value',
        name: '家数',
        axisLabel: { color: CHART.ink2 },
        splitLine: { lineStyle: { color: CHART.line } },
      },
      {
        type: 'value',
        name: '红盘比%',
        max: 100,
        position: 'right',
        axisLabel: { color: CHART.ink2 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '上涨家数',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: up,
        itemStyle: { color: CHART.up },
        lineStyle: { color: CHART.up, width: 1.2 },
      },
      {
        name: '下跌家数',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: down,
        itemStyle: { color: CHART.down },
        lineStyle: { color: CHART.down, width: 1.2 },
      },
      {
        name: '红盘比%',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        data: red,
        itemStyle: { color: CHART.ink2 },
        lineStyle: { color: CHART.ink2, width: 1, type: 'dashed' },
      },
    ],
  }

  return (
    <div>
      <EChart option={option} height={280} ariaLabel="长周期广度历史折线图：逐日涨跌家数与红盘比" />
      <div className="text-xs text-sf-ink-3 mt-1">
        数据来自 data/shepherd_history.json（逐日广度，共 {series.length} 个交易日，展示最近 250 个）
      </div>
    </div>
  )
}
