// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { FundamentalsView } from '@/features/stock/FundamentalsView'
import { ResearchView } from '@/features/stock/ResearchView'
import { NAV } from '@/nav/nav'

/**
 * W4-B · 两页前端契约 E2E（MSW）。
 * 照 w4-six-dim.test.tsx 用 <Providers> 独立渲染纯组件（无 RouterProvider）；
 * 纯组件里的 TanStack <Link> 需 router context 才能解析 href，这里以最小 <a> 替身替换，
 * 不触碰页面实现、不放宽任何守卫。
 */
vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
  }
})

// jsdom 无 canvas，ECharts 渲染会抛 clearRect(null)；与 w4-six-dim/w3-pages 等兄弟测试一致，
// 用轻量替身替换真实 EChart，只验证取数/降级契约，不验证绘图本身。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ height }: { height?: number }) => <div data-testid="echart" style={{ height }} />,
}))

if (!('ResizeObserver' in globalThis)) {
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const NOTE = '逐字段独立取数、独立降级；缺失为 null 且不补 0'
const FIND = { timeout: 5000 }

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

describe('W4-B · 基本面分析页 FundamentalsView', () => {
  it('完整：note 原文、权威数据日、perf 9 项有值、财报表有行、priceDomain 可见', async () => {
    render(
      <Providers>
        <FundamentalsView search={{ code: '600519' }} />
      </Providers>,
    )
    expect(await screen.findByText('基本面分析', {}, FIND)).toBeTruthy()
    expect(await screen.findByText('权威数据日：2026-11-06', {}, FIND)).toBeTruthy()
    expect(screen.getByText(NOTE)).toBeTruthy()
    expect(screen.getByText('market')).toBeTruthy()
    expect(screen.getByTestId('perf-revenue_yi').textContent).not.toBe('缺失')
    expect(screen.getByText('报告期')).toBeTruthy()
    expect(screen.getByText('2025-09-30')).toBeTruthy()
  })

  it('全字段 null 降级：暂无权威数据日、perf 显示「缺失」、KPI 显示「—」，不出现当前日期', async () => {
    render(
      <Providers>
        <FundamentalsView search={{ code: '000002' }} />
      </Providers>,
    )
    expect(await screen.findByText('暂无权威数据日', {}, FIND)).toBeTruthy()
    expect(screen.queryByText(/权威数据日：/)).toBeNull()
    expect(screen.getByTestId('perf-revenue_yi').textContent).toBe('缺失')
    expect(screen.getByTestId('perf-roe').textContent).toBe('缺失')
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(5)
    expect(screen.getByText('部分基本面数据未取到，缺失项如实留空，未做补零或日期兜底')).toBeTruthy()
  })

  it('perf 为 9 字段全 null 对象（后端全源失败态）：9 项逐字段显示「缺失」、绝不补 0', async () => {
    render(
      <Providers>
        <FundamentalsView search={{ code: '000002' }} />
      </Providers>,
    )
    expect(await screen.findByText('暂无权威数据日', {}, FIND)).toBeTruthy()
    const perfKeys = [
      'revenue_yi', 'revenue_yoy', 'net_profit_yi', 'profit_yoy',
      'gross_margin', 'roe', 'alr', 'current_ratio', 'equity_ratio',
    ]
    for (const k of perfKeys) {
      // 全 null 对象是「逐字段缺失」，不是「整体无绩效」，且任一格不得出现补 0 的数字
      const cell = screen.getByTestId(`perf-${k}`)
      expect(cell.textContent).toBe('缺失')
      expect(cell.textContent ?? '').not.toMatch(/[0-9]/)
    }
    // 页面任何位置都不得出现被补出的 0 / 0.00 绩效值
    expect(screen.queryByText(/^0(\.0+)?$/)).toBeNull()
  })

  it('perf 整体 null（Zod nullable 保守上界兼容）→「暂无绩效指标」；rows 空 →「暂无财报数据」', async () => {
    render(
      <Providers>
        <FundamentalsView search={{ code: '000003' }} />
      </Providers>,
    )
    expect(await screen.findByText('暂无绩效指标', {}, FIND)).toBeTruthy()
    expect(await screen.findByText('暂无财报数据', {}, FIND)).toBeTruthy()
  })

  it('date:null 独立：暂无权威数据日，但 spot_date/kline_date 分行照常展示', async () => {
    render(
      <Providers>
        <FundamentalsView search={{ code: '000004' }} />
      </Providers>,
    )
    expect(await screen.findByText('暂无权威数据日', {}, FIND)).toBeTruthy()
    expect(screen.queryByText(/权威数据日：/)).toBeNull()
    expect(screen.getByText('行情快照日 spot_date：2026-11-06')).toBeTruthy()
    expect(screen.getByText('K 线数据日 kline_date：2026-11-05')).toBeTruthy()
  })

  it('取数失败进入错误态（四态之一）', async () => {
    server.use(
      http.get('/api/v2/read/fundamentals', () =>
        HttpResponse.json({ status: 'error', code: 'boom', message: '后端炸了', data: null }, { status: 200 }),
      ),
    )
    render(
      <Providers>
        <FundamentalsView search={{ code: '600519' }} />
      </Providers>,
    )
    expect(await screen.findByText('后端炸了', {}, FIND)).toBeTruthy()
  })
})

describe('W4-B · 个股研究页 ResearchView', () => {
  it('首帧 view=quick（缺 view 回落）：分段控件、K 线表、数据日、note 原文、反向出边', async () => {
    render(
      <Providers>
        <ResearchView search={{ view: 'quick' }} />
      </Providers>,
    )
    expect(await screen.findByText('个股研究', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('radio', { name: /快速选取/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('radio', { name: /深度分析/ }).getAttribute('aria-checked')).toBe('false')
    // 缺 code → 输入框默认 600519
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('600519')
    expect(await screen.findByText('权威数据日：2026-11-06', {}, FIND)).toBeTruthy()
    expect(screen.getByText('open')).toBeTruthy()
    expect(screen.getByText('close')).toBeTruthy()
    expect(screen.getByText(NOTE)).toBeTruthy()
    expect(screen.getByText('← 返回基本面分析（600519）')).toBeTruthy()
  })

  it('rows 空 + date:null：暂无 K 线数据 + 暂无权威数据日', async () => {
    render(
      <Providers>
        <ResearchView search={{ view: 'quick', code: '000003' }} />
      </Providers>,
    )
    expect(await screen.findByText('暂无权威数据日', {}, FIND)).toBeTruthy()
    expect(await screen.findByText('暂无 K 线数据', {}, FIND)).toBeTruthy()
  })

  it('date:null 但 rows 完整：暂无权威数据日，OHLC 表照常渲染', async () => {
    render(
      <Providers>
        <ResearchView search={{ view: 'quick', code: '000004' }} />
      </Providers>,
    )
    expect(await screen.findByText('暂无权威数据日', {}, FIND)).toBeTruthy()
    expect(await screen.findByText('open', {}, FIND)).toBeTruthy()
  })

  it('首帧 view=deep：research-deep 豁免态显示「V2 暂未接入」+ 已预选 code，不渲染 K 线表', async () => {
    render(
      <Providers>
        <ResearchView search={{ view: 'deep', code: '000001' }} />
      </Providers>,
    )
    expect(await screen.findByText('个股研究', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('radio', { name: /深度分析/ }).getAttribute('aria-checked')).toBe('true')
    // W4-C 实现：deep 子视图真实调 getResearchDeep；该码走豁免态（56 键深度分析 V2 暂未接入）。
    expect(
      await screen.findByText('56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy 查看旧版', {}, FIND),
    ).toBeTruthy()
    expect(screen.getByText(/已预选 code：/)).toBeTruthy()
    expect(screen.queryByText('open')).toBeNull()
  })

  it('切换分段：600519 同样显示豁免卡（真后端恒 false，MSW 不得伪造「已接入」）', async () => {
    render(
      <Providers>
        <ResearchView search={{ view: 'quick', code: '600519' }} />
      </Providers>,
    )
    expect(await screen.findByText('open', {}, FIND)).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: /深度分析/ }))
    // 真后端 research_deep() 恒返回 deep_analysis_available=false；旧 MSW 夹具伪造 true，
    // 让这个测试建立在错误前提上。现在按真后端口径断言：豁免卡 + 不渲染技术字段表。
    expect(
      await screen.findByText('56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy 查看旧版', {}, FIND),
    ).toBeTruthy()
    expect(screen.queryByText('pe_ttm')).toBeNull()
    expect(screen.queryByText('open')).toBeNull()
  })

  it('技术字段表分支：仅显式注入 true 响应才渲染（组件分支覆盖，非后端真实行为）', async () => {
    server.use(
      http.get('/api/v2/read/research-deep', () =>
        HttpResponse.json({
          status: 'ok', code: 'ok', message: 'ok',
          data: { code: '600519', deep_analysis_available: true, pe_ttm: 30.1, market_cap: 2100000 },
        }),
      ),
    )
    render(
      <Providers>
        <ResearchView search={{ view: 'deep', code: '600519' }} />
      </Providers>,
    )
    expect(await screen.findByText('pe_ttm', {}, FIND)).toBeTruthy()
    expect(screen.getByText('market_cap')).toBeTruthy()
  })

  it('非法 code：仅给校验提示，不发请求、不渲染旧表', async () => {
    render(
      <Providers>
        <ResearchView search={{ view: 'quick', code: '600519' }} />
      </Providers>,
    )
    expect(await screen.findByText('open', {}, FIND)).toBeTruthy()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'abc' } })
    expect(await screen.findByText('请输入 6 位数字股票代码后再查询', {}, FIND)).toBeTruthy()
    expect(screen.queryByText('open')).toBeNull()
  })

  it('K 线取数失败进入错误态（四态之一）', async () => {
    server.use(
      http.get('/api/v2/read/stock-kline', () =>
        HttpResponse.json({ status: 'error', code: 'boom', message: 'K线炸了', data: null }, { status: 200 }),
      ),
    )
    render(
      <Providers>
        <ResearchView search={{ view: 'quick', code: '600519' }} />
      </Providers>,
    )
    expect(await screen.findByText('K线炸了', {}, FIND)).toBeTruthy()
  })
})

describe('W4-B · 导航注册', () => {
  it('仍 4 组、第 3 组含 W4-C 个股对比共 8 项、图标全局唯一', () => {
    expect(NAV.length).toBe(4)
    const g3 = NAV[2]
    expect(g3.group).toBe('量化与工具')
    expect(g3.items.some((it) => it.to === '/stock/research')).toBe(true)
    expect(g3.items.some((it) => it.to === '/stock/fundamentals')).toBe(true)
    expect(g3.items.some((it) => it.to === '/stock/compare')).toBe(true)
    expect(g3.items.length).toBe(11)
    const icons = NAV.flatMap((g) => g.items.map((it) => it.icon))
    expect(new Set(icons).size).toBe(icons.length)
  })
})
