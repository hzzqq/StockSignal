import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FundFlow } from './FundFlow'
import type { FundFlow as FundFlowData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getFundFlow: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getFundFlow } from '@/api/read'
const mocked = vi.mocked(getFundFlow)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: FundFlowData = {
  northbound: {
    available: true,
    trade_date: '2026-11-08',
    total_inflow: 5.0,
    sh_inflow: 3.0,
    sz_inflow: 2.0,
    northbound_net_available: true,
    boards: [
      { board: '沪股通', direction: '北向', trade_net: 12.0, net_inflow: 34.0, up_count: 300, down_count: 150, index_chg_pct: 1.2 },
    ],
    last_net_buy: 99.0,
    last_net_buy_date: '2024-08-15',
    cumulative: 18000.0,
    cumulative_date: '2024-08-15',
  },
  industry: {
    available: true,
    rows: [
      { industry: '半导体', chg_pct: 2.5, inflow: 500.0, outflow: 400.0, net: 100.0, leader: '中芯国际', leader_chg_pct: 5.1 },
      { industry: '银行', chg_pct: -1.1, inflow: 200.0, outflow: 250.0, net: -50.0, leader: '招商银行', leader_chg_pct: -0.8 },
    ],
  },
  market: {
    available: true,
    rows: [
      { date: '2026-11-06', index_chg_pct: 0.5, main_net: 120.0, main_net_pct: 3.1, super_net: 60.0, big_net: 60.0, mid_net: -50.0 },
      { date: '2026-11-07', index_chg_pct: -0.3, main_net: -80.0, main_net_pct: -2.2, super_net: -40.0, big_net: -40.0, mid_net: 30.0 },
    ],
  },
  margin: {
    available: true,
    rows: [
      { date: '2026-11-06', sh_rzmr_yi: 300.0, sz_rzmr_yi: 200.0, total_rzmr_yi: 500.0, sh_rzye_yi: 7000.0, sz_rzye_yi: 6000.0, total_rzye_yi: 13000.0, sh000001: 3300.0, sz399001: 11000.0, sz399006: 2300.0 },
    ],
    latest: { date: '2026-11-06', total_rzmr_yi: 500.0, total_rzye_yi: 13000.0, sh_rzmr_yi: 300.0, sz_rzmr_yi: 200.0, rzmr_change_yi: 12.5, rzye_change_yi: -8.3, rzmr_change_pct: 2.5, rzye_change_pct: -0.6 },
  },
  note: '资金流向数据来自东方财富/同花顺网络接口（fundflow / margin_trading 数据层）',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('FundFlow 三态 + 四块渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<FundFlow />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('数据不足（insufficient_data）')))
    renderWithClient(<FundFlow />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染四块标题 + 北向/行业/融资融券关键数据', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<FundFlow />)
    expect(await screen.findByText('北向资金（沪股通 / 深股通）')).toBeTruthy()
    expect(screen.getByText('行业板块资金流向')).toBeTruthy()
    expect(screen.getByText('大盘主力资金净流入（近 30 日）')).toBeTruthy()
    expect(screen.getByText('融资融券趋势（融资买入额 & 融资余额）')).toBeTruthy()
    // 北向实时 KPI
    expect(screen.getByText('北向净流入(实时)')).toBeTruthy()
    // 行业表内数据（行业名同时出现在 KPI 与表格，故用 getAllByText）
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
    // 融资融券最新 KPI
    expect(screen.getByText('融资买入额(最新)')).toBeTruthy()
  })

  it('全部不可用时显示整体暂不可用（诚实降级）', async () => {
    mocked.mockResolvedValue({
      ...okData,
      northbound: { ...okData.northbound, available: false },
      industry: { available: false, rows: [] },
      market: { available: false, rows: [] },
      margin: { available: false, rows: [], latest: null },
    })
    renderWithClient(<FundFlow />)
    expect(await screen.findByText('资金流向数据暂不可用')).toBeTruthy()
  })

  it('北向实时停披露时回退到「最近真实披露 + 历史累计」兜底', async () => {
    mocked.mockResolvedValue({
      ...okData,
      northbound: {
        ...okData.northbound,
        northbound_net_available: false,
        total_inflow: null,
        sh_inflow: null,
        sz_inflow: null,
      },
    })
    renderWithClient(<FundFlow />)
    expect(await screen.findByText(/北向资金实时净买额已停披露/)).toBeTruthy()
    expect(screen.getByText('北向净流入(最近真实披露)')).toBeTruthy()
    expect(screen.getByText('历史累计净买入')).toBeTruthy()
  })
})
