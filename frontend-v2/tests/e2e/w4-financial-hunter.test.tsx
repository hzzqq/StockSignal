// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { FinancialHunter } from '@/features/stock/FinancialHunter'

/**
 * 77 财报猎手（/financial-hunter）前端契约 E2E（MSW）。
 * 用 <Providers> 独立渲染（现有 E2E 无 RouterProvider）。
 * 重点验证三条诚实红线：
 *  ① 数值字段为 null 显示「—」，不补 0（禁止编造财务数据）；
 *  ② date 为 null 显示「暂无权威数据日」，禁止今天日期兜底；
 *  ③ note 为 null 显示「原始响应未提供口径说明」，原文/缺失如实呈现；
 *  ④ rows 为空数组时进入 QueryState 空态（「暂无财报数据」），不伪造行。
 * 另验证交互：代码输入框 + 查询按钮、报表 tablist 切换（含 report 回显）。
 */
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

/** 把代码切换为指定 6 位并点击查询（模拟真实用户深链 / 手输）。 */
function queryCode(code: string) {
  fireEvent.change(screen.getByRole('textbox', { name: '股票代码' }), {
    target: { value: code },
  })
  fireEvent.click(screen.getByRole('button', { name: '查询财报' }))
}

describe('77 · 财报猎手', () => {
  it('默认 600519 展示多期财报明细，且口径说明原文可见', async () => {
    render(
      <Providers>
        <FinancialHunter />
      </Providers>,
    )
    expect(await screen.findByText('财报猎手')).toBeTruthy()
    // 权威数据日有值（financialsFull.date = 2025-09-30）
    expect(await screen.findByText('权威数据日：2025-09-30', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('代码 600519')).toBeTruthy()
    expect(screen.getByText('报表 income')).toBeTruthy()
    // 表格渲染首行列名（来自后端原始响应）
    expect(await screen.findByText('报告期')).toBeTruthy()
    expect(screen.getByText('营业总收入')).toBeTruthy()
    // 口径说明卡存在（W4B_NOTE 原文）
    expect(
      screen.getByText(/逐字段独立取数|缺失为 null 且不补 0/i),
    ).toBeTruthy()
  })

  it('数值字段为 null 显示「—」，不补 0', async () => {
    render(
      <Providers>
        <FinancialHunter />
      </Providers>,
    )
    queryCode('000002')
    // 等 null 字段态的数据日出现，确保 000002 查询完成
    expect(await screen.findByText('暂无权威数据日', {}, { timeout: 5000 })).toBeTruthy()
    // 表格内 null 数值一律显「—」，不得补 0 / 0.00
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
    for (const d of dashes) expect(d.textContent).not.toMatch(/0/)
  })

  it('date 为 null 显示「暂无权威数据日」，不出现任何兜底日期', async () => {
    render(
      <Providers>
        <FinancialHunter />
      </Providers>,
    )
    queryCode('000004')
    expect(await screen.findByText('暂无权威数据日', {}, { timeout: 5000 })).toBeTruthy()
    // 不得出现「权威数据日：<某日期>」
    expect(screen.queryByText(/权威数据日：/)).toBeNull()
    // 000004 是 financialsFull 的副本（仅 date 置 null），rows 仍有值 → 表格正常渲染
    expect(await screen.findByText('报告期')).toBeTruthy()
  })

  it('note 为 null 显示「原始响应未提供口径说明」', async () => {
    render(
      <Providers>
        <FinancialHunter />
      </Providers>,
    )
    queryCode('000002')
    expect(
      await screen.findByText('原始响应未提供口径说明', {}, { timeout: 5000 }),
    ).toBeTruthy()
  })

  it('rows 为空数组进入空态，不伪造行', async () => {
    render(
      <Providers>
        <FinancialHunter />
      </Providers>,
    )
    queryCode('000003')
    // QueryState 空态文案（诚实提示，非编造数据）
    expect(await screen.findByText('暂无财报数据', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('rows 为空数组，未做填充')).toBeTruthy()
    // 不应渲染任何财报列名（报告期等）
    expect(screen.queryByText('报告期')).toBeNull()
  })

  it('报表 tablist 切换：资产负债表 → report 回显 balance，且三档互斥', async () => {
    render(
      <Providers>
        <FinancialHunter />
      </Providers>,
    )
    expect(await screen.findByText('财报猎手')).toBeTruthy()
    const tablist = screen.getByRole('tablist', { name: '报表类型' })
    const tabs = within(tablist).getAllByRole('tab')
    expect(tabs).toHaveLength(3)
    const balanceTab = within(tablist).getByRole('tab', { name: '资产负债表' })
    fireEvent.click(balanceTab)
    // 选中态互斥且 report 参数回显到口径行
    expect(balanceTab.getAttribute('aria-selected')).toBe('true')
    expect(within(tablist).getByRole('tab', { name: '利润表' }).getAttribute('aria-selected')).toBe(
      'false',
    )
    expect(await screen.findByText('报表 balance', {}, { timeout: 5000 })).toBeTruthy()
  })
})
