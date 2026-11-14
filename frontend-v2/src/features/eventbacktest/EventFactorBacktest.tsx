import { useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { EventBacktest } from '@/api/schemas/read'
import type { EventBacktestParams } from '@/api/read'
import { useEventBacktest } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 事件因子回测页（全新页，对应 IA-MIGRATION W4 后续簇 / 量化硬证据）。
 * 数据来源：useEventBacktest → GET /api/v2/read/event-backtest（backend 复用
 * modules.event_backtest.run 离线 walk-forward 计算）。
 *
 * 三态：加载中 / 取数失败（error）/ 无数据（available=false 或空分布）。
 * 展示：参数控制（预设事件 + 自定义指标/方向/分位/horizon）+ 统计卡（n/基准率/事件率/
 * 边缘 pp/z）+ 分布对比图（事件 vs 基准）+ 触发示例 + 诚实脚注（非指数收益率、z 缺失说明）。
 *
 * ⚠️ 诚实红线（modules.event_backtest + DESIGN.md）：
 *  - 取数为空 / 触发 0 次 → 后端 available=false，前端判空渲染 reason，不补零；
 *  - z 为 null（样本不足 MIN_N）→ 显式「未检验」，不伪造成显著性；
 *  - 本页衡量的是「市场红盘日占比」广度层面表现，非指数收益率，脚原本样带出。
 */
type MetricKey = EventBacktestParams['metric']
type Direction = EventBacktestParams['direction']
type Horizon = EventBacktestParams['horizon']

const PRESETS: Record<string, { label: string; metric: MetricKey; direction: Direction; quantile: number; why: string }> = {
  panic: { label: '极端恐慌', metric: 'limit_down_ratio', direction: 'high', quantile: 0.1, why: '跌停占比达历史前 10%：恐慌出清，次日红盘概率抬升（sentiment_edge 已验证）' },
  euphoria: { label: '极端亢奋', metric: 'limit_up_ratio', direction: 'high', quantile: 0.1, why: '涨停占比达历史前 10%：情绪过热，后续广度易回落' },
  breadth_ice: { label: '广度冰点', metric: 'red_ratio', direction: 'low', quantile: 0.1, why: '红盘率落历史后 10%：广度冰点，关注否极泰来' },
}

const METRIC_LABELS: Record<MetricKey, string> = {
  red_ratio: '红盘率',
  limit_up_ratio: '涨停占比',
  limit_down_ratio: '跌停占比',
}

function fmtPct(v: unknown, p = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(p)}%` : '—'
}
function fmtNum(v: unknown, p = 2): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(p) : '—'
}

export function EventFactorBacktest() {
  const [preset, setPreset] = useState<string>('panic')
  const [form, setForm] = useState<EventBacktestParams>({
    metric: 'limit_down_ratio',
    quantile: 0.1,
    direction: 'high',
    horizon: 1,
  })
  const [params, setParams] = useState<EventBacktestParams>(form)

  const q = useEventBacktest(params)
  const data = q.data

  function applyPreset(key: string) {
    const p = PRESETS[key]
    if (!p) return
    setPreset(key)
    setForm((f) => ({ ...f, metric: p.metric, direction: p.direction, quantile: p.quantile }))
  }
  function run() {
    setParams(form)
  }

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">事件因子回测</h2>
      <p className="text-body text-sf-ink-3">
        选一个市场广度事件，看它在前向 N 日里对「市场红盘日占比」的统计边缘。离线 walk-forward，无未来函数。
      </p>

      {/* 控制区 */}
      <Card title="事件设定">
        <div className="flex flex-wrap gap-2 mb-3">
          {Object.entries(PRESETS).map(([k, p]) => (
            <button
              key={k}
              type="button"
              onClick={() => applyPreset(k)}
              className={
                'rounded-tile border px-3 py-1.5 text-sm transition-colors ' +
                (preset === k
                  ? 'bg-sf-accent text-sf-ink border-sf-accent'
                  : 'bg-sf-surface-2 text-sf-ink-2 border-sf-line hover:text-sf-ink')
              }
              title={p.why}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            指标
            <select
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.metric}
              onChange={(e) => setForm((f) => ({ ...f, metric: e.target.value as MetricKey }))}
            >
              {(Object.keys(METRIC_LABELS) as MetricKey[]).map((m) => (
                <option key={m} value={m}>
                  {METRIC_LABELS[m]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            方向
            <select
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.direction}
              onChange={(e) => setForm((f) => ({ ...f, direction: e.target.value as Direction }))}
            >
              <option value="high">达历史高位（前 X%）</option>
              <option value="low">落历史低位（后 X%）</option>
            </select>
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            尾部比例
            <select
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.quantile}
              onChange={(e) => setForm((f) => ({ ...f, quantile: Number(e.target.value) }))}
            >
              {[0.05, 0.1, 0.2].map((qt) => (
                <option key={qt} value={qt}>
                  前/后 {qt * 100}%
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-sf-ink-3 flex flex-col gap-1">
            前向天数
            <select
              className="rounded-tile bg-sf-surface-2 border border-sf-line px-2 py-1.5 text-sm text-sf-ink"
              value={form.horizon}
              onChange={(e) => setForm((f) => ({ ...f, horizon: Number(e.target.value) as Horizon }))}
            >
              {([1, 3, 5, 10] as Horizon[]).map((h) => (
                <option key={h} value={h}>
                  {h} 日
                </option>
              ))}
            </select>
          </label>
        </div>
        <button
          type="button"
          onClick={run}
          className="mt-3 rounded-tile bg-sf-accent px-4 py-1.5 text-sm font-medium text-sf-ink hover:opacity-90"
        >
          运行回测
        </button>
      </Card>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && data.available === false}
        emptyLabel={data && data.reason ? data.reason : '暂无回测数据'}
        emptyHint="该事件在历史样本中未触发或数据缺失，无法给出边缘（后端 honest 降级）"
      >
        {data && data.available !== false ? <EventBacktestBody data={data} /> : null}
      </QueryState>
    </div>
  )
}

function EventBacktestBody({ data }: { data: EventBacktest }) {
  const dist = data.distribution ?? []
  const edge = data.edge_pp
  const edgeColor = typeof edge === 'number' && edge > 0 ? CHART.ok : typeof edge === 'number' && edge < 0 ? CHART.danger : undefined

  const option = useMemo<EChartsOption>(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['事件', '基准'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 40, right: 16, top: 28, bottom: 28 },
    xAxis: {
      type: 'category',
      data: dist.map((d) => d.bucket),
      axisLabel: { color: CHART.ink2, rotate: 38 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      name: '样本数',
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      { name: '事件', type: 'bar', data: dist.map((d) => d.event_count), itemStyle: { color: CHART.up } },
      { name: '基准', type: 'bar', data: dist.map((d) => d.base_count), itemStyle: { color: CHART.accent } },
    ],
  }), [dist])

  const examples = data.example_dates ?? []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="触发样本" value={fmtNum(data.n_event, 0)} sub={`基准样本 ${fmtNum(data.n_base, 0)}`} />
        <Stat label="基准红盘率" value={fmtPct(data.base_rate)} />
        <Stat label="事件红盘率" value={fmtPct(data.event_rate)} />
        <Stat label="边缘" value={fmtNum(edge, 1) + ' pp'} sub="事件 − 基准" color={edgeColor} />
        <Stat
          label="z 值"
          value={fmtNum(data.z, 2)}
          sub={data.z == null ? '样本不足未检验' : '两比例 z 检验'}
        />
      </div>

      <Card title="前向红盘日占比分布：事件 vs 基准">
        <EChart option={option} height={260} ariaLabel="事件与基准的前向红盘日占比分布对比柱状图" />
      </Card>

      {examples.length > 0 && (
        <Card title="触发示例（历史极值日）">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-sf-ink-3 text-label border-b border-sf-line">
                  <th className="text-left py-1.5 px-2">日期</th>
                  <th className="text-right py-1.5 px-2">指标值</th>
                  <th className="text-right py-1.5 px-2">后 {data.horizon} 日红盘占比</th>
                </tr>
              </thead>
              <tbody>
                {examples.map((ex) => (
                  <tr key={ex.date} className="border-b border-sf-line/60 text-sf-ink">
                    <td className="py-1.5 px-2">{ex.date}</td>
                    <td className="text-right py-1.5 px-2 tabular-nums">{fmtNum(ex.metric_value, 2)}</td>
                    <td className="text-right py-1.5 px-2 tabular-nums">{fmtPct(ex.forward_red_day_frac)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {(data.honesty_notes ?? []).length > 0 && (
        <Card title="方法与诚实说明">
          <ul className="list-disc pl-5 space-y-1 text-label text-sf-ink-3">
            {data.honesty_notes!.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
