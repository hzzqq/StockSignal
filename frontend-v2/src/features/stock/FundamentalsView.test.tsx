// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { fundamentalsFull, financialsFull } from '@/mocks/fixtures'
import { Providers } from '@/app/providers'
import { FundamentalsView } from './FundamentalsView'

/**
 * 基本面分析 · 已有 E2E（tests/e2e/w4b-pages.test.tsx）已守：完整态、全字段 null、
 * perf 9 字段全 null、perf 整体 null + rows 空、date:null 独立、fund 取数失败。
 * 本文件只补它**没覆盖**的边界：财报（fin）独立失败隔离、双日期双 null 不互兜底、
 * 非法 search.code 回落默认值、fin rows=[] 时主数据不受连累。
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

const calls = vi.hoisted(() => ({ list: [] as string[] }))

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

function recordFundamentals(data: unknown = fundamentalsFull) {
  server.use(
    http.get('/api/v2/read/fundamentals', ({ request }) => {
      calls.list.push(new URL(request.url).searchParams.get('code') ?? '')
      return ok(data)
    }),
  )
}

function renderView(search?: { code?: string }) {
  return render(
    <Providers>
      <FundamentalsView search={search} />
    </Providers>,
  )
}

describe('FundamentalsView · 已有 E2E 未覆盖的独立源/归一化边界', () => {
  it('⚠️ 财报源独立失败 → 财报卡显示错误 alert，主数据与 9 项指标照常渲染', async () => {
    recordFundamentals()
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
    expect(screen.getByText('权威数据日：2026-11-06')).toBeTruthy()
    expect(screen.getByTestId('perf-revenue_yi').textContent).not.toBe('缺失')
    // 副源失败不得让整页落进主错误态
    expect(screen.queryByText('暂无基本面数据')).toBeNull()
  })

  it('spot_date / kline_date 双 null → 各自显「—」，绝不互兜底或补日期', async () => {
    recordFundamentals({ ...fundamentalsFull, spot_date: null, kline_date: null })
    renderView()

    expect(
      await screen.findByText('行情快照日 spot_date：—', {}, FIND),
    ).toBeTruthy()
    expect(screen.getByText('K 线数据日 kline_date：—')).toBeTruthy()
    // 两个日期字段都不得借权威数据日 2026-11-06 冒充
    expect(screen.queryByText(/spot_date：2026/)).toBeNull()
    expect(screen.queryByText(/kline_date：2026/)).toBeNull()
  })

  it('非法 search.code → 回落默认 600519，且首帧只按 600519 请求', async () => {
    recordFundamentals()
    renderView({ code: 'abc' })

    await screen.findByText('权威数据日：2026-11-06', {}, FIND)
    expect(screen.getByText('代码 600519')).toBeTruthy()
    expect(calls.list[0]).toBe('600519')
    expect(calls.list).not.toContain('abc')
  })

  it('财报 rows=[] →「暂无财报数据」空态，主数据与 perf 不受连累', async () => {
    recordFundamentals()
    server.use(http.get('/api/v2/read/financials', () => ok({ ...financialsFull, rows: [] })))
    renderView()

    expect(await screen.findByText('暂无财报数据', {}, FIND)).toBeTruthy()
    expect(screen.getByText('rows 为空数组，未做填充')).toBeTruthy()
    expect(screen.getByText('权威数据日：2026-11-06')).toBeTruthy()
    expect(screen.getByTestId('perf-roe').textContent).not.toBe('缺失')
  })
})
