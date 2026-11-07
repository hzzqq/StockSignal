import type { ReactNode } from 'react'

/**
 * 轻量卡片流 · 加载 / 空 / 错误 三态。
 * 诚实红线：取不到即显示「无数据」，不补零、不编造。
 * 语义纠偏：错误态不再用交易屏跌色（绿，属价格语义误用），
 *   改为中性 hairline 细框 + 琥珀点（sf-warn），并带 role=alert 通知读屏。
 */

/** 加载中占位（圆点脉冲，尊重 prefers-reduced-motion）。 */
export function Loading({ label = '加载中…' }: { label?: string }) {
  return (
    <div role="status" className="py-10 flex items-center justify-center gap-2 text-body text-sf-ink-3">
      <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-sf-accent animate-pulse" />
      {label}
    </div>
  )
}

/** 数据缺失态（诚实红线：取不到即显示「无数据」，不补零/不编造）。 */
export function EmptyState({ label = '暂无数据', hint }: { label?: string; hint?: ReactNode }) {
  return (
    <div role="status" className="py-10 text-center">
      <div className="text-body text-sf-ink-2">{label}</div>
      {hint && <div className="text-label text-sf-ink-3 mt-1">{hint}</div>}
    </div>
  )
}

/** 错误态（解析失败 / 网络错误 / 鉴权过期）。 */
export function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="my-2 flex items-start gap-2 rounded-tile border border-sf-line bg-sf-surface px-4 py-3 text-body text-sf-ink-2"
    >
      <span aria-hidden="true" className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-sf-warn" />
      <span>{message}</span>
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
