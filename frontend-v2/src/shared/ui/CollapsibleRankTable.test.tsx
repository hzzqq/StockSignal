import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CollapsibleRankTable, type RankColumn } from './CollapsibleRankTable'

type Row = { name: string; chg: number | null; net: number }
const rows: Row[] = [
  { name: '小家电', chg: 1.87, net: 0 },
  { name: '银行', chg: 1.5, net: -2 },
  { name: '白酒', chg: 0.74, net: 5 },
  { name: '钢铁', chg: -0.82, net: null as unknown as number },
]
const columns: RankColumn<Row>[] = [
  { key: 'name', title: '行业', value: (r) => r.name, render: (r) => r.name, sortable: true },
  { key: 'chg', title: '涨跌幅%', align: 'right', value: (r) => r.chg, render: (r) => (r.chg == null ? '—' : `${r.chg}%`), sortable: true },
  { key: 'net', title: '净额(亿)', align: 'right', value: (r) => r.net, render: (r) => (r.net == null ? '—' : String(r.net)), sortable: true },
]
const props = {
  title: '行业板块资金流向',
  rows,
  columns,
  rowKey: (r: Row) => r.name,
  defaultSort: { key: 'chg', dir: 'desc' as const },
  summaryCount: 3,
}
const bodyNames = (c: HTMLElement) =>
  [...c.querySelectorAll('tbody tr')].map((tr) => tr.querySelectorAll('td')[1]?.textContent ?? '')

describe('CollapsibleRankTable · 折叠 + 排名正逆排序', () => {
  it('默认折叠：显示速览 Top3 与共 N 项，完整表被隐藏', () => {
    const { container } = render(<CollapsibleRankTable {...props} />)
    expect(screen.getByText('共 4 项')).toBeTruthy()
    expect(screen.getByRole('button', { name: /展开完整榜单/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /收起/ })).toBeNull()
    const region = container.querySelector('[aria-controls]')?.getAttribute('aria-controls')
    const panel = region ? document.getElementById(region) : null
    expect(panel?.hasAttribute('hidden')).toBe(true)
    // 速览只画 3 条
    expect(container.textContent).toContain('展示前 3 项')
  })

  it('展开后表头可点击：降序 -> 升序，行顺序真的反转', () => {
    const { container } = render(<CollapsibleRankTable {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /展开完整榜单/ }))
    expect(bodyNames(container).join(',')).toBe('小家电,银行,白酒,钢铁')

    const btn = screen.getByRole('button', { name: /按涨跌幅%排序/ })
    fireEvent.click(btn) // desc -> asc
    expect(bodyNames(container).join(',')).toBe('钢铁,白酒,银行,小家电')
    expect(btn.closest('th')?.getAttribute('aria-sort')).toBe('ascending')

    fireEvent.click(btn) // asc -> desc
    expect(bodyNames(container).join(',')).toBe('小家电,银行,白酒,钢铁')
    expect(btn.closest('th')?.getAttribute('aria-sort')).toBe('descending')
  })

  it('切换到另一数值列排序，缺失值恒排末尾', () => {
    const { container } = render(<CollapsibleRankTable {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /展开完整榜单/ }))
    fireEvent.click(screen.getByRole('button', { name: /按净额\(亿\)排序/ }))
    expect(bodyNames(container).join(',')).toBe('白酒,小家电,银行,钢铁')
    fireEvent.click(screen.getByRole('button', { name: /按净额\(亿\)排序/ }))
    expect(bodyNames(container).at(-1)).toBe('钢铁')
  })

  it('收起按钮可再次折叠，且带 aria-expanded 语义', () => {
    render(<CollapsibleRankTable {...props} />)
    const open = screen.getByRole('button', { name: /展开完整榜单/ })
    expect(open.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(open)
    const close = screen.getByRole('button', { name: /收起/ })
    expect(close.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(close)
    expect(screen.getByRole('button', { name: /展开完整榜单/ })).toBeTruthy()
  })

  it('空数据不编造条目', () => {
    render(<CollapsibleRankTable {...props} rows={[]} />)
    expect(screen.getByText('共 0 项')).toBeTruthy()
    expect(screen.getByText('本次没有可展示的条目。')).toBeTruthy()
  })
})
