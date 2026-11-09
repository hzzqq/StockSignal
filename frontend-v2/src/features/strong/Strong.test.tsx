import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Strong } from './Strong'
import type { Strong as StrongData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getStrong: vi.fn(),
}))

import { getStrong } from '@/api/read'
const mocked = vi.mocked(getStrong)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: StrongData = {
  items: [
    { rank: 1, code: '688256', name: '寒武纪', price: 95.0, chg: 5.6, amount: 2e9, turnover: 8.0, vol_ratio: 2.1, score: 88.3, s_chg: 96.0, s_vr: 92.0, s_to: 90.0, s_amt: 70.0 },
    { rank: 2, code: '300750', name: '宁德时代', price: 210.0, chg: 2.1, amount: 4e9, turnover: 3.0, vol_ratio: 1.5, score: 71.4, s_chg: 80.0, s_vr: 70.0, s_to: 60.0, s_amt: 95.0 },
    { rank: 3, code: '600519', name: '贵州茅台', price: 1685.0, chg: 3.5, amount: 5e9, turnover: 1.5, vol_ratio: 1.2, score: 66.2, s_chg: 90.0, s_vr: 55.0, s_to: 40.0, s_amt: 99.0 },
    { rank: 4, code: '000001', name: '平安银行', price: 11.5, chg: -1.2, amount: 3e9, turnover: 2.5, vol_ratio: 0.9, score: 42.0, s_chg: 20.0, s_vr: 30.0, s_to: 45.0, s_amt: 80.0 },
    { rank: 5, code: '601318', name: '中国平安', price: 48.0, chg: 0.8, amount: 2.5e9, turnover: 1.8, vol_ratio: 1.1, score: 51.7, s_chg: 60.0, s_vr: 48.0, s_to: 38.0, s_amt: 78.0 },
    { rank: 6, code: '002594', name: '比亚迪', price: 260.0, chg: -2.4, amount: 3.5e9, turnover: 4.0, vol_ratio: 1.3, score: 38.5, s_chg: 10.0, s_vr: 40.0, s_to: 55.0, s_amt: 82.0 },
  ],
  src_label: '东财实时快照（直连）',
  kicked: [],
  unavailable: [],
  date: null,
}

beforeEach(() => {
  mocked.mockReset()
})

describe('Strong 三态 + 榜单 + 仅看上涨过滤', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Strong />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('强势榜取数失败')))
    renderWithClient(<Strong />)
    await expect(screen.findByText(/强势榜取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染 KPI + 榜单（默认仅看上涨→4 只）+ 数据源标注', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<Strong />)
    expect(await screen.findByText('榜单标的')).toBeTruthy()
    // 数据源标注
    expect(screen.getByText('东财实时快照（直连）')).toBeTruthy()
    // 默认仅看上涨：6 只中 4 只上涨入榜；寒武纪为榜首
    expect(screen.getByText('强势榜（评分 Top 4）')).toBeTruthy()
    expect(screen.getByText('寒武纪')).toBeTruthy()
    expect(screen.getByText('+5.60%')).toBeTruthy()
    // 榜首强势评分 88.3
    // 下跌标的被「仅看上涨」过滤：平安银行/比亚迪不应出现
    expect(screen.queryByText('平安银行')).toBeNull()
    expect(screen.queryByText('比亚迪')).toBeNull()
  })

  it('fetch 失败 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      items: [],
      src_label: '不可用',
      kicked: [],
      unavailable: ['spot_unavailable'],
      date: null,
    })
    renderWithClient(<Strong />)
    expect(await screen.findByText('实时行情快照未就绪')).toBeTruthy()
  })

  it('关闭「仅看上涨」→ 全样本 6 只入榜，下跌标的可见', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<Strong />)
    await screen.findByText('榜单标的')
    expect(screen.queryByText('平安银行')).toBeNull()
    // 关闭仅看上涨
    fireEvent.click(screen.getByText('仅看上涨：开'))
    expect(await screen.findByText('强势榜（评分 Top 6）')).toBeTruthy()
    expect(screen.getByText('平安银行')).toBeTruthy()
    expect(screen.getByText('比亚迪')).toBeTruthy()
  })
})
