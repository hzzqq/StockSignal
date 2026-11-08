// @vitest-environment jsdom
/**
 * 零覆盖页面 · 真实渲染冒烟（MSW）。
 *
 * 背景：/decision /replay /p1 /recommend /paper /alerts /webapps /morning
 * 这 8 条路由此前**没有任何真实渲染测试**（只有源码字符串守卫或首帧断言）。
 * 本文件用 <Providers> + MSW 真实挂载每个页面，验证两件事：
 *   ① 成功态能渲染出实质内容，不卡在加载/空/错误态、不打 console.error；
 *   ② 取数失败时显示错误态（role=alert + 真实错误文案），绝不把失败吞成空数据。
 * 这是诚实红线的运行时证据，不是「页面文件存在」式健康检查。
 */
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ComponentType, ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { DecisionPanel } from '@/features/decision/DecisionPanel'
import { DecisionReplay } from '@/features/decision/DecisionReplay'
import { P1Signals } from '@/features/p1/P1Signals'
import { Recommendation } from '@/features/recommend/Recommendation'
import { PaperTrades } from '@/features/paper/PaperTrades'
import { Alerts } from '@/features/alerts/Alerts'
import { WebApps } from '@/features/webapps/WebApps'
import { MorningReport } from '@/features/morning/MorningReport'
import * as fixtures from '@/mocks/fixtures'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
    useNavigate: () => vi.fn(),
  }
})

// jsdom 无 canvas：SnapshotView 的 PositionGauge / ScenarioChart 替身，
// 只验证取数/降级契约，不验证绘图（与 w4b-pages 等兄弟测试一致）。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ ariaLabel }: { ariaLabel?: string }) => (
    <div data-testid="echart" role="img" aria-label={ariaLabel ?? '图表'} />
  ),
}))

const server = setupServer(...handlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  vi.restoreAllMocks()
})
afterAll(() => server.close())

interface Page {
  title: string
  Component: ComponentType
}

// 默认 MSW 有可用夹具的 6 页；Alerts（404 诚实降级）与 MorningReport（默认不取数）另测
const SUCCESS_PAGES: Page[] = [
  { title: '今日决策面板', Component: DecisionPanel },
  { title: 'P1 量化信号', Component: P1Signals },
  { title: '每日荐股', Component: Recommendation },
  { title: '模拟交易账本', Component: PaperTrades },
  { title: '网页作品集', Component: WebApps },
]

const FIND = { timeout: 8000 }
const ERROR_TEXT = '注入的服务器故障'

describe('零覆盖页面 · 成功态真实渲染', () => {
  it.each(SUCCESS_PAGES)('$title：标题 + 实质内容，不卡加载/空/错误态', async ({ title, Component }) => {
    const errSpy = vi.spyOn(console, 'error')
    const { container } = render(
      <Providers>
        <Component />
      </Providers>,
    )
    expect(screen.getByRole('heading', { name: title })).toBeTruthy()
    await waitFor(() => {
      expect(screen.queryByText('加载中…')).toBeNull()
      expect(screen.queryByText('暂无数据')).toBeNull()
      expect(screen.queryAllByRole('alert')).toHaveLength(0)
    }, FIND)
    // 不是只剩一个标题的空壳
    expect((container.textContent ?? '').length).toBeGreaterThan(title.length + 20)
    expect(errSpy).not.toHaveBeenCalled()
  })

  it.each(SUCCESS_PAGES)('$title：取数失败显示错误态，不把失败吞成空数据', async ({ title, Component }) => {
    server.use(
      http.get('/api/v2/read/*', () =>
        HttpResponse.json(
          { status: 'error', code: 'internal', message: ERROR_TEXT, data: null },
          { status: 500 },
        ),
      ),
    )
    render(
      <Providers>
        <Component />
      </Providers>,
    )
    expect(screen.getByRole('heading', { name: title })).toBeTruthy()
    await waitFor(() => {
      expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
    }, FIND)
    expect(screen.getAllByText(new RegExp(ERROR_TEXT)).length).toBeGreaterThan(0)
    expect(screen.queryByText('暂无数据')).toBeNull()
  })
})

describe('两个默认「诚实降级」页', () => {
  it('告警引擎：数据文件缺失时如实报错，不渲染伪造的规则 JSON', async () => {
    render(
      <Providers>
        <Alerts />
      </Providers>,
    )
    expect(screen.getByRole('heading', { name: '告警引擎' })).toBeTruthy()
    await waitFor(() => {
      expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
    }, FIND)
    expect(screen.getByText('告警规则（alert_rules.json）')).toBeTruthy()
    expect(screen.getByText('告警日志（alerts.log）')).toBeTruthy()
    // 404 不能被吞成「暂无数据」空态，也不能编造规则内容
    expect(screen.queryByText('暂无告警规则')).toBeNull()
  })

  it('每日晨报：默认不发请求；选日期后才按所选数据日查询', async () => {
    let hits = 0
    server.use(
      http.get('/api/v2/read/review-notes', ({ request }) => {
        hits += 1
        const date = new URL(request.url).searchParams.get('date')
        return HttpResponse.json({
          status: 'ok', code: 'ok', message: 'ok',
          data: { date, content: '当日复盘正文' },
        })
      }),
    )
    const { container } = render(
      <Providers>
        <MorningReport />
      </Providers>,
    )
    expect(screen.getByRole('heading', { name: /每日晨报/ })).toBeTruthy()
    expect(screen.getByText(/未选择日期，不发起查询/)).toBeTruthy()
    expect(hits).toBe(0)

    const input = container.querySelector('input[type="date"]') as HTMLInputElement
    expect(input).toBeTruthy()
    fireEvent.change(input, { target: { value: '2026-09-21' } })
    expect(await screen.findByText('当日复盘正文', {}, FIND)).toBeTruthy()
    expect(hits).toBeGreaterThan(0)
    expect(screen.queryByText(/未选择日期，不发起查询/)).toBeNull()
  })
})

const fixturesForReplay = fixtures.snapshots['2026-09-21']

describe('决策回放 · 需先选日期的交互链路', () => {
  it('默认不预选、不渲染快照；日期清单加载后选项真实出现', async () => {
    render(
      <Providers>
        <DecisionReplay />
      </Providers>,
    )
    expect(screen.getByRole('heading', { name: '决策回放' })).toBeTruthy()
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('')
    // 未选日期时不得拿今日快照冒充历史回放
    expect(screen.queryByText('仓位建议')).toBeNull()
    await waitFor(() => {
      expect(screen.getByRole('option', { name: '2026-09-21' })).toBeTruthy()
    }, FIND)
  })

  it('选归档日期后才渲染该日快照（走 snapshot/:date 而非 daily-snapshot）', async () => {
    let snapHits = 0
    let dailyHits = 0
    server.use(
      http.get('/api/v2/read/snapshot/:date', () => {
        snapHits += 1
        return HttpResponse.json({
          status: 'ok', code: 'ok', message: 'ok', data: fixturesForReplay,
        })
      }),
      http.get('/api/v2/read/daily-snapshot', () => {
        dailyHits += 1
        return HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data: null })
      }),
    )
    render(
      <Providers>
        <DecisionReplay />
      </Providers>,
    )
    await waitFor(() => {
      expect(screen.getByRole('option', { name: '2026-09-21' })).toBeTruthy()
    }, FIND)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2026-09-21' } })
    expect(await screen.findByText('仓位建议', {}, FIND)).toBeTruthy()
    expect(snapHits).toBeGreaterThan(0)
    expect(dailyHits).toBe(0)
  })

  it('日期清单失败：role=alert 并带出真实错误原因，不吞成笼统提示', async () => {
    server.use(
      http.get('/api/v2/read/snapshot-dates', () =>
        HttpResponse.json(
          { status: 'error', code: 'internal', message: ERROR_TEXT, data: null },
          { status: 500 },
        ),
      ),
    )
    render(
      <Providers>
        <DecisionReplay />
      </Providers>,
    )
    await waitFor(() => {
      expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
    }, FIND)
    expect(screen.getByText(new RegExp(ERROR_TEXT))).toBeTruthy()
  })
})
