// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { EarningsHunterPanel } from './EarningsHunterPanel'

/**
 * 77 财报猎手 · EarningsHunterPanel 交互语义边界（锐评轮补测）。
 *
 * 锁定语义：**任何条件变更（报告期 / 信号级别 / 最小幅度）都必须重新点
 * 「扫描业绩预告」才发起请求**——minPct 输入中途（如先敲 "-"）min_pct 校验
 * 失败传 undefined，若 key 变化自动 fetch，会以「无下限过滤」的中间态参数
 * 发请求并把结果表闪换成未过滤数据（诚实红线：不让用户看到语义错误的中间结果）。
 */
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  calls.count = 0
  calls.params.length = 0
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }
const calls = { count: 0, params: [] as string[] }

const ehOk = {
  available: true,
  rows: [{ 代码: '600519', 名称: '贵州茅台', 预增幅度: 15.5 }],
  n_total: 1,
  n_scanned: 5,
  signal_counts: { 利好: 1, 偏多: 0, 中性: 0, 偏空: 0, 利空: 0 },
  reason: null,
}

function recordCalls() {
  server.use(
    http.get('/api/v2/read/earnings-hunter', ({ request }) => {
      calls.count += 1
      const u = new URL(request.url)
      calls.params.push(u.searchParams.get('period') ?? '?')
      return HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data: ehOk })
    }),
  )
}

function renderPanel() {
  return render(
    <Providers>
      <EarningsHunterPanel />
    </Providers>,
  )
}

describe('EarningsHunterPanel · 条件变更必须手动重扫', () => {
  it('扫描成功后修改最小幅度输入框 → 零自动请求（不得以中间态参数偷偷 fetch）', async () => {
    recordCalls()
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: '扫描业绩预告' }))
    await waitFor(() => expect(calls.count).toBe(1), FIND)
    await screen.findByText(/筛选命中 1 条/, undefined, FIND)

    // 模拟用户逐字输入 -50：先敲 "-"（校验失败、min_pct 中间态 undefined）
    const input = screen.getByRole('spinbutton', { name: '最小业绩变动幅度' })
    fireEvent.change(input, { target: { value: '-' } })
    fireEvent.change(input, { target: { value: '-5' } })
    fireEvent.change(input, { target: { value: '-50' } })

    // 修复前：queryKey 随 min_pct 变化自动 fetch，calls.count 增到 4（含中间态 undefined 的无过滤请求）
    await new Promise((r) => setTimeout(r, 50))
    expect(calls.count).toBe(1)
  })

  it('切换报告期后不自动请求，重新点扫描才以新参数发起', async () => {
    recordCalls()
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: '扫描业绩预告' }))
    await waitFor(() => expect(calls.count).toBe(1), FIND)

    fireEvent.change(screen.getByRole('combobox', { name: '业绩预告报告期' }), {
      target: { value: '20251231' },
    })
    await new Promise((r) => setTimeout(r, 300))
    expect(calls.count).toBe(1) // 切期即失效，不自动请求
    expect(calls.params.join(',')).toBe('20260630') // 唯一请求以初值 period 发出

    fireEvent.click(screen.getByRole('button', { name: '扫描业绩预告' }))
    await waitFor(() => expect(calls.count).toBe(2), FIND)
  })

  it('minPct 非法（非数字）→ 扫描按钮禁用，不发请求', () => {
    renderPanel()
    const input = screen.getByRole('spinbutton', { name: '最小业绩变动幅度' })
    fireEvent.change(input, { target: { value: 'abc' } })
    expect(
      (screen.getByRole('button', { name: '扫描业绩预告' }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})
