import { useState } from 'react'
import { useEarningsCalendar } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Loading, EmptyState, ErrorState } from '@/shared/ui/States'

const MARKETS = ['沪深京', '沪市', '深市'] as const
const PERIODS = ['2026年报', '2025年报', '2024年报', '2023年报'] as const

/** 端点已把 akshare 原始列规整成「披露时间」，但保留旧列名兼容（akshare 换版本 / 旧快照）。
 *  候选列全部取不到时如实返回「—」，不补零、不编造日期。 */
function pickDisclosure(row: Record<string, unknown>): string {
  for (const k of ['披露时间', '实际披露', '实际披露日期', '首次预约', '披露日期', '预约披露日期']) {
    const v = row[k]
    if (v !== null && v !== undefined && v !== '') return String(v).slice(0, 10)
  }
  return '—'
}

function pickStatus(row: Record<string, unknown>): string {
  const v = row['披露状态']
  return v !== null && v !== undefined && v !== '' ? String(v) : '—'
}

/** 报告期：端点规整后每行都带；旧快照缺失时回落到请求参数（真实查询期，非编造）。 */
function pickReportPeriod(row: Record<string, unknown>, fallback: string): string {
  const v = row['报告期']
  return v !== null && v !== undefined && v !== '' ? String(v) : fallback
}

const SELECT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/**
 * 16 财报日历（v2 native /earnings-calendar）：财报预约披露日历（真实 akshare 数据源）。
 * 复用新增只读端点 /api/v2/read/earnings-calendar（包装 modules.fundflow.get_disclosure_calendar）。
 * 诚实红线：数据源限流/未披露时后端返回 unavailable=true + 空 rows，前端显诚实空态，绝不编造行；
 * 仅年报披露日历可得（akshare 限制），季报/中报由后端 best-effort 映射年报，页面如实呈现。
 */
export function EarningsCalendar() {
  const [market, setMarket] = useState<string>('沪深京')
  const [period, setPeriod] = useState<string>('2025年报')
  const q = useEarningsCalendar(market, period)
  const rows = q.data?.rows ?? []

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">财报日历</h2>
      <p className="text-xs text-sf-ink-3">
        财报预约披露日历（数据来源：东方财富，年报）。只读视图，无写能力。
      </p>

      <Card>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="text-xs text-sf-ink-2">
            市场
            <select
              className={SELECT_CLS}
              value={market}
              onChange={(e) => setMarket(e.target.value)}
            >
              {MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-sf-ink-2">
            报告期
            <select
              className={SELECT_CLS}
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              {PERIODS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {q.isLoading && <Loading label="加载披露日历…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '披露日历加载失败'} />
      )}
      {q.data && q.data.unavailable && (
        <EmptyState label="财报披露日历暂时取不到" hint={q.data.note} />
      )}
      {q.data && !q.data.unavailable && rows.length === 0 && (
        <EmptyState label="该市场/报告期暂无披露日历数据" hint={q.data.note} />
      )}
      {q.data && !q.data.unavailable && rows.length > 0 && (
        <Card title={`${q.data.market} · ${q.data.period}（${rows.length} 条）`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                  <th className="py-2 pr-3">代码</th>
                  <th className="py-2 pr-3">名称</th>
                  <th className="py-2 pr-3">报告期</th>
                  <th className="py-2 pr-3">披露时间</th>
                  <th className="py-2 pr-3">状态</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const code = r['股票代码'] ?? r['代码'] ?? '—'
                  const name = r['股票简称'] ?? r['名称'] ?? '—'
                  const rep = pickReportPeriod(r, q.data?.period ?? '—')
                  const disc = pickDisclosure(r)
                  const status = pickStatus(r)
                  const disclosed = status.includes('已披露')
                  return (
                    <tr key={`${code}-${i}`} className="border-b border-sf-line/60">
                      <td className="py-2 pr-3 text-sf-ink">{String(code)}</td>
                      <td className="py-2 pr-3 text-sf-ink">{String(name)}</td>
                      <td className="py-2 pr-3 text-sf-ink-2">{String(rep)}</td>
                      <td className="py-2 pr-3 text-sf-ink-2">{disc}</td>
                      <td className="py-2 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs ${
                            disclosed ? 'bg-sf-accent text-white' : 'bg-sf-surface-2 text-sf-ink-3'
                          }`}
                        >
                          {status}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {q.data?.note && <p className="mt-3 text-xs text-sf-ink-3">{q.data.note}</p>}
        </Card>
      )}
    </div>
  )
}
