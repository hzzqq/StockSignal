/**
 * 轻量卡片流 · 设计语言守卫（DESIGN.md §2 / §5）
 *
 * 与项目既有 AST 不变量护栏同款：真扫源码 + 渲染 DOM 双重验证，不用 skip 遮掩告警。
 * 防四类回退：
 *  1. 设计令牌被掏空（tokens.css 缺关键令牌）；
 *  2. 散落的透明度文字色 / 旧表面 class 回流；
 *  3. 无障碍退化（region/aria-label/role/tabular-nums/sr-only 丢失）；
 *  4. 状态色重新借用 A 股涨跌色（语义拧反的历史缺陷）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { Loading, EmptyState, ErrorState } from '@/shared/ui/States'

const ROOT = resolve(process.cwd(), 'src')
const read = (p: string) => readFileSync(resolve(ROOT, p), 'utf-8')
const css = read('styles/tokens.css')

/** 递归列出 src 下所有 .tsx 源码文本。 */
function allTsx(dir = ROOT): { file: string; text: string }[] {
  const out: { file: string; text: string }[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...allTsx(full))
    else if (name.endsWith('.tsx')) out.push({ file: full, text: readFileSync(full, 'utf-8') })
  }
  return out
}

describe('设计令牌单一真理源（DESIGN.md §2）', () => {
  it('tokens.css 声明全部轻量卡片流令牌', () => {
    for (const token of [
      '--color-sf-surface', '--color-sf-surface-2', '--color-sf-line',
      '--color-sf-ink', '--color-sf-ink-2', '--color-sf-ink-3',
      '--color-sf-warn', '--color-sf-danger', '--color-sf-ok', '--color-sf-accent',
      '--text-kpi', '--text-page', '--text-title', '--text-body', '--text-label',
      '--radius-card', '--radius-tile',
    ]) {
      expect(css, `tokens.css 缺令牌 ${token}`).toContain(token)
    }
  })

  it('保留 A 股双套语义（红涨绿跌 / 报告体绿涨红跌），不可被状态色替代', () => {
    expect(css).toContain('--color-ss-up: #ff4d4f')
    expect(css).toContain('--color-ss-down: #00d486')
    expect(css).toContain('--color-doc-up: #009e60')
    expect(css).toContain('--color-doc-down: #ff4d4f')
  })

  it('卡片流容器 / 焦点环 / 激活指示条 / 减少动态效果 齐备', () => {
    expect(css).toContain('.flow')
    expect(css).toContain(':focus-visible')
    expect(css).toContain('.nav-link[aria-current="page"]')
    expect(css).toContain('prefers-reduced-motion')
  })

  it('palette.ts 与 tokens.css 的表面/文字色逐项对齐', () => {
    const palette = read('shared/charts/palette.ts')
    for (const [k, v] of [
      ['surface', '#16162c'], ['surface2', '#1d1d38'], ['line', '#26263f'],
      ['ink2', '#a8b2cc'], ['ink3', '#7c86a3'], ['warn', '#e5a54b'],
      ['danger', '#e06c75'], ['ok', '#5bb98c'], ['accent', '#9aa6e8'],
    ]) {
      expect(palette, `palette.${k} 与令牌不一致`).toContain(`${k}: '${v}'`)
      expect(css, `tokens.css 缺对应色 ${v}`).toContain(v)
    }
  })
})

describe('全站无旧样式回流', () => {
  const files = allTsx()

  it('src 下 .tsx 数量足够（防止扫描逻辑失效造成假通过）', () => {
    expect(files.length).toBeGreaterThanOrEqual(20)
  })

  it('不再出现 text-sf-txt 透明度层级 / 旧边框 / 旧半透明表面', () => {
    const banned = ['text-sf-txt', 'border-sf-border', 'bg-sf-bg/40', 'focus:border-ss-up', 'bg-sf-card', 'rounded-xl']
    const hits: string[] = []
    for (const { file, text } of files) {
      for (const b of banned) if (text.includes(b)) hits.push(`${file} -> ${b}`)
    }
    expect(hits, `旧样式回流：\n${hits.join('\n')}`).toEqual([])
  })

  it('涨跌色只用于价格/盈亏域，不得借作错误、链接、按钮、悬停边框', () => {
    // 合法用法是 PaperTrades 里的 var(--color-ss-up/down)（交易盈亏着色）；
    // 这里禁的是把涨跌色当通用 UI 色的 Tailwind class。
    const banned = [
      'text-ss-up', 'text-ss-down', 'bg-ss-up', 'bg-ss-down',
      'border-ss-up', 'border-ss-down', 'hover:border-ss-up',
    ]
    const hits: string[] = []
    for (const { file, text } of files) {
      for (const b of banned) if (text.includes(b)) hits.push(`${file} -> ${b}`)
    }
    expect(hits, `涨跌色语义误用回流：\n${hits.join('\n')}`).toEqual([])
    // 正向：价格域仍保留 var() 用法（防止有人「修」过头把合法用法也删了）
    expect(read('features/paper/PaperTrades.tsx')).toContain('var(--color-ss-up)')
    expect(read('features/paper/PaperTrades.tsx')).toContain('var(--color-ss-down)')
  })

  it('页面根容器改用 .flow（广度/连板/概览/快照）', () => {
    for (const f of [
      'features/breadth/BreadthOverview.tsx',
      'features/breadth/LadderResonance.tsx',
      'features/dashboard/Dashboard.tsx',
      'features/decision/SnapshotView.tsx',
    ]) {
      expect(read(f), `${f} 未用 .flow`).toContain('className="flow"')
    }
  })
})

describe('无障碍（DESIGN.md §5）', () => {
  it('Card 有 region + aria-label；Stat 数值用等宽数字', () => {
    const card = renderToStaticMarkup(<Card title="测试卡片"><span>x</span></Card>)
    expect(card).toContain('role="region"')
    expect(card).toContain('aria-label="测试卡片"')
    expect(card).toContain('bg-sf-surface')
    expect(card).toContain('border-sf-line')
    const stat = renderToStaticMarkup(<Stat label="评分" value={47.9} />)
    expect(stat).toContain('tabular-nums')
    expect(stat).toContain('text-kpi')
  })

  it('加载/空态 role=status；错误态 role=alert 且不复用涨跌色', () => {
    expect(renderToStaticMarkup(<Loading />)).toContain('role="status"')
    expect(renderToStaticMarkup(<EmptyState />)).toContain('role="status"')
    const err = renderToStaticMarkup(<ErrorState message="加载失败" />)
    expect(err).toContain('role="alert"')
    expect(err).toContain('bg-sf-warn')
    expect(err).not.toContain('ss-down') // 绿=跌，绝不能表示错误
    expect(err).not.toContain('ss-up')
  })

  it('EChart 容器 role=img + aria-label + sr-only 文本替代', () => {
    const s = read('shared/charts/EChart.tsx')
    expect(s).toContain('role="img"')
    expect(s).toContain('aria-label={label}')
    expect(s).toContain('sr-only')
    expect(s).toContain('ariaLabel?: string')
  })

  it('图表调用点均传入可读的 ariaLabel', () => {
    const bo = read('features/breadth/BreadthOverview.tsx')
    const lr = read('features/breadth/LadderResonance.tsx')
    expect((bo.match(/ariaLabel=/g) ?? []).length).toBeGreaterThanOrEqual(4)
    expect((lr.match(/ariaLabel=/g) ?? []).length).toBeGreaterThanOrEqual(2)
    for (const t of [bo, lr]) {
      for (const m of t.matchAll(/ariaLabel="([^"]+)"/g)) {
        expect(m[1].length, 'ariaLabel 不得为空占位').toBeGreaterThan(8)
      }
    }
  })

  it('FreshnessBadge 状态色与涨跌语义隔离', () => {
    const s = read('shared/ui/FreshnessBadge.tsx')
    expect(s).not.toContain('ss-up')
    expect(s).not.toContain('ss-down')
    expect(s).toContain('sf-ok')
    expect(s).toContain('sf-warn')
    expect(s).toContain('sf-danger')
    expect(s).toContain('role="status"')
  })
})

describe('信息架构：两页互加深链', () => {
  it('广度页→连板页、连板页→广度页', () => {
    expect(read('features/breadth/BreadthOverview.tsx')).toContain('href="/ladder"')
    expect(read('features/breadth/LadderResonance.tsx')).toContain('href="/breadth"')
  })
})

/**
 * 亮色主题落地后的守卫补强（DESIGN.md §7）。
 * 分工：色值 / WCAG 实算 / 两主题恒等 / W0 兼容令牌由 theme-contrast.test.ts
 * 独立真读 CSS 验证；本文件只锁「作用域与叠色回流」，避免两处重复维护同一批色值。
 */
describe('亮色主题：作用域与叠色回流', () => {
  it('FreshnessBadge 用 -soft 实色底，零半透明叠色（/10、/30）', () => {
    const s = read('shared/ui/FreshnessBadge.tsx')
    expect(s, '亮色三底上叠半透明会破坏 AA，必须改实色底').not.toMatch(
      /(?:bg|text|border)-[a-z-]+\/(?:10|30)\b/,
    )
    for (const soft of ['bg-sf-ok-soft', 'bg-sf-warn-soft', 'bg-sf-danger-soft']) {
      expect(s, `缺实色底 ${soft}`).toContain(soft)
    }
    expect(s).toContain('border-sf-line')
  })

  it('sf-line-strong 仅用于主题控件选中态，全 src 不得扩散', () => {
    const hits = allTsx()
      .filter(({ text }) => text.includes('border-sf-line-strong'))
      .map(({ file }) => file.replace(/\\/g, '/'))
    expect(hits.length, `边界强调色扩散到：\n${hits.join('\n')}`).toBe(1)
    expect(hits[0]).toMatch(/shared\/ui\/ThemeToggle\.tsx$/)
  })
})
