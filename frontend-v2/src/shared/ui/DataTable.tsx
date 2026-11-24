import type { ReactNode } from 'react'

/**
 * 精致层次档 · 统一数据表（不分页、不排序，保持简单可扩）。
 * 缺失数据只用 emptyText 标注（默认「暂无数据」），绝不补 0 / 不编造。
 */
export interface DataTableColumn<T> {
  key: string
  title: ReactNode
  align?: 'left' | 'right' | 'center'
  width?: string
  render?: (row: T) => ReactNode
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
  emptyText?: string
  className?: string
  onRowClick?: (row: T) => void
}

const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ')

const alignClass = (align?: 'left' | 'right' | 'center') =>
  align === 'right'
    ? 'text-right tabular-nums'
    : align === 'center'
      ? 'text-center'
      : 'text-left'

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyText = '暂无数据',
  className = '',
  onRowClick,
}: DataTableProps<T>) {
  return (
    <div
      className={cx(
        'w-full overflow-x-auto rounded-card border border-sf-line bg-sf-surface',
        className,
      )}
    >
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={cx(
                  'bg-sf-surface-2 px-3 py-2 text-label font-medium text-sf-ink-3',
                  alignClass(column.align),
                )}
              >
                {column.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-8 text-center text-body text-sf-ink-3"
              >
                {emptyText}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cx(
                  'border-b border-sf-line hover:bg-sf-surface-2',
                  onRowClick && 'cursor-pointer',
                )}
              >
                {columns.map((column) => {
                  const raw: unknown = column.render
                    ? column.render(row)
                    : (row as Record<string, unknown>)[column.key]
                  const cell: ReactNode =
                    raw === null || raw === undefined ? emptyText : (raw as ReactNode)
                  return (
                    <td
                      key={column.key}
                      className={cx('px-3 py-2 text-body text-sf-ink-2', alignClass(column.align))}
                    >
                      {cell}
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
