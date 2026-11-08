// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import * as fixtures from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { DiagnosticsView } from '@/features/ops/DiagnosticsView'
import { NAV } from '@/nav/nav'

/**
 * W4-D · 数据源 + 接口检测页契约 E2E（MSW）。
 * 不 mock 页面实现、不放宽守卫；只验证两块检测同页、四态、诚实降级与主动探测。
 */
const NOTE_MSW = /MSW 已启用|开发 Mock 环境/

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

function mount() {
  return render(
    <Providers>
      <DiagnosticsView />
    </Providers>,
  )
}

describe('W4-D · 数据源与接口检测页', () => {
  it('两块检测同页：标题 + 汇总 + 依赖缓存 + 时效 + 网络探测 + 接口检测', async () => {
    mount()
    // 标题恒在（QueryState 之外），必须等真实取数结果出现，才能断言内容区已渲染
    expect(await screen.findByText('4/5 可用')).toBeTruthy()
    expect(screen.getByText('数据源与接口检测')).toBeTruthy()
    expect(screen.getByText('① 数据源检测')).toBeTruthy()
    expect(screen.getByText('② 接口检测')).toBeTruthy()
    expect(screen.getByText('依赖与本地缓存')).toBeTruthy()
    expect(screen.getByText('各数据源时效')).toBeTruthy()
    // Mock 态不得再自称「真实」网络探测（诚实红线）
    expect(screen.getByText('四源网络探测（模拟数据）')).toBeTruthy()
    expect(screen.queryByText('四源真实网络探测')).toBeNull()
    expect(screen.getByText(/当前为 Mock 环境：点击只会读取 MSW 夹具里的模拟结果/)).toBeTruthy()
    expect(screen.getByText('只读端点连通性')).toBeTruthy()
    // 汇总：4/5 可用，4 源时效，12 个端点（其中 5 个需参数）
    expect(screen.getByText('4/5 可用')).toBeTruthy()
    expect(screen.getByText('4 源')).toBeTruthy()
    expect(screen.getByText('12')).toBeTruthy()
  })

  it('诚实：默认零网络，probe=null 显示「尚未探测」，接口检测显示「尚未检测」', async () => {
    mount()
    expect(await screen.findByText('尚未探测（默认零网络）。')).toBeTruthy()
    expect(screen.getByText(/尚未检测。点击「开始检测」/)).toBeTruthy()
  })

  it('诚实：开发态标注 MSW 模拟响应，不冒充真实后端', async () => {
    mount()
    expect(await screen.findByText(NOTE_MSW)).toBeTruthy()
    expect(screen.getByText(/不代表真实后端连通性/)).toBeTruthy()
  })

  it('数据源逐项与时效如实渲染：失败项显示「不可用」、滞后显示「滞后」、null 显示「—」', async () => {
    mount()
    expect(await screen.findByText('BaoStock')).toBeTruthy()
    expect(screen.getAllByText('不可用').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('P1 事件因子')).toBeTruthy()
    expect(screen.getByText('2026-10-16')).toBeTruthy()
    expect(screen.getAllByText('滞后').length).toBeGreaterThanOrEqual(1)
    // 市场温度 as_of=null / lag_days=null → 两个 —
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('Mock 态点击查看模拟探测结果 → probe=1，且逐卡如实标注模拟、不冒充真实探网', async () => {
    mount()
    const btn = await screen.findByRole('button', { name: '查看模拟探测结果' })
    expect(screen.queryByRole('button', { name: '开始真实网络探测' })).toBeNull()
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText('连接超时')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByText('176 ms')).toBeTruthy()
    expect(screen.getByText('10000 ms')).toBeTruthy()
    // 负耗时（-1 ms）是假数据，必须显示为「—」而不是负数
    expect(screen.queryByText('-1 ms')).toBeNull()
    expect(screen.getAllByText('通').length).toBe(2)
    expect(screen.getAllByText('不通').length).toBe(2)
    // 四张卡片逐卡标「模拟」+ 整体提示，绝不冒充真实探网结果
    expect(screen.getAllByText('· 模拟').length).toBe(4)
    expect(screen.getByText(/以下四源结果来自 MSW 模拟夹具/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '重新查看模拟结果' })).toBeTruthy()
  })

  it('点「开始检测」→ 对可探测端点真实 GET，显示 HTTP/信封/耗时；需参数端点如实跳过', async () => {
    mount()
    const btn = await screen.findByRole('button', { name: '开始检测' })
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText('7/7')).toBeTruthy(), { timeout: 8000 })
    expect(screen.getByText(/跳过（需参数）：/)).toBeTruthy()
    // 每个结果行的 HTTP 200 + 信封 ok
    expect(screen.getAllByText('200').length).toBeGreaterThanOrEqual(7)
  })

  it('「重新探测」每次点击都真的重新请求（旧实现 setWantProbe(true) 是 no-op）', async () => {
    let hits = 0
    server.use(http.get('/api/v2/read/diagnostics', ({ request }) => {
      hits += 1
      const q = new URL(request.url).searchParams
      return HttpResponse.json({
        status: 'ok', code: 'ok', message: 'ok',
        data: q.get('probe') === '1' ? fixtures.diagnosticsProbe : fixtures.diagnostics,
      })
    }))
    mount()
    const first = await screen.findByRole('button', { name: '查看模拟探测结果' })
    fireEvent.click(first)
    await waitFor(() => expect(screen.getByText('连接超时')).toBeTruthy(), { timeout: 5000 })
    const baseline = hits
    fireEvent.click(screen.getByRole('button', { name: '重新查看模拟结果' }))
    await waitFor(() => expect(hits).toBeGreaterThan(baseline), { timeout: 5000 })
  })

  it('取数失败进入错误态，不谎报「全部正常」', async () => {
    server.use(
      http.get('/api/v2/read/diagnostics', () =>
        HttpResponse.json({ status: 'error', code: 'server_error', message: '后端异常', data: null }, { status: 500 }),
      ),
    )
    mount()
    expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.queryByText('① 数据源检测')).toBeNull()
  })

  it('检测项独立降级：available=false 时显示原因，不把空数组包装成成功', async () => {
    server.use(http.get('/api/v2/read/diagnostics', () =>
      HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data: fixtures.diagnosticsDegraded }),
    ))
    mount()
    expect(await screen.findByText(/模拟 fetcher 不可用/)).toBeTruthy()
    expect(screen.getByText(/模拟本地文件不可读/)).toBeTruthy()
    expect(screen.getAllByText('不可用').length).toBeGreaterThanOrEqual(2)
    expect(screen.queryByText('4/5 可用')).toBeNull()
  })

  it('导航注册：新页在 NAV 中、路径唯一、图标全局唯一、仍 4 组', () => {
    const items = NAV.flatMap((g) => g.items)
    const entry = items.filter((it) => it.to === '/diagnostics')
    expect(entry.length).toBe(1)
    expect(entry[0].label).toBe('数据源与接口检测')
    expect(NAV.length).toBe(4)
    expect(new Set(items.map((it) => it.icon)).size).toBe(items.length)
  })
})
