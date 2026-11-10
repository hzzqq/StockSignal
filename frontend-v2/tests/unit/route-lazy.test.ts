/**
 * 路由级懒加载守卫。
 *
 * 真实风险：新增页面时顺手把静态 `import { X } from '@/features/...'` 加回
 * router.tsx，会把整页代码重新塞进 index 主包（首屏变慢），而功能完全正常、
 * 任何现有测试都不会红。本守卫从源码真扫接线形态，并用反例自测保证
 * 扫描器自己能抓到回潮。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROUTER = resolve(process.cwd(), 'src/app/router.tsx')

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 从 `@/features/...` 静态导入的页面组件名（应只剩首屏 LoginPage）。 */
function staticFeatureImports(src: string): string[] {
  return [...src.matchAll(/^import\s+\{\s*(\w+)\s*\}\s+from\s+'@\/features\//gm)]
    .map((m) => m[1])
}

/** createRoute 里 `component: Identifier,` 形态的引用（箭头函数不在内）。 */
function componentRefs(src: string): string[] {
  return [...src.matchAll(/^\s*component:\s*([A-Za-z][\w]*)\s*,/gm)]
    .map((m) => m[1])
}

function lazyDefs(src: string): string[] {
  return [...src.matchAll(/^const\s+(Lazy\w+)\s*=\s*lazyRouteComponent\(/gm)]
    .map((m) => m[1])
}

const code = stripComments(readFileSync(ROUTER, 'utf-8'))

// 允许静态的只有：首屏登录页、鉴权外壳，以及 4 个要用 useSearch() 的薄 wrapper
const STATIC_OK = new Set([
  'LoginPage', 'AppShell',
  'DataRouteView', 'ResearchRouteView', 'FundamentalsRouteView', 'CompareRouteView',
  'FinancialHunterRouteView',
])

describe('router.tsx 保持路由级懒加载', () => {
  it('页面组件不得再被静态 import 进主包', () => {
    const imports = staticFeatureImports(code)
    expect(imports, `@/features 静态导入回潮：${imports.join(', ')}`)
      .toEqual(['LoginPage'])
  })

  it('component 引用全来自 Lazy 定义或明确白名单，且有接线数量下限', () => {
    const refs = componentRefs(code)
    expect(refs.length).toBeGreaterThanOrEqual(24)
    const bad = refs.filter((r) => !r.startsWith('Lazy') && !STATIC_OK.has(r))
    expect(bad, `未懒加载的路由组件：${bad.join(', ')}`).toEqual([])
    const lazyCount = refs.filter((r) => r.startsWith('Lazy')).length
    expect(lazyCount).toBeGreaterThanOrEqual(20)
    expect(lazyDefs(code).length).toBe(lazyCount)
    for (const r of refs.filter((x) => x.startsWith('Lazy'))) {
      expect(lazyDefs(code), `${r} 没有对应的 lazyRouteComponent 定义`).toContain(r)
    }
  })

  it('5 个 wrapper 内部确实走 React.lazy + Suspense（不是假懒加载）', () => {
    expect(code.match(/lazy\(\(\) => import\(/g)?.length ?? 0).toBe(5)
    expect(code.match(/<Suspense fallback=\{<RouteLoading \/>\}>/g)?.length ?? 0).toBe(5)
    expect(code).toContain('role="status"')
  })
})

describe('扫描器反例自测', () => {
  it('能抓到静态 import 回潮与未懒加载的 component（注释喂不饱）', () => {
    expect(staticFeatureImports("import { Dashboard } from '@/features/dashboard/Dashboard'"))
      .toEqual(['Dashboard'])
    expect(staticFeatureImports("// import { Dashboard } from '@/features/dashboard/Dashboard'"))
      .toEqual([])
    expect(componentRefs("  component: LazyDashboard,\n  component: Dashboard,"))
      .toEqual(['LazyDashboard', 'Dashboard'])
    expect(lazyDefs("const LazyDashboard = lazyRouteComponent(() => import('x'), 'Dashboard')"))
      .toEqual(['LazyDashboard'])
    expect(lazyDefs('// const LazyX = lazyRouteComponent(')).toEqual([])
  })

  it('把真实 router 的一个 Lazy 引用改回静态，必须被守卫判定为坏', () => {
    const regressed = code.replace('component: LazyDashboard,', 'component: Dashboard,')
    expect(regressed).not.toBe(code)
    const bad = componentRefs(regressed).filter(
      (r) => !r.startsWith('Lazy') && !STATIC_OK.has(r),
    )
    expect(bad).toContain('Dashboard')
  })
})
