import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FactorAnalysis } from './FactorAnalysis'
import type { FactorAnalysis as FactorAnalysisData } from '@/api/schemas/read'
import { CHART } from '@/shared/charts/palette'

// 隔离真实 API：只替换 getFactorAnalysis；图表组件在 jsdom 不可用，mock 为 null。
vi.mock('@/api/read', () => ({
  getFactorAnalysis: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getFactorAnalysis } from '@/api/read'
const mocked = vi.mocked(getFactorAnalysis)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/** Stat 结构：label div 的下一个兄弟节点即承载 style.color 的数值 div。 */
function statValueEl(label: string): HTMLElement {
  const el = screen.getByText(label).nextElementSibling
  if (!(el instanceof HTMLElement)) throw new Error(`Stat 数值节点缺失: ${label}`)
  return el
}

/** jsdom 会把 hex 归一化为 rgb；两种形态都接受，避免对序列化形式做 brittle 断言。 */
function colorMatches(el: HTMLElement, hex: string): boolean {
  const actual = el.style.color
  const n = parseInt(hex.slice(1), 16)
  const rgb = `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
  return actual === hex || actual === rgb
}

const okData: FactorAnalysisData = {
  codes: ['600519', '000001', '300750'],
  days: 250,
  factor: 'momentum',
  forward: 1,
  n_layers: 5,
  ic_series: [
    { date: '2026-10-01', ic: 0.03 },
    { date: '2026-10-02', ic: -0.02 },
  ],
  ic_summary: {
    n: 2,
    ic_mean: 0.005,
    ic_std: 0.03,
    ir: 0.16,
    positive_ratio: 0.5,
    t_stat: 0.4,
  },
  layered_cum: [
    { date: '2026-10-01', '0': 0.01, '1': 0.005, '2': 0, '3': -0.005, '4': -0.01 },
  ],
  long_short_cum: [{ date: '2026-10-01', ic: 0.02 }],
  errs: [],
  date: '2026-10-02',
  note: '逐标的独立取数、独立降级；缺失为 null 且不补 0',
}

beforeEach(() => {
  mocked.mockReset()
})

describe('FactorAnalysis 三态 + 字段渲染', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<FactorAnalysis />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态（诚实不谎报为数据）', async () => {
    mocked.mockImplementation(() =>
      Promise.reject(new Error('数据不足（insufficient_data）')),
    )
    renderWithClient(<FactorAnalysis />)
    await expect(screen.findByText(/数据不足/)).resolves.toBeTruthy()
  })

  it('ok 渲染 IC 汇总与三图卡片标题', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<FactorAnalysis />)
    expect(await screen.findByText('样本期数 n')).toBeTruthy()
    expect(screen.getByText('IC 均值')).toBeTruthy()
    expect(screen.getByText('逐期 IC 序列')).toBeTruthy()
    expect(
      screen.getByText('分层累计收益（因子由大到小分层的净值曲线）'),
    ).toBeTruthy()
    expect(screen.getByText('多空组合累计净值')).toBeTruthy()
  })

  it('IC 均值/IR 为真实数值时按方向着色（正向对照）', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<FactorAnalysis />)
    expect(await screen.findByText('IC 均值')).toBeTruthy()
    // ic_mean=0.005、ir=0.16 均为正 → A 股涨色 CHART.up
    expect(colorMatches(statValueEl('IC 均值'), CHART.up)).toBe(true)
    expect(colorMatches(statValueEl('IR'), CHART.up)).toBe(true)
  })

  it('IC 均值/IR 为 null 时显示「—」且无任何方向色（语义诚实）', async () => {
    mocked.mockResolvedValue({
      ...okData,
      ic_summary: { ...okData.ic_summary, ic_mean: null, ir: null },
    })
    renderWithClient(<FactorAnalysis />)
    expect(await screen.findByText('IC 均值')).toBeTruthy()
    const icMean = statValueEl('IC 均值')
    const ir = statValueEl('IR')
    // 缺失值只能显示「—」，不得被当作负值着成 CHART.down（A股跌色）
    expect(icMean.textContent).toBe('—')
    expect(ir.textContent).toBe('—')
    expect(icMean.style.color).toBe('')
    expect(ir.style.color).toBe('')
    // 显式再确认：没有沾染任一方向色
    expect(colorMatches(icMean, CHART.up)).toBe(false)
    expect(colorMatches(icMean, CHART.down)).toBe(false)
    expect(colorMatches(ir, CHART.up)).toBe(false)
    expect(colorMatches(ir, CHART.down)).toBe(false)
  })

  it('empty（ic_series 为空）显示暂无因子数据', async () => {
    mocked.mockResolvedValue({ ...okData, ic_series: [] })
    renderWithClient(<FactorAnalysis />)
    expect(await screen.findByText('暂无因子数据')).toBeTruthy()
  })
})
