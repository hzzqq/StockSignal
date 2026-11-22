import { useDailyRecommendation, useVirtualUsersSim } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'

/** 后端 meta 键 → 中文说明；未知键原样显示（不吞字段，不臆造说明）。 */
const META_LABELS: Record<string, string> = {
  n_users: '虚拟用户数',
  seed: '随机种子',
  universe_size: '股票池规模',
  pool_valid: '有效股票数',
  skipped_tickers: '跳过标的数',
  start: '回测起始',
  end: '回测截止',
  window: '窗口(交易日)',
  strategies: '策略集合',
  cost_model: '成本模型',
}

/** meta 值本就是报告里记录的配置参数，按类型如实格式化；不做任何补零/兜底。 */
function fmtMetaValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (Array.isArray(v)) return v.length ? v.map(String).join('、') : '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** 36 每日荐股：展示荐股状态与免责声明；若 unavailable 则如实展示原因（不编造推荐）。 */
export function Recommendation() {
  const q = useDailyRecommendation()
  const simQ = useVirtualUsersSim()
  const rec = q.data
  const unavailable = rec?.status === 'unavailable'

  return (
    <div className="space-y-4">
      <SectionTitle as="h2">每日荐股</SectionTitle>
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={!rec}>
        {rec && (
          <Card title={`状态：${rec.status ?? '—'}`}>
            {unavailable && rec.reason && <p className="text-body text-sf-warn">{rec.reason}</p>}
            {rec.generated_at && (
              <p className="text-xs text-sf-ink-3 mt-1">generated {rec.generated_at}</p>
            )}
            {rec.disclaimer && (
              <p className="text-xs text-sf-ink-3 mt-3 leading-relaxed">{rec.disclaimer}</p>
            )}
          </Card>
        )}
      </QueryState>

      <Card title="虚拟用户模拟">
        <QueryState
          isLoading={simQ.isLoading}
          isError={simQ.isError}
          error={simQ.error}
          isEmpty={!simQ.data}
          emptyLabel="暂无模拟统计"
        >
          {simQ.data && (
            <div className="text-sm text-sf-ink-2">
              <p className="mb-2">蒙特卡洛回测模拟（非实盘，报告首次生成参数如实展示）：</p>
              {simQ.data.meta && Object.keys(simQ.data.meta).length > 0 ? (
                <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
                  {Object.entries(simQ.data.meta).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 border-b border-sf-line py-1">
                      <dt className="text-sf-ink-3">{META_LABELS[k] ?? k}</dt>
                      <dd className="font-mono text-sf-ink-2">{fmtMetaValue(v)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-xs text-sf-ink-3">
                  {`报告存在但未提供生成参数（`}
                  <LeadText>如实留空，不编造</LeadText>
                  {`）。`}
                </p>
              )}
            </div>
          )}
        </QueryState>
      </Card>
    </div>
  )
}
