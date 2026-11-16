import { describe, it, expect } from 'vitest'
import { ariaSort, nextSortState, sortRankRows } from './rankSort'

type Row = { name: string; v: number | null }
const rows: Row[] = [
  { name: 'A', v: 3 },
  { name: 'B', v: null },
  { name: 'C', v: 10 },
  { name: 'D', v: 3 },
  { name: 'E', v: -1 },
]
const acc = (r: Row, k: string) => (k === 'v' ? r.v : r.name)
const names = (rs: Row[]) => rs.map((r) => r.name).join(',')

describe('sortRankRows · 排行表正/逆排序', () => {
  it('降序把大值排前，null 恒排末尾', () => {
    expect(names(sortRankRows(rows, 'v', 'desc', acc))).toBe('C,A,D,E,B')
  })

  it('升序把小值排前，null 仍恒排末尾（不补 0）', () => {
    expect(names(sortRankRows(rows, 'v', 'asc', acc))).toBe('E,A,D,C,B')
  })

  it('同值保持原始顺序（稳定排序），不随浏览器实现漂移', () => {
    expect(names(sortRankRows(rows, 'v', 'desc', acc))).toContain('A,D')
  })

  it('NaN / undefined 同样视为缺失，绝不参与数值比较', () => {
    const rs: Row[] = [{ name: 'X', v: Number.NaN }, { name: 'Y', v: 5 }]
    expect(names(sortRankRows(rs, 'v', 'asc', acc))).toBe('Y,X')
  })

  it('无排序列时原样返回副本', () => {
    const out = sortRankRows(rows, null, 'desc', acc)
    expect(names(out)).toBe('A,B,C,D,E')
    expect(out).not.toBe(rows)
  })

  it('文本列按 zh-CN 比较，正逆都生效', () => {
    const rs = [{ name: '银行' }, { name: '保险' }, { name: '白酒' }]
    const a = (r: { name: string }) => r.name
    expect(sortRankRows(rs, 'name', 'asc', a).map((r) => r.name).join(',')).toBe(
      sortRankRows(rs, 'name', 'asc', a).map((r) => r.name).join(','),
    )
    expect(sortRankRows(rs, 'name', 'desc', a).map((r) => r.name)).toEqual(
      [...sortRankRows(rs, 'name', 'asc', a).map((r) => r.name)].reverse(),
    )
  })
})

describe('nextSortState / ariaSort', () => {
  it('点新列从降序开始，再点切升序，第三下回降序', () => {
    let s = nextSortState({ key: null, dir: 'desc' }, 'v')
    expect(s).toEqual({ key: 'v', dir: 'desc' })
    s = nextSortState(s, 'v')
    expect(s).toEqual({ key: 'v', dir: 'asc' })
    s = nextSortState(s, 'v')
    expect(s).toEqual({ key: 'v', dir: 'desc' })
  })

  it('换列重置为默认方向', () => {
    expect(nextSortState({ key: 'v', dir: 'asc' }, 'net')).toEqual({ key: 'net', dir: 'desc' })
  })

  it('aria-sort 与方向一致', () => {
    expect(ariaSort(false, 'desc')).toBe('none')
    expect(ariaSort(true, 'desc')).toBe('descending')
    expect(ariaSort(true, 'asc')).toBe('ascending')
  })
})
