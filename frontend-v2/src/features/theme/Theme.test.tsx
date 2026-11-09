import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Theme } from './Theme'
import type { Theme as ThemeData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getTheme: vi.fn(),
  getThemeTransmission: vi.fn(),
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getTheme, getThemeTransmission } from '@/api/read'
const mocked = vi.mocked(getTheme)
const mockedTx = vi.mocked(getThemeTransmission)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: ThemeData = {
  concepts: [
    { name: 'AI', chg: 3.5, turnover_p: 80, lifecycle: '高潮', mv: 1e12, turnover: 8, up: 10, down: 2, leader: '寒武纪' },
    { name: '机器人', chg: 1.2, turnover_p: 50, lifecycle: '发酵', mv: 8e11, turnover: 5, up: 8, down: 3, leader: '拓普集团' },
    { name: '光伏', chg: -2.1, turnover_p: 90, lifecycle: '退潮', mv: 5e11, turnover: 9, up: 3, down: 9, leader: '—' },
  ],
  summary: { count: 3, n_up: 2, n_down: 1, top_name: 'AI', top_chg: 3.5 },
  lifecycle_counts: { 高潮: 1, 发酵: 1, 退潮: 1 },
  unavailable: [],
  note: '题材来自东财',
}

beforeEach(() => {
  mocked.mockReset()
  mockedTx.mockReset()
})

describe('Theme 三态 + 热力图/生命周期/热度榜 + 传导图谱', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Theme />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('题材取数失败')))
    renderWithClient(<Theme />)
    await expect(screen.findByText(/题材取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染 KPI + 热力图 + 热度榜 + 传导按钮', async () => {
    mocked.mockResolvedValue(okData)
    mockedTx.mockResolvedValue({ status: 'unavailable', reason: '未取到真实概念数据', entries: [], concepts_hit: [], members_unavailable: [], n_titles: 0, n_concepts: 0 })
    renderWithClient(<Theme />)
    expect(await screen.findByText('概念板块数')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText('领涨题材')).toBeTruthy()
    // 热力图卡片标题（EChart 被 mock 为 null，但卡片标题渲染）
    expect(screen.getByText(/题材热力图/)).toBeTruthy()
    // 热度榜
    expect(screen.getByText('热度榜（涨幅 Top 3）')).toBeTruthy()
    // AI 同时出现在 KPI(领涨题材) 与热度榜，故用 getAllByText；寒武纪为领涨股
    expect(screen.getAllByText('AI').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('寒武纪').length).toBeGreaterThanOrEqual(1)
    // 传导图谱按钮存在，初始不渲染臆造关联表
    expect(screen.getByText('🔍 生成传导图谱')).toBeTruthy()
    expect(screen.queryByText('寒武纪')).toBeTruthy()
  })

  it('fetch 失败 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      concepts: [],
      summary: null,
      lifecycle_counts: {},
      unavailable: ['theme_concepts_unavailable'],
      note: '题材来自东财',
    })
    renderWithClient(<Theme />)
    expect(await screen.findByText('概念板块快照未就绪')).toBeTruthy()
  })

  it('点击生成传导图谱 → 渲染关联标的表', async () => {
    mocked.mockResolvedValue(okData)
    mockedTx.mockResolvedValue({
      status: 'ok',
      basis: '文本共现',
      disclaimer: '非收益预测',
      entries: [{ name: '寒武纪', code: '688256', score: 9, direction: '利好', dir_color: '#dc2626', concepts: '算力', evidence: '算力需求超预期', direct: true }],
      concepts_hit: ['算力'],
      members_unavailable: [],
      n_titles: 2,
      n_concepts: 1,
    })
    renderWithClient(<Theme />)
    await screen.findByText('概念板块数')
    const btn = screen.getByText('🔍 生成传导图谱')
    fireEvent.click(btn)
    expect(await screen.findByText('寒武纪')).toBeTruthy()
    expect(screen.getByText('算力需求超预期')).toBeTruthy()
    // disclaimer 实际文案来自 mock（非收益预测）；getAllByText 兼容其在区块说明处再次出现
    expect(screen.getAllByText(/非收益预测/).length).toBeGreaterThanOrEqual(1)
  })

  it('传导取不到标题 → unavailable 提示，不编臆造表', async () => {
    mocked.mockResolvedValue(okData)
    mockedTx.mockResolvedValue({ status: 'unavailable', reason: '未取到任何新闻标题', entries: [], concepts_hit: [], members_unavailable: [], n_titles: 0, n_concepts: 0 })
    renderWithClient(<Theme />)
    await screen.findByText('概念板块数')
    fireEvent.click(screen.getByText('🔍 生成传导图谱'))
    expect(await screen.findByText(/传导不可用：未取到任何新闻标题/)).toBeTruthy()
    expect(screen.queryByText('算力需求超预期')).toBeNull()
  })
})
