import { useState } from 'react'
import { useSnapshotDates, useSnapshot } from '@/lib/queries'
import { SnapshotView } from './SnapshotView'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'

const SELECT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/** 97 决策回放：选归档日期 → 拉取当日快照（与面板同视图，验证历史一致性）。 */
export function DecisionReplay() {
  const datesQ = useSnapshotDates()
  const [selected, setSelected] = useState<string | null>(null)
  const snapQ = useSnapshot(selected)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">决策回放</h2>
      <Card>
        <label className="text-xs text-sf-ink-2">选择归档日期</label>
        <select
          className={SELECT_CLS}
          value={selected ?? ''}
          onChange={(e) => setSelected(e.target.value || null)}
        >
          <option value="">— 请选择 —</option>
          {datesQ.data?.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        {datesQ.isLoading && <span className="text-xs text-sf-ink-3 ml-2">加载日期清单…</span>}
        {datesQ.isError && (
          <span className="text-label text-sf-danger ml-2">日期清单加载失败</span>
        )}
      </Card>

      {selected && (
        <QueryState
          isLoading={snapQ.isLoading}
          isError={snapQ.isError}
          error={snapQ.error}
          isEmpty={!snapQ.data}
          emptyLabel="该日期无归档快照"
        >
          {snapQ.data && <SnapshotView snapshot={snapQ.data} />}
        </QueryState>
      )}
    </div>
  )
}
