import { Link } from '@tanstack/react-router'
import { useDailySnapshot, useP1Signals, useWebApps } from '@/lib/queries'
import { SnapshotView } from '@/features/decision/SnapshotView'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { fmtNum } from '@/lib/format'

/** 首页/概览：聚合当日快照、P1 最新数据日、作品集数量，并内嵌决策快照视图。 */
export function Dashboard() {
  const snapQ = useDailySnapshot()
  const p1Q = useP1Signals()
  const webQ = useWebApps()

  let p1Latest: string | null = null
  if (p1Q.data) {
    for (const s of Object.values(p1Q.data)) {
      if (s.latest_date && (!p1Latest || s.latest_date > p1Latest)) p1Latest = s.latest_date
    }
  }

  return (
    <div className="flow">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">概览</h2>
        <Link to="/decision" className="text-body text-sf-accent hover:underline">
          今日决策面板 →
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="P1 信号最新数据日"
          value={p1Latest ?? '—'}
          sub={p1Q.isError ? '加载失败' : undefined}
        />
        <Stat label="网页作品" value={webQ.data ? webQ.data.length : '—'} />
        <Stat label="快照数据日" value={snapQ.data?.date ?? '—'} />
        <Stat label="综合评分" value={snapQ.data ? fmtNum(snapQ.data.score) : '—'} />
      </div>

      {snapQ.data ? (
        <SnapshotView snapshot={snapQ.data} />
      ) : (
        <Card>
          <div className="py-6 text-center text-sf-ink-3">
            {snapQ.isError ? '决策快照加载失败' : '加载中…'}
          </div>
        </Card>
      )}
    </div>
  )
}
