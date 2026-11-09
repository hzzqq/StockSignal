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
 * 56 页「市场状态机」V2 化落地。
 * 数据来源：useMarketPanorama → GET /api/v2/read/market-panorama（后端复用
 * modules.market_regime.regime_report，读 data/shepherd_history.json，离线零网）。
 *
 * 展示：最新状态 + 置信度、状态分布、状态转移热力图、历史相似日及其后市表现。
 * 与 57 页共享同一后端（不重复计算）。
 *
 * ⚠️ 诚实红线：regime 不可用（广度历史缺失）→ 后端 status=error，前端判空渲染「数据不足」；
 * 数值缺失为 null → 显示「—」；历史相似 ≠ 预测，页脚带出后端 note。
 */

// 状态语义色：涨系红、跌系绿、震荡中性（A 股反向配色，红涨绿跌）
const STATE_COLOR: Record<string, string> = {
  普涨: CHART.up,
  结构牛: CHART.up,
  震荡: CHART.accent,
  恐慌: CHART.down,
  暴跌: CHART.down,
  暴涨: CHART.up,
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export function MarketRegime() {
  const [k, setK] = useState<number>(8)
  const params: MarketPanoramaParams = { k }
  const q = useMarketPanorama(params)
  const data = q.data

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">市场状态机</h2>

      <Card title="类比参数">
        <div className="flex items-center gap-3">
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
        </div>
      </Card>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && !data.regime?.latest}
        emptyLabel="暂无状态机数据"
        emptyHint="广度历史缺失或取数失败，无法判定市场状态（后端 honest 降级）"
      >
        {data ? <RegimeBody data={data} /> : null}
      </QueryState>
    </div>
  )
}

function RegimeBody({ data }: { data: MarketPanoramaData }) {
  const regime = data.regime ?? {}
  const latest = regime.latest ?? {}
  const dist = regime.state_distribution ?? {}
  const matrix = regime.transition_matrix ?? {}
  const analogs = regime.analogs ?? []
  const states = Object.keys(dist)

  const distOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: states,
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
        data: states.map((s) => ({
          value: num(dist[s]),
          itemStyle: { color: STATE_COLOR[s] ?? CHART.accent },
        })),
      },
    ],
  }

  const heatStates = states
  const heatData: Array<[number, number, number | null]> = []
  heatStates.forEach((a, i) => {
    const row = matrix[a] ?? {}
  heatStates.forEach((b, j) => {
    heatData.push([j, i, num(row[b])])
  })
  })
  const heatOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { position: 'top' },
    grid: { left: 64, right: 16, top: 16, bottom: 56 },
    xAxis: {
      type: 'category',
      data: heatStates,
      axisLabel: { color: CHART.ink2, rotate: 30 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'category',
      data: heatStates,
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    visualMap: {
      min: 0,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: CHART.ink2 },
      inRange: { color: [CHART.down, CHART.line, CHART.up] },
    },
    series: [
      {
        type: 'heatmap',
        data: heatData,
        label: { show: true, color: CHART.ink2, fontSize: 10 },
      },
    ],
  }

  const stateColor = STATE_COLOR[latest.state as string] ?? CHART.accent

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-label text-sf-ink-3">
          最新真值日 {latest.date ?? '—'} · 数据区间 {regime.data?.start ?? '—'} ~ {regime.data?.end ?? '—'} · 样本 {regime.data?.rows ?? '—'} 天
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <Stat label="当前市场状态" value={latest.state ?? '—'} color={stateColor} />
        <Stat label="状态置信度" value={latest.confidence != null ? `${((latest.confidence as number) * 100).toFixed(0)}%` : '—'} />
        <Stat label="红盘率" value={fmtPct((latest.metrics as Record<string, unknown>)?.red_ratio)} color={CHART.ink2} />
        <Stat label="涨停/跌停" value={`${num((latest.metrics as Record<string, unknown>)?.limit_up) ?? '—'} / ${num((latest.metrics as Record<string, unknown>)?.limit_down) ?? '—'}`} color={CHART.ink2} />
      </div>

      <Card title="状态分布（全样本各状态天数）">
        <EChart option={distOption} height={240} ariaLabel="市场状态分布柱状图，按状态语义着色" />
      </Card>

      <Card title="状态转移概率热力图（行=前一日状态，列=次日状态）">
        <EChart option={heatOption} height={320} ariaLabel="市场状态转移概率热力图" />
      </Card>

      <Card title={`历史相似日（Top ${analogs.length}，距最新日最近的市场形态）`}>
        {analogs.length === 0 ? (
          <div className="text-xs text-sf-ink-3">无相似日（历史样本不足或参数异常）。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-sf-ink">
              <thead>
                <tr className="text-sf-ink-3 border-b border-sf-line">
                  <th className="text-left py-1.5 pr-3">相似日</th>
                  <th className="text-right py-1.5 pr-3">距离</th>
                  <th className="text-left py-1.5 pr-3">状态</th>
                  <th className="text-right py-1.5 pr-3">红盘率</th>
                  <th className="text-right py-1.5 pr-3">后5日红盘率</th>
                  <th className="text-right py-1.5">后5日中位变化</th>
                </tr>
              </thead>
              <tbody>
        {analogs.map((a, i) => {
          const fwd = a.forward?.d5 as
            | { avg_red?: number; up_frac?: number; median_delta?: number }
            | undefined
          return (
                    <tr key={i} className="border-b border-sf-line/60">
                      <td className="py-1.5 pr-3">{a.date}</td>
                      <td className="py-1.5 pr-3 text-right">{num(a.distance)?.toFixed(2) ?? '—'}</td>
                      <td className="py-1.5 pr-3" style={{ color: STATE_COLOR[a.state as string] ?? CHART.ink2 }}>{a.state ?? '—'}</td>
                      <td className="py-1.5 pr-3 text-right">{fmtPct(a.metrics?.red_ratio)}</td>
                      <td className="py-1.5 pr-3 text-right">{fmtPct(fwd?.avg_red)}</td>
                      <td className="py-1.5 text-right">{fmtPct(fwd?.median_delta)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-2 text-xs text-sf-ink-3">⚠️ 历史相似 ≠ 预测，下表为相似日之后真实市场表现统计，仅供情境参照。</div>
      </Card>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}

function fmtPct(v: unknown): string {
  const n = num(v)
  return n == null ? '—' : `${n.toFixed(1)}%`
}
