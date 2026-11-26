import type { ReactNode } from 'react'

/**
 * 精致层次档 · 空态（独立新组件，不触碰旧 States.tsx）。
 * 语义与旧 EmptyState 一致：role=status，内容只来自调用方，绝不编造业务数据。
 */
export interface EmptyStateModernProps {
  title: string
  description?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  className?: string
}

const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ')

function DefaultIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-6 w-6"
    >
      <path d="M5 6.5A1.5 1.5 0 0 1 6.5 5h3.2a1.5 1.5 0 0 1 1.06.44l1.3 1.3a1.5 1.5 0 0 0 1.06.44h4.38A1.5 1.5 0 0 1 19 8.68v8.82a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 17.5v-11Z" />
      <path d="M5 10h14" />
      <path d="M9 14h6" />
    </svg>
  )
}

export function EmptyStateModern({
  title,
  description,
  action,
  icon,
  className = '',
}: EmptyStateModernProps) {
  return (
    <div role="status" className={cx('py-12 text-center', className)}>
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center text-sf-ink-3">
        {icon ?? <DefaultIcon />}
      </div>
      <div className="text-page text-sf-ink-2">{title}</div>
      {description && (
        <p className="mt-2 text-body text-sf-ink-3">{description}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}
