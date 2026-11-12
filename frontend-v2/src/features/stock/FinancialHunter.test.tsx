// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { financialsFull } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { FinancialHunter } from './FinancialHunter'

/**
 * 财报猎手 · 已有 E2E（tests/e2e/w4-financial-hunter.test.tsx）已守：null→「—」、
 * date:null、note:null、rows=[] 空态、tablist 选中互斥 + report 回显。
 * 本文件只补它**没覆盖**的边界：非法输入零请求、Enter 提交、深链预选、
 * 查询失败错误态（不伪装成「无数据」）、report 是否真的传到 API。
 */
const calls = vi.hoisted(() => ({
  list: [] as Array<{ code: string; report: string }>,
}))

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  calls.list.length = 0
})
afterAll(() => server.close())

const FIND = { timeout: 5000 }
const ok = (data: unknown) =>
  HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })

/** 记录每次 financials 请求的 code/report 参数，便于断言「零请求」与参数透传。 */
function recordCalls() {
  server.use(
    http.get('/api/v2/read/financials', ({ request }) => {
      const u = new URL(request.url)
      const report = u.searchParams.get('report') ?? 'income'
      calls.list.push({ code: u.searchParams.get('code') ?? '', report })
      // 与真实 handler 一致：report 由后端回显，页面显示 data.report（以后端为准）。
      return ok({ ...financialsFull, report })
    }),
  )
}

function renderView(search?: { code?: string }) {
  return render(
    <Providers>
      <FinancialHunter search={search} />
    </Providers>,
  )
}

describe('FinancialHunter · 已有 E2E 未覆盖的交互/错误边界', () => {
  it('非法输入 → 查询按钮 disabled，点击不发起请求', async () => {
    recordCalls()
    renderView()
    await screen.findByText('权威数据日：2025-09-30', {}, FIND)
    calls.list.length = 0

    const input = screen.getByRole('textbox', { name: '股票代码' })
    fireEvent.change(input, { target: { value: 'abc' } })
    const button = screen.getByRole('button', { name: '查询财报' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(button)
    expect(calls.list).toHaveLength(0)
    expect(screen.getByText('代码 600519')).toBeTruthy() // applied 未被非法值污染
  })

  it('Enter 键提交合法 code，请求参数带新 code', async () => {
    recordCalls()
    renderView()
    await screen.findByText('权威数据日：2025-09-30', {}, FIND)
    calls.list.length = 0

    const input = screen.getByRole('textbox', { name: '股票代码' })
    fireEvent.change(input, { target: { value: '000001' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await screen.findByText('代码 000001', {}, FIND)
    expect(calls.list.at(-1)?.code).toBe('000001')
  })

  it('深链 search.code 预选：首帧即按该 code 查询，不回落默认 600519', async () => {
    recordCalls()
    renderView({ code: '000002' })

    await screen.findByText('代码 000002', {}, FIND)
    expect(calls.list[0]?.code).toBe('000002')
    expect(calls.list.some((c) => c.code === '600519')).toBe(false)
  })

  it('⚠️ 查询失败 → ErrorState(alert) 显示真实原因，绝不伪装成「暂无财报数据」', async () => {
    server.use(
      http.get('/api/v2/read/financials', () =>
        HttpResponse.json(
          { status: 'error', code: 'boom', message: '财报接口 500', data: null },
          { status: 200 },
        ),
      ),
    )
    renderView()

    expect(await screen.findByText('财报接口 500', {}, FIND)).toBeTruthy()
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.queryByText('暂无财报数据')).toBeNull()
  })

  it('切换报表 tab → report 参数真的透传到 API（不只是 UI 回显）', async () => {
    recordCalls()
    renderView()
    await screen.findByText('权威数据日：2025-09-30', {}, FIND)
    calls.list.length = 0

    fireEvent.click(screen.getByRole('tab', { name: '现金流量表' }))
    await screen.findByText('报表 cash', {}, FIND)
    expect(calls.list.at(-1)?.report).toBe('cash')
    expect(calls.list.at(-1)?.code).toBe('600519')
  })
})
