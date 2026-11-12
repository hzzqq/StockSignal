import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Recommendation } from './Recommendation'

vi.mock('@/api/read', () => ({
  getDailyRecommendation: vi.fn(),
  getVirtualUsersSim: vi.fn(),
}))
import { getDailyRecommendation, getVirtualUsersSim } from '@/api/read'
const mockedRec = vi.mocked(getDailyRecommendation)
const mockedSim = vi.mocked(getVirtualUsersSim)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const simOk = { meta: { total: 100 } }

beforeEach(() => {
  mockedRec.mockReset()
  mockedSim.mockReset()
  // 默认两条查询都成功，避免多「加载中…」冲突
  mockedSim.mockResolvedValue(simOk)
})

describe('Recommendation 四态 + 诚实 unavailable', () => {
  it('loading（仅荐股挂起）显示加载占位', async () => {
    mockedRec.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Recommendation />)
    // 荐股挂起时，模拟统计查询也尚未完成 → 两个「加载中…」，用 findAllByText
    expect(await screen.findAllByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mockedRec.mockRejectedValue(new Error('荐股加载失败'))
    renderWithClient(<Recommendation />)
    await expect(screen.findByText('荐股加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染状态 + 免责声明', async () => {
    mockedRec.mockResolvedValue({
      status: 'ok',
      generated_at: '2026-03-01',
      disclaimer: '仅供参考，不构成投资建议。',
    })
    renderWithClient(<Recommendation />)
    // 标题「每日荐股」始终存在，改用数据态才出现的「状态：ok」作为加载完成信号
    expect(await screen.findByText('状态：ok')).toBeTruthy()
    expect(screen.getByText('每日荐股')).toBeTruthy()
    expect(screen.getByText(/generated 2026-03-01/)).toBeTruthy()
    expect(screen.getByText(/仅供参考，不构成投资建议。/)).toBeTruthy()
  })

  it('unavailable → 诚实展示原因（不编造推荐）', async () => {
    mockedRec.mockResolvedValue({ status: 'unavailable', reason: '荐股数据缺失，不编造推荐' })
    renderWithClient(<Recommendation />)
    expect(await screen.findByText('状态：unavailable')).toBeTruthy()
    expect(screen.getByText(/荐股数据缺失，不编造推荐/)).toBeTruthy()
  })

  it('模拟统计 ok 渲染（蒙特卡洛，非实盘）', async () => {
    mockedRec.mockResolvedValue({ status: 'ok' })
    renderWithClient(<Recommendation />)
    // 等待模拟统计（数据态）提交后再断言
    expect(await screen.findByText(/蒙特卡洛回测模拟（非实盘）/)).toBeTruthy()
    expect(screen.getByText('每日荐股')).toBeTruthy()
    expect(screen.getByText(/total/)).toBeTruthy()
  })
})
