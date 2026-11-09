import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { Portfolio as PortfolioData } from '@/api/schemas/read'
import { usePortfolio } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 45 页「持仓中心」V2 化落地（对应 IA-MIGRATION.md Tier1）。
 * 数据来源：usePortfolio → GET /api/v2/read/portfolio（backend 复用
 * modules.portfolio.PortfolioManager，本地 data/portfolio.csv 模拟持仓）。
 *
 * 三态：加载中 / 取数失败（error）/ 无持仓（empty）。
 * 分段：持仓（逐批盈亏表）/ 收益归因（贡献条形 + 权重条形 + 净值曲线）。
 *
 * ⚠️ 诚实红线（DESIGN.md / modules.portfolio）：
 *  - 持仓为本地模拟/历史数据，仅供学习；现价离线口径可能为静态样本，页脚原样带出后端 note；
 *  - 净值曲线为尽力而为的历史还原，curve_available=false 时如实标注、不补零曲线；
 *  - NaN/Inf 后端已清洗为 null，缺值显示「—」，绝不补 0。
 */
type View = 'positions' | 'attribution'

function f2(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—'
}
function pct(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(2)}%` : '—'
}
function pnlColor(v: unknown): string | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? (v >= 0 ? CHART.up : CHART.down) : undefined
}

export function Portfolio() {
  const [view, setView] = useState<View>('positions')
  const q = usePortfolio()
  const data = q.data

  return (
    <div className="flow">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-lg font-semibold">持仓中心</h2>
        <div className="flex gap-1 rounded-tile bg-sf-surface-2 p-1 text-xs">
          <button
            type="button"
            onClick={() => setView('positions')}
            className={`rounded-tile px-3 py-1.5 ${view === 'positions' ? 'bg-sf-accent text-sf-ink' : 'text-sf-ink-3'}`}
          >
            持仓
          </button>
          <button
            type="button"
            onClick={() => setView('attribution')}
            className={`rounded-tile px-3 py-1.5 ${view === 'attribution' ? 'bg-sf-accent text-sf-ink' : 'text-sf-ink-3'}`}
          >
            收益归因
          </button>
        </div>
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && (!data.positions || data.positions.length === 0)}
        emptyLabel="暂无持仓数据"
        emptyHint="本地持仓文件为空或缺失（后端 honest 降级）"
      >
        {data ? (
          view === 'positions' ? (
            <PositionsView data={data} />
          ) : (
            <AttributionView data={data} />
          )
        ) : null}
      </QueryState>
    </div>
  )
}

function PositionsView({ data }: { data: PortfolioData }) {
  const s = data.summary ?? {}
  const positions = data.positions ?? []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <Stat label="总持仓成本" value={typeof s.total_cost === 'number' ? `¥${s.total_cost.toLocaleString('zh-CN')}` : '—'} />
        <Stat label="总市值" value={typeof s.total_market_value === 'number' ? `¥${s.total_market_value.toLocaleString('zh-CN')}` : '—'} />
        <Stat label="总盈亏" value={pct(s.total_pnl_pct)} color={pnlColor(s.total_pnl)} />
        <Stat label="总盈亏额" value={typeof s.total_pnl === 'number' ? `¥${s.total_pnl.toLocaleString('zh-CN')}` : '—'} color={pnlColor(s.total_pnl)} />
        <Stat label="持仓批数" value={f2(s.position_count)} />
      </div>

      <Card title={`持仓明细（${positions.length} 批）`}>
        {positions.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无持仓。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-sf-ink">
              <thead>
                <tr className="text-sf-ink-3 border-b border-sf-line">
                  <th className="text-left py-1.5 pr-3">代码</th>
                  <th className="text-left py-1.5 pr-3">名称</th>
                  <th className="text-right py-1.5 pr-3">买入价</th>
                  <th className="text-right py-1.5 pr-3">现价</th>
                  <th className="text-right py-1.5 pr-3">剩余股数</th>
                  <th className="text-right py-1.5 pr-3">成本</th>
                  <th className="text-right py-1.5 pr-3">市值</th>
                  <th className="text-right py-1.5 pr-3">盈亏额</th>
                  <th className="text-right py-1.5">盈亏%</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={`${p.ticker}-${i}`} className="border-b border-sf-line/60">
                    <td className="py-1.5 pr-3">{p.ticker}</td>
                    <td className="py-1.5 pr-3">{p.name ?? '—'}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.buy_price)}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.current_price)}</td>
                    <td className="py-1.5 pr-3 text-right">{typeof p.remaining_shares === 'number' ? p.remaining_shares.toLocaleString('zh-CN') : '—'}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.cost)}</td>
                    <td className="py-1.5 pr-3 text-right">{f2(p.market_value)}</td>
                    <td className="py-1.5 pr-3 text-right" style={{ color: pnlColor(p.pnl) }}>
                      {f2(p.pnl)}
                    </td>
                    <td className="py-1.5 text-right" style={{ color: pnlColor(p.pnl_pct) }}>
                      {pct(p.pnl_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}

function AttributionView({ data }: { data: PortfolioData }) {
  const attr = data.attribution ?? []
  const weights = data.weights ?? []
  const curve = data.curve ?? []
  const curveAvailable = !!data.curve_available

  const contributionOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 96, right: 24, top: 16, bottom: 24 },
    xAxis: { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}%' }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'category', data: attr.map((a) => a.name ?? a.ticker).reverse(), axisLabel: { color: CHART.ink2 }, axisLine: { lineStyle: { color: CHART.line } } },
    series: [
      {
        type: 'bar',
        data: attr
          .map((a) => ({
            value: typeof a.contribution === 'number' ? a.contribution : null,
            itemStyle: { color: a.contribution == null ? CHART.ink2 : a.contribution >= 0 ? CHART.up : CHART.down },
          }))
          .reverse(),
      },
    ],
  }

  const weightOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 96, right: 24, top: 16, bottom: 24 },
    xAxis: { type: 'value', max: 100, axisLabel: { color: CHART.ink2, formatter: '{value}%' }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'category', data: weights.map((w) => w.name ?? w.ticker).reverse(), axisLabel: { color: CHART.ink2 }, axisLine: { lineStyle: { color: CHART.line } } },
    series: [{ type: 'bar', data: weights.map((w) => (typeof w.weight_pct === 'number' ? w.weight_pct : null)), itemStyle: { color: CHART.accent } }],
  }

  const dates = curve.map((c) => c.date)
  const pfVals = curve.map((c) => (typeof c.portfolio === 'number' && Number.isFinite(c.portfolio) ? c.portfolio : null))
  const bmVals = curve.map((c) => (typeof c.benchmark === 'number' && Number.isFinite(c.benchmark) ? c.benchmark : null))
  const curveOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['组合净值', '沪深300'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 48, right: 24, top: 28, bottom: 28 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: CHART.ink2, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'value', axisLabel: { color: CHART.ink2 }, splitLine: { lineStyle: { color: CHART.line } } },
    series: [
      { name: '组合净值', type: 'line', smooth: true, showSymbol: false, data: pfVals, itemStyle: { color: CHART.up }, lineStyle: { color: CHART.up, width: 1.5 } },
      { name: '沪深300', type: 'line', smooth: true, showSymbol: false, data: bmVals, itemStyle: { color: CHART.ink2 }, lineStyle: { color: CHART.ink2, width: 1, type: 'dashed' } },
    ],
  }

  return (
    <div className="space-y-4">
      <Card title="盈亏贡献（按个股，红涨绿跌）">
        {attr.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无归因数据。</div>
        ) : (
          <EChart option={contributionOption} height={Math.max(160, attr.length * 28)} ariaLabel="盈亏贡献条形图" />
        )}
      </Card>

      <Card title="持仓市值占比">
        {weights.length === 0 ? (
          <div className="text-xs text-sf-ink-3">暂无权重数据。</div>
        ) : (
          <EChart option={weightOption} height={Math.max(160, weights.length * 28)} ariaLabel="持仓市值占比条形图" />
        )}
      </Card>

      <Card title="组合净值曲线（基准沪深300，尽力而为）">
        {curveAvailable && curve.length >= 2 ? (
          <EChart option={curveOption} height={300} ariaLabel="组合净值曲线图，对比沪深300基准" />
        ) : (
          <div className="text-xs text-sf-ink-3">
            净值曲线需要个股日线数据，当前离线口径无法还原（后端诚实降级，不补零）。
          </div>
        )}
      </Card>

      {data.note && <div className="text-xs text-sf-ink-3">{data.note}</div>}
    </div>
  )
}
