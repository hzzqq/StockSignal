import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DragonTiger } from './DragonTiger'
import type { DragonTiger as DragonTigerData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getDragonTiger: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getDragonTiger } from '@/api/read'
const mocked = vi.mocked(getDragonTiger)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: DragonTigerData = {
  date: '20261109',
  count: 3,
  net_col: '净买额',
  net_sum_yi: 2.1,
  buy_top: [
    { code: '600519', name: '贵州茅台', net_yi: 2.5 },
    { code: '300750', name: '宁德时代', net_yi: 0.8 },
  ],
  sell_top: [{ code: '000001', name: '平安银行', net_yi: -1.2 }],
  detail: [
    { 代码: '600519', 名称: '贵州茅台', 净买额: 2.5e8 },
    { 代码: '000001', 名称: '平安银行', 净买额: -1.2e8 },
    { 代码: '300750', 名称: '宁德时代', 净买额: 0.8e8 },
  ],
  unavailable: [],
  note: '龙虎榜来自东财',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('DragonTiger 三态 + 排名渲染 + 诚实降级', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<DragonTiger />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('龙虎榜取数失败')))
    renderWithClient(<DragonTiger />)
    await expect(screen.findByText(/龙虎榜取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染 KPI + 净买入/净卖出排名 + 原始明细', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<DragonTiger />)
    // KPI
    expect(await screen.findByText('上榜家数')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText('2.10 亿')).toBeTruthy()
    expect(screen.getByText('净买额合计')).toBeTruthy()
    expect(screen.getByText('识别到的净买列')).toBeTruthy()
    // 排名表
    expect(screen.getByText('🔥 净买入 Top（2）')).toBeTruthy()
    expect(screen.getByText('🧊 净卖出 Top（1）')).toBeTruthy()
    // 贵州茅台/平安银行同时出现在排名表与原始明细，故用 getAllByText
    expect(screen.getAllByText('贵州茅台').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('平安银行').length).toBeGreaterThanOrEqual(1)
    // 原始明细
    expect(screen.getByText('原始明细（前 3 行）')).toBeTruthy()
    // 正常态不应出现「取不到」清单
    expect(screen.queryByText(/以下情况本次发生/)).toBeNull()
  })

  it('净买列识别不到 → 排名降级、明细仍保留、unavailable 标注', async () => {
    mocked.mockResolvedValue({
      date: '20261109',
      count: null,
      net_col: null,
      net_sum_yi: null,
      buy_top: null,
      sell_top: null,
      detail: [{ 代码: '600519', 名称: '贵州茅台', 净买额: 2.5e8 }],
      unavailable: ['net_col_missing'],
      note: '龙虎榜来自东财',
    })
    renderWithClient(<DragonTiger />)
    expect(await screen.findByText(/净买入 Top/)).toBeTruthy()
    // 排名降级提示（两张排名表都降级，故用 getAllByText）
    expect(screen.getAllByText(/净买列识别不到或本页无数据，已降级为不显示排名/).length).toBeGreaterThanOrEqual(2)
    // 明细仍保留
    expect(screen.getByText('原始明细（前 1 行）')).toBeTruthy()
    // unavailable 标注
    expect(screen.getByText(/以下情况本次发生（已诚实标注）：net_col_missing/)).toBeTruthy()
  })

  it('fetch 失败 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      date: null,
      count: null,
      net_col: null,
      net_sum_yi: null,
      buy_top: null,
      sell_top: null,
      detail: null,
      unavailable: ['lhb_fetch_failed'],
      note: '龙虎榜来自东财',
    })
    renderWithClient(<DragonTiger />)
    expect(await screen.findByText('龙虎榜暂不可用')).toBeTruthy()
  })
})
