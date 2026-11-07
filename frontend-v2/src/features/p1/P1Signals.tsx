import type { P1TopItem } from '@/api/schemas/read'
import { useP1Signals } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'

function P1Table({ title, rows }: { title: string; rows?: P1TopItem[] }) {
  return (
    <div>
      <div className="text-xs text-sf-ink-2 mb-1">{title}</div>
      {rows && rows.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-sf-ink-3 text-left">
              <th className="py-1">代码</th>
              <th className="py-1">预测</th>
              <th className="py-1">排名</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.symbol}-${i}`} className="border-t border-sf-line">
                <td>{r.symbol}</td>
                <td>{r.pred != null ? r.pred.toFixed(4) : '—'}</td>
                <td>{r.rank != null ? r.rank.toFixed(3) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="text-xs text-sf-ink-3">无</div>
      )}
    </div>
  )
}

/** 55 P1 量化信号：列出 data/p1_signals/ 下各 signal_*.json 的多头/空头 TOP。 */
export function P1Signals() {
  const q = useP1Signals()
  const entries = q.data ? Object.entries(q.data) : []

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">P1 量化信号</h2>
      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={entries.length === 0}
        emptyLabel="暂无 P1 信号文件"
        emptyHint="data/p1_signals/ 下未找到 signal_*.json"
      >
        <div className="space-y-4">
          {entries.map(([name, sig]) => (
            <Card key={name} title={name}>
              <div className="text-xs text-sf-ink-3 mb-2">
                latest_date {sig.latest_date ?? '—'} · generated {sig.generated_at ?? '—'}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <P1Table title="多头 TOP" rows={sig.top_long} />
                <P1Table title="空头 TOP" rows={sig.top_short} />
              </div>
            </Card>
          ))}
        </div>
      </QueryState>
    </div>
  )
}
