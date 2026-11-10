// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { getZen, setZen } from '@/lib/preferences'
import { ZenToggle } from '@/shared/ui/ZenToggle'

/**
 * 专注 / Zen 模式核心机制（不引入 Playwright）。
 * 覆盖：偏好持久化（localStorage ↔ html[data-zen]）+ ZenToggle 可访问性与点击回调。
 * 布局收起（display:none）由 tokens.css 的 html[data-zen="on"] 规则负责，静态校验。
 */
describe('Zen 专注模式', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-zen')
    try {
      localStorage.removeItem('ss_zen')
    } catch {
      /* 隐私模式守卫 */
    }
  })
  afterEach(() => cleanup())

  it('preferences：setZen(true) 写 data-zen=on 且 getZen 读回，setZen(false) 反之', () => {
    expect(getZen()).toBe(false)
    setZen(true)
    expect(document.documentElement.dataset.zen).toBe('on')
    expect(getZen()).toBe(true)
    setZen(false)
    expect(document.documentElement.dataset.zen).toBe('off')
    expect(getZen()).toBe(false)
  })

  it('ZenToggle 非专注态：aria-pressed=false，点击调用 onToggle', () => {
    const onToggle = vi.fn()
    render(<ZenToggle zen={false} onToggle={onToggle} />)
    const btn = screen.getByRole('button', { name: '进入专注模式' })
    expect(btn.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(btn)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('ZenToggle 专注态：aria-pressed=true，文案为「退出专注」', () => {
    const onToggle = vi.fn()
    render(<ZenToggle zen={true} onToggle={onToggle} />)
    const btn = screen.getByRole('button', { name: '退出专注模式' })
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('退出专注')).toBeTruthy()
  })
})
