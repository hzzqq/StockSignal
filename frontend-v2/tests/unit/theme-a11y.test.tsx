// @vitest-environment jsdom
/**
 * 亮色主题 · 无障碍与主题机制守卫（DESIGN.md §5 / §7.1）
 *
 * 与 theme-contrast.test.ts（纯 Node 读 CSS + 实算）分工：本文件验证
 * 交互控件、FOUC、EChart 重映射、键盘与读屏属性。
 * jsdom 无 canvas / matchMedia，图表一律用**源码真扫**，不实际初始化 echarts。
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ThemeToggle } from '@/shared/ui/ThemeToggle'
import { Providers } from '@/app/providers'
import { readPref, resolve as resolveTheme, THEME_KEY } from '@/lib/theme'

const ROOT = resolve(process.cwd(), 'src')
const read = (p: string) => readFileSync(resolve(ROOT, p), 'utf-8')
const readRoot = (p: string) => readFileSync(resolve(process.cwd(), p), 'utf-8')

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})
afterEach(() => cleanup())

describe('ThemeToggle · 三态 radiogroup', () => {
  it('role=radiogroup + 3 个 role=radio + aria-checked，文案齐全', () => {
    render(
      <Providers>
        <ThemeToggle />
      </Providers>,
    )
    const group = screen.getByRole('radiogroup', { name: '主题' })
    expect(group).toBeTruthy()
    const radios = screen.getAllByRole('radio')
    expect(radios.length).toBe(3)
    for (const label of ['深色', '浅色', '跟随系统']) {
      expect(screen.getByRole('radio', { name: label })).toBeTruthy()
    }
    expect(radios.filter((r) => r.getAttribute('aria-checked') === 'true').length).toBe(1)
  })

  it('点击「浅色」→ localStorage 与 html[data-theme] 同步为 light，再点深色回退', () => {
    render(
      <Providers>
        <ThemeToggle />
      </Providers>,
    )
    fireEvent.click(screen.getByRole('radio', { name: '浅色' }))
    expect(localStorage.getItem(THEME_KEY)).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    fireEvent.click(screen.getByRole('radio', { name: '深色' }))
    expect(localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('按钮原生可聚焦（键盘可达，不靠自定义 keydown）', () => {
    render(
      <Providers>
        <ThemeToggle />
      </Providers>,
    )
    for (const label of ['深色', '浅色', '跟随系统']) {
      expect(screen.getByRole('radio', { name: label }).tagName.toLowerCase()).toBe('button')
    }
  })
})

describe('theme.ts · 偏好读取与环境守卫', () => {
  it('无偏好 / 非法值一律回落 dark', () => {
    expect(readPref()).toBe('dark')
    localStorage.setItem(THEME_KEY, 'not-a-theme')
    expect(readPref()).toBe('dark')
    localStorage.setItem(THEME_KEY, 'light')
    expect(readPref()).toBe('light')
  })

  it('jsdom 无 matchMedia 时 resolve(system) 回落 dark 且不抛', () => {
    expect(() => resolveTheme('system')).not.toThrow()
    expect(['dark', 'light']).toContain(resolveTheme('system'))
    expect(resolveTheme('dark')).toBe('dark')
    expect(resolveTheme('light')).toBe('light')
  })
})

describe('index.html · FOUC 与脚本顺序', () => {
  it('head 内有内联同步脚本（非 module），且位于 module script 之前', () => {
    const html = readRoot('index.html')
    const inline = html.indexOf('<script>')
    const moduleTag = html.indexOf('<script type="module"')
    expect(inline, '缺内联 FOUC 脚本').toBeGreaterThan(-1)
    expect(moduleTag).toBeGreaterThan(-1)
    expect(inline).toBeLessThan(moduleTag)
    expect(html.slice(html.indexOf('<head>'), moduleTag)).toContain('ss_theme')
    expect(html.slice(html.indexOf('<head>'), moduleTag)).toContain('data-theme')
  })
})

describe('EChart · 主题重映射不破坏无障碍', () => {
  it('保留 role=img / aria-label / sr-only / ariaLabel prop', () => {
    const s = read('shared/charts/EChart.tsx')
    expect(s).toContain('role="img"')
    expect(s).toContain('aria-label={label}')
    expect(s).toContain('sr-only')
    expect(s).toContain('ariaLabel?: string')
  })
  it('订阅 ss-theme-change 且用 setOption(..., notMerge)，不 dispose/reinit', () => {
    const s = read('shared/charts/EChart.tsx')
    expect(s).toContain('ss-theme-change')
    expect(s).toContain('remapChartColors')
    expect(s).toContain('notMerge')
    expect(s).toContain('optionRef.current')
    // 主题切换只重算 option，不得重建实例
    expect(s.match(/dispose\(/g)?.length ?? 0).toBe(1)
  })
  it('不依赖 React Context（无 Provider 场景仍可渲染）', () => {
    expect(read('shared/charts/EChart.tsx')).not.toContain('useTheme')
  })
})

describe('AppShell / tokens.css · 顶栏顺序与全局无障碍', () => {
  it('顶栏顺序 [主题控件] [退出登录]，退出登录保持最右', () => {
    const s = read('app/AppShell.tsx')
    expect(s.indexOf('<ThemeToggle')).toBeGreaterThan(-1)
    expect(s.indexOf('<ThemeToggle')).toBeLessThan(s.indexOf('退出登录'))
  })
  it('所有导航 Link 都有 aria-label', () => {
    const s = read('app/AppShell.tsx')
    expect(s).toContain('aria-label={it.label}')
  })
  it('CSS 保留焦点环 / 减少动效 / 两态 color-scheme', () => {
    const css = read('styles/tokens.css')
    expect(css).toContain(':focus-visible')
    expect(css).toContain('prefers-reduced-motion')
    expect(css).toContain('color-scheme: dark')
    expect(css).toContain('color-scheme: light')
  })
})

describe('ThemeToggle 自身不触发设计语言守卫', () => {
  it('无 banned 旧样式 / 涨跌色类名 / -ink 派生类名', () => {
    const s = read('shared/ui/ThemeToggle.tsx')
    for (const banned of [
      'text-sf-txt', 'border-sf-border', 'bg-sf-bg/40', 'focus:border-ss-up',
      'bg-sf-card', 'rounded-xl', 'text-ss-up', 'text-ss-down', 'bg-ss-up',
      'bg-ss-down', 'border-ss-up', 'border-ss-down', 'hover:border-ss-up',
      'text-ss-up-ink', 'bg-ss-down-ink',
    ]) {
      expect(s, `ThemeToggle 含 banned 类 ${banned}`).not.toContain(banned)
    }
    expect(s).toContain('border-sf-line-strong')
  })
})
