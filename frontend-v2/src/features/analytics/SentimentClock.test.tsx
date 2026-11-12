// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { BreadthAnalytics } from '@/api/schemas/read'
import { breadthAnalytics } from '@/mocks/fixtures'
import { SentimentClock } from './SentimentClock'

/**
 * 65 投机情绪周期时钟 · 守卫清单（此前无 colocated 测试）。
 * 锁定诚实红线：
 *  - 四态：loading / error(role=alert) / 空数据 / 有数据。
 *  - phase 段 unavailable → 仅当前相位段显「暂无数据」，时序段/DataBoundary 不受影响（每段独立降级）。
 *  - 时序段 unavailable 或 dates 空 → 时序图区域显「暂无足够广度历史生成时序图」，不画空图。
 *  - red_ratio=null → 显「—」（不补 0）；real 46.67 → 「46.67%」。
 *  - 时间窗口切换：下拉 5 个档，响应窗口如实回显（不假装更长历史）。
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

describe('SentimentClock 四态 + 诚实降级', () => {
  it('loading → 加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderView(<SentimentClock />)
    expect(screen.getByText('加载离线广度统计…')).toBeTruthy()
  })

  it('error → role=alert 展示真实原因', async () => {
    mocked.mockRejectedValue(new Error('离线广度统计加载失败'))
    renderView(<SentimentClock />)
    expect(await screen.findByText('离线广度统计加载失败', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
  })

  it('空数据 → 诚实空态「暂无离线广度统计」', async () => {
    mocked.mockResolvedValue(null as unknown as BreadthAnalytics)
    renderView(<SentimentClock />)
    expect(await screen.findByText('暂无离线广度统计', {}, FIND)).toBeTruthy()
  })

  it('成功 → 当前相位卡 + 时序图 + 红盘占比显真实值', async () => {
    mocked.mockResolvedValue(base)
    renderView(<SentimentClock />)
    expect(await screen.findByText('当前投机情绪相位', {}, FIND)).toBeTruthy()
    // 红盘占比 46.67% 真实值（非「—」）
    expect(screen.getByText('46.67%')).toBeTruthy()
    expect(screen.getByText('涨停家数')).toBeTruthy()
    expect(screen.getByTestId('echart')).toBeTruthy() // 时序图渲染
    expect(screen.getByText(/离线数据边界/)).toBeTruthy()
  })

  it('phase 段 unavailable → 当前相位段显「暂无数据」，时序段与 DataBoundary 不受影响', async () => {
    const data = ({
      ...base,
      sections: {
        ...base.sections,
        phase: { available: false, reason: '相位不可用', current: undefined, series: undefined },
      },
    }) as unknown as BreadthAnalytics
    mocked.mockResolvedValue(data)
    renderView(<SentimentClock />)
    expect(await screen.findByText('当前相位暂无数据', {}, FIND)).toBeTruthy()
    // 时序段仍尝试渲染（series 缺失 → 空态），DataBoundary 仍在
    expect(screen.getByText(/离线数据边界/)).toBeTruthy()
  })

  it('时序段 dates 空 → 时序图区域显「暂无足够广度历史生成时序图」，不画图', async () => {
    const data = ({
      ...base,
      sections: {
        ...base.sections,
        phase: {
          ...base.sections.phase,
          series: { available: true, dates: [], labels: {}, series: {} },
        },
      },
    }) as unknown as BreadthAnalytics
    mocked.mockResolvedValue(data)
    renderView(<SentimentClock />)
    expect(await screen.findByText('暂无足够广度历史生成时序图', {}, FIND)).toBeTruthy()
    expect(screen.queryByTestId('echart')).toBeNull()
  })

  it('red_ratio=null → 红盘占比显「—」（不补 0）；切换窗口下拉 5 档可选项存在', async () => {
    const cur = { ...base.sections.phase.current, red_ratio: null }
    const data = ({
      ...base,
      sections: { ...base.sections, phase: { ...base.sections.phase, current: cur } },
    }) as unknown as BreadthAnalytics
    mocked.mockResolvedValue(data)
    renderView(<SentimentClock />)
    // 红盘占比 Stat 值应为「—」
    const label = await screen.findByText('红盘占比', {}, FIND)
    expect((label.nextElementSibling as HTMLElement)?.textContent).toBe('—')
    // 5 个时间窗口可选项
    expect(screen.getByText('近 60 日')).toBeTruthy()
    expect(screen.getByText('近 2000 日')).toBeTruthy()
  })
})
