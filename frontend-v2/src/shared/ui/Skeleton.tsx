/**
 * 精致层次档 · 骨架屏（纯展示，不含取数逻辑）。
 * 无障碍：role=status + sr-only「加载中」，视觉条 aria-hidden 避免读屏重复播报。
 */
export type SkeletonVariant = 'text' | 'card' | 'circle'

export interface SkeletonProps {
  className?: string
  rows?: number
  variant?: SkeletonVariant
}

const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ')

const VARIANT_CLASS: Record<SkeletonVariant, string> = {
  text: 'h-3 w-full rounded-tile',
  card: 'h-24 w-full rounded-card',
  circle: 'h-10 w-10 rounded-full',
}

export function Skeleton({ className = '', rows = 1, variant = 'text' }: SkeletonProps) {
  return (
    <div role="status" className={cx('w-full space-y-2', className)}>
      <span className="sr-only">加载中</span>
      {Array.from({ length: Math.max(0, rows) }, (_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className={cx('animate-pulse bg-sf-surface-2', VARIANT_CLASS[variant])}
        />
      ))}
    </div>
  )
}
