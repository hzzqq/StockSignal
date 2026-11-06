import type { ReactNode } from 'react'

/** 加载中占位。 */
export function Loading({ label = '加载中…' }: { label?: string }) {
  return <div className="py-10 text-center text-sf-txt/50 text-sm">{label}</div>
}

/** 数据缺失态（诚实红线：取不到即显示「无数据」，不补零/不编造）。 */
export function EmptyState({ label = '暂无数据', hint }: { label?: string; hint?: ReactNode }) {
  return (
    <div className="py-10 text-center">
      <div className="text-sf-txt/45 text-sm">{label}</div>
      {hint && <div className="text-sf-txt/30 text-xs mt-1">{hint}</div>}
    </div>
  )
}

/** 错误态（解析失败 / 网络错误 / 鉴权过期）。 */
export function ErrorState({ message }: { message: string }) {
  return (
    <div className="my-2 rounded-lg border border-ss-down/40 bg-ss-down/10 px-4 py-3 text-ss-down text-sm">
      {message}
    </div>
  )
}

/** 由 useQuery 结果统一分发 加载/错误/空/有数据 四态。 */
export function QueryState({
  isLoading,
  isError,
  error,
  isEmpty,
  children,
  emptyLabel,
  emptyHint,
}: {
  isLoading: boolean
  isError: boolean
  error?: unknown
  isEmpty?: boolean
  children: ReactNode
  emptyLabel?: string
  emptyHint?: ReactNode
}) {
  if (isLoading) return <Loading />
  if (isError) {
    const msg = error instanceof Error ? error.message : '加载失败'
    return <ErrorState message={msg} />
  }
  if (isEmpty) return <EmptyState label={emptyLabel} hint={emptyHint} />
  return <>{children}</>
}
