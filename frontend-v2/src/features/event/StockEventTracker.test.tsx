import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EChartsOption } from 'echarts'
import { StockEventTracker } from './StockEventTracker'

/** 捕获 EChart 收到的 option，用于证明无日期事件确实被时间轴排除。 */
const chartState = vi.hoisted(() => ({ latestOption: null as EChartsOption | null }))

vi.mock('@/api/read', () => ({ getStockEvents: vi.fn() }))
vi.mock('@/api/stockSearch', () => ({ getStockSearch: vi.fn() }))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: (props: { option: EChartsOption; ariaLabel?: string }) => {
    chartState.latestOption = props.option
    return <div role="img" aria-label={props.ariaLabel} data-testid="mock-echart" />
  },
}))

import { getStockEvents } from '@/api/read'
import { getStockSearch } from '@/api/stockSearch'

const mockedEvents = vi.mocked(getStockEvents)
const mockedSearch = vi.mocked(getStockSearch)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/** 用原生 6 位代码回车选中（StockSearchInput 的 allowRawCode 路径），不臆造名称。 */
function pickCode(code = '600519') {
  const input = screen.getByRole('combobox')
  fireEvent.change(input, { target: { value: code } })
  fireEvent.keyDown(input, { key: 'Enter' })
}

const okData = {
  code: '600519',
  name: '贵州茅台',
  date: '2026-11-23',
  available: true,
  events: [
    {
      date: '2026-11-20',
      title: '茅台提价公告',
      source: '上交所公告',
      url: 'https://example.com/maotai-up',
      sentiment: '正面',
      level: '大利好',
      score: 0.62,
      is_major: true,
    },
    {
      date: '2026-11-18',
      title: '渠道需求下滑担忧',
      source: '财联社',
      url: 'http://example.com/maotai-down',
      sentiment: '负面',
      level: '小利空',
      score: -0.22,
      is_major: false,
    },
  ],
  distribution: { 正面: 1, 负面: 1, 中性: 0 },
  count: 2,
  note: '事件来自公开渠道，仅供参考，不构成投资建议。',
}

beforeEach(() => {
  mockedEvents.mockReset()
  mockedSearch.mockReset()
  mockedSearch.mockResolvedValue([])
  chartState.latestOption = null
})

describe('StockEventTracker · 个股事件时间轴诚实渲染', () => {
  it('真数据：标题、五档徽章、时间轴容器、分布数字与 note 原文', async () => {
    mockedEvents.mockResolvedValue(okData)
    renderWithClient(<StockEventTracker />)
    pickCode()

    expect(await screen.findByText('茅台提价公告')).toBeTruthy()
    expect(screen.getByText('渠道需求下滑担忧')).toBeTruthy()
    expect(screen.getByText('大利好')).toBeTruthy()
    expect(screen.getByText('小利空')).toBeTruthy()
    // is_major 醒目样式：额外「重大」标记
    expect(screen.getByText('·重大')).toBeTruthy()

    // 时间轴容器存在（EChart 被替换为可断言的容器）
    expect(screen.getByTestId('stock-event-timeline')).toBeTruthy()
    expect(screen.getByRole('img', { name: /时间轴/ })).toBeTruthy()

    // 分布是真实计数：1 / 1 / 0（0 为真实计数，不是缺失补零）
    expect(within(screen.getByTestId('dist-正面')).getByText('1')).toBeTruthy()
    expect(within(screen.getByTestId('dist-负面')).getByText('1')).toBeTruthy()
    expect(within(screen.getByTestId('dist-中性')).getByText('0')).toBeTruthy()

    expect(screen.getByText('0.62')).toBeTruthy()
    expect(screen.getByText('-0.22')).toBeTruthy()
    expect(screen.getByText(okData.note)).toBeTruthy()
    expect(mockedEvents).toHaveBeenCalledWith('600519', 50)

    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
    expect(links[0].getAttribute('href')).toBe('https://example.com/maotai-up')
  })

  it('空态：available=false 且 events=[] 时如实显示，不渲染假事件', async () => {
    mockedEvents.mockResolvedValue({
      ...okData,
      available: false,
      events: [],
      distribution: { 正面: 0, 负面: 0, 中性: 0 },
      count: 0,
    })
    renderWithClient(<StockEventTracker />)
    pickCode()

    expect(await screen.findByText(/未做任何填充/)).toBeTruthy()
    expect(screen.queryByText('茅台提价公告')).toBeNull()
    expect(screen.queryByTestId('stock-event-timeline')).toBeNull()
    expect(screen.queryByText('情感分布')).toBeNull()
  })

  it('缺失字段：显示 —、无 NaN/undefined 泄漏，无日期事件不进时间轴', async () => {
    mockedEvents.mockResolvedValue({
      ...okData,
      events: [
        {
          date: '2026-11-20',
          title: '有日期但缺评分与链接',
          source: null,
          url: null,
          sentiment: '中性',
          level: '小利好',
          score: null,
          is_major: false,
        },
        {
          date: null,
          title: '无日期事件',
          source: null,
          url: 'javascript:alert(1)',
          sentiment: '中性',
          level: '大利空',
          score: null,
          is_major: false,
        },
      ],
      distribution: undefined,
      count: 2,
    })
    renderWithClient(<StockEventTracker />)
    pickCode()

    expect(await screen.findByText('有日期但缺评分与链接')).toBeTruthy()
    expect(screen.getByText('无日期事件')).toBeTruthy()

    // date / source / score / 三维分布缺失一律 '—'
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)
    expect(document.body.textContent).not.toMatch(/NaN|undefined/)

    // 时间轴只纳入 1 条（有日期那条），并如实说明跳过数
    expect(screen.getByText(/1 条无日期事件未纳入时间轴/)).toBeTruthy()
    const series = (
      chartState.latestOption as unknown as { series?: Array<{ data?: unknown[] }> }
    )?.series
    expect(series?.[0]?.data).toHaveLength(1)

    // 伪协议 URL 不渲染成链接；distribution 整体缺失不得补 0
    expect(screen.queryByRole('link', { name: '无日期事件' })).toBeNull()
    expect(within(screen.getByTestId('dist-正面')).getByText('—')).toBeTruthy()
  })
})
