import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { EventPoolView } from './EventPoolView'
import type { EventPool } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({ getEventPool: vi.fn() }))
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))
import { getEventPool } from '@/api/read'
const mocked = vi.mocked(getEventPool)

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
})

describe('EventPoolView · 事件因子池 · 免责口径 + 不补零', () => {
  it('loading → 加载中…', () => {
    mocked.mockReturnValue(new Promise<EventPool>(() => {}))
    renderWithClient(<EventPoolView />)
    expect(screen.getByText('加载中…')).toBeTruthy()
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
