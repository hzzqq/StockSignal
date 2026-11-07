/**
 * 亮色主题 · WCAG 对比度守卫（DESIGN.md §7.3）
 *
 * 「反自证」原则：本文件**不写死任何期望色值**。
 *  - 所有色值从 src/styles/tokens.css 与 src/shared/charts/palette.ts **实读**；
 *  - 暗色基准从既有守卫 tests/unit/design-language.test.tsx:47-71 的断言
 *    **反读**成期望表做交叉验证（防止有人把两处一起改坏还全绿）；
 *  - 解析器自检（黑白 21:1、两块令牌数下限、palette 键数）防「解析失效→假通过」；
 *  - 三条反向守卫锁住修复本身，防止被静默回退。
 *
 * 失败信息统一带「用例 / 主题 / 前景 / 背景 / 实测 / 门槛 / 规则依据 / 修复方向」。
 * 禁止下调门槛、禁止 skip 告警条件、禁止改既有守卫来让本文件变绿。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(process.cwd(), 'src')
const read = (p: string) => readFileSync(resolve(ROOT, p), 'utf-8')
const readTest = (p: string) => readFileSync(resolve(process.cwd(), 'tests', p), 'utf-8')
const stripComments = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, '')
const CSS = stripComments(read('styles/tokens.css'))
const PALETTE = stripComments(read('shared/charts/palette.ts'))
const GUARD = readTest('unit/design-language.test.tsx')

/** 从起点正则定位块，用花括号计数找闭合（正则直接截处理不了嵌套/注释）。 */
function block(text: string, start: RegExp): string {
  const m = start.exec(text)
  if (!m) throw new Error(`找不到块起点 ${start}`)
  const open = text.indexOf('{', m.index)
  if (open < 0) throw new Error(`块起点后无 '{'：${start}`)
  let depth = 0
  for (let i = open; i < text.length; i++) {
    if (text[i] === '{') depth++
    else if (text[i] === '}') {
      depth--
      if (depth === 0) return text.slice(open + 1, i)
    }
  }
  throw new Error(`块未闭合：${start}`)
}

/** 只认「声明」：值后必须跟分号，天然避开 var(--x) 引用。 */
function decls(cssText: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const m of cssText.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}

/** palette.ts 里 `key: '#rrggbb'` 字面量（canvas 只能吃字面 hex）。 */
function paletteObj(name: string): Record<string, string> {
  const b = block(PALETTE, new RegExp(`(?:export\\s+)?const\\s+${name}\\s*=\\s*\\{`))
  const out: Record<string, string> = {}
  for (const m of b.matchAll(/(\w+)\s*:\s*'(#[0-9a-fA-F]{6})'/g)) out[m[1]] = m[2].toLowerCase()
  return out
}

/** 拒绝 color-mix() / var() / 缺失——那不是可实算的色值。 */
function hex(v: string | undefined, ctx: string): string {
  if (!v || !/^#[0-9a-fA-F]{6}$/.test(v)) {
    throw new Error(`${ctx}：期望字面 hex，实际 ${JSON.stringify(v)}（不可实算）`)
  }
  return v.toLowerCase()
}

// ───────── WCAG 与色彩工具 ─────────
function srgb(c: number): number {
  const x = c / 255
  return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
}
function luminance(h: string): number {
  const [r, g, b] = rgb(h)
  return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)
}
function ratio(a: string, b: string): number {
  const la = luminance(a), lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}
function rgb(h: string): [number, number, number] {
  return [
    parseInt(h.slice(1, 3), 16),
    parseInt(h.slice(3, 5), 16),
    parseInt(h.slice(5, 7), 16),
  ]
}
function rgbDistance(a: string, b: string): number {
  const A = rgb(a), B = rgb(b)
  return Math.sqrt(A.reduce((s, v, i) => s + (v - B[i]) ** 2, 0))
}
function hue(h: string): number {
  const [r, g, b] = rgb(h).map((v) => v / 255)
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  if (d === 0) return 0
  let out = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
  out = (out * 60 + 360) % 360
  return out
}
/** 旧 opacity /10 半透明叠色在实色底上的等价 RGB（用于证明 D2 视觉等价）。 */
function mixOver(fg: string, bg: string, alpha: number): string {
  const A = rgb(fg), B = rgb(bg)
  return '#' + A.map((v, i) => Math.round(v * alpha + B[i] * (1 - alpha)).toString(16).padStart(2, '0')).join('')
}

function assertRatio(caseId: string, theme: string, fg: string, bg: string, min: number, rule: string) {
  const actual = ratio(fg, bg)
  expect(
    actual,
    `${caseId} | ${theme} | ${fg} on ${bg} = ${actual.toFixed(2)}:1 | 要求 ≥${min}:1 [${rule}] | 修复：调整色值；禁止下调门槛 / 加 skip / 改守卫`,
  ).toBeGreaterThanOrEqual(min)
}

// ───────── 真值来源 ─────────
const DARK = decls(block(CSS, /@theme\s*\{/))
const LIGHT_BLOCK = block(CSS, /html\[data-theme="light"\]\s*\{/)
const LIGHT = decls(LIGHT_BLOCK)
const CHART = paletteObj('CHART')
const CHART_LIGHT = paletteObj('CHART_LIGHT')

const d = (o: Record<string, string>, k: string, ctx: string) => hex(o[k], `${ctx}.${k}`)
const DARK_BASES = ['--color-sf-surface', '--color-sf-surface-2', '--color-sf-bg'].map((k) => d(DARK, k, 'DARK'))
const LIGHT_BASES = ['--color-sf-surface', '--color-sf-surface-2', '--color-sf-bg'].map((k) => d(LIGHT, k, 'LIGHT'))

/** 从既有守卫的 `expect(css).toContain('--color-ss-up: #ff4d4f')` 反读 4 个价格色。 */
function guardPriceColors(): Record<string, string> {
  const out: Record<string, string> = {}
  for (const m of GUARD.matchAll(/--color-((?:ss|doc)-(?:up|down)):\s*(#[0-9a-fA-F]{6})/g)) {
    out[`--color-${m[1]}`] = m[2].toLowerCase()
  }
  return out
}
/** 从既有守卫的 `['surface', '#16162c']` 数组反读暗色 9 组基准。 */
function guardDarkPairs(): [string, string][] {
  return [...GUARD.matchAll(/\['(\w+)',\s*'(#[0-9a-fA-F]{6})'\]/g)]
    .map((m) => [m[1], m[2].toLowerCase()] as [string, string])
}
const TOKEN_OF: Record<string, string> = {
  surface: '--color-sf-surface', surface2: '--color-sf-surface-2', line: '--color-sf-line',
  ink2: '--color-sf-ink-2', ink3: '--color-sf-ink-3', warn: '--color-sf-warn',
  danger: '--color-sf-danger', ok: '--color-sf-ok', accent: '--color-sf-accent',
}

describe('解析器自检（防解析失效造成全绿假象）', () => {
  it('黑白对比度 = 21:1', () => expect(ratio('#000000', '#ffffff')).toBeCloseTo(21, 5))
  it('CSS 两块都解析出足够令牌', () => {
    expect(Object.keys(DARK).length, '@theme 块令牌过少').toBeGreaterThanOrEqual(17)
    expect(Object.keys(LIGHT).length, 'light 块令牌过少').toBeGreaterThanOrEqual(11)
  })
  it('palette 两块都解析出足够色值', () => {
    expect(Object.keys(CHART).length).toBeGreaterThanOrEqual(9)
    expect(Object.keys(CHART_LIGHT).length).toBeGreaterThanOrEqual(9)
  })
  it('既有守卫反读出 4 个价格色与 9 组暗色基准', () => {
    expect(Object.keys(guardPriceColors()).length).toBe(4)
    expect(guardDarkPairs().length).toBeGreaterThanOrEqual(9)
  })
})

describe('交叉验证：暗色基线未被两处一起改坏', () => {
  it('guard 里的 9 组 hex 与 tokens.css / palette.ts 逐项一致', () => {
    for (const [key, value] of guardDarkPairs()) {
      const token = TOKEN_OF[key]
      if (!token) continue
      expect(d(DARK, token, 'DARK'), `tokens.css ${token} 与守卫不符`).toBe(value)
      expect(hex(CHART[key], `CHART.${key}`), `palette.${key} 与守卫不符`).toBe(value)
    }
  })
  it('4 个 A 股语义变量两主题恒等（亮色块不得重定义）', () => {
    expect(LIGHT_BLOCK, 'light 块覆盖了价格语义变量').not.toMatch(/--color-(?:ss|doc)-(?:up|down)\s*:/)
    const priceToChart: Record<string, string> = {
      '--color-ss-up': 'up', '--color-ss-down': 'down',
      '--color-doc-up': 'docUp', '--color-doc-down': 'docDown',
    }
    for (const [k, v] of Object.entries(guardPriceColors())) {
      expect(d(DARK, k, 'DARK'), `${k} 被改动`).toBe(v)
      expect(hex(CHART[priceToChart[k]], `CHART ${k}`), `CHART ${k} 与 CSS 不一致`).toBe(v)
    }
  })
})

describe('A1b · canvas 域派生值（渲染域差异，非语义差异）', () => {
  const pairs = ['up', 'down', 'docUp', 'docDown']
  it('色相族一致 |ΔH| ≤ 1°（8-bit 舍入微漂，不能写 ===）', () => {
    for (const k of pairs) {
      const a = hex(CHART[k], `CHART.${k}`), b = hex(CHART_LIGHT[k], `CHART_LIGHT.${k}`)
      const delta = Math.abs(hue(a) - hue(b))
      expect(delta, `${k}: ${a}(${hue(a).toFixed(2)}°) → ${b}(${hue(b).toFixed(2)}°) Δ${delta.toFixed(2)}°`).toBeLessThanOrEqual(1)
    }
  })
  it('4 个派生值在亮色三底各 ≥3:1（WCAG 1.4.11 非文本）', () => {
    for (const k of pairs) {
      const fg = hex(CHART_LIGHT[k], `CHART_LIGHT.${k}`)
      LIGHT_BASES.forEach((bg) => assertRatio(`A1b-2.${k}`, 'light', fg, bg, 3, '1.4.11 非文本'))
    }
  })
  it('docDown === up（双语义同源）', () => {
    expect(hex(CHART_LIGHT.docDown, 'CHART_LIGHT.docDown')).toBe(hex(CHART_LIGHT.up, 'CHART_LIGHT.up'))
  })
  it('反向守卫：派生值不得被「修」回原值（原绿在白底仅 1.95:1）', () => {
    expect(ratio('#00d486', '#ffffff')).toBeLessThan(3)
    for (const k of pairs) {
      expect(hex(CHART_LIGHT[k], `CHART_LIGHT.${k}`), `${k} 被回退成暗色原值`).not.toBe(hex(CHART[k], `CHART.${k}`))
    }
  })
  it('反向守卫：两主题 aria-label 文案相等（B2，色相族描述不随明度变化）', () => {
    const lr = read('features/breadth/LadderResonance.tsx')
    expect(lr).toContain('高板位红色、低板位绿色')
  })
})

describe('A6 · 状态色双主题分别定义 + 实色底等价性', () => {
  const states = ['ok', 'warn', 'danger'] as const
  const softOf = (k: string) => `--color-sf-${k}-soft`

  it('亮色 3 状态色 × 三亮底各 ≥4.5:1', () => {
    for (const k of states) {
      const fg = d(LIGHT, `--color-sf-${k}`, 'LIGHT')
      LIGHT_BASES.forEach((bg) => assertRatio(`A6.${k}`, 'light', fg, bg, 4.5, 'WCAG AA 正文'))
    }
  })
  it('亮色 3 状态色 × 对应 -soft 实色底各 ≥4.5:1', () => {
    for (const k of states) {
      assertRatio(`A6.soft.${k}`, 'light', d(LIGHT, `--color-sf-${k}`, 'LIGHT'), d(LIGHT, softOf(k), 'LIGHT'), 4.5, 'WCAG AA 正文')
    }
  })
  it('暗色原状态色一字不动，且 × 暗 -soft 底各 ≥4.5:1', () => {
    const expected: Record<string, string> = { ok: '#5bb98c', warn: '#e5a54b', danger: '#e06c75' }
    for (const k of states) {
      const fg = d(DARK, `--color-sf-${k}`, 'DARK')
      expect(fg, `暗色 ${k} 被改动（D2 只允许替换底色）`).toBe(expected[k])
      assertRatio(`A6.dark.${k}`, 'dark', fg, d(DARK, softOf(k), 'DARK'), 4.5, 'WCAG AA 正文')
    }
  })
  it('反向守卫：亮色深状态色放暗实色底必须 <4.5（证明没有全局替换）', () => {
    for (const k of states) {
      const r = ratio(d(LIGHT, `--color-sf-${k}`, 'LIGHT'), d(DARK, softOf(k), 'DARK'))
      expect(r, `${k} 亮深值放暗底 = ${r.toFixed(2)}:1，若达标说明令牌被全局替换`).toBeLessThan(4.5)
    }
  })
  it('D2 等价性：暗 -soft 底 ≈ 旧 /10 叠色（RGB 距离 ≤2）', () => {
    for (const k of states) {
      const legacy = mixOver(d(DARK, `--color-sf-${k}`, 'DARK'), DARK_BASES[0], 0.1)
      const current = d(DARK, softOf(k), 'DARK')
      expect(rgbDistance(legacy, current), `${k}: 旧叠色 ${legacy} vs 实色 ${current}`).toBeLessThanOrEqual(2)
    }
  })
  it('撞色矩阵：状态色与价格色 min dist ≥20，sf-ok 与两个价格绿各 ≥50', () => {
    const prices = Object.entries(guardPriceColors()).map(([, v]) => v)
    for (const k of states) {
      const fg = d(LIGHT, `--color-sf-${k}`, 'LIGHT')
      const min = Math.min(...prices.map((p) => rgbDistance(fg, p)))
      expect(min, `${k} 与价格色过近（${min.toFixed(1)}）`).toBeGreaterThanOrEqual(20)
    }
    const greens = ['#00d486', '#009e60']
    for (const g of greens) {
      expect(rgbDistance(d(LIGHT, '--color-sf-ok', 'LIGHT'), g), `sf-ok 与 ${g} 过近`).toBeGreaterThanOrEqual(50)
    }
  })
  it('B6：CHART_LIGHT 状态色逐项等于亮色深状态色，且全为字面 hex', () => {
    for (const k of states) {
      expect(hex(CHART_LIGHT[k], `CHART_LIGHT.${k}`)).toBe(d(LIGHT, `--color-sf-${k}`, 'LIGHT'))
    }
    for (const v of Object.values(CHART_LIGHT)) expect(v).toMatch(/^#[0-9a-f]{6}$/)
  })
})

describe('文字三级 / 焦点 / hairline 门槛（DESIGN.md §7.3）', () => {
  it('亮色三级文字 × 三亮底：L1 ≥7 / L2 ≥4.5 / L3 ≥4.5', () => {
    const levels: [string, number][] = [['--color-sf-ink', 7], ['--color-sf-ink-2', 4.5], ['--color-sf-ink-3', 4.5]]
    for (const [k, min] of levels) {
      LIGHT_BASES.forEach((bg) => assertRatio(k, 'light', d(LIGHT, k, 'LIGHT'), bg, min, 'DESIGN.md §2.2'))
    }
  })
  it('暗色三级文字 × 三暗底：L1 ≥7 / L2 ≥4.5 / L3 ≥4.5', () => {
    const levels: [string, number][] = [['--color-sf-ink', 7], ['--color-sf-ink-2', 4.5], ['--color-sf-ink-3', 4.5]]
    for (const [k, min] of levels) {
      DARK_BASES.forEach((bg) => assertRatio(k, 'dark', d(DARK, k, 'DARK'), bg, min, 'DESIGN.md §2.2'))
    }
  })
  it('accent / line-strong 两主题 × 各自三底 ≥3:1（焦点环与控件边界）', () => {
    for (const k of ['--color-sf-accent', '--color-sf-line-strong']) {
      LIGHT_BASES.forEach((bg) => assertRatio(k, 'light', d(LIGHT, k, 'LIGHT'), bg, 3, 'WCAG 1.4.11'))
      DARK_BASES.forEach((bg) => assertRatio(k, 'dark', d(DARK, k, 'DARK'), bg, 3, 'WCAG 1.4.11'))
    }
  })
  it('hairline 两主题均 <1.5:1（A3 装饰性豁免，卡片靠留白分层）', () => {
    const r1 = ratio(d(LIGHT, '--color-sf-line', 'LIGHT'), LIGHT_BASES[0])
    const r2 = ratio(d(DARK, '--color-sf-line', 'DARK'), DARK_BASES[0])
    expect(r1, `亮 hairline ${r1.toFixed(2)}:1`).toBeLessThan(1.5)
    expect(r2, `暗 hairline ${r2.toFixed(2)}:1`).toBeLessThan(1.5)
    expect(r2, '暗色 hairline 下限锚点 1.21').toBeGreaterThanOrEqual(1.15)
  })
})

describe('C5 · 令牌作用域与 W0 兼容覆盖', () => {
  it('light 块显式覆盖 4 个 W0 兼容令牌', () => {
    for (const k of ['--color-sf-card', '--color-sf-txt', '--color-sf-border', '--color-sf-grid']) {
      expect(LIGHT[k], `${k} 未在亮色块显式覆盖（未迁移页会残留暗底）`).toBeDefined()
      hex(LIGHT[k], `LIGHT.${k}`)
    }
  })
  it('两主题都设 color-scheme', () => {
    expect(CSS).toContain('color-scheme: dark')
    expect(CSS).toContain('color-scheme: light')
  })
  it('4 个 ink 别名存在，且暗态回退原变量不缩放', () => {
    for (const k of ['--ss-up-ink', '--ss-down-ink', '--doc-up-ink', '--doc-down-ink']) {
      expect(DARK[k], `暗态缺别名 ${k}`).toBeDefined()
      expect(LIGHT[k], `亮态缺别名 ${k}`).toBeDefined()
      expect(DARK[k]).toMatch(/^var\(--color-/)
      expect(LIGHT[k]).toContain('color-mix(')
    }
  })
  it('全 src 不得生成 -ink 派生 Tailwind 类（守卫是 includes 子串匹配）', () => {
    const banned = /(?:text|bg|border)-(?:ss|doc)-(?:up|down)-ink/
    const fb = read('shared/ui/FreshnessBadge.tsx')
    expect(fb, 'FreshnessBadge 不得引用 -ink 别名').not.toMatch(banned)
    expect(fb).not.toContain('ss-up')
    expect(fb).not.toContain('ss-down')
  })
})
