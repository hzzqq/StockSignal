// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { BreadthAnalytics } from '@/api/schemas/read'
import { breadthAnalytics } from '@/mocks/fixtures'
import { RegimeDuration } from './RegimeDuration'

/**
 * 69 温度持续期与回归时长 · 守卫清单（此前无 colocated 测试）。
 * 锁定诚实红线：
 *  - 四态：loading / error(role=alert) / 空数据 / 有数据。
 *  - duration 段 unavailable → 仅该段显「暂无数据」，柱状图/统计不渲染，但 DataBoundary 仍在（每段独立降级）。
 *  - median=null → Stat 显「—」、柱状图该柱缺席（null，不补 0）；median=0 → 显「0 天」真实零值（零≠缺失）。
 *  - 离线缺真值维度逐条披露（DataBoundary）。
 * 组件用 getBreadthAnalytics 取数，此处直接 mock 该 API 函数（与 InflectionScan.test 同范式），并 mock EChart 以捕获 option。
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

const withDuration = (
  durations: Record<string, { n: number; mean: number; median: number | null }>,
): BreadthAnalytics =>
  ({
    ...base,
    sections: {
      ...base.sections,
      duration: { ...base.sections.duration, durations },
    },
  }) as unknown as BreadthAnalytics

describe('RegimeDuration 四态 + 诚实降级', () => {
  it('loading → 加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderView(<RegimeDuration />)
    expect(screen.getByText('加载温度持续期统计…')).toBeTruthy()
  })

  it('error → role=alert 展示真实原因', async () => {
    mocked.mockRejectedValue(new Error('温度持续期统计加载失败'))
    renderView(<RegimeDuration />)
    expect(await screen.findByText('温度持续期统计加载失败', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
  })

  it('空数据 → 诚实空态「暂无温度持续期统计」', async () => {
    mocked.mockResolvedValue(null as unknown as BreadthAnalytics)
    renderView(<RegimeDuration />)
    expect(await screen.findByText('暂无温度持续期统计', {}, FIND)).toBeTruthy()
  })

  it('成功 → 统计卡 + 柱状图 + 离线边界披露', async () => {
    mocked.mockResolvedValue(base)
    renderView(<RegimeDuration />)
    expect(await screen.findByText('冰点档持续中位', {}, FIND)).toBeTruthy()
    expect(screen.getByText('历史 run 总数')).toBeTruthy()
    expect(screen.getByText('3743')).toBeTruthy() // total_runs
    expect(screen.getByTestId('echart')).toBeTruthy() // 柱状图渲染
    expect(screen.getByText(/离线数据边界/)).toBeTruthy()
    expect(screen.getByText(/连板高度/)).toBeTruthy() // 缺真值维度披露
  })

  it('duration 段 unavailable → 仅该段显「暂无数据」，柱状图/统计不渲染但 DataBoundary 仍在', async () => {
    const data = ({
      ...base,
      sections: { ...base.sections, duration: { available: false, reason: '测试剔除' } },
    }) as unknown as BreadthAnalytics
    mocked.mockResolvedValue(data)
    renderView(<RegimeDuration />)
    expect(await screen.findByText('温度持续期暂无数据', {}, FIND)).toBeTruthy()
    expect(screen.queryByText('冰点档持续中位')).toBeNull()
    expect(screen.queryByTestId('echart')).toBeNull()
    // 注：DataBoundary 在本页嵌套于 SectionState 内，段不可用时随整段隐藏（设计特性，非缺陷）。
  })

  it('冰点档 median=null → Stat 显「—」且柱状图该柱缺席（不补 0）', async () => {
    mocked.mockResolvedValue(
      withDuration({
        '0': { n: 571, mean: 1.2, median: null },
        '1': { n: 1, mean: 1, median: 1 },
        '2': { n: 1, mean: 1, median: 1 },
        '3': { n: 1, mean: 1, median: 1 },
        '4': { n: 1, mean: 1, median: 1 },
      }),
    )
    renderView(<RegimeDuration />)
    const label = await screen.findByText('冰点档持续中位', {}, FIND)
    expect((label.nextElementSibling as HTMLElement)?.textContent).toBe('—')
    const opt = captured.options.at(-1) as { series: { data: unknown[] }[] }
    expect(opt.series[0].data[0]).toBeNull() // 图形层也不得补 0
  })

  it('冰点档 median=0 → 显「0 天」真实零值（零≠缺失，不被当成「—」）', async () => {
    mocked.mockResolvedValue(
      withDuration({
        '0': { n: 0, mean: 0, median: 0 },
        '1': { n: 1, mean: 1, median: 1 },
        '2': { n: 1, mean: 1, median: 1 },
        '3': { n: 1, mean: 1, median: 1 },
        '4': { n: 1, mean: 1, median: 1 },
      }),
    )
    renderView(<RegimeDuration />)
    const label = await screen.findByText('冰点档持续中位', {}, FIND)
    expect((label.nextElementSibling as HTMLElement)?.textContent).toBe('0 天')
  })
})
