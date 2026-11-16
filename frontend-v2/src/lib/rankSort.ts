/** 排行表排序：正/逆两态 + 缺失值诚实排末尾 + 稳定排序。 */

export type SortDir = 'asc' | 'desc'

export interface SortState<K extends string = string> {
  key: K | null
  dir: SortDir
}

/** 点同一列在正/逆之间切换；点新列从默认方向（降序，榜单习惯）开始。 */
export function nextSortState<K extends string>(
  cur: SortState<K>,
  key: K,
  defaultDir: SortDir = 'desc',
): SortState<K> {
  if (cur.key !== key) return { key, dir: defaultDir }
  return { key, dir: cur.dir === 'desc' ? 'asc' : 'desc' }
}

export type SortValue = number | string | null | undefined

function isMissing(v: SortValue): boolean {
  return v == null || (typeof v === 'number' && !Number.isFinite(v))
}

/**
 * 排序纯函数：
 *  - `null` / `undefined` / `NaN` **永远排末尾**，不补 0、不把缺失当最小值（诚实红线）；
 *  - 数值按数值比较，其余按 zh-CN 文本比较；
 *  - 同值用原始下标做 tiebreak，保证稳定，不因浏览器排序实现漂移。
 */
export function sortRankRows<T>(
  rows: readonly T[],
  key: string | null,
  dir: SortDir,
  accessor: (row: T, key: string) => SortValue,
): T[] {
  if (!key) return [...rows]
  const decorated = rows.map((row, i) => ({ row, i, v: accessor(row, key) }))
  decorated.sort((a, b) => {
    const aNull = isMissing(a.v)
    const bNull = isMissing(b.v)
    if (aNull && bNull) return a.i - b.i
    if (aNull) return 1
    if (bNull) return -1
    const av = a.v as number | string
    const bv = b.v as number | string
    let cmp = 0
    if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv
    else cmp = String(av).localeCompare(String(bv), 'zh-CN')
    if (cmp === 0) return a.i - b.i
    return dir === 'asc' ? cmp : -cmp
  })
  return decorated.map((d) => d.row)
}

/** 表头 aria-sort 值，避免各处手写字符串漂移。 */
export function ariaSort(active: boolean, dir: SortDir): 'ascending' | 'descending' | 'none' {
  if (!active) return 'none'
  return dir === 'asc' ? 'ascending' : 'descending'
}
