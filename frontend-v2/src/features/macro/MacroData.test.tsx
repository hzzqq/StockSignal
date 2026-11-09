import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MacroData } from './MacroData'
import type { MacroData as MacroDataData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getMacroData: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getMacroData } from '@/api/read'
const mocked = vi.mocked(getMacroData)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: MacroDataData = {
  indicators: {
    pmi: { key: 'pmi', name: '制造业 PMI', unit: '%', freq: '月', source: '国家统计局', region: '国内', desc: '荣枯线 50', value: 51.2, prev: 50.8, change: 0.4, date: '2026-11-01' },
    cpi: null, // 取不到，诚实降级
    dxy: { key: 'dxy', name: '美元指数 DXY', unit: '点', freq: '日', source: 'ICE', region: '全球', desc: '强美元', value: 102.3, prev: 101.8, change: 0.5, date: '2026-11-08' },
  },
  regime: {
    score: 62, sub: { dxy: 55.0, us_treasury_10y: 60.0 }, parts: { dxy: 102.3 },
    yield_curve: null, cn_us_spread: null, dates: { dxy: '2026-11-08' },
  },
  unavailable: ['cpi'],
  note: '宏观数据来自公开源',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('MacroData 三态 + 分组渲染 + 诚实降级', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<MacroData />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('宏观数据取数失败')))
    renderWithClient(<MacroData />)
    await expect(screen.findByText(/宏观数据取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染全球评分 + 国内/全球分组 + 缺失指标如实标注', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<MacroData />)
    // 全球风险评分块
    expect(await screen.findByText('全球宏观风险偏好 / 流动性评分（0-100）')).toBeTruthy()
    expect(screen.getByText('62')).toBeTruthy()
    expect(screen.getByText('宽松 · 利好风险资产')).toBeTruthy()
    // 分组
    expect(screen.getByText('国内指标（1）')).toBeTruthy()
    expect(screen.getByText('全球指标（1）')).toBeTruthy()
    // 指标行
    expect(screen.getByText('制造业 PMI')).toBeTruthy()
    expect(screen.getByText('美元指数 DXY')).toBeTruthy()
    // 取不到的指标（cpi）如实标注在缺失清单，且不在表格里补 0
    expect(screen.getByText(/以下指标本次取不到（已诚实降级）：cpi/)).toBeTruthy()
    expect(screen.queryByText(/^0(\.0+)?$/)).toBeNull()
  })

  it('全指标 null + 无评分 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      indicators: { pmi: null, cpi: null },
      regime: null,
      unavailable: ['pmi', 'cpi'],
      note: '宏观数据来自公开源',
    })
    renderWithClient(<MacroData />)
    expect(await screen.findByText('宏观数据暂不可用')).toBeTruthy()
  })

  it('regime 为 null 但指标齐备 → 仍渲染分组，不渲染评分块', async () => {
    mocked.mockResolvedValue({
      indicators: {
        pmi: { key: 'pmi', name: '制造业 PMI', unit: '%', freq: '月', source: '国家统计局', region: '国内', desc: '荣枯线 50', value: 51.2, prev: 50.8, change: 0.4, date: '2026-11-01' },
      },
      regime: null,
      unavailable: [],
      note: '宏观数据来自公开源',
    })
    renderWithClient(<MacroData />)
    expect(await screen.findByText('国内指标（1）')).toBeTruthy()
    expect(screen.queryByText(/全球宏观风险偏好/)).toBeNull()
  })
})
