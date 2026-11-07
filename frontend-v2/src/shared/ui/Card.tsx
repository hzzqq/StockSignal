import type { ReactNode } from 'react'

/**
 * 轻量卡片流 · 通用卡片容器。
 * 扁平实色表面 + 1px hairline 边框 + 零阴影 + 20px 留白（DESIGN.md §2.3）。
 * 无障碍：有标题时以 region 语义 + aria-label 命名，读屏可逐块跳转。
 * 注：title 可为 ReactNode，仅 string 时作为 aria-label（节点无法可靠转文本）。
 */
export function Card({
  title,
  children,
  className = '',
  right,
}: {
  title?: ReactNode
  children: ReactNode
  className?: string
  right?: ReactNode
}) {
  const ariaLabel = typeof title === 'string' ? title : undefined
  return (
    <section
      role={ariaLabel ? 'region' : undefined}
      aria-label={ariaLabel}
      className={`rounded-card bg-sf-surface border border-sf-line p-5 ${className}`}
    >
      {(title || right) && (
        <header className="flex items-center justify-between mb-4">
          {title && <h3 className="text-title font-medium text-sf-ink-2">{title}</h3>}
          {right}
        </header>
      )}
      {children}
    </section>
  )
}
