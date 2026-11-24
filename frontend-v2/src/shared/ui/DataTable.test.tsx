import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { DataTable } from './DataTable'
import type { DataTableColumn } from './DataTable'

interface Row {
  code: string
  name: string
  pnl: number
}

const columns: DataTableColumn<Row>[] = [
  { key: 'code', title: '代码', width: '30%' },
  { key: 'name', title: '名称', render: (row) => row.name },
  { key: 'pnl', title: '盈亏', align: 'right', render: (row) => String(row.pnl) },
]

const rows: Row[] = [
  { code: '600519', name: '甲', pnl: 12 },
  { code: '000001', name: '乙', pnl: -3 },
]

describe('DataTable · 统一样式 / 空态 / 行点击', () => {
  it('渲染列头（scope=col）与全部行，无 render 列按 key 取值', () => {
    const { container } = render(
      <DataTable columns={columns} rows={rows} rowKey={(row) => row.code} />,
    )
    const ths = container.querySelectorAll('thead th')
    expect(ths.length).toBe(3)
    ths.forEach((th) => expect(th.getAttribute('scope')).toBe('col'))
    expect(screen.getByText('代码')).toBeTruthy()
    expect(screen.getByText('名称')).toBeTruthy()
    expect(screen.getByText('盈亏')).toBeTruthy()
    expect(container.querySelectorAll('tbody tr').length).toBe(2)
    expect(screen.getByText('600519')).toBeTruthy()
    expect(screen.getByText('乙')).toBeTruthy()
  })

  it('align=right 的列带 tabular-nums 与 text-right', () => {
    const { container } = render(
      <DataTable columns={columns} rows={rows} rowKey={(row) => row.code} />,
    )
    const cells = container.querySelectorAll('tbody tr')[0].querySelectorAll('td')
    expect(cells[2].className).toContain('text-right')
    expect(cells[2].className).toContain('tabular-nums')
    expect(cells[0].className).not.toContain('tabular-nums')
    expect(cells[0].className).toContain('px-3')
    expect(cells[0].className).toContain('py-2')
  })

  it('onRowClick 携带对应行数据触发', () => {
    const onRowClick = vi.fn()
    const { container } = render(
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.code}
        onRowClick={onRowClick}
      />,
    )
    fireEvent.click(container.querySelectorAll('tbody tr')[1])
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(rows[1])
  })

  it('空数据渲染单行 colspan 与「暂无数据」，不补零', () => {
    const { container } = render(
      <DataTable columns={columns} rows={[]} rowKey={(row) => row.code} />,
    )
    expect(screen.getByText('暂无数据')).toBeTruthy()
    const td = container.querySelector('tbody td')!
    expect(td.getAttribute('colspan')).toBe('3')
    expect(container.textContent).not.toContain('0')
  })

  it('emptyText / className 可覆盖，宽度写入 style', () => {
    const { container } = render(
      <DataTable
        columns={columns}
        rows={[]}
        rowKey={(row) => row.code}
        emptyText="无匹配记录"
        className="mt-4"
      />,
    )
    expect(screen.getByText('无匹配记录')).toBeTruthy()
    expect(container.firstElementChild!.className).toContain('mt-4')
    expect((container.querySelector('thead th') as HTMLElement).style.width).toBe('30%')
  })
})
