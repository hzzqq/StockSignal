import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import { useTemperatureBacktest } from '@/lib/queriesBatchB'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'

/**
 * 63 全温度档历史回测（v2 native /temperature-backtest）。
 *
 * 后端 GET /api/v2/read/temperature-backtest 直接封装 modules/temperature_backtest.band_backtest，
 * 把历史交易日按红盘率映射进五档，统计其后 1/5 日红盘率回归。
 *
 * 诚实红线：
 *  - n<50 的档位标「低置信」，不隐藏样本量、不把小样本说成规律；
 *  - available=false 时只显示后端给出的 reason（如历史末尾不足 5 日），不补零、不伪造柱状图；
 *  - 方法学 note 原文展示，不改写为「预测」或「策略收益」。
 */
const WINDOWS = [
  { label: '全历史', value: '' },
  { label: '近 10 年', value: '2500' },
  { label: '近 5 年', value: '1250' },
  { label: '近 3 年', value: '750' },
  { label: '近 1 年', value: '250' },
] as const

function fmt(v: number | null | undefined, digits = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}

export function TemperatureBacktest() {
  const [windowText, setWindowText] = useState<string>('')
  const parsed = windowText === '' ? undefined : Number(windowText)
  const paramsValid = parsed === undefined || (Number.isFinite(parsed) && parsed >= 1 && parsed <= 5000)

  const query = useTemperatureBacktest(paramsValid ? { window_days: parsed } : undefined)
  const d = query.data

  const bars: EChartsOption | null = d?.available && d.bands
    ? {
        tooltip: { trigger: 'axis' },
        legend: { data: ['次日改善率', '5 日改善率'] },
        grid: { left: 48, right: 24, top: 36, bottom: 28 },
        xAxis: {
          type: 'category',
          data: d.bands.map((b) => `${b.label}（n=${b.n}）`),
        },
        yAxis: { type: 'value', name: '改善率 %' },
        series: [
          {
            name: '次日改善率',
            type: 'bar',
            data: d.bands.map((b) => (b.available ? b.next_impr_rate ?? null : null)),
          },
          {
            name: '5 日改善率',
            type: 'bar',
            data: d.bands.map((b) => (b.available ? b.d5_impr_rate ?? null : null)),
          },
        ],
      }
    : null

  return (
    <div className="space-y-4">
      <SectionTitle as="h2">温度档历史回测</SectionTitle>
      <p className="text-xs text-sf-ink-3">
        {`把每个历史交易日按红盘率归入五档，分别统计其后 1 日 / 5 日的红盘率变化。 `}
        <LeadText>这是历史统计，不是收益预测</LeadText>
        {`；样本不足 50 的档位标注低置信。`}
      </p>

      <Card title="回测窗口">
        <label className="text-label text-sf-ink-3">
          窗口
          <select
            value={windowText}
            onChange={(e) => setWindowText(e.target.value)}
            className="mt-1 block w-40 rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-sf-ink"
          >
            {WINDOWS.map((w) => (
              <option key={w.value} value={w.value}>{w.label}</option>
            ))}
          </select>
        </label>
      </Card>

      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        isEmpty={!paramsValid || !d?.available}
        emptyLabel={!paramsValid ? '参数不合法' : '回测不可用'}
        emptyHint={d?.available === false ? d.reason : undefined}
      >
        {d?.available ? (
          <>
            <div className="grid gap-3 sm:grid-cols-4">
              <Card title="样本区间">
                <div className="text-body tabular-nums">
                  {d.data?.start ?? '—'} ~ {d.data?.end ?? '—'}
                </div>
                <div className="text-label text-sf-ink-3">共 {d.data?.rows ?? '—'} 个交易日</div>
              </Card>
              <Card title="全样本 · 次日改善率">
                <div className="text-xl font-semibold tabular-nums">
                  {fmt(d.baseline?.next_impr_rate)}%
                </div>
                <div className="text-label text-sf-ink-3">
                  平均变化 {fmt(d.baseline?.next_mean_delta, 2)} · n={d.baseline?.n ?? '—'}
                </div>
              </Card>
              <Card title="全样本 · 5 日改善率">
                <div className="text-xl font-semibold tabular-nums">
                  {fmt(d.baseline?.d5_impr_rate)}%
                </div>
                <div className="text-label text-sf-ink-3">
                  平均变化 {fmt(d.baseline?.d5_mean_delta, 2)}
                </div>
              </Card>
              <Card title="档位数">
                <div className="text-xl font-semibold tabular-nums">{d.bands?.length ?? '—'}</div>
              </Card>
            </div>

            <Card title="五档回测明细">
              <table className="w-full text-label tabular-nums">
                <thead>
                  <tr className="text-sf-ink-3">
                    <th className="text-left py-1">温度档</th>
                    <th className="text-right py-1">样本 n</th>
                    <th className="text-right py-1">次日改善率</th>
                    <th className="text-right py-1">次日平均变化</th>
                    <th className="text-right py-1">5 日改善率</th>
                    <th className="text-right py-1">平均次日红盘率</th>
                  </tr>
                </thead>
                <tbody>
                  {d.bands?.map((b) => (
                    <tr key={b.level} className="border-t border-sf-line">
                      <td className="py-1">
                        <span style={{ color: b.color }}>{b.label}</span>
                        {b.available && b.n < 50 && (
                          <span className="ml-2 text-sf-warn">低置信</span>
                        )}
                      </td>
                      <td className="text-right py-1">{b.n}</td>
                      <td className="text-right py-1">
                        {b.available ? `${fmt(b.next_impr_rate)}%` : '—'}
                      </td>
                      <td className="text-right py-1">
                        {b.available ? fmt(b.next_mean_delta, 2) : '—'}
                      </td>
                      <td className="text-right py-1">
                        {b.available ? `${fmt(b.d5_impr_rate)}%` : '—'}
                      </td>
                      <td className="text-right py-1">
                        {b.available ? `${fmt(b.avg_next_red)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="各档改善率对比">
              {bars ? <EChart option={bars} height={320} /> : null}
            </Card>

            {d.note && (
              <Card title="方法学说明">
                <p className="text-xs text-sf-ink-3 whitespace-pre-wrap">{d.note}</p>
              </Card>
            )}
          </>
        ) : null}
      </QueryState>
    </div>
  )
}
