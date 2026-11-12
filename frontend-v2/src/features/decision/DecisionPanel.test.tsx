import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DecisionPanel } from './DecisionPanel'
import type { DailySnapshot } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({ getDailySnapshot: vi.fn() }))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getDailySnapshot } from '@/api/read'
const mocked = vi.mocked(getDailySnapshot)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  date: '2026-03-01',
  temperature: 55.5,
  indicators: { up_count: 3000 },
} as DailySnapshot

beforeEach(() => {
  mocked.mockReset()
})

describe('DecisionPanel · 54 今日决策面板 · 四态 + 诚实空态', () => {
  it('loading → 加载中…（标题常驻，不作为完成信号）', () => {
    mocked.mockReturnValue(new Promise(() => {}) as ReturnType<typeof getDailySnapshot>)
    renderWithClient(<DecisionPanel />)
    expect(screen.getByText('加载中…')).toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('error → 原样带出 error.message，不吞异常', async () => {
    mocked.mockRejectedValue(new Error('决策面板加载失败'))
    renderWithClient(<DecisionPanel />)
    await expect(screen.findByText('决策面板加载失败')).resolves.toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('ok → 渲染后端快照（前端不重算仓位）', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<DecisionPanel />)
    expect(await screen.findByText('权威数据日')).toBeTruthy()
    expect(screen.getByText('2026-03-01')).toBeTruthy()
    expect(screen.getByText('55.50')).toBeTruthy()
    expect(screen.getByText('3000')).toBeTruthy()
  })

  it('空结果 → 诚实空态「暂无数据」，不伪造快照', async () => {
    // 空态用 null（React Query 拒绝 undefined 作成功结果）
    mocked.mockResolvedValue(null as unknown as DailySnapshot)
    renderWithClient(<DecisionPanel />)
    await expect(screen.findByText('暂无数据')).resolves.toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })
})
