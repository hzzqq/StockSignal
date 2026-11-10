// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { DashboardCustom } from '@/features/dashboard/DashboardCustom'

/**
 * 73 自定义看板（/dashboard-custom）前端契约 E2E（MSW）。
 * 重点：
 *  ① 默认 5 个组件均渲染（来自只读端点的真实数据）；
 *  ② 勾选切换实时移出/放回组件，并持久化到 localStorage（刷新保留）；
 *  ③ 每日荐股组件在 status=unavailable 时如实展示状态与原因，不编造标的列表；
 *  ④ 全部取消后诚实提示「至少启用一个面板」。
 */
const LS_KEY = 'ss-dashboard-widgets-v1'
const ALL = ['snapshot', 'recommendation', 'breadth', 'event', 'backtest']

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())
beforeEach(() => {
  localStorage.clear()
})

describe('73 · 自定义看板', () => {
  it('默认 5 个组件均渲染（真实只读端点）', async () => {
    render(
      <Providers>
        <DashboardCustom />
      </Providers>,
    )
    expect(await screen.findByText('自定义看板')).toBeTruthy()
    for (const t of ['今日决策快照', '每日荐股', '广度温度时序', '事件因子池', '回测运行记录']) {
      expect(await screen.findByText(t, {}, { timeout: 5000 })).toBeTruthy()
    }
  })

  it('取消勾选组件后从看板移除，并写入 localStorage', async () => {
    render(
      <Providers>
        <DashboardCustom />
      </Providers>,
    )
    // 等首屏渲染完成
    expect(await screen.findByText('自定义看板')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '管理组件' }))
    const cb = screen.getByLabelText('切换组件 回测运行记录')
    fireEvent.click(cb)
    // 关闭编辑面板
    fireEvent.click(screen.getByRole('button', { name: '完成' }))
    // 组件卡片被移除
    expect(screen.queryByText('回测运行记录')).toBeNull()
    // 持久化：localStorage 不含 backtest
    const saved = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]')
    expect(saved).toEqual(ALL.filter((id) => id !== 'backtest'))
  })

  it('重新勾选组件后放回看板', async () => {
    render(
      <Providers>
        <DashboardCustom />
      </Providers>,
    )
    expect(await screen.findByText('自定义看板')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '管理组件' }))
    const cb = screen.getByLabelText('切换组件 回测运行记录')
    fireEvent.click(cb) // 先取消
    fireEvent.click(cb) // 再勾回
    fireEvent.click(screen.getByRole('button', { name: '完成' }))
    expect(await screen.findByText('回测运行记录', {}, { timeout: 5000 })).toBeTruthy()
  })

  it('每日荐股在 unavailable 时如实展示状态与原因，不编造列表', async () => {
    render(
      <Providers>
        <DashboardCustom />
      </Providers>,
    )
    expect(
      await screen.findByText('推荐状态：unavailable', {}, { timeout: 5000 }),
    ).toBeTruthy()
    // 因 unavailable，不应出现任何编造的「推荐标的 / 买入建议」列表项
    expect(screen.queryByText(/推荐标的|买入建议|今日推荐个股/)).toBeNull()
  })

  it('全部取消后诚实提示至少启用一个面板', async () => {
    render(
      <Providers>
        <DashboardCustom />
      </Providers>,
    )
    expect(await screen.findByText('自定义看板')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '管理组件' }))
    for (const id of ALL) {
      const label = {
        snapshot: '今日决策快照',
        recommendation: '每日荐股',
        breadth: '广度温度时序',
        event: '事件因子池',
        backtest: '回测运行记录',
      }[id]
      const cb = screen.getByLabelText(`切换组件 ${label}`)
      if (cb instanceof HTMLInputElement && cb.checked) fireEvent.click(cb)
    }
    fireEvent.click(screen.getByRole('button', { name: '完成' }))
    expect(
      await screen.findByText('请在「管理组件」中至少启用一个面板', {}, { timeout: 5000 }),
    ).toBeTruthy()
  })
})
