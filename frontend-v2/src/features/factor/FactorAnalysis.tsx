import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { FactorAnalysis as FactorAnalysisData } from '@/api/schemas/read'
import type { FactorAnalysisParams } from '@/api/read'
import { useFactorAnalysis } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 71 页「因子分析」V2 化落地（对应 IA-MIGRATION.md W4 后续簇）。
 * 数据来源：useFactorAnalysis → GET /api/v2/read/factor-analysis（backend 复用
 * modules.factor_analysis 纯函数 + page_utils.hist_cached 实时取数）。
 *
 * 三图：① 逐期 IC 柱状（红涨绿跌按 IC 正负）② 分层累计收益折线（高因子层红 / 低因子层绿）
 * ③ 多空累计净值折线。IC 汇总用 Stat 卡呈现。
 *
 * ⚠️ 诚实红线（DESIGN.md / modules.factor_analysis）：
 *  - 有效标的<3 或全取数失败 → 后端 status=error，前端判空渲染「数据不足」，不补零、不编造；
 *  - NaN/Inf 后端已清洗为 null，页面显示「—」；
 *  - 因子分析是统计规律（IC/IR），非买卖指令，页脚必须原样带出后端 note。
 */
const FACTORS: Record<string, string> = {
  momentum: '20 日动量',
  reversal: '5 日反转',
  volatility: '20 日波动率',
  turnover: '20 日平均换手',
}

function fmt(v: unknown, p = 4): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(p) : '—'
}

export function FactorAnalysis() {
  // 表单态（未应用）与已应用参数态分离：点「运行分析」才触发 query。
  const [form, setForm] = useState<FactorAnalysisParams>({
    codes: ['600519', '000001', '300750'],
    days: 250,
    factor: 'momentum',
    n_layers: 5,
    forward: 1,
  })
  const [params, setParams] = useState<FactorAnalysisParams>(form)

  const q = useFactorAnalysis(params)
  const data = q.data

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">因子分析</h2>

      {/* 控制区 */}
      <Card title="分析参数">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            标的代码（逗号分隔，6 位）
            <input
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.codes.join(',')}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  codes: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter((s) => /^\d{6}$/.test(s)),
                }))
              }
            />
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            因子
            <select
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.factor}
              onChange={(e) => setForm((f) => ({ ...f, factor: e.target.value }))}
            >
              {Object.entries(FACTORS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            回看天数
            <input
              type="number"
              min={20}
              max={1000}
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.days}
              onChange={(e) => setForm((f) => ({ ...f, days: Math.max(20, Math.min(1000, Number(e.target.value) || 250)) }))}
            />
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            分层数
            <input
              type="number"
              min={2}
              max={10}
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.n_layers}
              onChange={(e) => setForm((f) => ({ ...f, n_layers: Math.max(2, Math.min(10, Number(e.target.value) || 5)) }))}
            />
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            持有期(forward)
            <input
              type="number"
              min={1}
              max={20}
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.forward}
              onChange={(e) => setForm((f) => ({ ...f, forward: Math.max(1, Math.min(20, Number(e.target.value) || 1)) }))}
            />
          </label>
        </div>
        <button
          type="button"
          onClick={() => setParams(form)}
          className="mt-3 rounded-tile bg-sf-accent px-4 py-1.5 text-sm font-medium text-sf-ink hover:opacity-90"
        >
          运行分析
        </button>
      </Card>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && (!data.ic_series || data.ic_series.length === 0)}
        emptyLabel="暂无因子数据"
        emptyHint="有效标的不足 3 只或取数全部失败，无法得出因子结论（后端 honest 降级）"
      >
        {data ? <FactorBody data={data} /> : null}
      </QueryState>
    </div>
  )
}

function FactorBody({ data }: { data: FactorAnalysisData }) {
  const summary = data.ic_summary ?? {}
  const icRows = data.ic_series ?? []
  const dates = icRows.map((r) => r.date)
  const icVals = icRows.map((r) => (typeof r.ic === 'number' && Number.isFinite(r.ic) ? r.ic : null))

  // 分层累计：列名除 date 外为层号字符串（0..n-1）
  const layerRows = data.layered_cum ?? []
  const layerDates = layerRows.map((r) => String(r['date'] ?? ''))
  const layerKeys = layerRows.length
    ? Object.keys(layerRows[0])
        .filter((k) => k !== 'date')
        .sort((a, b) => Number(a) - Number(b))
    : []
  const layerColors = layerKeys.map((_, i) => {
    if (layerKeys.length <= 1) return CHART.accent
    if (i === 0) return CHART.up // 最高因子组
    if (i === layerKeys.length - 1) return CHART.down // 最低因子组
    return CHART.accent
  })
  const layerSeries = layerKeys.map((key, i) => ({
    name: `第 ${Number(key) + 1} 层`,
    type: 'line' as const,
    smooth: true,
    showSymbol: false,
    data: layerRows.map((r) => {
      const v = r[key]
      return typeof v === 'number' && Number.isFinite(v) ? v : null
    }),
    itemStyle: { color: layerColors[i] },
    lineStyle: { color: layerColors[i], width: 1.5 },
  }))

  // 多空累计：long_short_cum[{date,ic}]
  const lsRows = data.long_short_cum ?? []
  const lsDates = lsRows.map((r) => r.date)
  const lsVals = lsRows.map((r) => (typeof r.ic === 'number' && Number.isFinite(r.ic) ? r.ic : null))
  const lastLs = lsVals.filter((v): v is number => v != null).at(-1)
  const lsColor = lastLs == null ? CHART.accent : lastLs >= 0 ? CHART.up : CHART.down

  const icOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
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
        type: 'bar',
        data: icVals.map((v) => ({
          value: v,
          itemStyle: { color: v == null ? CHART.line : v >= 0 ? CHART.up : CHART.down },
        })),
      },
    ],
  }

  const layerOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: layerSeries.map((s) => s.name), textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 44, right: 16, top: 28, bottom: 28 },
    xAxis: {
      type: 'category',
      data: layerDates,
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2, formatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: layerSeries,
  }

  const lsOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: lsDates,
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink2, formatter: (v: number) => `${(v * 100).toFixed(1)}%` },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: lsVals,
        itemStyle: { color: lsColor },
        lineStyle: { color: lsColor, width: 1.5 },
        areaStyle: { color: lsColor, opacity: 0.08 },
      },
    ],
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-label text-sf-ink-3">
          因子 {FACTORS[data.factor] ?? data.factor} · 回看 {data.days} 日 · 分层 {data.n_layers} · 持有 {data.forward} 日
        </span>
        <span className="text-label text-sf-ink-3">权威数据日 {data.date ?? '—'}</span>
      </div>

      {/* IC 汇总 Stat 卡 */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Stat label="样本期数 n" value={fmt(summary.n, 0)} />
        <Stat label="IC 均值" value={fmt(summary.ic_mean)} color={typeof summary.ic_mean === 'number' && summary.ic_mean >= 0 ? CHART.up : CHART.down} />
        <Stat label="IC 标准差" value={fmt(summary.ic_std)} />
        <Stat label="IR" value={fmt(summary.ir)} color={typeof summary.ir === 'number' && summary.ir >= 0 ? CHART.up : CHART.down} />
        <Stat label="正 IC 占比" value={fmt(summary.positive_ratio != null ? (summary.positive_ratio as number) * 100 : null, 1)} sub="%" />
        <Stat label="t 值" value={fmt(summary.t_stat)} />
      </div>

      {/* 取数错误清单（诚实带出，不隐藏） */}
      {data.errs && data.errs.length > 0 && (
        <Card title="取数错误清单">
          <ul className="text-xs text-sf-ink-3 list-disc list-inside space-y-1">
            {data.errs.map((e, i) => (
              <li key={i}>
                {String(e[0] ?? '')}：{String(e[1] ?? '')}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="逐期 IC 序列">
        <EChart option={icOption} height={240} ariaLabel="因子逐期信息系数 IC 柱状图，红色为正 IC、绿色为负 IC" />
      </Card>

      <Card title="分层累计收益（因子由大到小分层的净值曲线）">
        <EChart option={layerOption} height={280} ariaLabel="因子分层累计收益折线图，最高因子层为红、最低因子层为绿" />
      </Card>

      <Card title="多空组合累计净值">
        <EChart option={lsOption} height={240} ariaLabel="因子多空组合累计净值折线图" />
      </Card>

      {data.note && (
        <div className="text-xs text-sf-ink-3">
          {data.note} 因子分析是统计意义上的规律，非买卖指令。
        </div>
      )}
    </div>
  )
}
