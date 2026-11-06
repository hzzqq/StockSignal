import type { ReactNode } from 'react'

/** 通用卡片容器（暗色 Bento 风格）。 */
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
  return (
    <section className={`rounded-xl bg-sf-card border border-sf-border p-4 ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between mb-3">
          {title && <h3 className="text-sm font-medium text-sf-txt/80">{title}</h3>}
          {right}
        </header>
      )}
      {children}
    </section>
  )
}
