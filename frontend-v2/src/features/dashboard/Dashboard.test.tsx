import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Dashboard } from './Dashboard'
import type { DailySnapshot } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getDailySnapshot: vi.fn(),
  getP1Signals: vi.fn(),
  getWebApps: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}))
vi.mock('@/features/stock/components/IndexQuotes', () => ({ IndexQuotes: () => null }))
vi.mock('./ProjectIntro', () => ({ ProjectIntro: () => null }))
import { getDailySnapshot, getP1Signals, getWebApps } from '@/api/read'
const snapMock = vi.mocked(getDailySnapshot)
const p1Mock = vi.mocked(getP1Signals)
const webMock = vi.mocked(getWebApps)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okSnap = { date: '2026-03-01', score: 62, indicators: { up_count: 3000 } } as DailySnapshot

beforeEach(() => {
  snapMock.mockReset().mockResolvedValue(okSnap)
  p1Mock.mockReset().mockResolvedValue({})
  webMock.mockReset().mockResolvedValue([])
})

describe('Dashboard · 首页概览 · 多查询聚合 + 诚实占位', () => {
  it('三查询成功 → P1 最新数据日取最大、作品数、快照数据日/评分、内嵌快照视图', async () => {
    // P1 信号按数据日取最大（不是文件 mtime、也不是数组顺序）
    p1Mock.mockResolvedValue({
      a: { latest_date: '2026-09-01' },
      b: { latest_date: '2026-10-16' },
      c: {},
    } as never)
    webMock.mockResolvedValue([{ id: '1' }, { id: '2' }] as never)
    renderWithClient(<Dashboard />)
    expect(await screen.findByText('2026-10-16')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy() // 网页作品
    // 同一日期在首页 Stat 与 SnapshotView 大标题各出现一次
    expect(screen.getAllByText('2026-03-01')).toHaveLength(2)
    // 综合评分 62 同样在首页 Stat 与 SnapshotView 各出现一次
    expect(screen.getAllByText('62').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('权威数据日')).toBeTruthy() // SnapshotView 复用
  })

  it('三查询全失败 → 4 个 Stat 显「—」占位，错误如实标注，不编造数值', async () => {
    snapMock.mockRejectedValue(new Error('快照挂了'))
    p1Mock.mockRejectedValue(new Error('P1 挂了'))
    webMock.mockRejectedValue(new Error('作品挂了'))
    renderWithClient(<Dashboard />)
    await expect(screen.findByText('决策快照加载失败')).resolves.toBeTruthy()
    expect(screen.getByText('加载失败')).toBeTruthy() // P1 Stat 的 sub
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('P1 信号全部无 latest_date → 「—」，不用数组顺序或空字符串冒充', async () => {
    p1Mock.mockResolvedValue({ a: {}, b: {} } as never)
    renderWithClient(<Dashboard />)
    expect(await screen.findByText('权威数据日')).toBeTruthy()
    const stat = screen.getByText('P1 信号最新数据日').parentElement
    expect(stat?.textContent).toContain('—')
  })

  it('快照 score 缺失 → fmtNum 显「—」，绝不补 0', async () => {
    snapMock.mockResolvedValue({ date: '2026-03-01' } as DailySnapshot)
    renderWithClient(<Dashboard />)
    expect(await screen.findByText('权威数据日')).toBeTruthy()
    // SnapshotView 内也有同名「综合评分」Stat → 取首页那个（第 0 个）
    const stat = screen.getAllByText('综合评分')[0].parentElement
    expect(stat?.textContent).toContain('—')
    expect(stat?.textContent).not.toContain('0.00')
  })

  it('快照加载中 → 显「加载中…」，不提前渲染快照视图', () => {
    snapMock.mockReturnValue(new Promise<DailySnapshot>(() => {}))
    renderWithClient(<Dashboard />)
    expect(screen.getByText('加载中…')).toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })
})
