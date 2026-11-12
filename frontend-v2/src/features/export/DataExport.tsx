import { useState } from 'react'
import { useSnapshotDates, useSnapshot } from '@/lib/queries'
import { SnapshotView } from '@/features/decision/SnapshotView'
import { EmptyState, ErrorState, Loading } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'
import { ApiError } from '@/api/client'
import type { DailySnapshot } from '@/api/schemas/read'

const SELECT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/** 把快照导出为 JSON 文件（纯前端，不写后端；环境不支持下载能力时安全降级）。 */
function downloadJson(filename: string, data: DailySnapshot) {
  try {
    if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    /* 下载能力缺失时静默降级，不影响页面其余功能 */
  }
}

/**
 * 95 数据导出（v2 native /export）：浏览归档快照（data/snapshots/*.json）并导出原始 JSON。
 *
 * 复用既有只读端点 snapshot-dates / snapshot/<date> 与 SnapshotView 富视图，v2 只读界面，
 * 无任何写能力。诚实红线：不回退今日快照冒充历史归档。
 *
 * ⚠️ 错误按后端 code 分流（2026-11-12 修复）：后端对「该日无归档」返回 status=error /
 * code=not_found 信封，前端据此显「该日期无归档快照」空态是正确的；但旧实现把**所有**
 * isError 都塞进该空态，导致网络 500 / 鉴权过期 / 解析失败也被伪装成「无数据」。
 * 现仅 not_found 走空态，其余失败走 ErrorState 并原样带出原因。
 */
export function DataExport() {
  const datesQ = useSnapshotDates()
  const [selected, setSelected] = useState<string | null>(null)
  const snapQ = useSnapshot(selected)

  const snapErr = snapQ.error
  const notFound = snapErr instanceof ApiError && snapErr.code === 'not_found'
  // 「无数据」= 查询成功但无快照，或后端明确 not_found；「失败」= 其余任何错误。
  const showEmpty = !!selected && !snapQ.isLoading && !snapQ.data && (!snapQ.isError || notFound)
  const showError = !!selected && !snapQ.isLoading && snapQ.isError && !notFound

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">数据导出</h2>
      <p className="text-xs text-sf-ink-3">
        浏览归档快照（data/snapshots/*.json）并导出原始 JSON。v2 只读界面，不写入任何数据。
      </p>

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
          <p className="text-xs text-sf-warn mt-1">
            {datesQ.error instanceof Error ? datesQ.error.message : '日期清单加载失败'}
          </p>
        )}
        {datesQ.data && datesQ.data.length === 0 && (
          <p className="text-xs text-sf-ink-3 mt-1">暂无归档快照日期</p>
        )}
      </Card>

      {selected && snapQ.isLoading && <Loading label="加载快照…" />}
      {showError && (
        <ErrorState message={snapErr instanceof Error ? snapErr.message : '快照加载失败'} />
      )}
      {showEmpty && (
        <Card>
          <EmptyState
            label="该日期无归档快照"
            hint={notFound ? 'data/snapshots 中无该日期归档' : undefined}
          />
        </Card>
      )}
      {selected && !snapQ.isLoading && snapQ.data && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-sf-ink-3">已选 {selected}</span>
            <button
              type="button"
              onClick={() => downloadJson(`snapshot-${selected}.json`, snapQ.data as DailySnapshot)}
              className="rounded bg-sf-accent px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
            >
              导出 JSON
            </button>
          </div>
          <SnapshotView snapshot={snapQ.data} />
        </div>
      )}
    </div>
  )
}
