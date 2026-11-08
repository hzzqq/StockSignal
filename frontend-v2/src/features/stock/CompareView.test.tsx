import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CompareView, chunkCodes } from './CompareView'
import { getCompareOne } from '@/api/stock'

vi.mock('@/api/stock', () => ({
  getCompareOne: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

const mocked = vi.mocked(getCompareOne)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  mocked.mockReset()
})

describe('chunkCodes 分批（≤4 并发依据）', () => {
  it('按 size 切片', () => {
    expect(chunkCodes([1, 2, 3, 4, 5, 6, 7, 8], 4)).toEqual([
      [1, 2, 3, 4],
      [5, 6, 7, 8],
    ])
    expect(chunkCodes([1, 2, 3], 4)).toEqual([[1, 2, 3]])
    expect(chunkCodes([], 4)).toEqual([])
  })
})

describe('CompareView 逐股 4 态降级 + 字段数', () => {
  it('ok / error / empty / loading 分别渲染，字段并集正确', async () => {
    mocked.mockImplementation((code: string) => {
      if (code === '000002') return Promise.reject(new Error('fail'))
      if (code === '000003') return Promise.resolve({ code: '000003' })
      if (code === '000009') return new Promise<never>(() => {}) // 永不 resolve → loading
      return Promise.resolve({ code, price: 1523.5, change_pct: 1.24, revenue_yoy: 5.1 })
    })

    renderWithClient(<CompareView search={{ codes: ['600519', '000002', '000003', '000009'] }} />)

    // ok：字段头渲染（主对比表 + 等价数据表各一次）
    expect(await screen.findAllByText('price')).toHaveLength(2)
    expect(screen.getAllByText('change_pct').length).toBeGreaterThan(0)
    expect(screen.getAllByText('revenue_yoy').length).toBeGreaterThan(0)

    // error：获取失败（不谎报为数据；错误列每个字段格均回退为「获取失败」）
    expect((await screen.findAllByText('获取失败')).length).toBe(3)

    // empty：000003 无指标字段 → '—'
    expect((await screen.findAllByText('—')).length).toBeGreaterThanOrEqual(3)

    // loading：000009 在途 → '加载中…'
    expect((await screen.findAllByText('加载中…')).length).toBeGreaterThanOrEqual(3)
  })

  it('全部无指标字段时显示「暂无对比数据」', async () => {
    mocked.mockImplementation((code: string) =>
      code === '000002' ? Promise.reject(new Error('fail')) : Promise.resolve({ code }),
    )
    renderWithClient(<CompareView search={{ codes: ['000002', '000003'] }} />)
    expect(await screen.findByText('暂无对比数据')).toBeTruthy()
  })
})
