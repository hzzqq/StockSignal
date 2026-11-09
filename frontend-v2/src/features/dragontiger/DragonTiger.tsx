import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { DragonTiger, DragonTigerRow } from '@/api/schemas/read'
import { useDragonTiger } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 85 页「龙虎榜」V2 化（对应 V2-STATUS-PLAN Tier2）。
 * 数据来源：useDragonTiger → GET /api/v2/read/dragon-tiger?date=YYYYMMDD（后端复用 modules.lhb）。
 *
 * 红线（与 modules.lhb 一致）：
 * - 取不到（akshare 缺失 / 网络失败 / 非交易日）→ 仍 200、unavailable=['lhb_fetch_failed']，不 500、不编造。
 * - 净买列识别不到（列名变更）→ buy/sell_top 降级 None，但原始明细(detail)保留，宁缺毋滥不猜列编方向。
 * - 数值后端已清洗 NaN/Inf 为 null，前端不补 0（避开 ?? 0 / || 0 / new Date()）。
 */
function fmtYi(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const s = v.toFixed(2)
    return `${s} 亿`
  }
  return '—'
}

function netColor(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 0 ? CHART.up : v < 0 ? CHART.down : CHART.ink2
  }
  return CHART.ink2
}

function netText(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)} 亿`
  }
  return '—'
}

/** 仅用于图表坐标：缺失值→0 高度柱（不显示伪造数值，表格侧仍显示「—」）。 */
function nz(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

function buildBarOption(buy: DragonTigerRow[], sell: DragonTigerRow[]): EChartsOption {
  // 取前 10：净买入为正（红）、净卖出为负（绿），合成一张分歧条形图。
  const topBuy = buy.slice(0, 10)
  const topSell = sell.slice(0, 10)
  const cats: string[] = []
  const vals: { value: number; itemStyle: { color: string } }[] = []
  for (const r of topBuy) {
    const label = r.name ?? r.code ?? '—'
    cats.push(label)
    vals.push({ value: nz(r.net_yi), itemStyle: { color: CHART.up } })
  }
  for (const r of topSell) {
    const label = r.name ?? r.code ?? '—'
    cats.push(label)
    vals.push({ value: -nz(r.net_yi), itemStyle: { color: CHART.down } })
  }
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2, formatter: (v: number) => `${v} 亿` },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'category',
      data: cats,
      inverse: true,
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [{ type: 'bar', data: vals, barMaxWidth: 18 }],
  }
}

export function DragonTiger() {
  const [dateInput, setDateInput] = useState('')
  const [queryDate, setQueryDate] = useState<string | undefined>(undefined)
  const q = useDragonTiger(queryDate)
  const d = q.data

  const count = d?.count ?? null
  const netSumYi = d?.net_sum_yi ?? null
  const netCol = d?.net_col ?? null
  const buyTop = d?.buy_top ?? null
  const sellTop = d?.sell_top ?? null
  const detail = d?.detail ?? null
  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')

  const isEmpty = !!d && count == null && !buyTop && !detail

  const showChart = !!buyTop && !!sellTop && (buyTop.length > 0 || sellTop.length > 0)

  return (
    <div className="dragon-tiger">
      <h2 className="text-lg font-semibold">龙虎榜</h2>
      <div className="text-xs text-sf-ink-3">
        席位级资金博弈（东方财富龙虎榜）：谁在上榜、净买还是净卖。数据源 akshare，按交易日更新，非实时行情；
        取不到就显示「取不到」，绝不用示例数据填充；净买列识别不到时不猜列编资金方向。
      </div>

      <div className="flex items-end gap-3 my-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-sf-ink-3" htmlFor="dt-date">
            交易日期（YYYYMMDD，留空=最近交易日）
          </label>
          <input
            id="dt-date"
            className="px-2 py-1.5 rounded-md border border-sf-line bg-sf-surface text-sm text-sf-ink w-56"
            placeholder="例如 20261109"
            value={dateInput}
            onChange={(e) => setDateInput(e.target.value.trim())}
          />
        </div>
        <button
          type="button"
          className="px-4 py-1.5 rounded-md bg-sf-accent text-white text-sm font-medium"
          onClick={() => setQueryDate(dateInput || undefined)}
        >
          查询
        </button>
        {queryDate && (
          <button
            type="button"
            className="px-3 py-1.5 rounded-md border border-sf-line text-sm text-sf-ink-3"
            onClick={() => {
              setDateInput('')
              setQueryDate(undefined)
            }}
          >
            重置
          </button>
        )}
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="龙虎榜暂不可用"
        emptyHint="取数失败（离线 / 接口受限 / 非交易日）；后端已诚实降级，未编造明细"
      >
        {d ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Stat label="上榜家数" value={count == null ? '—' : String(count)} />
              <Stat
                label="净买额合计"
                value={fmtYi(netSumYi)}
                color={netSumYi == null ? undefined : netColor(netSumYi)}
                sub={netSumYi == null ? undefined : netSumYi >= 0 ? '整体净流入' : '整体净流出'}
              />
              <Stat label="识别到的净买列" value={netCol ?? '—'} />
            </div>

            {showChart && (
              <Card title="净买入 Top vs 净卖出 Top（前 10）">
                <EChart
                  option={buildBarOption(buyTop ?? [], sellTop ?? [])}
                  height={Math.max(220, (buyTop ? buyTop.length : 0) + (sellTop ? sellTop.length : 0)) * 22}
                  ariaLabel="龙虎榜净买入净卖出分歧条形图"
                />
                <div className="mt-2 text-xs text-sf-ink-3">
                  红=净买入（资金净流入），绿=净卖出（资金净流出）；净买额单位亿元，由服务端按数据源列口径计算。
                </div>
              </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <RankTable title="🔥 净买入 Top" rows={buyTop} />
              <RankTable title="🧊 净卖出 Top" rows={sellTop} />
            </div>

            {detail && detail.length > 0 && (
              <Card title={`原始明细（前 ${detail.length} 行）`}>
                <DetailTable rows={detail} />
              </Card>
            )}

            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下情况本次发生（已诚实标注）：{unavailable.join('、')}
              </div>
            )}

            <div className="text-xs text-sf-ink-3">
              口径与来源：龙虎榜明细=东财接口（modules.lhb.fetch_lhb，30 分钟缓存，按交易日更新，非实时行情）；
              净买额口径以数据源列为准（列名识别不到时排名整体降级为 None，不用错列编资金方向）。席位行为为历史事实披露，不构成投资建议。
            </div>
          </div>
        ) : null}
      </QueryState>
    </div>
  )
}

function RankTable({ title, rows }: { title: string; rows: DragonTigerRow[] | null }) {
  if (!rows || rows.length === 0) {
    return (
      <Card title={title}>
        <div className="text-xs text-sf-ink-3">
          净买列识别不到或本页无数据，已降级为不显示排名（避免用错列编出资金方向）。可在下方「原始明细」中自行查看。
        </div>
      </Card>
    )
  }
  return (
    <Card title={`${title}（${rows.length}）`}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">代码</th>
              <th className="text-left py-1.5 pr-3">名称</th>
              <th className="text-right py-1.5">净买额</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.code ?? r.name ?? i} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{r.code ?? '—'}</td>
                <td className="py-1.5 pr-3">{r.name ?? '—'}</td>
                <td className="py-1.5 text-right font-medium" style={{ color: netColor(r.net_yi) }}>
                  {netText(r.net_yi)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function DetailTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))))
  return (
    <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
      <table className="w-full text-xs text-sf-ink">
        <thead>
          <tr className="text-sf-ink-3 border-b border-sf-line sticky top-0 bg-sf-surface">
            {cols.map((c) => (
              <th key={c} className="text-left py-1.5 pr-3 whitespace-nowrap">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-sf-line/60">
              {cols.map((c) => {
                const v = r[c]
                const txt =
                  typeof v === 'number' && Number.isFinite(v)
                    ? v.toFixed(2)
                    : v == null
                      ? '—'
                      : String(v)
                return (
                  <td key={c} className="py-1.5 pr-3 whitespace-nowrap">
                    {txt}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
