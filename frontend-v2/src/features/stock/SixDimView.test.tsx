// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { sixDimFull, sixDimPartial } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { SixDimView } from './SixDimView'

/**
 * 六维评分 · 已有 E2E（tests/e2e/w4-six-dim.test.tsx）已守：缺维 DOM 显「缺失」、
 * date:null 无兜底、note 原文、导航注册。本文件只补它**没覆盖**的边界：
 *  ① 传给 ECharts 的 option 里缺维必须是 null，不能补 0 分（图形层诚实，DOM 绿不代表图绿）；
 *  ② coverage=0 全缺失空态；③ overall / note / date 三处 null；④ 非法 code 零请求。
 */
const captured = vi.hoisted(() => ({ options: [] as unknown[], calls: [] as string[] }))

vi.mock('@/shared/charts/EChart', () => ({
  EChart: (props: { option: unknown }) => {
    captured.options.push(props.option)
    return <div data-testid="echart" />
  },
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  captured.options.length = 0
  captured.calls.length = 0
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }
const ok = (data: unknown) =>
  HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })

function mockSixDim(data: unknown) {
  server.use(
    http.get('/api/v2/read/six-dim', ({ request }) => {
      captured.calls.push(new URL(request.url).searchParams.get('code') ?? '')
      return ok(data)
    }),
  )
}

function renderView() {
  return render(
    <Providers>
      <SixDimView />
    </Providers>,
  )
}

type RadarOption = {
  series: Array<{
    symbolSize: number
    data: Array<{
      value: (number | null)[]
      lineStyle?: { opacity?: number }
      areaStyle?: unknown
    }>
  }>
}

describe('SixDimView · 已有 E2E 未覆盖的边界', () => {
  it('⚠️ 雷达 option 缺维为 null，绝不补 0 分（图形层诚实）', async () => {
    mockSixDim(sixDimPartial)
    renderView()
    // 统一搜索输入：输入合法码后点「直接按代码查询」（等价于旧手输提交）。
    const input = screen.getByRole('combobox', { name: '搜索股票（代码 / 名称 / 首字母）' })
    fireEvent.change(input, { target: { value: '000001' } })
    const rawBtn = await screen.findByRole(
      'button',
      { name: /直接按代码 000001 查询/ },
      FIND,
    )
    fireEvent.click(rawBtn)
    await screen.findByText('仅 4/6 维有效，缺失维未取到数据', {}, FIND)

    const option = captured.options.at(-1) as RadarOption
    const values = option.series[0].data[0].value
    expect(values).toHaveLength(6)
    expect(values[1]).toBeNull() // capital
    expect(values[3]).toBeNull() // growth
    expect(values.filter((v) => v === null)).toHaveLength(2)
    expect(values.some((v) => v === 0)).toBe(false)
    expect(values[0]).toBe(50.2)
    // 缺维不相邻，连线会跨过 null 形成假多边形 → 必须隐藏线与面积，只留孤立数据点
    expect(option.series[0].symbolSize).toBe(7)
    expect(option.series[0].data[0].lineStyle?.opacity).toBe(0)
    expect(option.series[0].data[0].areaStyle).toBeUndefined()
  })

  it('⚠️ 六维齐全才恢复雷达连线与面积填充', async () => {
    mockSixDim(sixDimFull)
    renderView()
    await screen.findByText('权威数据日：2026-11-07', {}, FIND)

    const option = captured.options.at(-1) as RadarOption
    expect(option.series[0].symbolSize).toBe(5)
    expect(option.series[0].data[0].lineStyle?.opacity).toBe(1)
    expect(option.series[0].data[0].areaStyle).toBeTruthy()
  })

  it('coverage=0 六维全缺失 → 诚实空态，不渲染雷达图、不显 0/6 假数据', async () => {
    mockSixDim({
      ...sixDimFull,
      dims: {
        technical: null, capital: null, value: null,
        growth: null, fundamental: null, cycle: null,
      },
      overall: null,
      coverage: 0,
      missing: ['technical', 'capital', 'value', 'growth', 'fundamental', 'cycle'],
    })
    renderView()

    expect(await screen.findByText('该股六维数据均缺失', {}, FIND)).toBeTruthy()
    expect(screen.getByText('未取到任何有效维度，未做补零填充')).toBeTruthy()
    expect(screen.queryByTestId('echart')).toBeNull()
    expect(screen.queryByText('0/6')).toBeNull()
  })

  it('overall=null →「暂无综合分」，不得出现 0 / 0.00', async () => {
    mockSixDim({ ...sixDimFull, overall: null })
    renderView()

    expect(await screen.findByText('暂无综合分', {}, FIND)).toBeTruthy()
    expect(screen.queryByText(/^0(\.0+)?$/)).toBeNull()
  })

  it('note=null →「原始响应未提供口径说明」，不编造口径文案', async () => {
    mockSixDim({ ...sixDimFull, note: null })
    renderView()

    expect(await screen.findByText('原始响应未提供口径说明', {}, FIND)).toBeTruthy()
  })

  it('date=null → 横幅「暂无权威数据日」+ Stat「最新数据日」显「—」，禁互兜底', async () => {
    mockSixDim({ ...sixDimFull, date: null })
    renderView()

    expect(await screen.findByText('暂无权威数据日', {}, FIND)).toBeTruthy()
    expect(screen.queryByText(/权威数据日：/)).toBeNull()
    const stat = screen.getByText('最新数据日').parentElement
    expect(stat?.querySelector('.text-kpi')?.textContent).toBe('—')
    // 真实数据日不得借其它字段（note / code）冒充
    expect(screen.queryByText('2026-11-07')).toBeNull()
  })

  it('名称展示：响应 name 优先 → 显示「代码 · 名称」+ Stat「股票」', async () => {
    mockSixDim({ ...sixDimFull, name: '贵州茅台' })
    renderView()
    await screen.findByText('权威数据日：2026-11-07', {}, FIND)
    expect(screen.getByText('600519 · 贵州茅台')).toBeTruthy()
    const stat = screen.getByText('股票').parentElement
    expect(stat?.querySelector('.text-kpi')?.textContent).toBe('贵州茅台')
  })

  it('名称缺失且非搜索选中 → 只显代码，绝不臆造股票名', async () => {
    mockSixDim({ ...sixDimFull, name: null })
    renderView()
    await screen.findByText('权威数据日：2026-11-07', {}, FIND)
    expect(screen.getByText('代码 600519')).toBeTruthy()
    expect(screen.queryByText('600519 · 贵州茅台')).toBeNull()
    const stat = screen.getByText('股票').parentElement
    expect(stat?.querySelector('.text-kpi')?.textContent).toBe('600519')
  })

  it('非法 code → 零新请求（搜索框非 6 位输入无候选、无直接查询入口，Enter 不触发）', async () => {
    mockSixDim(sixDimFull)
    renderView()
    await screen.findByText('权威数据日：2026-11-07', {}, FIND)
    captured.calls.length = 0

    const input = screen.getByRole('combobox', { name: '搜索股票（代码 / 名称 / 首字母）' })
    fireEvent.change(input, { target: { value: 'abc' } })
    // 等搜索防抖落地：'abc' 无候选 → 下拉显「未找到匹配的股票」，也无「直接按代码查询」入口
    await screen.findByText('未找到匹配的股票', {}, FIND)
    expect(screen.queryByText(/直接按代码/)).toBeNull()
    fireEvent.keyDown(input, { key: 'Enter' })
    // 再等一拍：确认没有任何 six-dim 请求发出（非法码行为不变）
    await new Promise((r) => setTimeout(r, 100))
    expect(captured.calls).toHaveLength(0)
  })
})
