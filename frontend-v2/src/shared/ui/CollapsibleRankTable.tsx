import { useId, useState, type ReactNode } from 'react'
import { ariaSort, nextSortState, sortRankRows, type SortDir, type SortState } from '@/lib/rankSort'

/**
 * 折叠式排行榜（截图 1 反馈：长榜单希望先折叠，展开后排名列可正/逆排序）。
 *
 * 折叠前 —— 「榜单速览」摘要卡（本组件自行设计，不要求调用方另写）：
 *   TopN 名称 + 主指标迷你条 + 主指标渲染值 + 共 N 项 + 展开按钮；
 *   条形只按真实数值比例画，缺失值不画条也不补 0。
 * 展开后 —— 完整表格，表头点击在降序 / 升序之间切换，带 aria-sort 与 ▲▼ 指示。
 *
 * 排序是纯前端、稳定、缺失值恒排末尾（lib/rankSort.ts），不改动后端数据、
 * 不把 null 当 0、不编造名次。行序号列始终按当前排序后的顺序显示。
 */
export interface RankColumn<T> {
  key: string
  title: string
  align?: 'left' | 'right'
  /** 是否可排序；数值/排名列默认 true（由调用方显式声明以守契约） */
  sortable?: boolean
  value: (row: T) => number | string | null | undefined
  render: (row: T, index: number) => ReactNode
}

export interface CollapsibleRankTableProps<T> {
  title: string
  rows: readonly T[]
  columns: RankColumn<T>[]
  rowKey: (row: T, index: number) => string
  defaultSort?: { key: string; dir: SortDir }
  /** 折叠前速览条数，默认 3 */
  summaryCount?: number
  hint?: string
  /** 迷你条颜色（A股红涨绿跌由调用方决定）；不给则用当前主题色 */
  barColor?: (row: T) => string | undefined
  initiallyOpen?: boolean
}

export function CollapsibleRankTable<T>({
  title,
  rows,
  columns,
  rowKey,
  defaultSort,
  summaryCount = 3,
  hint,
  barColor,
  initiallyOpen = false,
}: CollapsibleRankTableProps<T>) {
  const [open, setOpen] = useState(initiallyOpen)
  const [sort, setSort] = useState<SortState<string>>(
    defaultSort ?? { key: null, dir: 'desc' },
  )
  const listId = useId()

  const activeCol = columns.find((c) => c.key === sort.key) ?? null
  const ordered = sortRankRows(
    rows,
    activeCol?.key ?? null,
    sort.dir,
    (row, k) => columns.find((c) => c.key === k)?.value(row) ?? null,
  )

  const metricCol =
    columns.find((c) => c.key === (sort.key ?? defaultSort?.key)) ??
    columns.find((c) => c.sortable) ??
    columns[0]
  const labelCol = columns[0]
  const summaryRows = ordered.slice(0, Math.max(1, summaryCount))
  const maxAbs = rows.reduce((m, r) => {
    const v = Number(metricCol?.value(r))
    return Number.isFinite(v) ? Math.max(m, Math.abs(v)) : m
  }, 0)

  const toggle = (
    <button
      type="button"
      onClick={() => setOpen((v) => !v)}
      aria-expanded={open}
      aria-controls={listId}
      className="rounded-tile border border-sf-line px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
    >
      {open ? '收起 ▲' : `展开完整榜单（${rows.length} 项）▼`}
    </button>
  )

  return (
    <section className="rounded-tile border border-sf-line bg-sf-surface p-3 text-sf-ink">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="text-body font-semibold text-sf-ink">{title}</h3>
        <div className="flex items-center gap-2">
          <span className="text-label text-sf-ink-3">共 {rows.length} 项</span>
          {toggle}
        </div>
      </div>

      {!open && (
        <div className="mt-3 space-y-2">
          {summaryRows.length === 0 ? (
            <p className="text-body text-sf-ink-3">本次没有可展示的条目。</p>
          ) : (
            summaryRows.map((row, i) => {
              const raw = metricCol?.value(row)
              const num = Number(raw)
              const hasNum = raw != null && raw !== '' && Number.isFinite(num)
              const width = hasNum && maxAbs > 0 ? Math.min(100, (Math.abs(num) / maxAbs) * 100) : 0
              return (
                <div key={rowKey(row, i)} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto] items-center gap-2">
                  <span className="truncate text-body text-sf-ink-2">
                    <span className="mr-1.5 text-label text-sf-ink-3">{i + 1}</span>
                    {labelCol?.render(row, i)}
                  </span>
                  <div className="h-1.5 overflow-hidden rounded-full bg-sf-line/50" aria-hidden="true">
                    <div
                      className="h-full rounded-full text-sf-accent"
                      style={{ width: `${width}%`, backgroundColor: barColor?.(row) ?? 'currentColor' }}
                    />
                  </div>
                  <span className="text-right text-body tabular-nums text-sf-ink">
                    {metricCol?.render(row, i)}
                  </span>
                </div>
              )
            })
          )}
          <p className="text-label text-sf-ink-3">
            速览按{metricCol?.title ?? '默认顺序'}
            {sort.key ? `（${sort.dir === 'desc' ? '降序' : '升序'}）` : ''}展示前 {summaryRows.length} 项；展开后可点击表头正/逆排序。
          </p>
        </div>
      )}

      <div id={listId} hidden={!open} className="mt-3">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-sf-ink">
            <thead>
              <tr className="border-b border-sf-line text-sf-ink-3">
                <th scope="col" className="py-1.5 pr-3 text-left">#</th>
                {columns.map((c) => {
                  const active = sort.key === c.key
                  return (
                    <th
                      key={c.key}
                      scope="col"
                      aria-sort={ariaSort(active, sort.dir)}
                      className={`py-1.5 pr-3 ${c.align === 'right' ? 'text-right' : 'text-left'}`}
                    >
                      {c.sortable ? (
                        <button
                          type="button"
                          onClick={() => setSort((s) => nextSortState(s, c.key))}
                          className="inline-flex items-center gap-1 hover:text-sf-accent"
                          aria-label={`按${c.title}排序`}
                        >
                          {c.title}
                          <span aria-hidden="true">{active ? (sort.dir === 'desc' ? '▼' : '▲') : '⇅'}</span>
                        </button>
                      ) : (
                        c.title
                      )}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {ordered.map((row, i) => (
                <tr key={rowKey(row, i)} className="border-b border-sf-line/60">
                  <td className="py-1.5 pr-3 text-label text-sf-ink-3">{i + 1}</td>
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={`py-1.5 pr-3 ${c.align === 'right' ? 'text-right' : 'text-left'}`}
                    >
                      {c.render(row, i)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hint && <p className="mt-2 text-label text-sf-ink-3">{hint}</p>}
      </div>
    </section>
  )
}
