import { useState } from 'react'
import { useSnapshotDates, useSnapshot } from '@/lib/queries'
import { SnapshotView } from './SnapshotView'
import { ErrorState, QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'
import { Select } from '@/shared/ui/Field'

/** 97 决策回放：选归档日期 → 拉取当日快照（与面板同视图，验证历史一致性）。 */
export function DecisionReplay() {
  const datesQ = useSnapshotDates()
  const [selected, setSelected] = useState<string | null>(null)
  const snapQ = useSnapshot(selected)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">决策回放</h2>
      <Card>
        <Select
          label="选择归档日期"
          value={selected ?? ''}
          onChange={(e) => setSelected(e.target.value || null)}
        >
          <option value="">— 请选择 —</option>
          {datesQ.data?.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </Select>
        {datesQ.isLoading && <span className="text-xs text-sf-ink-3 ml-2">加载日期清单…</span>}
        {datesQ.isError && (
          <ErrorState
            message={datesQ.error instanceof Error
              ? `日期清单加载失败：${datesQ.error.message}`
              : '日期清单加载失败'}
          />
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
