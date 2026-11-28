import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { StockEvent, StockEventItem, EventFactorSignal } from '@/api/schemas/read'
import { useStockEvents, useEventFactorSignal } from '@/lib/queries'
import { useTheme } from '@/app/providers'
import type { Theme } from '@/lib/theme'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { SectionTitle } from '@/shared/ui/EmphasisText'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'

/**
 * 个股事件追踪（v1 pages/23_事件追踪.py 的「爬取 + 时间轴 + 好坏判定」迁移）。
 *
 * 诚实红线：
 *  - 事件、日期、评分、来源、URL 一律原样透出，缺失渲染 '—'，不补 0 / 不编造日期；
 *  - 无日期的事件不进时间轴，但仍在明细表展示，并在图下如实说明跳过条数；
 *  - note 原文展示，不包装成荐股或买卖指令。
 *
 * 时间轴用 ECharts 的 line 系列（lineStyle 透明、仅显示 symbol）实现散点语义：
 * 本仓 echartsSetup.ts 尚未注册 ScatterChart，该写集不含它，静默不渲染的风险不可接受。
 */
const LEVEL_WEIGHT: Record<string, number> = {
  大利好: 2,
  小利好: 1,
  中性: 0,
  小利空: -1,
  大利空: -2,
}

/**
 * 事件五档标签色 —— 单一真理源锚定 modules/event_levels.py::DIR_COLOR（T-287）。
 *
 * 语义与交易屏涨跌色（CHART.up/down）是两件事：这里是「事件好坏档位」，
 * A 股语义利好=红、利空=绿、中性=灰，且「大」档比「小」档深一档。
 * 禁止再借 CHART.up/down 渲染档位——那会随主题/涨跌语义漂移。
 * 色值逐字对齐 Python DIR_COLOR；light 主题按同色相提亮一档（深红→亮红、深绿→亮绿），
 * 保证小字号对比度；未知档位一律中性灰，不臆造。
 */
export const EVENT_LEVEL_COLORS: Readonly<Record<string, string>> = {
  大利好: '#b91c1c', 小利好: '#dc2626', 中性: '#94a3b8',
  小利空: '#16a34a', 大利空: '#15803d',
  利好: '#dc2626', 利空: '#16a34a',
}
export const EVENT_LEVEL_COLORS_LIGHT: Readonly<Record<string, string>> = {
  大利好: '#b91c1c', 小利好: '#dc2626', 中性: '#64748b',
  小利空: '#16a34a', 大利空: '#15803d',
  利好: '#dc2626', 利空: '#16a34a',
}
const NEUTRAL_COLOR = '#94a3b8'

export function levelColor(level: string, theme: Theme = 'dark'): string {
  const palette = theme === 'light' ? EVENT_LEVEL_COLORS_LIGHT : EVENT_LEVEL_COLORS
  return palette[level] ?? NEUTRAL_COLOR
}

function hasDate(e: StockEventItem): e is StockEventItem & { date: string } {
  return typeof e.date === 'string' && e.date.length > 0
}

function LevelBadge({ level, isMajor, theme }: { level: string; isMajor: boolean; theme: Theme }) {
  const color = levelColor(level, theme)
  return (
    <span
      className={`inline-flex items-center rounded-tile border px-1.5 py-0.5 text-label ${isMajor ? 'font-bold ring-1' : ''}`}
      style={{ color, borderColor: color }}
    >
      <span>{level}</span>
      {isMajor ? <span className="ml-1">·重大</span> : null}
    </span>
  )
}

/** 按 date 升序排布；未知档位权重为 null（不画点、不伪造成中性 0）。 */
function buildTimelineOption(events: StockEventItem[], theme: Theme): EChartsOption {
  const dated = events.filter(hasDate).slice().sort((a, b) => a.date.localeCompare(b.date))
  const points = dated.map((e) => ({
    value: LEVEL_WEIGHT[e.level] ?? null,
    name: e.title,
    itemStyle: { color: levelColor(e.level, theme) },
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      renderMode: 'richText',
      // 富文本模式不解析 HTML，避免外部标题注入。
      formatter: (raw: unknown) => {
        const index = (raw as { dataIndex?: number }).dataIndex
        const e = typeof index === 'number' ? dated[index] : undefined
        if (!e) return ''
        return `${e.title}\n${e.level} · 评分 ${fmtNum(e.score)}\n来源：${e.source ?? '—'}`
      },
    },
    grid: { left: 52, right: 24, top: 12, bottom: 56 },
    xAxis: {
      type: 'category',
      data: dated.map((e) => e.date),
      axisLabel: { color: CHART.ink2, rotate: 30, fontSize: 10 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      min: -2,
      max: 2,
      interval: 1,
      name: '五档强度',
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'line',
        showSymbol: true,
        symbolSize: 12,
        lineStyle: { opacity: 0 },
        data: points,
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: CHART.ink3, type: 'dashed' },
          data: [{ yAxis: 0 }],
        },
      },
    ],
  }
}

export function StockEventTracker() {
  const [code, setCode] = useState<string | null>(null)
  const q = useStockEvents(code)
  const ef = useEventFactorSignal(code)
  const { theme } = useTheme()

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <SectionTitle as="h2">个股事件追踪</SectionTitle>
        <span className="text-label text-sf-ink-3">
          v1 23 页迁移 · 公开事件爬取 / 时间轴 / 五档好坏判定
        </span>
      </div>

      <Card title="选择股票">
        <div className="w-80 max-w-full">
          <StockSearchInput
            label="个股代码 / 名称 / 拼音首字母"
            value={code ?? ''}
            placeholder="如 600519、茅台、gzmt"
            onSelect={(next) => setCode(next)}
          />
        </div>
        {!code && (
          <p className="mt-3 text-body text-sf-ink-3">
            请先搜索并选择一只股票，再查看其公开事件时间轴。未选中时不发起任何事件请求。
          </p>
        )}
      </Card>

      {code && (
        <>
          <EventFactorCard data={ef.data} isLoading={ef.isLoading} isError={ef.isError} error={ef.error} />
          <QueryState
            isLoading={q.isLoading}
            isError={q.isError}
            error={q.error}
            isEmpty={!q.data?.available || !q.data.events.length}
            emptyLabel="暂无事件数据"
            emptyHint="暂未抓取到该个股的公开事件，未做任何填充"
          >
            {q.data ? <StockEventBody data={q.data} theme={theme} /> : null}
          </QueryState>
        </>
      )}
    </div>
  )
}

/**
 * 事件因子（五源融合）区块：接 GET /event-factor 真实适配器结果。
 * 诚实红线：available=false 时只显示 reason，不显示任何伪评分；
 * 字段缺失一律 fmtNum → '—'，note 原样透出（MSW 演示夹具自带「演示数据」标注）。
 */
function EventFactorCard({
  data, isLoading, isError, error,
}: {
  data?: EventFactorSignal
  isLoading: boolean
  isError: boolean
  error: unknown
}) {
  return (
    <Card title="事件因子（五源融合）">
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={error}
        isEmpty={!data}
        emptyLabel="无可用事件因子"
        emptyHint="未选中标的或五源均无信号，未做任何填充"
      >
        {data ? (
          data.available ? (
            <div className="flow">
              <div className="flex flex-wrap gap-x-8 gap-y-2 text-body">
                <span>代码 <b className="font-mono">{data.symbol}</b></span>
                <span>信号 {fmtNum(data.signal)}</span>
                <span>评分 {fmtNum(data.score)}</span>
                <span>排名 {fmtNum(data.rank)}</span>
                <span>数据日 {fmtNum(data.date)}</span>
                <span>来源 {fmtNum(data.source)}</span>
              </div>
              {data.hard_logic != null && (
                <p className="text-label text-sf-ink-3">硬逻辑 {fmtNum(
                  typeof data.hard_logic === 'object'
                    ? (data.hard_logic as Record<string, unknown>).label ?? data.hard_logic
                    : data.hard_logic,
                )}</p>
              )}
              {data.note ? <p className="text-label text-sf-ink-3">{data.note}</p> : null}
            </div>
          ) : (
            <p className="text-body text-sf-ink-3">
              {fmtNum(data.reason) === '—'
                ? '无可用事件因子，未做任何填充'
                : `无可用事件因子：${data.reason}（未做任何填充）`}
            </p>
          )
        ) : null}
      </QueryState>
    </Card>
  )
}

function StockEventBody({ data, theme }: { data: StockEvent; theme: Theme }) {
  const events = data.events
  const datedCount = events.filter(hasDate).length
  const skipped = events.length - datedCount
  const dist = data.distribution

  return (
    <div className="flow">
      <Card title="抓取摘要">
        <div className="flex flex-wrap gap-x-8 gap-y-2 text-body">
          <span>
            代码 <b className="font-mono">{data.code}</b>
          </span>
          <span>名称 {fmtNum(data.name)}</span>
          <span>抓取日 {fmtNum(data.date)}</span>
          <span>事件数 {fmtNum(data.count)}</span>
        </div>
      </Card>

      <Card title="情感分布">
        <div className="grid gap-3 sm:grid-cols-3">
          <div data-testid="dist-正面">
            <Stat label="正面" value={fmtNum(dist?.正面)} color={CHART.up} />
          </div>
          <div data-testid="dist-负面">
            <Stat label="负面" value={fmtNum(dist?.负面)} color={CHART.down} />
          </div>
          <div data-testid="dist-中性">
            <Stat label="中性" value={fmtNum(dist?.中性)} color={CHART.ink3} />
          </div>
        </div>
      </Card>

      <Card title="事件时间轴">
        {datedCount > 0 ? (
          <>
            <div data-testid="stock-event-timeline">
              <EChart
                option={buildTimelineOption(events, theme)}
                height={280}
                ariaLabel="个股事件时间轴：利好在上、利空在下、中性居中"
              />
            </div>
            <p className="mt-2 text-label text-sf-ink-3">
              时间轴纳入 {datedCount} 条（按日期升序）；{skipped} 条无日期事件未纳入时间轴，仍在明细表展示。
            </p>
          </>
        ) : (
          <p className="text-body text-sf-ink-3">
            {events.length} 条事件均无日期，无法按时间排布；未伪造日期，全部仅在明细表展示。
          </p>
        )}
      </Card>

      <Card title="事件明细">
        <div className="overflow-x-auto">
          <table className="w-full text-body">
            <thead>
              <tr className="border-b border-sf-line text-left text-label text-sf-ink-3">
                <th className="py-2 pr-3">日期</th>
                <th className="py-2 pr-3">标题</th>
                <th className="py-2 pr-3">来源</th>
                <th className="py-2 pr-3">档位</th>
                <th className="py-2">评分</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => {
                // 仅 http(s) 链接可点击，避免 javascript: 等伪协议。
                const href = e.url && /^https?:\/\//i.test(e.url) ? e.url : null
                return (
                  <tr key={`${e.date ?? 'no-date'}-${i}`} className="border-b border-sf-line last:border-0 hover:bg-sf-surface-2 align-top">
                    <td className="py-2 pr-3 whitespace-nowrap font-mono text-label">{fmtNum(e.date)}</td>
                    <td className="py-2 pr-3">
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sf-accent underline underline-offset-2"
                        >
                          {e.title}
                        </a>
                      ) : (
                        <span>{e.title}</span>
                      )}
                    </td>
                    <td className="py-2 pr-3">{fmtNum(e.source)}</td>
                    <td className="py-2 pr-3">
                      <LevelBadge level={e.level} isMajor={e.is_major} theme={theme} />
                    </td>
                    <td className="py-2 tabular-nums">{fmtNum(e.score)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="口径与免责">
        <p className="whitespace-pre-wrap text-body text-sf-ink-2">{data.note}</p>
      </Card>
    </div>
  )
}
