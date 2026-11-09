// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'
import { handlers } from '@/mocks/handlers'
import { Providers } from '@/app/providers'
import { GuideView } from '@/features/guide/GuideView'
import { LeadLagMatrixView } from '@/features/matrix/LeadLagMatrixView'
import { NAV, UTILITY_PATHS } from '@/nav/nav'
import { V1_PAGES } from '@/features/catalog/v1Pages.generated'
import { mappingOf, statusCounts } from '@/features/catalog/v2Mapping'
import type { BreadthHistoryPoint } from '@/api/schemas/read'

/**
 * W4-F · 两个 v1-only 高 ROI 页的 v2 等价实现 + 接线守卫。
 *
 * 纯组件用 <Providers> 独立渲染，TanStack <Link> 以最小 <a> 替身替换；
 * 网络一律走 MSW node，零真实请求。守卫从源码真扫，防止「只建组件不接线」
 * 或「单一真理源与 UI 漂移」。
 */
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

const ROOT = resolve(process.cwd(), '..')  // vitest cwd = frontend-v2
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  localStorage.clear()
})
afterAll(() => server.close())

function mount(node: ReactNode) {
  return render(<Providers>{node}</Providers>)
}

function src(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf8')
}

function ok(data: unknown) {
  return HttpResponse.json({ status: 'ok', code: 'ok', message: 'ok', data })
}

/** 40 个交易日的真实结构序列（字段与 /breadth-history 契约一致，数值为构造样本）。 */
function longHistory(): BreadthHistoryPoint[] {
  return Array.from({ length: 40 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10),
    up_count: 1000 + (i % 7) * 137,
    down_count: 3000 - (i % 5) * 211,
    flat_count: 5 + (i % 3),
    limit_up: 10 + (i % 11) * 3,
    limit_down: 3 + (i % 4),
    red_ratio: 20 + (i % 9) * 4,
  }))
}

describe('W4-F · 新手教程（/guide）', () => {
  it('六块引导内容都在，未移植项如实说明且不做假入口', () => {
    mount(<GuideView />)
    for (const title of ['四步上手', '差异化主线速览', '模块导览', '术语表', '常见误区', '常见问题']) {
      expect(screen.getByRole('heading', { name: title })).toBeTruthy()
    }
    expect(screen.getByText(/进度保存在此浏览器/)).toBeTruthy()
    expect(screen.getByText(/教学视频与 Streamlit 原生快捷键说明未移植/)).toBeTruthy()
    expect(document.querySelector('video')).toBeNull()
    expect(screen.getByText(/v2 暂无等价页面/)).toBeTruthy()
  })

  it('勾选真实写入 localStorage 并推进进度条，不是摆设', () => {
    mount(<GuideView />)
    const bar = screen.getByRole('progressbar', { name: '上手进度' })
    expect(bar.getAttribute('aria-valuenow')).toBe('0')
    fireEvent.click(screen.getByRole('checkbox', { name: '看一遍今日决策面板' }))
    expect(bar.getAttribute('aria-valuenow')).toBe('25')
    expect(JSON.parse(localStorage.getItem('ss_guide_steps') ?? '[]')).toEqual(['decision'])
    fireEvent.click(screen.getByRole('checkbox', { name: '看一遍今日决策面板' }))
    expect(bar.getAttribute('aria-valuenow')).toBe('0')
    expect(JSON.parse(localStorage.getItem('ss_guide_steps') ?? '[]')).toEqual([])
  })

  it('FAQ 关键词筛选真实生效，无匹配时给空态', () => {
    mount(<GuideView />)
    const input = screen.getByRole('searchbox', { name: '搜索常见问题' })
    fireEvent.change(input, { target: { value: '教学视频' } })
    expect(screen.getByText('新手教程和 v1 完全一样吗？')).toBeTruthy()
    expect(screen.queryByText('v2 和 v1 是什么关系？')).toBeNull()
    fireEvent.change(input, { target: { value: '不存在的关键词xyz' } })
    expect(screen.getByText('没有匹配的问题，请换个关键词。')).toBeTruthy()
  })

  it('模块导览链接数 == NAV 条目数（同源，不手抄）', () => {
    mount(<GuideView />)
    const region = screen.getByRole('region', { name: '模块导览' })
    expect(region.querySelectorAll('a').length).toBe(NAV.flatMap((g) => g.items).length)
  })
})

describe('W4-F · 领先滞后矩阵（/matrix）', () => {
  it('40 日真实结构序列 → 30 组有序对、带符号 lag 列、机械相关与非因果声明', async () => {
    server.use(http.get('/api/v2/read/breadth-history', () => ok(longHistory())))
    mount(<LeadLagMatrixView />)
    await waitFor(() => expect(screen.getByText(/共 30 组/)).toBeTruthy(), { timeout: 8000 })
    const table = screen.getByRole('table', { name: '广度维度有序对互相关的最优错位' })
    expect(table.querySelectorAll('tbody tr')).toHaveLength(30)
    expect(screen.getByRole('columnheader', { name: '带符号 lag' })).toBeTruthy()
    expect(screen.getByText(/红盘占比由/)).toBeTruthy()
    expect(screen.getAllByText(/非因果、非预测/).length).toBeGreaterThan(0)
    expect(screen.getByText(/样本区间 2026-01-01/)).toBeTruthy()
    expect(screen.getByText(/已剔除（离线缺真值，不编造）/)).toBeTruthy()
    // 有序对两个方向都在表里
    expect(screen.getByText('上涨家数 → 下跌家数')).toBeTruthy()
    expect(screen.getByText('下跌家数 → 上涨家数')).toBeTruthy()
  })

  it('默认 fixture 只有 3 日 → 如实空态，不编造相关系数、不渲染表格', async () => {
    mount(<LeadLagMatrixView />)
    await waitFor(() => expect(screen.getByText('有效样本不足，未计算矩阵')).toBeTruthy(), { timeout: 8000 })
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText(/未参与计算的可靠维度/)).toBeTruthy()
    expect(screen.getByText(/取不到真实广度日序列时如实留空，不编造相关系数/)).toBeTruthy()
  })

  it('后端如实报数据缺失（status=error）→ 错误态，不降级成 0 值矩阵', async () => {
    server.use(http.get('/api/v2/read/breadth-history', () => HttpResponse.json({
      status: 'error', code: 'not_found', message: '数据文件缺失或为空：shepherd_history.json', data: null,
    })))
    mount(<LeadLagMatrixView />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy(), { timeout: 8000 })
    expect(screen.getByRole('alert').textContent).toContain('数据文件缺失或为空')
    expect(screen.queryByRole('table')).toBeNull()
  })
})

describe('W4-F · 接线守卫（源码真扫）', () => {
  it('router.tsx 注册 /matrix 与 /guide，且真的挂进 routeTree', () => {
    const r = src('frontend-v2/src/app/router.tsx')
    for (const p of ['/matrix', '/guide']) expect(r).toContain(`path: '${p}'`)
    expect(r).toMatch(/addChildren\(\[[\s\S]*?matrixRoute,[\s\S]*?guideRoute,[\s\S]*?\]\)/)
    // 路由级懒加载后不再静态 import 页面组件：接线证据必须是 lazyRouteComponent
    expect(r).toContain("lazyRouteComponent(() => import('@/features/matrix/LeadLagMatrixView'), 'LeadLagMatrixView')")
    expect(r).toContain("lazyRouteComponent(() => import('@/features/guide/GuideView'), 'GuideView')")
    expect(r).toContain('component: LazyLeadLagMatrixView')
    expect(r).toContain('component: LazyGuideView')
  })

  it('UTILITY_PATHS 是单一真理源：每条都在 router 注册，AppShell 有对应底部入口', () => {
    const r = src('frontend-v2/src/app/router.tsx')
    const shell = src('frontend-v2/src/app/AppShell.tsx')
    for (const p of UTILITY_PATHS) expect(r).toContain(`path: '${p}'`)
    expect(new Set(UTILITY_PATHS).size).toBe(UTILITY_PATHS.length)
    const rendered = [...shell.matchAll(/to="(\/[^"]+)"/g)].map((m) => m[1])
    for (const p of ['/matrix', '/guide', '/settings', '/catalog']) expect(rendered).toContain(p)
    // /data 由功能全景深链进入，没有底部入口，但必须留在回流白名单里
    expect(UTILITY_PATHS).toContain('/data')
    expect(rendered).not.toContain('/data')
  })

  it('LoginPage knownPaths 覆盖 UTILITY_PATHS（防「登录后被静默甩回首页」复发）', () => {
    const lp = src('frontend-v2/src/features/auth/LoginPage.tsx')
    expect(lp).toContain('NAV, UTILITY_PATHS')
    expect(lp).toContain('...UTILITY_PATHS')
    expect(lp).not.toContain('new Set<string>(NAV.flatMap')
  })

  it('三页在功能全景如实登记为 native，数量守恒且登录页 note 不夸大', () => {
    const cases: [string, string][] = [
      ['66_维度领先滞后矩阵.py', '/matrix'],
      ['90_登录.py', '/login'],
      ['96_新手教程.py', '/guide'],
    ]
    for (const [file, to] of cases) {
      const page = V1_PAGES.find((p) => p.file === file)
      expect(page, `清单缺少 ${file}`).toBeTruthy()
      const m = mappingOf(page!)
      expect(m.status).toBe('native')
      expect(m.to).toBe(to)
    }
    const login = mappingOf(V1_PAGES.find((p) => p.file === '90_登录.py')!)
    expect(login.note).toContain('不做假功能')
    expect(login.note).toContain('未接入')
    const c = statusCounts()
    expect(c.native + c.data + c['v1-only']).toBe(V1_PAGES.length)
    expect(c.native).toBeGreaterThan(17)
    expect(c['v1-only']).toBeGreaterThan(0)
  })

  it('新页走底部入口，NAV 仍 4 组 / 第 3 组 8 项 / 图标唯一', () => {
    expect(NAV.length).toBe(4)
    expect(NAV[2].items.length).toBe(11)
    const items = NAV.flatMap((g) => g.items)
    expect(new Set(items.map((i) => i.icon)).size).toBe(items.length)
    const paths = items.map((i) => i.to)
    expect(paths).not.toContain('/matrix')
    expect(paths).not.toContain('/guide')
  })
})
