import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { QuoteBoard } from './QuoteBoard'
import type { QuoteBoard as QuoteBoardData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getQuoteBoard: vi.fn(),
}))

import { getQuoteBoard } from '@/api/read'
const mocked = vi.mocked(getQuoteBoard)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: QuoteBoardData = {
  indices: [
    { code: 'sh000001', name: '上证指数', current: 3955.9, prev_close: 3946.2, change: 9.7, change_pct: 0.25, date: '2026-11-11' },
    { code: 'sz399001', name: '深证成指', current: 13210.4, prev_close: 13188.5, change: 21.9, change_pct: 0.17, date: '2026-11-11' },
    { code: 'sz399006', name: '创业板指', current: 2785.6, prev_close: 2801.2, change: -15.6, change_pct: -0.56, date: '2026-11-11' },
    { code: 'sh000016', name: '上证50', current: null, prev_close: null, change: null, change_pct: null, date: null },
  ],
  sectors: [
    { name: '半导体', chg_pct: 3.52, net: 18.6, leader: '中微公司', leader_chg_pct: 6.21 },
    { name: '计算机', chg_pct: 2.45, net: 14.7, leader: '海康威视', leader_chg_pct: 2.80 },
    { name: '银行', chg_pct: 0.81, net: 12.4, leader: '招商银行', leader_chg_pct: 1.12 },
    { name: '医药', chg_pct: -0.66, net: -3.2, leader: '迈瑞医疗', leader_chg_pct: 0.30 },
    { name: '白酒', chg_pct: -1.24, net: -5.3, leader: '贵州茅台', leader_chg_pct: -0.52 },
  ],
  market_status: { is_open: true, text: '🟢 下午交易中', refresh_ms: 60000 },
  summary: { index_count: 4, index_available: 3, sector_count: 5, sector_available: true },
  src_labels: { indices: '主要指数(akshare 日线)', sectors: '行业资金流(akshare)' },
  unavailable: [],
  note: '本页为 V2 只读行情看板。',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('QuoteBoard 三态 + KPI + 指数卡 + 板块榜 + 市场状态', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<QuoteBoard />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('行情看板取数失败')))
    renderWithClient(<QuoteBoard />)
    await expect(screen.findByText(/行情看板取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染 KPI + 指数卡 + 板块榜 + 市场状态，且缺失指数显示「暂无数据」不补 0', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<QuoteBoard />)
    expect(await screen.findByText('指数只数')).toBeTruthy()
    // KPI 值（取到报价=3，板块数=5，上涨板块=3）
    expect(screen.getAllByText('3').length).toBeGreaterThan(0)
    expect(screen.getAllByText('5').length).toBeGreaterThan(0)
    // 指数卡：名称 + 权威数据日
    expect(screen.getAllByText('上证指数').length).toBeGreaterThan(0)
    expect(screen.getAllByText((c) => (c ?? '').includes('数据日 2026-11-11')).length).toBeGreaterThan(0)
    // 缺失指数（上证50）诚实显示「—」与「暂无数据」，绝不出现 0.00 伪装
    expect(screen.getAllByText('上证50').length).toBeGreaterThan(0)
    expect(screen.getAllByText('暂无数据').length).toBeGreaterThan(0)
    expect(screen.queryByText('0.00')).toBeNull()
    // 板块榜两块标题 + 明细表
    expect(screen.getByText('🔺 涨幅 TOP6')).toBeTruthy()
    expect(screen.getByText('🔻 跌幅 TOP6')).toBeTruthy()
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
    expect(screen.getAllByText('+3.52%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('+18.60 亿').length).toBeGreaterThan(0)
    // 市场状态
    expect(screen.getAllByText('🟢 下午交易中').length).toBeGreaterThan(0)
    expect(screen.getByText('🕒 市场状态（服务器北京时间）')).toBeTruthy()
  })

  it('指数全取不到但板块有数据 → 指数卡全为暂无数据，板块仍展示', async () => {
    mocked.mockResolvedValue({
      ...okData,
      indices: [
        { code: 'sh000001', name: '上证指数', current: null, prev_close: null, change: null, change_pct: null, date: null },
        { code: 'sz399001', name: '深证成指', current: null, prev_close: null, change: null, change_pct: null, date: null },
        { code: 'sz399006', name: '创业板指', current: null, prev_close: null, change: null, change_pct: null, date: null },
        { code: 'sh000016', name: '上证50', current: null, prev_close: null, change: null, change_pct: null, date: null },
      ],
      summary: { index_count: 4, index_available: 0, sector_count: 5, sector_available: true },
      unavailable: ['index_fetch_failed'],
    })
    renderWithClient(<QuoteBoard />)
    expect((await screen.findAllByText('暂无数据')).length).toBe(4)
    // 板块榜仍在，不会因为指数缺失而整页空态
    expect(screen.getByText('🔺 涨幅 TOP6')).toBeTruthy()
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
    // 诚实标注本次不可用原因
    expect(screen.getByText(/index_fetch_failed/)).toBeTruthy()
  })

  it('指数与板块皆空 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      indices: [],
      sectors: [],
      market_status: { is_open: false, text: '⚪ 已休市', refresh_ms: 0 },
      summary: { index_count: 0, index_available: 0, sector_count: 0, sector_available: false },
      src_labels: { indices: null, sectors: null },
      unavailable: ['sector_flow_unavailable'],
      note: '诚实降级',
    })
    renderWithClient(<QuoteBoard />)
    expect(await screen.findByText('暂无行情看板数据')).toBeTruthy()
    expect(screen.queryByText('🔺 涨幅 TOP6')).toBeNull()
  })
})
