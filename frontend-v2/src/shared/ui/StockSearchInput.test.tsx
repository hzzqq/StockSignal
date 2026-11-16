import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useStockSearch } from '@/lib/queries'
import type { StockSearchItem } from '@/api/schemas/stockSearch'
import { StockSearchInput } from './StockSearchInput'

vi.mock('@/lib/queries', () => ({ useStockSearch: vi.fn() }))
const mHook = vi.mocked(useStockSearch)

const moutai: StockSearchItem = {
  code: '600519',
  name: '贵州茅台',
  market: 'SH',
  asset_type: 'stock',
  pinyin_initials: 'gzmt',
  pinyin_full: 'guizhoumaotai',
  score: 1000,
}

function setResults(data: StockSearchItem[], extra: Record<string, unknown> = {}) {
  mHook.mockReturnValue({
    data,
    isFetching: false,
    isError: false,
    error: null,
    ...extra,
  } as ReturnType<typeof useStockSearch>)
}

beforeEach(() => {
  vi.clearAllMocks()
  setResults([moutai])
})

describe('StockSearchInput · 代码/名称/首字母 + 匹配结果', () => {
  it('输入后列出匹配结果，显示名称、代码、市场与匹配方式标签', async () => {
    render(<StockSearchInput onSelect={() => {}} />)
    const input = screen.getByRole('combobox')
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'gzmt' } })
    expect(screen.getByText('贵州茅台')).toBeTruthy()
    expect(screen.getByText('600519')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('拼音首字母')).toBeTruthy())
    expect(screen.getByText('SH')).toBeTruthy()
  })

  it('点击候选项回调纯代码与完整条目，输入框回写代码', () => {
    const onSelect = vi.fn()
    render(<StockSearchInput onSelect={onSelect} />)
    const input = screen.getByRole('combobox')
    fireEvent.focus(input)
    fireEvent.click(screen.getByRole('option', { name: /贵州茅台/ }))
    expect(onSelect).toHaveBeenCalledWith('600519', moutai)
    expect((input as HTMLInputElement).value).toBe('600519')
  })

  it('键盘 ↓ + Enter 选中高亮项', () => {
    const onSelect = vi.fn()
    render(<StockSearchInput onSelect={onSelect} />)
    const input = screen.getByRole('combobox')
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: '600519' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith('600519', moutai)
  })

  it('无匹配时诚实显示空结果，不编造股票', async () => {
    setResults([])
    render(<StockSearchInput onSelect={() => {}} />)
    const input = screen.getByRole('combobox')
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'zzzzzz' } })
    await waitFor(() => expect(screen.getByText('未找到匹配的股票')).toBeTruthy())
  })

  it('接口失败显示为「搜索失败」而非「无匹配」', () => {
    setResults([], { isError: true, error: new Error('HTTP 502 网关错误') })
    render(<StockSearchInput onSelect={() => {}} />)
    fireEvent.focus(screen.getByRole('combobox'))
    expect(screen.getByRole('alert').textContent).toContain('HTTP 502 网关错误')
    expect(screen.queryByText('未找到匹配的股票')).toBeNull()
  })

  it('6 位代码无匹配时可回车直接查询，item 为 null（不臆造名称）', () => {
    setResults([])
    const onSelect = vi.fn()
    render(<StockSearchInput onSelect={onSelect} />)
    const input = screen.getByRole('combobox')
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: '688999' } })
    expect(screen.getByText(/直接按代码 688999 查询/)).toBeTruthy()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith('688999', null)
  })

  it('Esc 关闭下拉', () => {
    render(<StockSearchInput onSelect={() => {}} />)
    const input = screen.getByRole('combobox')
    fireEvent.focus(input)
    expect(input.getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input.getAttribute('aria-expanded')).toBe('false')
  })
})
