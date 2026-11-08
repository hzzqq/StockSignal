/**
 * 守卫反自静音 · 注释剥离机制自测。
 *
 * 与 Python 侧批次 6 / 11 同款思路：守卫要能「被杀毒测试」（killed by a counter-example）。
 * 这里直接验证 _src_scan 的剥注释逻辑——若它失效，theme-a11y / design-language 两个
 * toContain 守卫就会被注释喂饱而假通过。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { stripTsComments, stripCssComments, commentOnlySource } from './_src_scan'

const ROOT = resolve(process.cwd(), 'src')

describe('stripTsComments · 注释剥离机制', () => {
  it('行注释 // 里的 token 被移除，正文保留', () => {
    const src = `// role="img" 这一行是注释\nexport const X = 1; // aria-label={label} 行尾注释`
    const s = stripTsComments(src)
    expect(s).not.toContain('role="img"')
    expect(s).not.toContain('aria-label={label}')
    expect(s).toContain('export const X = 1;')
  })

  it('块注释 /* */ 里的 token 被移除（含跨行）', () => {
    const src = `/*\n * ss-theme-change 在块注释里\n * notMerge 也在块注释里\n */\nexport const Y = 2;`
    const s = stripTsComments(src)
    expect(s).not.toContain('ss-theme-change')
    expect(s).not.toContain('notMerge')
    expect(s).toContain('export const Y = 2;')
  })

  it('字符串字面量里的 // 与 /* 不被误删', () => {
    const src = `const u = "https://example.com/a/*b*/c"; const q = 'a // b';`
    const s = stripTsComments(src)
    expect(s).toContain('https://example.com')
    expect(s).toContain('a // b')
  })

  it('注释-only 源码经剥离后不含任何守卫 token（杀毒测试）', () => {
    const tokens = ['role="img"', 'aria-label={label}', 'ss-theme-change', 'remapChartColors', 'notMerge', 'optionRef.current']
    const s = stripTsComments(commentOnlySource(tokens))
    for (const t of tokens) {
      expect(s, `注释里的 ${t} 仍被命中，剥注释失效`).not.toContain(t)
    }
    expect(s).toContain('__real__')
  })
})

describe('stripCssComments · CSS 块注释', () => {
  it('CSS /* */ 里的 token 被移除', () => {
    const src = `/* --color-sf-ink 在注释里 */\n:root { --color-sf-ink: #fff; }`
    const s = stripCssComments(src)
    expect(s).not.toContain('--color-sf-ink 在注释里')
    expect(s).toContain('--color-sf-ink: #fff;')
  })
})

describe('守卫锚定真实代码（非注释）', () => {
  it('EChart.tsx 的守卫 token 在剥注释后仍存在（证明不是靠注释通过）', () => {
    const raw = readFileSync(resolve(ROOT, 'shared/charts/EChart.tsx'), 'utf-8')
    const s = stripTsComments(raw)
    for (const t of ['role="img"', 'aria-label={label}', 'sr-only', 'ss-theme-change', 'remapChartColors', 'notMerge', 'optionRef.current']) {
      expect(s, `剥注释后缺失真实 token ${t}`).toContain(t)
    }
  })

  it('tokens.css 的令牌在剥注释后仍存在', () => {
    const raw = readFileSync(resolve(ROOT, 'styles/tokens.css'), 'utf-8')
    const s = stripCssComments(raw)
    for (const t of ['--color-sf-surface', '--color-ss-up: #ff4d4f', ':focus-visible', 'prefers-reduced-motion', 'color-scheme: dark']) {
      expect(s, `剥注释后缺失真实令牌 ${t}`).toContain(t)
    }
  })

  it('AppShell 的 aria-label 守卫锚定真实代码', () => {
    const raw = readFileSync(resolve(ROOT, 'app/AppShell.tsx'), 'utf-8')
    const s = stripTsComments(raw)
    expect(s).toContain('aria-label={it.label}')
    expect(s).toContain('<ThemeToggle')
  })
})
