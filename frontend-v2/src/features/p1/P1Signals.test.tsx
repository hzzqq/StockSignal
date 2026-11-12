import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { P1Signals } from './P1Signals'

vi.mock('@/api/read', () => ({
  getP1Signals: vi.fn(),
}))
import { getP1Signals } from '@/api/read'
const mocked = vi.mocked(getP1Signals)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  signal_h10: {
    latest_date: '2026-10-16',
    generated_at: '2026-11-02',
    top_long: [{ symbol: '600000', pred: 0.1234, rank: 1.5 }],
    top_short: [{ symbol: '600001', pred: 0.5, rank: 2.0 }],
  },
}

beforeEach(() => {
  mocked.mockReset()
})

describe('P1Signals 四态', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<P1Signals />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('P1 信号加载失败'))
    renderWithClient(<P1Signals />)
    await expect(screen.findByText('P1 信号加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染信号文件 + 多空 TOP 表（pred/rank 格式化，null→—）', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<P1Signals />)
    // 标题始终存在，改用数据态才出现的信号文件名作为加载完成信号
    expect(await screen.findByText('signal_h10')).toBeTruthy()
    expect(screen.getByText('P1 量化信号')).toBeTruthy()
    expect(screen.getByText(/latest_date 2026-10-16 · generated 2026-11-02/)).toBeTruthy()
    expect(screen.getByText('多头 TOP')).toBeTruthy()
    expect(screen.getByText('空头 TOP')).toBeTruthy()
    expect(screen.getByText('600000')).toBeTruthy()
    expect(screen.getByText('0.1234')).toBeTruthy()
    expect(screen.getByText('1.500')).toBeTruthy()
    expect(screen.getByText('600001')).toBeTruthy()
  })

  it('空对象 → 暂无 P1 信号文件（诚实空态）', async () => {
    mocked.mockResolvedValue({})
    renderWithClient(<P1Signals />)
    await expect(screen.findByText('暂无 P1 信号文件')).resolves.toBeTruthy()
    expect(screen.getByText(/data\/p1_signals/)).toBeTruthy()
  })
})
