// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { DataExport } from '@/features/export/DataExport'

// ECharts 在 jsdom 无 canvas，init/dispose 会抛错；与全站 E2E 约定一致，渲染期直接置空。
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))

/**
 * 95 数据导出（/export）前端契约 E2E（MSW）。
 * 重点：
 *  ① 默认渲染标题 + 日期下拉（来自只读 snapshot-dates 端点）；
 *  ② 选中「有归档」的日期 → 复用 SnapshotView 富视图（渲染该日期）+ 出现「导出 JSON」按钮；
 *  ③ 选中「无归档」的日期（fixture 刻意缺 2026-11-06）→ 诚实显「该日期无归档快照」，不回退今日快照；
 *  ④ 点击「导出 JSON」不崩溃（jsdom 无下载能力时安全降级）。
 */
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())
beforeEach(() => {
  localStorage.clear()
  // 方法级 stub：保留 URL 构造器（MSW 依赖 new URL），仅堵掉 jsdom 未实现的下载/导航。
  Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:mock', configurable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true })
  HTMLAnchorElement.prototype.click = () => {}
})

describe('95 · 数据导出', () => {
  it('默认渲染标题 + 日期下拉（只读端点）', async () => {
    render(
      <Providers>
        <DataExport />
      </Providers>,
    )
    expect(await screen.findByText('数据导出')).toBeTruthy()
    // 下拉中存在来自 snapshot-dates 的归档日期（option 文本）
    expect(await screen.findByText('2026-09-21', {}, { timeout: 5000 })).toBeTruthy()
    expect(screen.getByText('2026-09-20')).toBeTruthy()
  })

  it('选中「有归档」日期 → 展示快照富视图 + 导出按钮', async () => {
    render(
      <Providers>
        <DataExport />
      </Providers>,
    )
    // 先等日期清单 query 落定（option 出现），再触发 change，避开 act 时序抖动。
    await screen.findByText('2026-09-21')
    const select = screen.getByDisplayValue('— 请选择 —') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '2026-09-21' } })
    // 「导出 JSON」按钮仅在快照成功加载后出现 → 证明 SnapshotView 已渲染该日期。
    expect(await screen.findByRole('button', { name: '导出 JSON' }, { timeout: 5000 })).toBeTruthy()
  })

  it('选中「无归档」日期 → 诚实显空态，不回退今日快照', async () => {
    render(
      <Providers>
        <DataExport />
      </Providers>,
    )
    await screen.findByText('2026-09-21')
    const select = screen.getByDisplayValue('— 请选择 —') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '2026-11-06' } })
    // 诚实空态文案（真实后端缺该日归档即如此）。
    expect(
      await screen.findByText('该日期无归档快照', {}, { timeout: 5000 }),
    ).toBeTruthy()
    // 空态下不应出现快照富视图的「导出 JSON」入口（未被今日/其他快照冒充）。
    expect(screen.queryByRole('button', { name: '导出 JSON' })).toBeNull()
  })

  it('点击「导出 JSON」安全降级（jsdom 无下载能力不崩溃）', async () => {
    render(
      <Providers>
        <DataExport />
      </Providers>,
    )
    await screen.findByText('2026-09-21')
    const select = screen.getByDisplayValue('— 请选择 —') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '2026-09-21' } })
    const btn = await screen.findByRole('button', { name: '导出 JSON' }, { timeout: 5000 })
    expect(() => fireEvent.click(btn)).not.toThrow()
  })
})
