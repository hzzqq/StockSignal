import { useDailyRecommendation, useVirtualUsersSim } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'

/** 36 每日荐股：展示荐股状态与免责声明；若 unavailable 则如实展示原因（不编造推荐）。 */
export function Recommendation() {
  const q = useDailyRecommendation()
  const simQ = useVirtualUsersSim()
  const rec = q.data
  const unavailable = rec?.status === 'unavailable'

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">每日荐股</h2>
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
              蒙特卡洛回测模拟（非实盘）：
              {simQ.data.meta
                ? ` ${JSON.stringify(simQ.data.meta).slice(0, 200)}`
                : ' 数据存在但结构未解析'}
            </div>
          )}
        </QueryState>
      </Card>
    </div>
  )
}
