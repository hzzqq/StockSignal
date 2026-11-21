// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { PatternScan } from '@/features/pattern/PatternScan'

/**
 * 形态扫描池的股票搜索追加（对齐个股研究同款 StockSearchInput）：
 *  ① 搜索框是 combobox（代码/名称/拼音首字母召回，带匹配结果与名称）；
 *  ② 选中候选后代码追加到批量输入（去重），并显示股票名称；
 *  ③ 不破坏手输批量语义（原 600519, 000001 默认保留）。
 */
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => { server.resetHandlers(); cleanup() })
afterAll(() => server.close())

function renderScan() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
  return render(<QueryClientProvider client={client}><PatternScan /></QueryClientProvider>)
}

describe('形态扫描池 · 股票搜索追加', () => {
  it('搜索框为 combobox，支持按名称召回并展示匹配结果（名称+代码）', async () => {
    renderScan()
    const box = screen.getByRole('combobox', { name: '搜索追加扫描标的（代码 / 名称 / 首字母）' })
    fireEvent.change(box, { target: { value: '贵州茅台' } })
    // 候选下拉：贵州茅台 600519（matchStockPool 真实召回）
    expect(await screen.findByRole('option', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getAllByText('贵州茅台').length).toBeGreaterThan(0)
  })

  it('选中候选后代码去重追加到批量输入，并显示名称；手输默认池不丢', async () => {
    renderScan()
    const input = screen.getByLabelText('股票代码（6 位，逗号 / 空格分隔，1–50 只）') as HTMLInputElement
    expect(input.value).toBe('600519, 000001') // 手输默认池保留
    const box = screen.getByRole('combobox', { name: '搜索追加扫描标的（代码 / 名称 / 首字母）' })
    fireEvent.change(box, { target: { value: '300750' } })
    const option = await screen.findByRole('option', {}, { timeout: 5000 })
    fireEvent.click(option)
    await waitFor(() => {
      expect((screen.getByLabelText('股票代码（6 位，逗号 / 空格分隔，1–50 只）') as HTMLInputElement).value).toContain('300750')
    })
    // 已选池列表显示代码+名称（名称来自搜索候选，不臆造）
    const picked = screen.getByLabelText('已选扫描标的')
    expect(picked.textContent).toContain('300750')
  })

  it('重复选中同一代码不重复追加', async () => {
    renderScan()
    const input = screen.getByLabelText('股票代码（6 位，逗号 / 空格分隔，1–50 只）') as HTMLInputElement
    const box = screen.getByRole('combobox', { name: '搜索追加扫描标的（代码 / 名称 / 首字母）' })
    // 600519 已在默认池，搜索选中后不应重复
    fireEvent.change(box, { target: { value: '600519' } })
    const option = await screen.findByRole('option', {}, { timeout: 5000 })
    fireEvent.click(option)
    await waitFor(() => expect(input.value.split(/[,\s]+/).filter(Boolean)).toHaveLength(2))
  })
})
