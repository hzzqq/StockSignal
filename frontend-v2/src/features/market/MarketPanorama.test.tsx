import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MarketPanorama } from './MarketPanorama'

vi.mock('@/api/read', () => ({
  getMarketPanorama: vi.fn(),
}))
// ECharts 在 jsdom 无 canvas，桩掉避免挂载崩溃（与 Portfolio/Backtest 等测试同手法）。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))
import { getMarketPanorama } from '@/api/read'
const mocked = vi.mocked(getMarketPanorama)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

// analogs 必须放在 regime 下（组件读 regime.analogs）。
const okData = {
  regime: {
    latest: { date: '2026-03-01', state: '震荡' },
    state_distribution: { 震荡: 12, 普涨: 5 },
    analogs: [
      { date: '2025-08-01', state: '普涨', distance: 0.32, metrics: { red_ratio: 48.0 }, forward: { d5: { avg_red: 55.3 } } },
    ],
  },
  shepherd_latest: {
    date: '2026-03-01',
    red_ratio: 51.2,
    limit_up: 30,
    limit_down: 7,
    connect_hl: 4,
    zt_fail_ratio: 20.5,
  },
  shepherd_series: [
    { date: '2026-02-25', red_ratio: 48.0 },
    { date: '2026-03-01', red_ratio: 51.2 },
  ],
  shepherd_unavailable: [['vix'], ['some_field']],
  note: '全景数据由后端 honest 降级',
}

// regime.latest 缺失 → 触发诚实空态「暂无市场全景数据」。
const emptyData = { regime: {} }

beforeEach(() => {
  mocked.mockReset()
})

describe('MarketPanorama 四态 + 诚实降级', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<MarketPanorama />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('市场全景加载失败'))
    renderWithClient(<MarketPanorama />)
    await expect(screen.findByText('市场全景加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染状态/广度快照 Stat + 缺失字段诚实带出 + 相似日', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MarketPanorama />)
    // 标题「市场全景」始终存在，不能作为加载完成信号；改用数据态才出现的「市场状态」
    expect(await screen.findByText('市场状态')).toBeTruthy()
    expect(screen.getByText('市场全景')).toBeTruthy()
    // 状态卡
    expect(screen.getByText('市场状态')).toBeTruthy()
    // 广度快照：红盘率 / 涨停 / 跌停 / 连板高度 / 炸板率（均非 select 选项值，避免碰撞）
    expect(screen.getByText('红盘率(%)')).toBeTruthy()
    expect(screen.getByText('51.2%')).toBeTruthy()
    expect(screen.getByText('涨停家数')).toBeTruthy()
    expect(screen.getByText('30')).toBeTruthy()
    expect(screen.getByText('跌停家数')).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy()
    expect(screen.getByText('连板高度')).toBeTruthy()
    expect(screen.getByText('4')).toBeTruthy()
    expect(screen.getByText('炸板率(%)')).toBeTruthy()
    expect(screen.getByText('20.5%')).toBeTruthy()
    // 数据源缺失字段诚实带出（不隐藏）
    expect(screen.getByText(/数据源缺失字段（诚实带出）/)).toBeTruthy()
    expect(screen.getByText(/vix/)).toBeTruthy()
    // 历史相似日（≠ 预测）
    expect(screen.getByText(/历史相似日速览/)).toBeTruthy()
    // 55.3% 与「后5日红盘率」同文本节点，用正则子串匹配
    expect(screen.getByText(/55\.3%/)).toBeTruthy()
  })

  it('regime.latest 缺失 → 诚实空态「暂无市场全景数据」', async () => {
    mocked.mockResolvedValue(emptyData)
    renderWithClient(<MarketPanorama />)
    await expect(screen.findByText('暂无市场全景数据')).resolves.toBeTruthy()
    expect(screen.getByText(/广度历史缺失或取数失败/)).toBeTruthy()
  })
})
