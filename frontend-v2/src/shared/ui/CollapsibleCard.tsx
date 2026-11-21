import { useId, useState } from 'react'
import type * as React from 'react'

/**
 * 通用「折叠卡片」：把超长内容折成一行摘要，点击展开后显示完整内容。
 *
 * - 折叠态：标题 + 可选摘要（单行 truncate，title 属性保留全文）+「展开 ▾」按钮。
 * - 展开态：标题 +「收起 ▴」按钮 + 完整 children（折叠时不渲染 children）。
 * - 无障碍：section 为 region 语义并用 string 标题命名；按钮带 aria-expanded，
 *   aria-controls 指向内容容器 id（useId 生成，SSR 安全）。
 * - 视觉：对齐 Card 的实色表面 + hairline 边框 + 令牌类，不引入新颜色。
 */
export interface CollapsibleCardProps {
  title: React.ReactNode
  summary?: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  className?: string
}

export function CollapsibleCard({
  title,
  summary,
  children,
  defaultOpen,
  className = '',
}: CollapsibleCardProps) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  const contentId = useId()
  const ariaLabel = typeof title === 'string' ? title : undefined
  const summaryText = typeof summary === 'string' ? summary : undefined

  return (
    <section
      role="region"
      aria-label={ariaLabel}
      className={`rounded-tile border border-sf-line bg-sf-surface p-4 text-sf-ink ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-body font-semibold text-sf-ink" title={ariaLabel}>
            {title}
          </h3>
          {!open && summary != null && (
            <p className="mt-1 truncate text-label text-sf-ink-2" title={summaryText}>
              {summary}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={contentId}
          className="shrink-0 rounded-tile border border-sf-line px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
        >
          {open ? '收起 ▴' : '展开 ▾'}
        </button>
      </div>
      <div id={contentId} className="mt-3">
        {open ? children : null}
      </div>
    </section>
  )
}
