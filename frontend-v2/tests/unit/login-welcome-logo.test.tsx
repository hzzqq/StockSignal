import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LoginWelcome } from '@/features/auth/LoginWelcome'

/**
 * 欢迎页品牌 logo 居中的真实回归守卫。
 *
 * 根因（实测截图）：Tailwind v4 preflight 把 `img` 设为 `display:block`，
 * 父级卡片的 `text-center` 只对行内内容生效，块级 img 会贴左。
 * 因此 logo 必须自带 `mx-auto`；图片缺失时的星芒兜底同理。
 *
 * 这是渲染级断言（不是读源码字符串），className 回潮会直接红。
 */
describe('LoginWelcome — 品牌 logo 水平居中', () => {
  it('logo img 必须显式 mx-auto block，不能再只靠父级 text-center', () => {
    render(<LoginWelcome onLogin={() => {}} />)
    const img = screen.getByAltText('StockSignal') as HTMLImageElement
    expect(img.tagName).toBe('IMG')
    expect(img.className).toContain('mx-auto')
    expect(img.className).toContain('block')
    expect(img.getAttribute('src')).toBe('/icon-256.png')
  })

  it('图片加载失败时：隐藏破图，星芒兜底同样居中', () => {
    render(<LoginWelcome onLogin={() => {}} />)
    const img = screen.getByAltText('StockSignal') as HTMLImageElement
    fireEvent.error(img)
    expect(img.style.display).toBe('none')

    const fallback = img.nextElementSibling as HTMLElement | null
    expect(fallback).not.toBeNull()
    expect(fallback?.textContent).toContain('✨')
    const style = fallback?.getAttribute('style') ?? ''
    expect(style).toContain('margin:0 auto')
    expect(style).toContain('text-align:center')
  })
})
