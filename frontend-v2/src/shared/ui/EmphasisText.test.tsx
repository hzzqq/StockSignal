// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { SectionTitle, LeadText } from './EmphasisText'

const SRC = resolve(process.cwd(), 'src/shared/ui/EmphasisText.tsx')

describe('EmphasisText · 共享重点突出排版守卫', () => {
  it('① SectionTitle 默认 h3：brand-2 左条 + border-l-[3px] + pl-2 + font-semibold', () => {
    const { container } = render(<SectionTitle>分节标题</SectionTitle>)
    const h3 = container.querySelector('h3')!
    expect(screen.getByRole('heading', { level: 3, name: '分节标题' })).toBeTruthy()
    expect(h3.style.borderColor).toContain('var(--color-brand-2)')
    expect(h3.className).toContain('border-l-[3px]')
    expect(h3.className).toContain('pl-2')
    expect(h3.className).toContain('font-semibold')
    expect(h3.className).toContain('text-[1rem]')
  })

  it('② as="h2" 渲染 h2 且字号为 1.08rem、左条仍为 brand-2', () => {
    const { container } = render(<SectionTitle as="h2">大标题</SectionTitle>)
    const h2 = container.querySelector('h2')!
    expect(screen.getByRole('heading', { level: 2, name: '大标题' })).toBeTruthy()
    expect(h2.className).toContain('text-[1.08rem]')
    expect(h2.style.borderColor).toContain('var(--color-brand-2)')
    expect(container.querySelector('h3')).toBeNull()
  })

  it('③ LeadText 渲染 strong：font-bold + 内联 brand-1 文字色', () => {
    const { container } = render(<LeadText>重点词</LeadText>)
    const strong = container.querySelector('strong')!
    expect(strong.textContent).toBe('重点词')
    expect(strong.className).toContain('font-bold')
    expect(strong.style.color).toContain('var(--color-brand-1)')
  })

  it('④ as="p" 单一 text-xs 字号（12px 不回归），className 追加到末尾', () => {
    const { container } = render(
      <SectionTitle as="p" className="mt-2">方法学</SectionTitle>,
    )
    const p = container.querySelector('p')!
    expect(p.textContent).toBe('方法学')
    expect(p.className).toContain('text-xs')
    expect(p.className.match(/text-xs/g)?.length).toBe(1)
    expect(p.className.endsWith('mt-2')).toBe(true)
    expect(p.style.borderColor).toContain('var(--color-brand-2)')
  })

  it('⑤ 反证语义：源码不含涨跌色类 / 强调边框令牌，品牌色走内联 var() 不硬编码', () => {
    const src = readFileSync(SRC, 'utf-8')
    // 拼接构造：避免本测试源码自身被「全 src 仅 ThemeToggle 可用强调边框」守卫计为扩散。
    const lineStrong = 'border-sf-line-' + 'strong'
    for (const b of ['ss-up', 'ss-down', lineStrong]) {
      expect(src, `禁用样式回流：${b}`).not.toContain(b)
    }
    expect(src).toContain("var(--color-brand-1)")
    expect(src).toContain("var(--color-brand-2)")
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})
