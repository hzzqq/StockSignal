import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { Backtest as BacktestData } from '@/api/schemas/read'
import type { BacktestParams } from '@/api/read'
import { useBacktest } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 30 页「策略回测」V2 化落地（对应 IA-MIGRATION.md W4 后续簇）。
 * 数据来源：useBacktest → GET /api/v2/read/backtest（backend 复用
 * modules.backtest.Backtester.run 一体取数+信号+模拟）。
 *
 * 三态：加载中 / 取数失败（error）/ 无数据（empty）。
 * 展示：摘要指标卡（累计收益/年化/最大回撤/夏普/胜率/盈亏比/单笔均值/交易次数/持仓占比）
 *      + 资金曲线（累计收益 + 回撤双轴）+ 逐笔交易明细表。
 *
 * ⚠️ 诚实红线（DESIGN.md / modules.backtest.BacktestResult）：
 *  - 取数为空 → 后端 status=error（insufficient_data），前端判空渲染「数据不足」，不补零曲线；
 *  - NaN/Inf 后端已清洗为 null，页面显示「—」（盈亏比全胜/无交易时为 null，不显示 0）；
 *  - 回测是历史模拟，非未来收益保证，页脚原样带出后端 note。
 */
const STRATEGIES: Record<string, string> = {
  multi_factor: '多因子',
  ma_cross: '均线交叉',
  event_driven: '事件驱动',
}

function fmtPct(v: unknown, p = 2): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(p)}%` : '—'
}
function fmt(v: unknown, p = 2): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(p) : '—'
}

export function Backtest() {
  const [form, setForm] = useState<BacktestParams>({
    ticker: '600519',
    start: '2024-01-01',
    end: '2024-12-31',
    strategy: 'multi_factor',
  })
  const [params, setParams] = useState<BacktestParams>(form)

  const q = useBacktest(params)
  const data = q.data

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">策略回测</h2>

      {/* 控制区 */}
      <Card title="回测参数">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            标的代码（6 位）
            <input
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.ticker}
              onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value.trim() }))}
            />
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            起始日期
            <input
              type="date"
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.start}
              onChange={(e) => setForm((f) => ({ ...f, start: e.target.value }))}
            />
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            结束日期
            <input
              type="date"
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.end}
              onChange={(e) => setForm((f) => ({ ...f, end: e.target.value }))}
            />
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            策略
            <select
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.strategy}
              onChange={(e) => setForm((f) => ({ ...f, strategy: e.target.value }))}
            >
              {Object.entries(STRATEGIES).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button
          type="button"
          onClick={() => setParams(form)}
          className="mt-3 rounded-tile bg-sf-accent px-4 py-1.5 text-sm font-medium text-sf-ink hover:opacity-90"
        >
          运行回测
        </button>
      </Card>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && (!data.equity_curve || data.equity_curve.length === 0)}
        emptyLabel="暂无回测数据"
        emptyHint="该标的在所选区间取数为空，无法回测（后端 honest 降级）"
      >
        {data ? <BacktestBody data={data} /> : null}
      </QueryState>
    </div>
  )
}

function BacktestBody({ data }: { data: BacktestData }) {
  const curve = data.equity_curve ?? []
  const dates = curve.map((r) => r.date)
  const cumVals = curve.map((r) =>
    typeof r.cumulative_return === 'number' && Number.isFinite(r.cumulative_return) ? r.cumulative_return : null,
  )
  const ddVals = curve.map((r) =>
    typeof r.drawdown === 'number' && Number.isFinite(r.drawdown) ? r.drawdown : null,
  )
  const lastCum = cumVals.filter((v): v is number => v != null).at(-1)
  const cumColor = lastCum == null ? CHART.accent : lastCum >= 0 ? CHART.up : CHART.down

  const curveOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['累计收益', '回撤'], textStyle: { color: CHART.ink2 }, top: 0 },
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
        name: '累计%',
        axisLabel: { color: CHART.ink2, formatter: (v: number) => `${v.toFixed(0)}%` },
        splitLine: { lineStyle: { color: CHART.line } },
      },
      {
        type: 'value',
        name: '回撤%',
        axisLabel: { color: CHART.ink2, formatter: (v: number) => `${v.toFixed(0)}%` },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '累计收益',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 0,
        data: cumVals,
        itemStyle: { color: cumColor },
        lineStyle: { color: cumColor, width: 1.5 },
        areaStyle: { color: cumColor, opacity: 0.08 },
      },
      {
        name: '回撤',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: ddVals,
        itemStyle: { color: CHART.down },
        lineStyle: { color: CHART.down, width: 1, type: 'dashed' },
      },
    ],
  }

  const trades = data.trades ?? []
  const meta = data
  const totalRet = meta.total_return_pct
  const annRet = meta.annualized_return_pct
  const sharpe = meta.sharpe_ratio
  const winRet = meta.avg_trade_return_pct

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-label text-sf-ink-3">
          标的 {data.ticker} · 策略 {STRATEGIES[data.strategy] ?? data.strategy} · {data.start} ~ {data.end}
        </span>
        <span className="text-label text-sf-ink-3">权威数据日 {data.date ?? '—'}</span>
      </div>

      {/* 摘要指标 Stat 卡 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <Stat label="累计收益" value={fmtPct(totalRet)} color={typeof totalRet === 'number' ? (totalRet >= 0 ? CHART.up : CHART.down) : undefined} />
        <Stat label="年化收益" value={fmtPct(annRet)} color={typeof annRet === 'number' ? (annRet >= 0 ? CHART.up : CHART.down) : undefined} />
        <Stat label="最大回撤" value={fmtPct(meta.max_drawdown_pct)} color={CHART.down} />
        <Stat label="夏普比率" value={fmt(sharpe)} color={typeof sharpe === 'number' ? (sharpe >= 0 ? CHART.up : CHART.down) : undefined} />
        <Stat label="胜率" value={fmtPct(meta.win_rate_pct, 1)} sub="%" />
        <Stat label="盈亏比" value={fmt(meta.profit_factor)} sub={meta.profit_factor == null ? '（全胜/无交易）' : ''} />
        <Stat label="单笔均值" value={fmtPct(winRet)} color={typeof winRet === 'number' ? (winRet >= 0 ? CHART.up : CHART.down) : undefined} />
        <Stat label="交易次数" value={fmt(meta.trade_count, 0)} />
        <Stat label="持仓占比" value={fmtPct(meta.exposure_pct, 1)} sub="%" />
        <Stat label="初始资金" value={typeof meta.initial_capital === 'number' ? `¥${meta.initial_capital.toLocaleString('zh-CN')}` : '—'} />
      </div>

      <Card title="资金曲线（累计收益 + 回撤）">
        <EChart option={curveOption} height={320} ariaLabel="策略回测资金曲线图，展示累计收益与回撤" />
      </Card>

      <Card title={`逐笔交易明细（${trades.length} 笔）`}>
        {trades.length === 0 ? (
          <div className="text-xs text-sf-ink-3">该区间无完整交易（信号未触发或持仓未了结）。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-sf-ink">
              <thead>
                <tr className="text-sf-ink-3 border-b border-sf-line">
                  <th className="text-left py-1.5 pr-3">买入日</th>
                  <th className="text-left py-1.5 pr-3">卖出日</th>
                  <th className="text-right py-1.5 pr-3">买入价</th>
                  <th className="text-right py-1.5 pr-3">卖出价</th>
                  <th className="text-right py-1.5 pr-3">收益率</th>
                  <th className="text-left py-1.5 pr-3">离场原因</th>
                  <th className="text-right py-1.5">持有(日)</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => {
                  const p = t.profit_pct
                  const color = typeof p === 'number' ? (p >= 0 ? CHART.up : CHART.down) : CHART.ink2
                  return (
                    <tr key={i} className="border-b border-sf-line/60">
                      <td className="py-1.5 pr-3">{t.entry_date ?? '—'}</td>
                      <td className="py-1.5 pr-3">{t.exit_date ?? '—'}</td>
                      <td className="py-1.5 pr-3 text-right">{typeof t.entry_price === 'number' ? t.entry_price.toFixed(2) : '—'}</td>
                      <td className="py-1.5 pr-3 text-right">{typeof t.exit_price === 'number' ? t.exit_price.toFixed(2) : '—'}</td>
                      <td className="py-1.5 pr-3 text-right" style={{ color }}>
                        {typeof p === 'number' ? `${p >= 0 ? '+' : ''}${p.toFixed(2)}%` : '—'}
                      </td>
                      <td className="py-1.5 pr-3">{t.exit_reason ?? '—'}</td>
                      <td className="py-1.5 text-right">{typeof t.bars_held === 'number' ? t.bars_held : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data.note && (
        <div className="text-xs text-sf-ink-3">
          {data.note} 回测为历史模拟，不代表未来收益。
        </div>
      )}
    </div>
  )
}
