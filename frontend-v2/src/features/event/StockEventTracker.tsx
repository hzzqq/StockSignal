import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { StockEvent, StockEventItem } from '@/api/schemas/read'
import { useStockEvents } from '@/lib/queries'
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

/** A 股语义：利好=红、利空=绿、中性=灰。 */
function levelColor(level: string): string {
  if (level.includes('利好')) return CHART.up
  if (level.includes('利空')) return CHART.down
  return CHART.ink3
}

function hasDate(e: StockEventItem): e is StockEventItem & { date: string } {
  return typeof e.date === 'string' && e.date.length > 0
}

function LevelBadge({ level, isMajor }: { level: string; isMajor: boolean }) {
  const color = levelColor(level)
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
function buildTimelineOption(events: StockEventItem[]): EChartsOption {
  const dated = events.filter(hasDate).slice().sort((a, b) => a.date.localeCompare(b.date))
  const points = dated.map((e) => ({
    value: LEVEL_WEIGHT[e.level] ?? null,
    name: e.title,
    itemStyle: { color: levelColor(e.level) },
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
        <QueryState
          isLoading={q.isLoading}
          isError={q.isError}
          error={q.error}
          isEmpty={!q.data?.available || !q.data.events.length}
          emptyLabel="暂无事件数据"
          emptyHint="暂未抓取到该个股的公开事件，未做任何填充"
        >
          {q.data ? <StockEventBody data={q.data} /> : null}
        </QueryState>
      )}
    </div>
  )
}

function StockEventBody({ data }: { data: StockEvent }) {
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
                option={buildTimelineOption(events)}
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
                      <LevelBadge level={e.level} isMajor={e.is_major} />
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
