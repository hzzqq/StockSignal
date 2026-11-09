import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SectorRotation } from './SectorRotation'
import type { SectorRotation as SectorRotationData } from '@/api/schemas/read'

vi.mock('@/api/read', () => ({
  getSectorRotation: vi.fn(),
}))

// ECharts 在 jsdom 无 canvas，init 会抛错；与全站约定一致，渲染期直接置空。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: () => null,
}))

import { getSectorRotation } from '@/api/read'
const mocked = vi.mocked(getSectorRotation)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData: SectorRotationData = {
  items: [
    { name: '半导体', chg_pct: 3.52, net: 18.6, leader: '中微公司', leader_chg_pct: 6.21 },
    { name: '白酒', chg_pct: -1.24, net: -5.3, leader: '贵州茅台', leader_chg_pct: -0.52 },
    { name: '银行', chg_pct: 0.81, net: 12.4, leader: '招商银行', leader_chg_pct: 1.12 },
    { name: '军工', chg_pct: 2.07, net: 7.8, leader: '中航沈飞', leader_chg_pct: 3.44 },
    { name: '新能源', chg_pct: 1.93, net: 9.1, leader: '宁德时代', leader_chg_pct: 2.1 },
    { name: '医药', chg_pct: -0.66, net: -3.2, leader: '迈瑞医疗', leader_chg_pct: 0.3 },
    { name: '计算机', chg_pct: 2.45, net: 14.7, leader: '海康威视', leader_chg_pct: 2.8 },
    { name: '汽车', chg_pct: 0.42, net: 2.1, leader: '比亚迪', leader_chg_pct: -2.4 },
  ],
  src_label: '行业资金流(akshare)',
  unavailable: [],
  date: null,
}

beforeEach(() => {
  mocked.mockReset()
})

describe('SectorRotation 三态 + KPI + 轮动解读 + 视图切换', () => {
  it('loading 显示加载中占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<SectorRotation />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockImplementation(() => Promise.reject(new Error('板块轮动取数失败')))
    renderWithClient(<SectorRotation />)
    await expect(screen.findByText(/板块轮动取数失败/)).resolves.toBeTruthy()
  })

  it('ok 渲染 KPI + 数据源标注 + 热力图视图 + 轮动解读', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<SectorRotation />)
    expect(await screen.findByText('板块数量')).toBeTruthy()
    // 板块数量 = 8
    expect(screen.getByText('8')).toBeTruthy()
    // 数据源标注（仅 KPI 值出现一次）
    expect(screen.getByText('行业资金流(akshare)')).toBeTruthy()
    // 默认热力图视图标题（唯一 Card 标题）
    expect(screen.getByText('🔥 热力图（块大小=资金净流入，颜色=涨跌幅）')).toBeTruthy()
    // 轮动解读：领涨前三（标题含 emoji 前缀）；半导体在 KPI 与解读中均出现，用 getAllByText
    expect(screen.getByText('🟢 领涨前三')).toBeTruthy()
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0)
    expect(screen.getAllByText('+3.52%').length).toBeGreaterThan(0)
  })

  it('fetch 失败 → 整体空态（诚实降级）', async () => {
    mocked.mockResolvedValue({
      items: [],
      src_label: '行业资金流不可用',
      unavailable: ['industry_flow_unavailable'],
      date: null,
    })
    renderWithClient(<SectorRotation />)
    expect(await screen.findByText('板块数据未就绪')).toBeTruthy()
  })

  it('切换排行榜视图 → 涨幅 TOP10 卡片出现', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<SectorRotation />)
    await screen.findByText('板块数量')
    // 默认热力图：排行榜卡片不应出现
    expect(screen.queryByText('🚀 涨幅 TOP10')).toBeNull()
    fireEvent.click(screen.getByText('📊 排行榜'))
    expect(await screen.findByText('🚀 涨幅 TOP10')).toBeTruthy()
  })

  it('切换强弱象限视图 → 象限卡片出现', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<SectorRotation />)
    await screen.findByText('板块数量')
    fireEvent.click(screen.getByText('🔄 强弱象限'))
    expect(await screen.findByText('🔄 强弱象限（涨跌幅 × 资金净额）')).toBeTruthy()
  })
})
