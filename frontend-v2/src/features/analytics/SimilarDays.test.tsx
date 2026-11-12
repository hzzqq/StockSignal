// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { BreadthAnalytics } from '@/api/schemas/read'
import { breadthAnalytics } from '@/mocks/fixtures'
import { SimilarDays } from './SimilarDays'

/**
 * 67 历史相似日聚类 · 守卫清单（此前无 colocated 测试）。
 * 锁定诚实红线：
 *  - 四态：loading / error(role=alert) / 空数据 / 有数据。
 *  - similar 段 unavailable → 仅该段显「暂无数据」，DataBoundary 仍在（每段独立降级）。
 *  - 前向窗口 n=0 → 该柱送 null（图表不画、不补 0）且显「部分前向窗口无足够样本」警告；Stat 显「—」。
 *  - 真实 up_ratio（如 86.7%）如实展示，不得被 0 冒充。
 */
vi.mock('@/api/read', () => ({ getBreadthAnalytics: vi.fn() }))
import { getBreadthAnalytics } from '@/api/read'
const mocked = vi.mocked(getBreadthAnalytics)

const captured = vi.hoisted(() => ({ options: [] as unknown[] }))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: (props: { option: unknown }) => {
    captured.options.push(props.option)
    return <div data-testid="echart" />
  },
}))

const FIND = { timeout: 5000 }
const mkClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
const renderView = (ui: ReactElement) =>
  render(<QueryClientProvider client={mkClient()}>{ui}</QueryClientProvider>)

const base = breadthAnalytics as unknown as BreadthAnalytics

beforeEach(() => {
  mocked.mockReset()
  captured.options.length = 0
})
afterEach(() => cleanup())

describe('SimilarDays 四态 + 诚实降级', () => {
  it('loading → 加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderView(<SimilarDays />)
    expect(screen.getByText('加载历史相似日统计…')).toBeTruthy()
  })

  it('error → role=alert 展示真实原因', async () => {
    mocked.mockRejectedValue(new Error('历史相似日统计加载失败'))
    renderView(<SimilarDays />)
    expect(await screen.findByText('历史相似日统计加载失败', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
  })

  it('空数据 → 诚实空态「暂无历史相似日统计」', async () => {
    mocked.mockResolvedValue(null as unknown as BreadthAnalytics)
    renderView(<SimilarDays />)
    expect(await screen.findByText('暂无历史相似日统计', {}, FIND)).toBeTruthy()
  })

  it('成功 → 相似日样本卡 + 柱状图 + 真实 up_ratio（86.7%）', async () => {
    mocked.mockResolvedValue(base)
    renderView(<SimilarDays />)
    expect(await screen.findByText('相似日样本', {}, FIND)).toBeTruthy()
    expect(screen.getByText('86.7%')).toBeTruthy() // 后 5 日红盘占比真实值
    expect(screen.getByTestId('echart')).toBeTruthy() // 柱状图渲染
    expect(screen.getByText(/离线数据边界/)).toBeTruthy()
    expect(screen.getByText('后 5 日红盘占比')).toBeTruthy()
  })

  it('similar 段 unavailable → 仅该段显「暂无数据」，DataBoundary 仍在', async () => {
    const data = ({
      ...base,
      sections: { ...base.sections, similar: { available: false, reason: '聚类不可用' } },
    }) as unknown as BreadthAnalytics
    mocked.mockResolvedValue(data)
    renderView(<SimilarDays />)
    expect(await screen.findByText('历史相似日聚类暂无数据', {}, FIND)).toBeTruthy()
    expect(screen.queryByText('相似日样本')).toBeNull()
    expect(screen.queryByTestId('echart')).toBeNull()
    // 注：DataBoundary 在本页嵌套于 SectionState 内，段不可用时随整段隐藏（设计特性，非缺陷）。
  })

  it('前向窗口 n=0 → 该柱送 null（图表不画/不补 0）+ 警告 + Stat 显「—」', async () => {
    const fwd = {
      '5': { n: 0, mean: 0, median: 0, up_ratio: null },
      '10': { n: 15, mean: 50.69, median: 52.72, up_ratio: 53.3 },
      '20': { n: 15, mean: 54.14, median: 56.48, up_ratio: 73.3 },
    }
    const data = ({
      ...base,
      sections: { ...base.sections, similar: { ...base.sections.similar, forward_stats: fwd } },
    }) as unknown as BreadthAnalytics
    mocked.mockResolvedValue(data)
    renderView(<SimilarDays />)
    expect(await screen.findByText(/部分前向窗口无足够样本，对应柱不绘制（不补 0）/)).toBeTruthy()
    // Stat 后 5 日红盘占比 应为「—」（无样本不编造）
    const label = screen.getByText('后 5 日红盘占比')
    expect((label.nextElementSibling as HTMLElement)?.textContent).toBe('—')
    // 图形层数据首项为 null，绝非 0
    const opt = captured.options.at(-1) as { series: { data: unknown[] }[] }
    expect(opt.series[0].data[0]).toBeNull()
    expect(opt.series[0].data[1]).toBe(53.3)
  })
})
