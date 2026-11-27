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

const simOk = {
  meta: {
    n_users: 10000,
    seed: '20261011',
    universe_size: 300,
    pool_valid: 286,
    skipped_tickers: 14,
    start: '2024-01-01',
    end: '2026-09-30',
    window: 180,
    strategies: ['multi_factor', 'dual_trend'],
    cost_model: 'realistic',
  },
}

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

  it('data_staleness.freshness=warn → 显示偏旧徽标与后端 note 原文', async () => {
    mockedRec.mockResolvedValue({
      status: 'ok',
      generated_at: '2026-03-01',
      data_staleness: {
        latest: '2026-11-21',
        lag_days: 5,
        stale: false,
        freshness: 'warn',
        note: '行情数据最新 2026-11-21，滞后 5 天（≥4 天，数据偏旧，谨慎参考）',
      },
    })
    renderWithClient(<Recommendation />)
    expect(await screen.findByText('状态：ok')).toBeTruthy()
    expect(screen.getByLabelText('数据新鲜度：数据偏旧')).toBeTruthy()
    expect(screen.getByText(/数据偏旧，谨慎参考/)).toBeTruthy()
  })

  it('无 freshness 仅 lag_days=5（旧格式落盘）→ 降级仍显示偏旧', async () => {
    mockedRec.mockResolvedValue({
      status: 'ok',
      data_staleness: {
        latest: '2026-11-21',
        lag_days: 5,
        stale: false,
        note: '行情数据最新 2026-11-21，滞后 5 天（≥4 天，数据偏旧，谨慎参考）',
      },
    })
    renderWithClient(<Recommendation />)
    expect(await screen.findByText('状态：ok')).toBeTruthy()
    expect(screen.getByLabelText('数据新鲜度：数据偏旧')).toBeTruthy()
    expect(screen.getByText(/数据偏旧，谨慎参考/)).toBeTruthy()
  })

  it('无 freshness 仅 lag_days=8 → 降级按后端口径显示「数据陈旧」（非偏旧）', async () => {
    mockedRec.mockResolvedValue({
      status: 'ok',
      data_staleness: {
        latest: '2026-11-19',
        lag_days: 8,
        stale: true,
        note: '行情数据最新 2026-11-19，滞后 8 天（≥8 天，数据陈旧）',
      },
    })
    renderWithClient(<Recommendation />)
    expect(await screen.findByText('状态：ok')).toBeTruthy()
    expect(screen.getByLabelText('数据新鲜度：数据陈旧')).toBeTruthy()
    expect(screen.queryByLabelText('数据新鲜度：数据偏旧')).toBeNull()
    expect(screen.getByText(/滞后 8 天/)).toBeTruthy()
  })

  it('freshness=ok → 只显示新鲜徽标，不打扰用户（note 不出场）', async () => {
    mockedRec.mockResolvedValue({
      status: 'ok',
      data_staleness: {
        latest: '2026-11-26',
        lag_days: 1,
        stale: false,
        freshness: 'ok',
        note: '行情数据最新 2026-11-26，滞后 1 天（数据新鲜）',
      },
    })
    renderWithClient(<Recommendation />)
    expect(await screen.findByText('状态：ok')).toBeTruthy()
    expect(screen.getByLabelText('数据新鲜度：数据新鲜')).toBeTruthy()
    expect(screen.queryByText(/滞后 1 天/)).toBeNull()
  })

  it('模拟统计 ok 渲染为结构化参数（不贴原始 JSON 字符串），截断值不丢字段', async () => {
    mockedRec.mockResolvedValue({ status: 'ok' })
    renderWithClient(<Recommendation />)
    expect(await screen.findByText(/蒙特卡洛回测模拟（非实盘/)).toBeTruthy()
    // 中文标签 + 真实值逐项展示，不再是一段 JSON.stringify(...).slice(0,200)
    expect(screen.getByText('虚拟用户数')).toBeTruthy()
    expect(screen.getByText('10000')).toBeTruthy()
    expect(screen.getByText('股票池规模')).toBeTruthy()
    expect(screen.getByText('300')).toBeTruthy()
    expect(screen.getByText('multi_factor、dual_trend')).toBeTruthy()
    // 全字段在册（原 slice(0,200) 会截断末尾的 cost_model）
    expect(screen.getByText('成本模型')).toBeTruthy()
    expect(screen.getByText('realistic')).toBeTruthy()
    expect(screen.queryByText(/\{"n_users"/)).toBeNull()
  })
})
