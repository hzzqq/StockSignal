import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { NAV, UTILITY_PATHS, type AppPath } from './nav'

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

/** AppPath 是类型，运行时从 nav.ts 源码真扫，确保「新增路由必进侧栏分类」。 */
const APP_PATHS: string[] = [...read('./nav.ts').matchAll(/\| '(\/[^']*)'/g)].map((m) => m[1])

/**
 * 2026-11-16 侧栏重排守卫；2026-11-22 减臃肿：7 组 → 6 组。
 * 历史缺陷：NAV 只有 4 组 36 项，另外 20 个入口在 AppShell 里手抄平铺，
 * 左侧 40+ 链接无分类、真源分裂。重排后所有功能入口必须归 NAV 语义分组，
 * 且 AppShell 不得再出现任何硬编码 `to="/..."`。
 * 2026-11-22：P1 组合构建诊断 / 市场驱动力并入 tab 视图（删 2 项），
 * 「智能助手与社区」并入决策组（删 1 组）——旧路径 redirect 保留深链兼容。
 */
describe('NAV · 侧栏分类单一真理源', () => {
  it('6 个语义分组、组名唯一、每组 2~12 项', () => {
    expect(NAV.length).toBe(6)
    expect(new Set(NAV.map((g) => g.group)).size).toBe(NAV.length)
    for (const g of NAV) {
      expect(g.items.length, `${g.group} 条目数`).toBeGreaterThanOrEqual(2)
      expect(g.items.length, `${g.group} 条目数`).toBeLessThanOrEqual(12)
    }
  })

  it('按股民日常动线排序：看盘 → 判环境 → 研个股 → 定策略 → 决策与助手 → 系统', () => {
    expect(NAV.map((g) => g.group)).toEqual([
      '行情与市场',
      '广度·温度与情绪',
      '个股研究',
      '策略与持仓',
      '决策·晨报与助手',
      '数据·运维·系统',
    ])
    // 组内首项必须是该场景的第一入口，避免后续回填把常用功能挤到末尾。
    expect(NAV[0].items[0].to).toBe('/quote-board')
    expect(NAV[1].items[0].to).toBe('/market-sentiment')
    expect(NAV[2].items[0].to).toBe('/stock/research')
    expect(NAV[3].items[0].to).toBe('/recommend')
    expect(NAV[4].items[1].to).toBe('/decision')
    expect(NAV[5].items[0].to).toBe('/guide')
  })

  it('图标、路径、标签全部全局唯一', () => {
    const items = NAV.flatMap((g) => g.items)
    expect(new Set(items.map((i) => i.icon)).size).toBe(items.length)
    expect(new Set(items.map((i) => i.to)).size).toBe(items.length)
    expect(new Set(items.map((i) => i.label)).size).toBe(items.length)
  })

  it('除 /login 与 /data 外，每个 AppPath 恰好出现在 NAV 一次', () => {
    const paths = NAV.flatMap((g) => g.items).map((i) => i.to)
    for (const p of APP_PATHS) {
      if (p === '/login' || p === '/data') continue
      expect(paths.filter((x) => x === p).length, `${p} 在 NAV 中出现次数`).toBe(1)
    }
    expect(paths).not.toContain('/login')
    expect(paths).not.toContain('/data')
  })

  it('每个 NAV 入口都在 router.tsx 注册真实路由', () => {
    const router = read('../app/router.tsx')
    for (const p of NAV.flatMap((g) => g.items).map((i) => i.to)) {
      expect(router, `${p} 未注册`).toContain(`path: '${p}'`)
    }
  })

  it('UTILITY_PATHS 只是深链补集，不与 NAV 重叠', () => {
    const paths: AppPath[] = NAV.flatMap((g) => g.items).map((i) => i.to)
    for (const p of UTILITY_PATHS) expect(paths).not.toContain(p)
    expect(UTILITY_PATHS).toContain('/data')
  })

  it('AppShell 由 NAV 派生、可折叠分组，零硬编码平铺入口', () => {
    const shell = read('../app/AppShell.tsx')
    expect(shell).toContain('NAV.map')
    expect(shell).toContain('aria-expanded={open}')
    expect(shell).toContain('aria-controls={listId}')
    expect(shell).toContain('aria-label={it.label}')
    expect(shell).not.toMatch(/to="\//)
  })

  it('高度链确定：html/body/#root → h-screen → main min-h-0', () => {
    const css = read('../styles/tokens.css')
    const shell = read('../app/AppShell.tsx')
    expect(css).toContain('html, body, #root { height: 100%; }')
    expect(shell).toContain('h-screen flex')
    expect(shell).toContain('flex-1 flex flex-col min-w-0 min-h-0')
    expect(shell).toContain('app-main flex-1 min-h-0 overflow-auto')
  })
})
