import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { EventPoolView } from './EventPoolView'
import type { EventPool } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getEventPool: vi.fn(),
  getEventLongList: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getEventPool, getEventLongList } from '@/api/read'
const mocked = vi.mocked(getEventPool)
const mockedLong = vi.mocked(getEventLongList)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  date: '2026-03-01',
  model: 'v40',
  source: 'P1',
  count: 2,
  note: '统计意义上的超额收益概率排序，非买卖指令',
  pool: [
    { rank: 1, symbol: '600000', score: 88.5, raw_rank: 1, raw_pred: 0.1234, signal: '多头', source: 'P1' },
    { rank: 2, symbol: '600519', score: 72, raw_rank: 2, raw_pred: 0.0987, signal: '多头', source: 'P1' },
  ],
} as unknown as EventPool

beforeEach(() => {
  mocked.mockReset().mockResolvedValue(okData)
  // 新看多榜区块默认走空榜，避免干扰既有事件池用例；本批次末尾单独测非空榜。
  mockedLong.mockReset().mockResolvedValue({ items: [], count: 0, note: '演示：空榜' })
})

describe('EventPoolView · 事件因子池 · 免责口径 + 不补零', () => {
  it('loading → 加载中…', () => {
    mocked.mockReturnValue(new Promise<EventPool>(() => {}))
    renderWithClient(<EventPoolView />)
    // 新增 I3 看多榜区块后同屏有两处加载态，两者都应是加载中
    expect(screen.getAllByText('加载中…').length).toBeGreaterThanOrEqual(1)
  })

  it('error → 原样带出错误', async () => {
    mocked.mockRejectedValue(new Error('事件池加载失败'))
    renderWithClient(<EventPoolView />)
    await expect(screen.findByText('事件池加载失败')).resolves.toBeTruthy()
  })

  it('空池 → 诚实空态「事件池为空」+ 未填充 hint', async () => {
    mocked.mockResolvedValue({ date: '2026-03-01', pool: [] } as EventPool)
    renderWithClient(<EventPoolView />)
    await expect(screen.findByText('事件池为空')).resolves.toBeTruthy()
    expect(screen.getByText('数据文件缺失或池内无标的，未做任何填充')).toBeTruthy()
  })

  it('ok → 口径免责原文原样带出 + 数据日/模型/来源 + 明细', async () => {
    renderWithClient(<EventPoolView />)
    expect(await screen.findByText('统计意义上的超额收益概率排序，非买卖指令')).toBeTruthy()
    expect(screen.getByText('2026-03-01')).toBeTruthy()
    expect(screen.getByText('v40')).toBeTruthy()
    expect(screen.getByText('600000')).toBeTruthy()
    expect(screen.getByText('88.50')).toBeTruthy() // fmtNum 浮点保留两位
    expect(screen.getByText('0.12')).toBeTruthy()
    expect(screen.getByText(/不构成投资建议/)).toBeTruthy()
    expect(screen.getByText(/不代表预期收益率/)).toBeTruthy()
  })

  it('逐条字段缺失 → 一律「—」，绝不补 0 或伪造信号', async () => {
    mocked.mockResolvedValue({
      date: '2026-03-01',
      pool: [
        { rank: 1, symbol: '600000', score: null, raw_rank: null, raw_pred: null, signal: null, source: null },
      ],
    } as unknown as EventPool)
    renderWithClient(<EventPoolView />)
    expect(await screen.findByText('600000')).toBeTruthy()
    const row = screen.getByText('600000').closest('tr')
    expect(row?.textContent).not.toContain('0.00')
    expect(row?.textContent).toContain('—')
    // note 缺失也不编造
    expect(screen.getByText('原始文件未提供口径说明')).toBeTruthy()
  })

  it('count 缺失 → 用实际明细行数（诚实派生值），不补 0 不臆造', async () => {
    mocked.mockResolvedValue({
      date: '2026-03-01',
      count: null,
      pool: okData.pool,
    } as unknown as EventPool)
    renderWithClient(<EventPoolView />)
    expect(await screen.findByText('池内标的')).toBeTruthy()
    expect(screen.getByText('池内标的').parentElement?.textContent).toContain('2')
  })
})

describe('EventPoolView · I3 事件驱动看多榜', () => {
  it('空榜 → 诚实显示「无信号」，不补 0', async () => {
    mockedLong.mockResolvedValue({ items: [], count: 0, note: '演示：空榜' })
    renderWithClient(<EventPoolView />)
    expect(await screen.findByText('无信号')).toBeTruthy()
    expect(screen.getByText('P1 榜单不可用或为空，未做任何填充')).toBeTruthy()
    expect(mockedLong).toHaveBeenCalledWith(20)
  })

  it('非空榜 → 展示真实字段与 note 原文，缺失不补 0', async () => {
    mockedLong.mockResolvedValue({
      items: [
        { symbol: '600519', score: 92, raw_rank: 0.92, signal: '看多', source: 'P1-ev-top_long' },
        { symbol: '000001', score: null, raw_rank: null, signal: '看多', source: 'P1-ev-top_long' },
      ],
      count: 2,
      note: '演示数据（MSW），非真实事件驱动看多榜',
    })
    renderWithClient(<EventPoolView />)
    // await 数据到达（Card 标题同步渲染）；表格单元格与 note 均为多节点文本，用 textContent 包含断言
    const longCard = await screen.findByRole('region', { name: '事件驱动看多榜（P1 EV top_long）' })
    await vi.waitFor(() => {
      expect(longCard.textContent).toContain('92')
      expect(longCard.textContent).toContain('演示数据（MSW），非真实事件驱动看多榜')
    })
    // 第二条缺失评分 → 该行显示 —，绝不显示 0.00
    const row = screen.getByText('000001').closest('tr')
    expect(row?.textContent).toContain('—')
    expect(row?.textContent).not.toContain('0.00')
  })

  it('error → 看多榜错误态可重试，不伪装成空榜', async () => {
    mockedLong.mockRejectedValue(new Error('榜单加载失败'))
    renderWithClient(<EventPoolView />)
    expect(await screen.findByText('榜单加载失败')).toBeTruthy()
  })
})
