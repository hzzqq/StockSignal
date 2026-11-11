import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { useConstructionDiag, type ConstructionDiag } from './constructionDiag'

/**
 * P1 组合构建诊断（frontend-v2 化）。
 *
 * 原始交付物是单文件 Chart.js 看板（P1 诊断的产物），本组件按 StockSignal v2 的
 * 设计令牌与图表栈（Tailwind v4 + ECharts 6 + DESIGN.md）重建：
 *  - 数据：本地随包 JSON（constructionDiag.json），经 Zod 严格校验，零网络、零写入；
 *  - 视觉：轻量卡片流（暗色默认），涨=红/跌=绿 仅用于收益语义（P&L 域）；
 *  - 无障碍：Card=region+aria-label，EChart=role=img+ariaLabel+sr-only，Stat=tabular-nums，
 *    图形不是关键数值唯一载体（同页 KPI/脚注给出等价数字）；
 *  - 诚实红线：缺失即空态，不补零、不编造；收益含真实交易成本（net）。
 */

const WINDOW_LABELS: Record<string, string> = {
  FULL: '全样本',
  '2024+': '2024至今',
  '2026': '2026',
  recent59td: '近59交易日',
}

/** 收益/数值格式化为带符号百分比（涨=正）。 */
function pct(v: number): string {
  const s = v >= 0 ? '+' : '−'
  return `${s}${(Math.abs(v) * 100).toFixed(1)}%`
}

/** 盈亏着色：A 股语义，涨=红（ss-up）、跌=绿（ss-down）。 */
function pnlColor(v: number): string {
  return v >= 0 ? 'var(--color-ss-up)' : 'var(--color-ss-down)'
}

/** 净值倍数诚实格式化：缺失即显「—」，绝不补 0（诚实红线）。 */
function netX(v: number | undefined): string {
  return v === undefined || v === null || Number.isNaN(v) ? '—' : `${v.toFixed(3)}x`
}

/** 净值曲线：三轮净值倍数 + 2026 阴影区带。 */
export function buildEquityOption(d: ConstructionDiag): EChartsOption {
  const { dates, long_only_net, long_short_net, benchmark_gross, idx_2026 } = d.curves
  const bandStart = dates[idx_2026] ?? dates[0]
  const bandEnd = dates[dates.length - 1]
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 16, top: 32, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const arr = Array.isArray(params) ? params : [params]
        if (!arr.length) return ''
        const i = (arr[0] as { dataIndex: number }).dataIndex
        const date = dates[i] ?? ''
        // dates 与三条序列等长（schema 保证），dataIndex 恒在范围内：直接索引，不补零。
        const rows = [
          `纯多头 net ${netX(long_only_net[i])}`,
          `市场中性 net ${netX(long_short_net[i])}`,
          `基准 gross ${netX(benchmark_gross[i])}`,
        ]
        return `<b>${date}</b><br/>${rows.join('<br/>')}`
      },
    },
    legend: {
      data: ['纯多头 net', '市场中性 net', '基准 gross'],
      top: 0,
      itemGap: 14,
      textStyle: { color: CHART.ink2 },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLabel: { color: CHART.ink3, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: CHART.ink3, formatter: (v: number) => `${v.toFixed(1)}x` },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        name: '纯多头 net',
        type: 'line',
        data: long_only_net,
        showSymbol: false,
        lineStyle: { width: 2, color: CHART.up },
        itemStyle: { color: CHART.up },
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(229,165,75,0.10)' },
          label: { show: true, position: 'insideTop', color: CHART.ink3, formatter: '2026' },
          data: [[{ xAxis: bandStart }, { xAxis: bandEnd }]],
        },
      },
      {
        name: '市场中性 net',
        type: 'line',
        data: long_short_net,
        showSymbol: false,
        lineStyle: { width: 2, color: CHART.accent },
        itemStyle: { color: CHART.accent },
      },
      {
        name: '基准 gross',
        type: 'line',
        data: benchmark_gross,
        showSymbol: false,
        lineStyle: { width: 1.5, color: CHART.ink3, type: 'dashed' },
        itemStyle: { color: CHART.ink3 },
      },
    ],
  }
}

/** alpha 衰减：基准相对收益随窗口逐级塌缩。 */
export function buildDecayOption(d: ConstructionDiag): EChartsOption {
  const items = d.alpha_decay
  const cats = items.map((a) => WINDOW_LABELS[a.window] ?? a.window)
  const data = items.map((a) => a.excess_total_return)
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 16, top: 24, bottom: 28 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => pct(v as number) },
    xAxis: {
      type: 'category',
      data: cats,
      axisLabel: { color: CHART.ink3 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink3, formatter: (v: number) => `${v * 100}%` },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        type: 'bar',
        data,
        itemStyle: { color: CHART.warn, borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: 'top',
          color: CHART.ink2,
          formatter: (p) => pct(p.value as number),
        },
      },
    ],
  }
}

/** 降频低换手（提高 rf）的 2026 市场中性净收益扫描：错误杠杆。 */
export function buildRfSweepOption(d: ConstructionDiag): EChartsOption {
  const items = d.rf_sweep
  const cats = items.map((r) => `rf=${r.rf}`)
  const data = items.map((r) => ({
    value: r.y2026_market_neutral_return,
    itemStyle: {
      color: r.y2026_market_neutral_return >= 0 ? CHART.up : CHART.down,
      borderRadius: [4, 4, 0, 0],
    },
  }))
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 16, top: 24, bottom: 28 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => pct(v as number) },
    xAxis: {
      type: 'category',
      data: cats,
      axisLabel: { color: CHART.ink3 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.ink3, formatter: (v: number) => `${v * 100}%` },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        type: 'bar',
        data,
        label: {
          show: true,
          position: 'top',
          color: CHART.ink2,
          formatter: (p) => pct(p.value as number),
        },
      },
    ],
  }
}

export function ConstructionDiagnostics() {
  const q = useConstructionDiag()
  return (
    <div className="flow">
      <header className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-page font-semibold">组合构建诊断</h2>
        <span className="text-label text-sf-ink-3">
          {q.data?.meta.generated_at ?? ''} · P1 只读复算 · {q.data?.meta.model ?? ''}
        </span>
      </header>
      <p className="text-body text-sf-ink-2">
        结论先行：组合构建改造是<strong className="text-sf-ink">止血 / 防御</strong>，非治愈；根因是
        <strong className="text-sf-ink"> alpha 衰减</strong>。市场中性是回血杠杆，降频低换手（提高 rf）是错误杠杆，
        buffer=0.1 才是免费午餐。
      </p>
      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!q.data}
        emptyLabel="暂无组合构建诊断数据"
      >
        {q.data ? <DiagBody d={q.data} /> : null}
      </QueryState>
    </div>
  )
}

function DiagBody({ d }: { d: ConstructionDiag }) {
  const equityOpt = useMemo(() => buildEquityOption(d), [d])
  const decayOpt = useMemo(() => buildDecayOption(d), [d])
  const rfOpt = useMemo(() => buildRfSweepOption(d), [d])
  const h = d.headline
  const tl = d.turnover_free_lunch

  return (
    <div className="flow">
      {/* KPI：决策最相关的四数 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="纯多头 2026 净收益"
          value={pct(h.pure_long.y2026_return)}
          color={pnlColor(h.pure_long.y2026_return)}
          sub={`夏普 ${h.pure_long.y2026_sharpe.toFixed(2)}`}
        />
        <Stat
          label="市场中性 2026 净收益"
          value={pct(h.market_neutral.y2026_return)}
          color={pnlColor(h.market_neutral.y2026_return)}
          sub={`夏普 ${h.market_neutral.y2026_sharpe.toFixed(2)}`}
        />
        <Stat
          label="市场中性 全样本净收益"
          value={pct(h.market_neutral.full_return)}
          color={pnlColor(h.market_neutral.full_return)}
          sub={`夏普 ${h.market_neutral.full_sharpe.toFixed(2)}`}
        />
        <Stat
          label="免费午餐 换手降幅"
          value={`${(tl.market_neutral.buffer0_turnover * 100).toFixed(0)}%→${(tl.market_neutral.buffer01_turnover * 100).toFixed(0)}%`}
          sub={`收益 ${pct(tl.market_neutral.buffer01_full_return)}`}
        />
      </div>

      <Card title="诊断结论（结论先行）">
        <ol className="list-decimal pl-5 space-y-1.5 text-body text-sf-ink-2">
          {d.conclusions.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ol>
      </Card>

      <Card title="净值曲线（rf=10, buffer=0, net；2026 阴影区带）">
        <EChart
          option={equityOpt}
          height={320}
          ariaLabel="净值曲线：纯多头 net、市场中性 net 与基准 gross 三轮净值倍数，2026 年起以阴影标出"
        />
        <p className="text-label text-sf-ink-3 mt-2">
          起始 = 1.0x；net 含 A 股真实交易成本，基准 gross 为零成本等权全市场代理。
        </p>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="根因：alpha 衰减（基准相对）">
          <EChart
            option={decayOpt}
            height={240}
            ariaLabel="alpha 衰减柱状图：基准相对收益从全样本到近59交易日逐级塌缩"
          />
          <p className="text-label text-sf-ink-3 mt-2">
            基准相对 = 纯多头 − 等权全市场；逐级塌缩说明 alpha 在衰减，而非构造费 / 换手费问题。
          </p>
        </Card>
        <Card title="错误杠杆：降频低换手（提高 rf）">
          <EChart
            option={rfOpt}
            height={240}
            ariaLabel="rf 扫描柱状图：市场中性 2026 净收益随 rf 升高先恶化后略回"
          />
          <p className="text-label text-sf-ink-3 mt-2">
            rf=10 +10.5% → rf=20 −4.4% → rf=40 +3.8%：调仓越稀越差，降频不是正确杠杆。
          </p>
        </Card>
      </div>

      <Card title="免费午餐：buffer=0.1（降换手不降收益）">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat
            label="市场中性 换手"
            value={`${(tl.market_neutral.buffer0_turnover * 100).toFixed(0)}%→${(tl.market_neutral.buffer01_turnover * 100).toFixed(0)}%`}
          />
          <Stat
            label="市场中性 全样本"
            value={pct(tl.market_neutral.buffer0_full_return)}
            sub={`→ ${pct(tl.market_neutral.buffer01_full_return)}`}
          />
          <Stat
            label="纯多头 全样本"
            value={pct(tl.pure_long.buffer0_full_return)}
            sub={`→ ${pct(tl.pure_long.buffer01_full_return)}`}
          />
          <Stat
            label="市场中性 2026"
            value={pct(h.market_neutral.y2026_return)}
            sub={`→ ${pct(tl.market_neutral.buffer01_y2026_return)}`}
          />
        </div>
        <p className="text-label text-sf-ink-3 mt-3">{tl.note}</p>
      </Card>

      <Card title="诚实边界">
        <div className="rounded-tile bg-sf-warn-soft border border-sf-line px-4 py-3 text-body text-sf-ink-2">
          {d.honesty}
        </div>
      </Card>
    </div>
  )
}
