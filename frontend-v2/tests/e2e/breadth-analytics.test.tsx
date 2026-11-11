// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import * as fixtures from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { SentimentClock } from '@/features/analytics/SentimentClock'
import { SimilarDays } from '@/features/analytics/SimilarDays'
import { InflectionScan } from '@/features/analytics/InflectionScan'
import { RegimeDuration } from '@/features/analytics/RegimeDuration'

/**
 * 65/67/68/69 离线可靠广度统计四页 E2E（v2 native 真页面）。
 *
 * 钉死四条诚实契约：
 *  1. 段级独立降级：某段 available=false 只让该段显「暂无」+ reason，其余段照常；
 *  2. 缺样本不补 0：前向窗口/持续档无样本显「—」，柱不绘制；
 *  3. 数据日取端点 data_as_of，全页声明「历史描述、不预测」；
 *  4. 10 个离线缺真值维度逐条披露，不进入任何计算。
 * ECharts 在 jsdom 无 canvas，按全站约定用轻量替身；只验证取数/降级/渲染契约。
 */
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ height, ariaLabel }: { height?: number; ariaLabel?: string }) => (
    <div data-testid="echart" aria-label={ariaLabel} style={{ height }} />
  ),
}))

const server = setupServer(
  ...handlers,
  http.get('/api/health', () => HttpResponse.json({ status: 'ok' })),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  localStorage.clear()
})
afterAll(() => server.close())

function mount(node: ReactNode) {
  return render(<Providers>{node}</Providers>)
}

/** 严格带齐统一信封四字段（缺 code/message 会被 client 判「响应不符合统一信封」）。 */
function okEnvelope(data: unknown) {
  return HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })
}

/** 真端点形态的夹具深拷贝，供逐段降级用例改写。 */
function cloneAnalytics(): any {
  return JSON.parse(JSON.stringify(fixtures.breadthAnalytics))
}

const ANALYTICS_URL = '/api/v2/read/breadth-analytics'
const ZSERIES_URL = '/api/v2/read/breadth-zseries'

describe('65 投机情绪周期时钟（/sentiment-clock）', () => {
  it('渲染权威数据日与当前相位；切换窗口把 window 真传到端点', async () => {
    const seen: string[] = []
    server.use(
      http.get(ANALYTICS_URL, ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('window') ?? '')
        return okEnvelope(fixtures.breadthAnalytics)
      }),
    )
    mount(<SentimentClock />)
    expect(screen.getByRole('heading', { name: '投机情绪周期时钟' })).toBeTruthy()
    // 首帧未取到数据时数据日如实显「—」，等端点回来才是权威数据日 2026-08-21。
    await waitFor(() => expect(screen.getByText(/数据截至 2026-08-21/)).toBeTruthy(), { timeout: 5000 })
    await waitFor(() => expect(screen.getAllByText('中性').length).toBeGreaterThan(0), { timeout: 5000 })
    expect(screen.getByText(/全部为历史统计描述，不预测收益/)).toBeTruthy()
    expect(screen.getAllByTestId('echart').length).toBeGreaterThan(0)
    expect(seen).toContain('250')

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: '60' } })
    await waitFor(() => expect(seen).toContain('60'), { timeout: 5000 })
  })

  it('当前相位段不可用只降级该段（带 reason），时序段与数据边界照常渲染', async () => {
    const d = cloneAnalytics()
    d.sections.phase.current = { available: false, reason: '最新一行关键字段缺失' }
    server.use(http.get(ANALYTICS_URL, () => okEnvelope(d)))
    mount(<SentimentClock />)
    await waitFor(() => expect(screen.getByText('当前相位暂无数据')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/最新一行关键字段缺失/)).toBeTruthy()
    expect(screen.getByText('离线数据边界（务必阅读）')).toBeTruthy()
    expect(screen.getAllByTestId('echart').length).toBeGreaterThan(0)
  })

  it('端点报错显 role=alert，不谎报空数据', async () => {
    server.use(
      http.get(ANALYTICS_URL, () =>
        HttpResponse.json({ status: 'error', code: 'x', message: '离线广度统计加载失败', data: null }),
      ),
    )
    mount(<SentimentClock />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/离线广度统计加载失败/)).toBeTruthy()
  })

  it('10 个离线缺真值维度逐条披露，不隐藏', async () => {
    mount(<SentimentClock />)
    await waitFor(() => expect(screen.getByText(/以下 10 个维度离线缺真值/)).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/connect_hl/)).toBeTruthy()
  })
})

describe('67 历史相似日聚类（/similar-days）', () => {
  it('相似日表与 5/10/20 日前向统计真实渲染', async () => {
    mount(<SimilarDays />)
    expect(screen.getByRole('heading', { name: '历史相似日聚类 · 前向分布' })).toBeTruthy()
    await waitFor(() => expect(screen.getByText('2025-04-15')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText('86.7%')).toBeTruthy() // forward_stats['5'].up_ratio
    const table = screen.getByRole('table')
    expect(within(table).getByText('48.84%')).toBeTruthy() // 首个相似日后 5 日红盘占比
    expect(screen.getByText(/排除末 ±15 日防泄漏/)).toBeTruthy()
  })

  it('某前向窗口无样本显「—」并提示不补 0', async () => {
    const d = cloneAnalytics()
    d.sections.similar.forward_stats['10'] = {
      n: 0, mean: null, median: null, p10: null, p90: null, up_ratio: null,
    }
    server.use(http.get(ANALYTICS_URL, () => okEnvelope(d)))
    mount(<SimilarDays />)
    await waitFor(() => expect(screen.getByText(/部分前向窗口无足够样本/)).toBeTruthy(), { timeout: 5000 })
    // 无样本时 n=0 是真实统计事实（不是补零），但 up_ratio 必须显「—」。
    expect(screen.getByText(/n=0/)).toBeTruthy()
    const label = screen.getByText('后 10 日红盘占比')
    expect(within(label.parentElement as HTMLElement).getByText('—')).toBeTruthy()
    expect(screen.queryByText('0%')).toBeNull()
  })
})

describe('68 情绪拐点扫描器（/inflection-scan）', () => {
  it('事件表 + 维度切换把新 dim 真传到 zseries 端点', async () => {
    const seen: string[] = []
    server.use(
      http.get(ZSERIES_URL, ({ request }) => {
        const url = new URL(request.url)
        seen.push(url.searchParams.get('dim') ?? '')
        return okEnvelope(fixtures.breadthZSeries)
      }),
    )
    mount(<InflectionScan />)
    expect(screen.getByRole('heading', { name: '情绪拐点扫描器' })).toBeTruthy()
    await waitFor(() => expect(screen.getAllByText('触顶回落').length).toBeGreaterThan(0), { timeout: 5000 })
    await waitFor(() => expect(seen).toContain('up_count'), { timeout: 5000 })
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'red_ratio' } })
    await waitFor(() => expect(seen).toContain('red_ratio'), { timeout: 5000 })
  })

  it('z-score 段不可用只降级该段（带 reason），事件表仍在', async () => {
    server.use(
      http.get(ZSERIES_URL, () =>
        okEnvelope({
          ...fixtures.breadthZSeries,
          available: false,
          reason: '该维度历史数据不足',
          dates: [], z: [], raw: [], markers: [],
        }),
      ),
    )
    mount(<InflectionScan />)
    await waitFor(() => expect(screen.getByText('该维度暂无 z-score 轨迹')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText(/该维度历史数据不足/)).toBeTruthy()
    await waitFor(() => expect(screen.getByRole('table')).toBeTruthy(), { timeout: 5000 })
  })
})

describe('69 温度持续期（/regime-duration）', () => {
  it('五档明细与冰点磨底时长真实渲染', async () => {
    mount(<RegimeDuration />)
    expect(screen.getByRole('heading', { name: '温度持续期与回归时长' })).toBeTruthy()
    await waitFor(() => expect(screen.getByRole('table')).toBeTruthy(), { timeout: 5000 })
    const table = screen.getByRole('table')
    expect(within(table).getByText('冰点')).toBeTruthy()
    expect(within(table).getByText('狂热')).toBeTruthy()
    expect(screen.getAllByTestId('echart').length).toBeGreaterThan(0)
    expect(screen.getByText(/红盘占比\(red_ratio\) 五档代理/)).toBeTruthy()
  })

  it('某档中位缺失显「—」，绝不补 0 天', async () => {
    const d = cloneAnalytics()
    d.sections.duration.durations['0'].median = null
    server.use(http.get(ANALYTICS_URL, () => okEnvelope(d)))
    mount(<RegimeDuration />)
    await waitFor(() => expect(screen.getByRole('table')).toBeTruthy(), { timeout: 5000 })
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('—').length).toBeGreaterThan(0)
    expect(within(table).queryByText('0 天')).toBeNull()
  })
})
