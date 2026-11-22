import { useDailySnapshot } from '@/lib/queries'
import { SnapshotView } from './SnapshotView'
import { QueryState } from '@/shared/ui/States'
import { SectionTitle } from '@/shared/ui/EmphasisText'

/** 54 今日决策面板：渲染后端算好的当日快照，前端不重算任何仓位规则（PLAN.md §5）。 */
export function DecisionPanel() {
  const q = useDailySnapshot()
  return (
    <div className="space-y-4">
      <SectionTitle as="h2">今日决策面板</SectionTitle>
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={!q.data}>
        {q.data && <SnapshotView snapshot={q.data} />}
      </QueryState>
    </div>
  )
}
