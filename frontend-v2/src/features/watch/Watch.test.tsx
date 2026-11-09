import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Watch } from './Watch'
import type { Watch as WatchData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getWatch: vi.fn(),
}))

import { getWatch } from '@/api/read'
const mocked = vi.mocked(getWatch)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: WatchData = {
  watchlist: [
    { code: '600519', name: '贵州茅台', note: '核心持仓', fund: { source: 'akshare', main_net: 5.0, main_net_pct: 4.2, big_net: 3.0, super_net: 2.0, latest_date: '2026-11-10' } },
    { code: '000001', name: '平安银行', note: '', fund: { source: 'estimate', main_net: -2.0, main_net_pct: -3.5, big_net: null, super_net: null, latest_date: '2026-11-10' } },
    { code: '300750', name: '宁德时代', note: '观察', fund: { source: 'akshare', main_net: 8.4, main_net_pct: 2.1, big_net: 5.0, super_net: 3.4, latest_date: '2026-11-10' } },
  ],
  sector_items: [
    { name: '半导体', chg_pct: 3.52, net: 18.6, leader: '中微公司', leader_chg_pct: 6.21 },
    { name: '白酒', chg_pct: -1.24, net: -5.3, leader: '贵州茅台', leader_chg_pct: -0.52 },
    { name: '银行', chg_pct: 0.81, net: 12.4, leader: '招商银行', leader_chg_pct: 1.12 },
  ],
  alerts: [
    { code: '600519', name: '贵州茅台', level: '强', reason: '主力净流入占比 +4.20%（强）' },
    { code: '000001', name: '平安银行', level: '弱', reason: '主力净流出占比 -3.50%（弱）' },
    { code: '300750', name: '宁德时代', level: '中性', reason: '主力净流入占比 +2.10%（中性）' },
  ],
  summary: { watch_count: 3, with_fund: 3, strong_count: 1, weak_count: 1, sector_available: true },
  src_labels: { watchlist_fund: '个股主力资金流(akshare/估算)', sector: '行业资金流(akshare)' },
  unavailable: [],
  note: '本页为 V2 只读盯盘聚合。',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('Watch 三态 + KPI + 三块内容 + 空态', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Watch />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('智能盯盘取数失败')))
    renderWithClient(<Watch />)
    await expect(screen.findByText(/智能盯盘取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染 KPI + 自选股表 + 板块异动 + 预警', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<Watch />)
    expect(await screen.findByText('盯盘数量')).toBeTruthy()
    // 盯盘数量 = 3（另 有资金流=3 也命中，用 getAllByText）
    expect(screen.getAllByText('3').length).toBeGreaterThan(0)
    // 自选股表：代码与名称（代码同时出现在表与预警行，用 getAllByText）
    expect(screen.getAllByText('600519').length).toBeGreaterThan(0)
    expect(screen.getAllByText('贵州茅台').length).toBeGreaterThan(0)
    // 资金流金额（亿元，红涨绿跌，+5.00 亿）
    expect(screen.getAllByText('+5.00 亿').length).toBeGreaterThan(0)
    // 预警徽标（强 / 弱 / 中性）：表内联 + 预警卡各出现一次，用计数断言
    expect(screen.getAllByText('强').length).toBeGreaterThan(0)
    expect(screen.getAllByText('弱').length).toBeGreaterThan(0)
    expect(screen.getAllByText('中性').length).toBeGreaterThan(0)
    // 板块异动两块标题
    expect(screen.getByText('💰 主力净流入 TOP8')).toBeTruthy()
    expect(screen.getByText('📈 涨跌幅 TOP8')).toBeTruthy()
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
  })

  it('无自选股但板块有数据 → 个股卡提示 + 板块仍展示', async () => {
    mocked.mockResolvedValue({
      ...okData,
      watchlist: [],
      alerts: [],
      summary: { watch_count: 0, with_fund: 0, strong_count: 0, weak_count: 0, sector_available: true },
    })
    renderWithClient(<Watch />)
    expect(await screen.findByText((c) => (c ?? '').includes('当前账号暂无自选股'))).toBeTruthy()
    // 板块仍在
    expect(screen.getByText('💰 主力净流入 TOP8')).toBeTruthy()
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
  })

  it('两者皆空 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      watchlist: [],
      sector_items: [],
      alerts: [],
      summary: { watch_count: 0, with_fund: 0, strong_count: 0, weak_count: 0, sector_available: false },
      src_labels: { watchlist_fund: null, sector: null },
      unavailable: ['sector_flow_unavailable'],
      note: '诚实降级',
    })
    renderWithClient(<Watch />)
    expect(await screen.findByText('暂无盯盘数据')).toBeTruthy()
  })
})
