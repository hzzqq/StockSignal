import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DecisionReplay } from './DecisionReplay'
import type { DailySnapshot } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getSnapshotDates: vi.fn(),
  getSnapshotByDate: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getSnapshotDates, getSnapshotByDate } from '@/api/read'
const datesMock = vi.mocked(getSnapshotDates)
const snapMock = vi.mocked(getSnapshotByDate)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = { date: '2026-03-01', temperature: 55.5 } as DailySnapshot

beforeEach(() => {
  datesMock.mockReset().mockResolvedValue(['2026-03-01', '2026-02-28'])
  snapMock.mockReset().mockResolvedValue(okData)
})

describe('DecisionReplay · 97 决策回放 · 日期交互 + 不发起查询守卫', () => {
  it('默认未选日期 → 不发快照查询（enabled 守卫），仅列出归档日期', async () => {
    renderWithClient(<DecisionReplay />)
    expect(screen.getByText('— 请选择 —')).toBeTruthy()
    await expect(screen.findByText('2026-02-28')).resolves.toBeTruthy()
    expect(snapMock).not.toHaveBeenCalled()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('日期清单加载失败 → ErrorState 原样带出原因', async () => {
    datesMock.mockRejectedValue(new Error('清单挂了'))
    renderWithClient(<DecisionReplay />)
    await expect(screen.findByText('日期清单加载失败：清单挂了')).resolves.toBeTruthy()
    expect(snapMock).not.toHaveBeenCalled()
  })

  it('选中归档日期 → 拉取该日快照并复用 SnapshotView 渲染', async () => {
    renderWithClient(<DecisionReplay />)
    await screen.findByText('2026-02-28')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-03-01' } })
    expect(await screen.findByText('权威数据日')).toBeTruthy()
    expect(snapMock).toHaveBeenCalledWith('2026-03-01')
    expect(screen.getByText('55.50')).toBeTruthy()
  })

  it('选中日期但该日无归档快照 → 诚实空态「该日期无归档快照」', async () => {
    snapMock.mockResolvedValue(null as unknown as DailySnapshot)
    renderWithClient(<DecisionReplay />)
    await screen.findByText('2026-02-28')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-03-01' } })
    await expect(screen.findByText('该日期无归档快照')).resolves.toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })

  it('选中日期但快照加载失败 → 错误态，不回退成空数据', async () => {
    snapMock.mockRejectedValue(new Error('快照加载失败'))
    renderWithClient(<DecisionReplay />)
    await screen.findByText('2026-02-28')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-03-01' } })
    await expect(screen.findByText('快照加载失败')).resolves.toBeTruthy()
    expect(screen.queryByText('权威数据日')).toBeNull()
  })
})
