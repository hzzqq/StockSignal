import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/**
 * 搜索框是外部依赖（内部会发 /api/stocks/search），本测试聚焦删除确认交互，
 * 用最简替身隔离网络查询，避免把「删除是否发生」与「搜索是否可用」耦合。
 */
vi.mock('@/shared/ui/StockSearchInput', () => ({
  StockSearchInput: ({ label }: { label?: string }) => (
    <label>
      {label}
      <input aria-label={label} />
    </label>
  ),
}))

/** 三组读 hooks + 全部写 hooks 均来自同一模块，此处一次性替身。 */
vi.mock('@/lib/queriesUserCollections', () => ({
  useWatchlistQuery: vi.fn(),
  useJunkStocksQuery: vi.fn(),
  useUserScoresQuery: vi.fn(),
  useAddWatchlist: vi.fn(),
  useDeleteWatchlist: vi.fn(),
  useAddWatchlistBatch: vi.fn(),
  useDeleteWatchlistBatch: vi.fn(),
  useAddJunkStock: vi.fn(),
  useDeleteJunkStock: vi.fn(),
  useDeleteJunkStockBatch: vi.fn(),
  useUpsertUserScore: vi.fn(),
  useDeleteUserScore: vi.fn(),
}))

import * as Hooks from '@/lib/queriesUserCollections'
import { WatchWritePanels } from './WatchWritePanels'

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

type Mutate = ReturnType<typeof vi.fn>
const mutation = (mutate: Mutate) => ({
  mutate,
  isPending: false,
  reset: vi.fn(),
  error: null,
})
const query = (data: unknown[]) => ({
  data,
  isLoading: false,
  isError: false,
  error: null,
})

let delWatchlist: Mutate
let delJunk: Mutate
let delScore: Mutate

beforeEach(() => {
  vi.clearAllMocks()
  delWatchlist = vi.fn()
  delJunk = vi.fn()
  delScore = vi.fn()

  vi.mocked(Hooks.useWatchlistQuery).mockReturnValue(
    query([{ id: 1, stock_code: '600519', stock_name: '贵州茅台', note: '' }]) as never,
  )
  vi.mocked(Hooks.useJunkStocksQuery).mockReturnValue(
    query([{ id: 2, stock_code: '000001', stock_name: '平安银行', note: '' }]) as never,
  )
  vi.mocked(Hooks.useUserScoresQuery).mockReturnValue(
    query([{ id: 3, stock_code: '300750', stock_name: '宁德时代', score: 88, updated_at: null }]) as never,
  )

  vi.mocked(Hooks.useAddWatchlist).mockReturnValue(mutation(vi.fn()) as never)
  vi.mocked(Hooks.useDeleteWatchlist).mockReturnValue(mutation(delWatchlist) as never)
  vi.mocked(Hooks.useAddWatchlistBatch).mockReturnValue(mutation(vi.fn()) as never)
  vi.mocked(Hooks.useDeleteWatchlistBatch).mockReturnValue(mutation(vi.fn()) as never)
  vi.mocked(Hooks.useAddJunkStock).mockReturnValue(mutation(vi.fn()) as never)
  vi.mocked(Hooks.useDeleteJunkStock).mockReturnValue(mutation(delJunk) as never)
  vi.mocked(Hooks.useDeleteJunkStockBatch).mockReturnValue(mutation(vi.fn()) as never)
  vi.mocked(Hooks.useUpsertUserScore).mockReturnValue(mutation(vi.fn()) as never)
  vi.mocked(Hooks.useDeleteUserScore).mockReturnValue(mutation(delScore) as never)
})

describe('WatchWritePanels 单行删除就地确认（P1：误点即不可恢复 → 首击只确认）', () => {
  it('自选股：首击只进入确认态、不调用 mutate；确认按钮才删除', () => {
    renderWithClient(<WatchWritePanels />)
    fireEvent.click(screen.getByRole('button', { name: '删除自选股 600519' }))
    expect(delWatchlist).not.toHaveBeenCalled()
    expect(screen.getByText('确认删除 自选股 600519？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    expect(delWatchlist).toHaveBeenCalledTimes(1)
    expect(delWatchlist).toHaveBeenCalledWith({ id: 1 }, expect.any(Object))
  })

  it('自选股：取消复位到普通删除按钮，不调用 mutate', () => {
    renderWithClient(<WatchWritePanels />)
    fireEvent.click(screen.getByRole('button', { name: '删除自选股 600519' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(delWatchlist).not.toHaveBeenCalled()
    expect(screen.queryByText('确认删除 自选股 600519？')).toBeNull()
    expect(screen.getByRole('button', { name: '删除自选股 600519' })).toBeTruthy()
  })

  it('垃圾股：首击不删、确认才删（id 参数正确）', () => {
    renderWithClient(<WatchWritePanels />)
    fireEvent.click(screen.getByRole('button', { name: '删除垃圾股 000001' }))
    expect(delJunk).not.toHaveBeenCalled()
    expect(screen.getByText('确认删除 垃圾股 000001？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    expect(delJunk).toHaveBeenCalledTimes(1)
    expect(delJunk).toHaveBeenCalledWith({ id: 2 }, expect.any(Object))
  })

  it('打分：首击不删、确认才删（code 参数正确）', () => {
    renderWithClient(<WatchWritePanels />)
    fireEvent.click(screen.getByRole('button', { name: '删除打分 300750' }))
    expect(delScore).not.toHaveBeenCalled()
    expect(screen.getByText('确认删除 打分 300750？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    expect(delScore).toHaveBeenCalledTimes(1)
    expect(delScore).toHaveBeenCalledWith({ code: '300750' }, expect.any(Object))
  })

  it('三块面板互不串扰：确认自选股不会触发垃圾股/打分删除', () => {
    renderWithClient(<WatchWritePanels />)
    fireEvent.click(screen.getByRole('button', { name: '删除自选股 600519' }))
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
    expect(delWatchlist).toHaveBeenCalledTimes(1)
    expect(delJunk).not.toHaveBeenCalled()
    expect(delScore).not.toHaveBeenCalled()
  })
})
