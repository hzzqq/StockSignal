import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * 2026-11-23 单滚动条契约守卫（老板截图报修：25 个页面右侧双滚轮 + 页面下方空白）。
 *
 * 根因：app-main 已是内容滚动区，但 ECharts absolute canvas 让 documentElement
 * scrollHeight 虚高，html/body 也变可滚；滚轮溢出外层后整个应用上移露白。
 * 契约：①文档层 overflow:hidden ②内容滚动只走 app-main ③AppShell 外的登录页
 * 自带 overflow-y-auto（小屏不被截断）。
 */
const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

describe('单滚轮 · 文档层不滚动，内容只走 app-main', () => {
  it('tokens.css 关掉 html/body 文档滚动并阻止滚动链外溢', () => {
    const css = read('../../src/styles/tokens.css')
    expect(css).toContain('html, body, #root { height: 100%; }') // 高度链不断
    expect(css).toMatch(/html, body \{[^}]*overflow: hidden;/)
    expect(css).toMatch(/html, body \{[^}]*overscroll-behavior: contain;/)
  })

  it('AppShell 根 h-screen + app-main 唯一内容滚动区', () => {
    const shell = read('../../src/app/AppShell.tsx')
    expect(shell).toContain('h-screen flex')
    expect(shell).toContain('app-main flex-1 min-h-0 overflow-auto')
  })

  it('AppShell 外的登录页自带 overflow-y-auto（小屏可滚，不被文档层 hidden 截断）', () => {
    for (const f of ['LoginPage.tsx', 'LoginWelcome.tsx']) {
      const src = read(`../../src/features/auth/${f}`)
      expect(src, `${f} 根容器需可滚`).toMatch(/min-h-screen[^"']*overflow-y-auto/)
    }
  })
})
