// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { router as prodRouter, searchSerialization } from '@/app/router'
import { Providers } from '@/app/providers'

/**
 * W4-B · /legacy redirect 运行时集成测试（真实 routeTree + createMemoryHistory + RouterProvider）。
 *
 * 背景：CDP 目检抓到 tsc/vitest/build 全绿但运行时才暴露的缺陷——view 映射正确、
 * 合法 code 却丢失。根因是 TanStack Router 1.170.46 默认 parseSearch 用 JSON.parse
 * (router-core/dist/esm/searchParams.js:5/22/26-29) 把纯数字 '600519' 解析成 number，
 * 令 legacyRoute.validateSearch 的 `typeof === 'string'` 校验拒收；
 * '000001' 因前导零令 JSON.parse 抛错而保持字符串，恰好绕过缺陷。
 *
 * 本测试用与生产完全相同的 searchSerialization（从 router.tsx 导出，避免漂移），
 * 断言 redirect 落地后 history.location.search（等价浏览器地址栏，即 CDP 读的 location.search）
 * 的字面量，覆盖防伪码 000001 与中文 deep + 600519 等硬红线。
 */
afterEach(() => cleanup())

/** 用生产同一份 routeTree + 序列化配置构造独立 router，渲染 RouterProvider，等 redirect 落地。 */
async function runFrom(initial: string) {
  localStorage.setItem('ss_token', 'test-token') // 让 appRoute 的 requireAuth 通过，不跳 /login
  const history = createMemoryHistory({ initialEntries: [initial] })
  const router = createRouter({
    routeTree: prodRouter.routeTree,
    history,
    ...searchSerialization,
  })
  render(
    <Providers>
      <RouterProvider router={router as never} />
    </Providers>,
  )
  // 等 beforeLoad → materializeRedirect → followRedirect → commitLocation 落地
  for (let i = 0; i < 50 && router.state.location.pathname === '/legacy'; i++) {
    await new Promise((r) => setTimeout(r, 20))
  }
  return { router, history }
}

const ZH_DEEP = encodeURIComponent('🔬 深度分析')

describe('W4-B · /legacy redirect 运行时（createMemoryHistory + RouterProvider）', () => {
  it('防伪码 /legacy?pick_stock=000001 → ?view=quick&code=000001，URL 不含 600519', async () => {
    const { history } = await runFrom('/legacy?pick_stock=000001')
    expect(history.location.pathname).toBe('/stock/research')
    expect(history.location.search).toContain('view=quick')
    expect(history.location.search).toContain('code=000001')
    expect(history.location.search).not.toContain('600519')
  })

  it('/legacy?pick_stock=600519 → ?view=quick&code=600519（纯数字 code 不再丢）', async () => {
    const { history } = await runFrom('/legacy?pick_stock=600519')
    expect(history.location.pathname).toBe('/stock/research')
    expect(history.location.search).toContain('view=quick')
    expect(history.location.search).toContain('code=600519')
  })

  it('中文 hub_gyj_view=🔬 深度分析 + 600519 → ?view=deep&code=600519', async () => {
    const { history } = await runFrom('/legacy?hub_gyj_view=' + ZH_DEEP + '&pick_stock=600519')
    expect(history.location.pathname).toBe('/stock/research')
    expect(history.location.search).toContain('view=deep')
    expect(history.location.search).toContain('code=600519')
  })

  it('只带 hub_gyj_view 中文、不带 code → ?view=deep 且不写 code 键', async () => {
    const { history } = await runFrom('/legacy?hub_gyj_view=' + ZH_DEEP)
    expect(history.location.search).toContain('view=deep')
    expect(history.location.search).not.toContain('code=')
  })

  it('非法 pick_stock=abc → ?view=quick，不写 code 键、不含 abc', async () => {
    const { history } = await runFrom('/legacy?hub_gyj_view=quick&pick_stock=abc')
    expect(history.location.pathname).toBe('/stock/research')
    expect(history.location.search).toContain('view=quick')
    expect(history.location.search).not.toContain('code=')
    expect(history.location.search).not.toContain('abc')
  })

  it('直达 /stock/research?view=deep&code=600519：URL 不被 rewrite，首帧 search 拿到字符串 code', async () => {
    const { router, history } = await runFrom('/stock/research?view=deep&code=600519')
    expect(history.location.pathname).toBe('/stock/research')
    expect(history.location.search).toBe('?view=deep&code=600519')
    const search = router.state.location.search as Record<string, unknown>
    expect(search.view).toBe('deep')
    expect(search.code).toBe('600519') // 字符串，不是 number
  })
})

describe('W4-B · 根因修复的序列化证据（生产 searchSerialization）', () => {
  it('parseSearch 把纯数字 code 保持为字符串（不再 JSON.parse 成 number）', () => {
    expect(searchSerialization.parseSearch('?pick_stock=600519&code=600519')).toEqual({
      pick_stock: '600519',
      code: '600519',
    })
    expect(searchSerialization.parseSearch('?pick_stock=000001')).toEqual({
      pick_stock: '000001',
    })
  })

  it('stringifySearch 不给纯数字串加 JSON 引号', () => {
    expect(searchSerialization.stringifySearch({ view: 'quick', code: '600519' })).toBe(
      '?view=quick&code=600519',
    )
    expect(searchSerialization.stringifySearch({ view: 'deep' })).toBe('?view=deep')
  })
})
