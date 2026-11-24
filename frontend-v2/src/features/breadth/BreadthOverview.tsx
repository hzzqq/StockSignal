import type {
  DailySnapshot,
  BreadthPoint,
  LadderDay,
  BreadthHistoryPoint,
  MarketTemperature,
  MarketTemperatureWindow,
} from '@/api/schemas/read'
import type { EChartsOption } from 'echarts'
import { useState } from 'react'
import { useDailySnapshot, useBreadthTimeseries, useLadderDetail, useBreadthHistory, useMarketTemperature } from '@/lib/queries'
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
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import { Select } from '@/shared/ui/Field'

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

/**
 * v1 modules/market_temperature.py BANDS 的五档阈值（静态常量，非数据）：
 * 冰点[0,20) / 偏冷[20,40) / 中性[40,60) / 活跃[60,80) / 狂热[80,101)。
 * 末档上界取 v1 真值 101（显示区间仍为 80–100°），且 v1 在 temperature_band:63 有
 * `return BANDS[-1]` 兜底，故数值可得但越界时也落末档，不返回「不可得」。
 * 用当前快照温度派生档位标签，绝不在数据层缺字段时凭空编造指标贡献或信号。
 */
const V1_TEMP_BANDS = [
  { lo: 0, hi: 20, label: '冰点' },
  { lo: 20, hi: 40, label: '偏冷' },
  { lo: 40, hi: 60, label: '中性' },
  { lo: 60, hi: 80, label: '活跃' },
  { lo: 80, hi: 101, label: '狂热' },
] as const

/** 按 v1 五档阈值派生档位；温度缺失（null/undefined/非有限数）返回 null 供页面显「—」。 */
export function v1BandOf(
  temp: number | null | undefined,
): { label: string; range: string } | null {
  if (typeof temp !== 'number' || !Number.isFinite(temp)) return null
  const t = Math.max(0, Math.min(100, temp))
  for (const b of V1_TEMP_BANDS) {
    if (t >= b.lo && t < b.hi) {
      return { label: b.label, range: `${b.lo}–${b.hi - 1}°` }
    }
  }
  // 忠实 v1 `return BANDS[-1]`：仅当温度数值可得却越出所有档位时兜底末档（狂热）。
  // 缺失温度已在上面提前返回 null，不在此兜底，保持「缺失显—不补零」的诚实红线。
  const last = V1_TEMP_BANDS[V1_TEMP_BANDS.length - 1]
  return { label: last.label, range: `${last.lo}–${last.hi - 1}°` }
}

/**
 * 基准窗口切换（v1 59 页侧栏同款三档）：切换即换 queryKey 重取聚合数据。
 * 默认全历史 2000（忠实 v1 侧栏默认），档位文案标明数据起止口径。
 */
const HIST_WINDOWS: Array<{ value: MarketTemperatureWindow; label: string }> = [
  { value: 2000, label: '全历史（2007 起 · 2000 日）' },
  { value: 250, label: '近一年（250 日）' },
  { value: 60, label: '近一季（60 日）' },
]

/**
 * heat 五档条色（冷→热渐进，全部取自 CHART 调色板，亮色主题由 remapChartColors 自动换算）：
 * 冰点(accent 蓝紫) / 偏冷(ok 绿) / 中性(ink2 灰) / 活跃(warn 橙) / 狂热(up 红)。
 */
function heatColor(heat: number | null | undefined): string {
  if (typeof heat !== 'number' || !Number.isFinite(heat)) return CHART.line
  const t = Math.max(0, Math.min(100, heat))
  if (t < 20) return CHART.accent
  if (t < 40) return CHART.ok
  if (t < 60) return CHART.ink2
  if (t < 80) return CHART.warn
  return CHART.up
}

export function BreadthOverview() {
  const daily = useDailySnapshot()
  const breadth = useBreadthTimeseries()
  const ladder = useLadderDetail()
  const history = useBreadthHistory()
  const [histDays, setHistDays] = useState<MarketTemperatureWindow>(2000)
  const temperature = useMarketTemperature(histDays)

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

      {/* ───── v1 59「市场温度计」四块迁移：基准窗口 + 三卡（牧羊人贡献 / 极端区信号 / 历史情境类比）───── */}
      <div className="flex flex-wrap items-center gap-3 mt-2">
        <SectionTitle as="h2">市场温度计（v1 59 页四块）</SectionTitle>
        <Select
          label="基准窗口"
          aria-label="温度基准窗口"
          className="w-56"
          value={histDays}
          onChange={(e) => setHistDays(Number(e.target.value) as MarketTemperatureWindow)}
        >
          {HIST_WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>
              {w.label}
            </option>
          ))}
        </Select>
      </div>

      <Card title="牧羊人指标热度贡献分解">
        <QueryState
          isLoading={temperature.isLoading}
          isError={temperature.isError}
          error={temperature.error}
        >
          {temperature.data ? <TempContributionView t={temperature.data.temperature} /> : null}
        </QueryState>
      </Card>

      <Card title="极端区信号（sentiment_edge）">
        <QueryState
          isLoading={temperature.isLoading}
          isError={temperature.isError}
          error={temperature.error}
        >
          {temperature.data ? <ExtremeSignalView s={temperature.data.extreme_signal} /> : null}
        </QueryState>
      </Card>

      <Card title="历史情境类比">
        <QueryState
          isLoading={temperature.isLoading}
          isError={temperature.isError}
          error={temperature.error}
        >
          {temperature.data ? <AnalogsView a={temperature.data.analogs} /> : null}
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
        <SectionTitle as="h2">市场广度·温度总览</SectionTitle>
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

      <Card title="温度档位（按 v1 阈值派生）">
        <div className="text-body text-sf-ink-2">
          当前快照温度 <span className="tabular-nums font-semibold">{fmtNum(snapshot.temperature)}</span>
          {' → 档位 '}
          <span className="font-semibold">
            {v1BandOf(snapshot.temperature)?.label ?? '—'}
          </span>
          <span className="text-label text-sf-ink-3">
            （{v1BandOf(snapshot.temperature)?.range ?? '温度不可得，不派生档位'}）
          </span>
        </div>
        <div className="flex flex-wrap gap-3 mt-2 text-label text-sf-ink-3">
          {V1_TEMP_BANDS.map((b) => (
            <span key={b.label}>{b.label} {b.lo}–{b.hi - 1}°</span>
          ))}
        </div>
        <p className="text-label text-sf-ink-3 mt-2">
          档位由快照温度按 v1 五档阈值派生（非 v1 八指标合成口径）。v1《市场温度计》的牧羊人 8 指标贡献分解、
          极端区信号（sentiment_edge）、历史情境类比与基准窗口切换<strong>已迁移至本页下方三卡</strong>
          {`（实时取数走后端聚合端点 /market-temperature，`}
          <LeadText>缺失指标诚实显「—」不补 0</LeadText>
          {`）； 五档历史回测见 `}
          <a href="/temperature-backtest" className="text-sf-accent underline underline-offset-4">温度档回测</a>，
          历史相似日延伸见 <a href="/similar-days" className="text-sf-accent underline underline-offset-4">历史相似日</a>，
          指标级情绪五维见 <a href="/market-sentiment" className="text-sf-accent underline underline-offset-4">市场情绪温度计</a>（对应 v1 50 页）。
        </p>
      </Card>

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
  // 取最近 60 个交易日，保证可读；dataZoom 滚轮/滑块仍只作用于这 60 日窗口。
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
    grid: { left: 48, right: 16, top: 28, bottom: 52 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 6, height: 18 }],
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
      <EChart option={option} height={280} ariaLabel="近期广度时序折线图：逐日上涨家数与下跌家数" />
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

/**
 * 长周期广度历史的日期区间过滤（纯函数，供单测直接断言）。
 * ISO 日期字符串（YYYY-MM-DD）字典序即时间序，直接字符串比较，不经 new Date 兜底。
 * 合法区间 = 起止都非空 且 起 ≤ 止；非法区间由调用方禁用按钮，函数不裁剪数据。
 */
export function histRangeValid(start: string, end: string): boolean {
  return start !== '' && end !== '' && start <= end
}

/** 按 [start, end] 闭区间过滤（含两端）；仅按真实日期裁剪，缺失数据不补 0。 */
export function filterBreadthHistoryByRange(
  series: BreadthHistoryPoint[],
  start: string,
  end: string,
): BreadthHistoryPoint[] {
  return series.filter((p) => p.date >= start && p.date <= end)
}

/** 图下口径说明按视图模式如实书写：区间筛选 / 全历史 / 默认近 250 日。 */
export function histCaption(view: 'recent' | 'full' | 'range', total: number, shown: number, start: string, end: string): string {
  if (view === 'range') return `区间筛选 ${start} ~ ${end}（命中 ${shown} 个交易日）`
  if (view === 'full') return `全历史（共 ${total} 个交易日）`
  return `展示最近 250 个（共 ${total} 个交易日）`
}

function BreadthHistoryTrend({ series }: { series: BreadthHistoryPoint[] }) {
  // 真实文件跨 2007→2026（数千交易日）。默认展示最近 250 个保证可读；
  // 日期区间选择后按真实日期过滤（缺失数据不补 0），「全历史」按钮放开全部。
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [view, setView] = useState<'recent' | 'full' | 'range'>('recent')
  const rangeOk = histRangeValid(rangeStart, rangeEnd)

  const shown =
    view === 'range' && rangeOk
      ? filterBreadthHistoryByRange(series, rangeStart, rangeEnd)
      : view === 'full'
        ? series
        : series.slice(-250)
  const dates = shown.map((p) => p.date)
  const up = shown.map((p) => num(p.up_count))
  const down = shown.map((p) => num(p.down_count))
  const red = shown.map((p) => num(p.red_ratio))

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['上涨家数', '下跌家数', '红盘比%'],
      textStyle: { color: CHART.ink2 },
      top: 0,
    },
    grid: { left: 48, right: 48, top: 28, bottom: 52 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 6, height: 18 }],
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
      <div className="flex flex-wrap items-end gap-3 mb-2 text-label text-sf-ink-3">
        <label>
          起
          <input
            type="date"
            aria-label="历史区间起始日期"
            value={rangeStart}
            onChange={(e) => setRangeStart(e.target.value)}
            className="ml-1 rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-sm text-sf-ink"
          />
        </label>
        <label>
          止
          <input
            type="date"
            aria-label="历史区间结束日期"
            value={rangeEnd}
            onChange={(e) => setRangeEnd(e.target.value)}
            className="ml-1 rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-sm text-sf-ink"
          />
        </label>
        <button
          type="button"
          disabled={!rangeOk}
          onClick={() => setView('range')}
          className="rounded-tile border border-sf-line bg-sf-surface px-3 py-1 text-sm text-sf-ink disabled:opacity-40 disabled:cursor-not-allowed"
        >
          查区间
        </button>
        <button
          type="button"
          onClick={() => setView('full')}
          className="rounded-tile border border-sf-line bg-sf-surface px-3 py-1 text-sm text-sf-ink"
        >
          全历史
        </button>
        <button
          type="button"
          onClick={() => setView('recent')}
          className="rounded-tile border border-sf-line bg-sf-surface px-3 py-1 text-sm text-sf-ink"
        >
          近 250 日
        </button>
      </div>
      <EChart option={option} height={280} ariaLabel="长周期广度历史折线图：逐日涨跌家数与红盘比" />
      <div className="text-xs text-sf-ink-3 mt-1">
        数据来自 data/shepherd_history.json（逐日广度，{histCaption(view, series.length, shown.length, rangeStart, rangeEnd)}）
      </div>
    </div>
  )
}

/** 牧羊人指标热度贡献分解：水平条形图 x=heat(0–100)，y=`${name} ${round(value)}${unit}`，条色按五档。 */
function TempContributionView({ t }: { t: MarketTemperature['temperature'] }) {
  if (!t.available) {
    return <div className="text-body text-sf-ink-3">{t.reason ?? '牧羊人指标热度贡献不可得'}</div>
  }
  const rows = t.contributions ?? []
  const band = v1BandOf(t.temp ?? null)

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    grid: { left: 150, right: 32, top: 8, bottom: 24 },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map((c) =>
        // 缺失值诚实带「—」，不把无数据渲染成 0。
        `${c.name} ${c.value == null ? '—' : Math.round(c.value)}${c.unit}`,
      ),
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        barWidth: '55%',
        data: rows.map((c) => ({
          value: c.heat ?? null,
          itemStyle: { color: heatColor(c.heat) },
        })),
        label: { show: true, position: 'right', color: CHART.ink2 },
      },
    ],
  }

  return (
    <div>
      <div className="text-body text-sf-ink-2 mb-2">
        合成温度 <span className="tabular-nums font-semibold">{fmtNum(t.temp ?? null)}</span>
        {' → 档位 '}
        <span className="font-semibold">{band?.label ?? '—'}</span>
        <span className="text-label text-sf-ink-3">（{band?.range ?? '温度不可得，不派生档位'}）</span>
      </div>
      {rows.length === 0 ? (
        <div className="text-body text-sf-ink-3">{t.reason ?? '无可用指标贡献'}</div>
      ) : (
        <EChart
          option={option}
          height={Math.max(120, rows.length * 30)}
          ariaLabel="牧羊人指标热度贡献水平条形图，条色按热度五档"
        />
      )}
      {t.indicators_unavailable && t.indicators_unavailable.length > 0 && (
        <div className="text-label text-sf-ink-3 mt-1">
          不可得指标（诚实带出）：
          {t.indicators_unavailable?.map(([key, why]) => `${key}（${why}）`).join('、')}
        </div>
      )}
    </div>
  )
}

/** 极端区信号（sentiment_edge）：触发=红色告警卡 + hits 表；未触发=statement；不可得=reason。 */
function ExtremeSignalView({ s }: { s: MarketTemperature['extreme_signal'] }) {
  if (!s.available) {
    return <div className="text-body text-sf-ink-3">{s.reason ?? '极端区信号不可得'}</div>
  }
  const hit = s.hits?.[0]

  return (
    <div>
      {s.triggered ? (
        <div
          role="alert"
          className="rounded-tile border border-sf-danger bg-sf-danger-soft px-3 py-2 text-body text-sf-danger"
        >
          {s.statement}
        </div>
      ) : (
        <div className="text-body text-sf-ink-2">{s.statement}</div>
      )}

      {s.triggered && s.hits && s.hits.length > 0 && (
        <table className="w-full text-xs text-sf-ink mt-3">
          <caption className="sr-only">极端区触发指标明细</caption>
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">指标</th>
              <th className="text-right py-1.5 pr-3">当前值</th>
              <th className="text-right py-1.5 pr-3">阈值</th>
              <th className="text-right py-1.5 pr-3">后市上涨概率</th>
              <th className="text-right py-1.5">z 值</th>
            </tr>
          </thead>
          <tbody>
            {s.hits.map((h) => (
              <tr key={h.key} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{h.name}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(h.value)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(h.threshold)}</td>
                {/* prob 是 0-1 分数（statement 里为百分数口径），此处统一转百分比显示；缺失显「—」。 */}
                <td className="py-1.5 pr-3 text-right tabular-nums">
                  {h.prob == null || !Number.isFinite(h.prob) ? '—' : `${(h.prob * 100).toFixed(1)}%`}
                </td>
                <td className="py-1.5 text-right tabular-nums">{fmtNum(h.z)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {s.triggered && hit && (
        <div className="text-label text-sf-ink-3 mt-2">
          样本 {fmtNum(hit.n)} 天 · 边际 {fmtNum(s.edge_pp)} pp
        </div>
      )}

      <p className="text-label text-sf-ink-3 mt-2">统计概率，非确定性预测</p>
    </div>
  )
}

/**
 * 历史情境类比：最多 8 个相似日网格卡。后5日上涨占比 >0.5 用红色系、<=0.5 用绿色系
 * ——这是历史后市统计展示，遵循 A股涨红跌绿；缺失显「—」，绝不补 0。
 */
function AnalogsView({ a }: { a: MarketTemperature['analogs'] }) {
  if (!a.available) {
    return <div className="text-body text-sf-ink-3">{a.reason ?? '历史情境类比不可得'}</div>
  }
  const rows = a.analogs ?? []

  return (
    <div>
      {a.today_metrics && (
        <div className="text-label text-sf-ink-3 mb-2">
          当日画像：红盘比 {fmtNum(a.today_metrics.red_ratio)}% · 涨停 {fmtNum(a.today_metrics.limit_up)} · 跌停{' '}
          {fmtNum(a.today_metrics.limit_down)}
        </div>
      )}
      {rows.length === 0 ? (
        <div className="text-body text-sf-ink-3">{a.reason ?? '无相似历史日'}</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {rows.slice(0, 8).map((an) => {
            const upFrac = an.forward?.d5?.up_frac ?? null
            // 后市统计配色（A股涨红跌绿语义）：up_frac>0.5 红、<=0.5 绿；缺失不着色显「—」。
            // 涨跌色按设计守卫以 var() 内联（ss-up/down 是价格域语义色，禁 Tailwind class）。
            const upColor =
              upFrac == null || !Number.isFinite(upFrac)
                ? undefined
                : upFrac > 0.5
                  ? 'var(--color-ss-up)'
                  : 'var(--color-ss-down)'
            return (
              <div key={an.date} className="rounded-tile border border-sf-line px-3 py-2">
                <div className="text-sm text-sf-ink font-semibold">
                  {an.date}
                  <span className="ml-2 text-label font-normal text-sf-ink-3">{an.state ?? '—'}</span>
                </div>
                <div className="text-label text-sf-ink-3 mt-0.5">
                  相似距离 {an.distance == null || !Number.isFinite(an.distance) ? '—' : an.distance.toFixed(2)}
                </div>
                <div className="text-xs mt-1.5 text-sf-ink-2" style={upColor ? { color: upColor } : undefined}>
                  <div>后5日红盘率 {fmtNum(an.forward?.d5?.avg_red ?? null)}%</div>
                  <div>
                    后5日上涨占比{' '}
                    {upFrac == null || !Number.isFinite(upFrac)
                      ? '—'
                      : `${(upFrac * 100).toFixed(0)}%`}
                  </div>
                  <div>后10日红盘率 {fmtNum(an.forward?.d10?.avg_red ?? null)}%</div>
                  <div>后20日红盘率 {fmtNum(an.forward?.d20?.avg_red ?? null)}%</div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <p className="text-label text-sf-ink-3 mt-2">历史相似≠预测</p>
    </div>
  )
}
