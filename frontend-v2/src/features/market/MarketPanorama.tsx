import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { MarketPanorama as MarketPanoramaData } from '@/api/schemas/read'
import type { MarketPanoramaParams } from '@/api/read'
import { useMarketPanorama } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 57 页「市场全景」V2 化落地。
 * 数据来源：useMarketPanorama → GET /api/v2/read/market-panorama（后端复用
 * modules.market_regime.regime_report + modules.shepherd_history.get_shepherd_indicators）。
 *
 * 展示：市场状态卡 + 广度快照（红盘率/涨停/跌停/连板高度/炸板率）+ 红盘率历史趋势 +
 * 状态分布 + 历史相似日速览 + 数据源缺失字段（诚实带出，不隐藏）。
 * 与 56 页共享同一后端（不重复计算）。
 *
 * ⚠️ 诚实红线：regime 不可用 → 后端 status=error，前端判空渲染「数据不足」；
 * 广度字段缺失为 null → 「—」；数据源缺失清单原样带出；历史相似 ≠ 预测。
 */

const STATE_COLOR: Record<string, string> = {
  普涨: CHART.up,
  结构牛: CHART.up,
  震荡: CHART.accent,
  恐慌: CHART.down,
  暴跌: CHART.down,
  暴涨: CHART.up,
}
const BREADTH_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'red_ratio', label: '红盘率(%)' },
  { key: 'limit_up', label: '涨停家数' },
  { key: 'limit_down', label: '跌停家数' },
  { key: 'connect_hl', label: '连板高度' },
  { key: 'zt_fail_ratio', label: '炸板率(%)' },
]

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export function MarketPanorama() {
  const [k, setK] = useState<number>(8)
  const params: MarketPanoramaParams = { k }
  const q = useMarketPanorama(params)
  const data = q.data

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">市场全景</h2>

      <Card title="类比参数">
        <label className="text-xs text-sf-ink-3 flex items-center gap-2">
          相似日数量 k
          <select
            className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
          >
            {[3, 5, 8, 10, 12, 15].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </Card>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && !data.regime?.latest}
        emptyLabel="暂无市场全景数据"
        emptyHint="广度历史缺失或取数失败，无法渲染全景（后端 honest 降级）"
      >
        {data ? <PanoramaBody data={data} /> : null}
      </QueryState>
    </div>
  )
}

function PanoramaBody({ data }: { data: MarketPanoramaData }) {
  const regime = data.regime ?? {}
  const latest = regime.latest ?? {}
  const dist = regime.state_distribution ?? {}
  const analogs = regime.analogs ?? []
  const shepherd = data.shepherd_latest ?? {}
  const series = data.shepherd_series ?? []

  const trendDates = series.map((r) => String(r['date'] ?? ''))
  const trendVals = series.map((r) => num(r['red_ratio']))
  const trendOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: trendDates,
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2, formatter: (v: number) => `${v.toFixed(0)}%` },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: trendVals,
        itemStyle: { color: CHART.accent },
        lineStyle: { color: CHART.accent, width: 1.5 },
        areaStyle: { color: CHART.accent, opacity: 0.08 },
      },
    ],
  }

  const distStates = Object.keys(dist)
  const distOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: distStates,
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
        type: 'bar',
        data: distStates.map((s) => ({
          value: num(dist[s]),
          itemStyle: { color: STATE_COLOR[s] ?? CHART.accent },
        })),
      },
    ],
  }

  const stateColor = STATE_COLOR[latest.state as string] ?? CHART.accent
  const unavailable = (data.shepherd_unavailable ?? []).map((x) => x[0])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-label text-sf-ink-3">
          广度快照最新日 {shepherd['date'] ? String(shepherd['date']).slice(0, 10) : '—'} ·
          状态判定最新真值日 {latest.date ?? '—'}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Stat label="市场状态" value={latest.state ?? '—'} color={stateColor} />
        {BREADTH_FIELDS.map((f) => (
          <Stat
            key={f.key}
            label={f.label}
            value={
              f.key.endsWith('ratio')
                ? num(shepherd[f.key]) != null
                  ? `${num(shepherd[f.key])!.toFixed(1)}%`
                  : '—'
                : (num(shepherd[f.key]) != null ? String(num(shepherd[f.key])) : '—')
            }
            color={f.key === 'red_ratio' ? (num(shepherd[f.key]) != null && num(shepherd[f.key])! >= 50 ? CHART.up : CHART.down) : undefined}
          />
        ))}
      </div>

      <Card title="红盘率历史趋势（广度快照）">
        <EChart option={trendOption} height={240} ariaLabel="红盘率历史趋势折线图" />
      </Card>

      <Card title="状态分布（全样本各状态天数）">
        <EChart option={distOption} height={220} ariaLabel="市场状态分布柱状图" />
      </Card>

      <Card title={`历史相似日速览（Top ${Math.min(analogs.length, 4)}）`}>
        {analogs.length === 0 ? (
          <div className="text-xs text-sf-ink-3">无相似日。</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {analogs.slice(0, 4).map((a, i) => (
              <div
                key={i}
                className="rounded-tile bg-sf-surface-2 border border-sf-line px-3 py-2 text-xs"
                style={{ borderLeft: `4px solid ${STATE_COLOR[a.state as string] ?? CHART.accent}` }}
              >
                <div className="text-sf-ink font-medium">{a.date}</div>
                <div className="text-sf-ink-3">
                  状态 {a.state ?? '—'} · 距离 {num(a.distance)?.toFixed(2) ?? '—'}
                </div>
                <div className="text-sf-ink-3">后5日红盘率 {fmtPct((a.forward?.d5 as { avg_red?: number } | undefined)?.avg_red)}</div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-2 text-xs text-sf-ink-3">⚠️ 历史相似 ≠ 预测，仅供情境参照。</div>
      </Card>

      {unavailable.length > 0 && (
        <Card title="数据源缺失字段（诚实带出）">
          <div className="text-xs text-sf-ink-3">
            ⚠️ 以下字段数据源缺失：{unavailable.slice(0, 3).join('、')}
            {unavailable.length > 3 ? ' 等' : ''}
          </div>
        </Card>
      )}

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}

function fmtPct(v: unknown): string {
  const n = num(v)
  return n == null ? '—' : `${n.toFixed(1)}%`
}
